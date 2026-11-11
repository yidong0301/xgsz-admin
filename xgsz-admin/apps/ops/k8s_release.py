#!/bin/env python3
# -*- coding: utf-8 -*-
"""
发布单 K8s 真实滚动更新能力。

职责：
1. 读取目标 Deployment，做镜像版本对比（当前线上 vs 本次发布）；
2. 以 RollingUpdate 策略下发镜像/副本数，等待滚动完成并做健康检查（Ready/Available/Updated）；
3. 发布详情：Deployment 状态、Pod 列表、Pod 日志；
4. 回滚：恢复到上一版本镜像与副本数，而不是简单缩容到 0。

所有 K8s 异常统一抛 ReleaseError，由视图层转成可读提示，避免把原始堆栈暴露给前端。
"""
import json
import logging
import os
import re
import time

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger('default')

# 滚动更新策略：先起新 Pod 再停旧 Pod，保证发布过程不中断
MAX_SURGE = '25%'
MAX_UNAVAILABLE = '25%'
DEFAULT_TIMEOUT = 90


class ReleaseError(Exception):
    """发布流程可预期错误（K8s 不可用、资源冲突等）"""


def safe_name(name, fallback='app'):
    """K8s 资源名必须满足 RFC1123：小写字母/数字/-，长度 <= 63"""
    s = re.sub(r'[^a-z0-9-]', '-', (name or '').lower())
    s = re.sub(r'-+', '-', s).strip('-')
    return (s[:63].strip('-') or fallback)


def load_kube_config():
    """兼容旧调用：默认 kubeconfig 是否可加载"""
    try:
        config.load_incluster_config()
        return True
    except Exception:
        pass
    try:
        config.load_kube_config(config_file=None)
        return True
    except Exception as e:
        logger.error('发布单加载 kubeconfig 失败: %s' % str(e))
        return False


def cluster_config_file(cluster):
    """多集群：优先使用 kube/clusters/<cluster>.yaml，找不到时回退默认 kubeconfig"""
    if not cluster:
        return None
    base = os.getenv('KUBECONFIG_DIR', '/root/.kube/clusters')
    candidates = []
    for name in (cluster, safe_name(cluster, 'cluster')):
        candidates.append(os.path.join(base, '%s.yaml' % name))
        candidates.append(os.path.join(base, '%s.yml' % name))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


_API_CLIENTS = {}


def _api_client(order=None):
    """按发布单的 cluster 加载对应 kubeconfig，返回独立 ApiClient。

    - kube/clusters/<cluster>.yaml 存在 → 多集群模式；
    - 否则回退 in-cluster / ~/.kube/config（当前 kind 单集群）。
    """
    cluster = getattr(order, 'cluster', None) if order is not None else None
    path = cluster_config_file(cluster)
    if not path and cluster and cluster not in ('kind', 'default'):
        # 显式指定了真实集群却找不到 kubeconfig：直接失败，避免误发到默认集群
        raise ReleaseError('未找到目标集群 kubeconfig：kube/clusters/%s.yaml，请先上传'
                           % safe_name(cluster, 'cluster'))
    cache_key = path or ('__default__:%s' % (cluster or ''))
    if cache_key in _API_CLIENTS:
        return _API_CLIENTS[cache_key]
    cfg = client.Configuration()
    try:
        if path:
            config.load_kube_config(config_file=path, client_configuration=cfg)
        else:
            try:
                config.load_incluster_config(client_configuration=cfg)
            except Exception:
                config.load_kube_config(config_file=None, client_configuration=cfg)
    except Exception as e:
        logger.error('发布单加载 kubeconfig 失败（cluster=%s）: %s' % (cluster, str(e)))
        raise ReleaseError('K8s 集群连接不可用（%s）：%s' % (cluster or '默认', str(e)[:160]))
    api_client = client.ApiClient(configuration=cfg)
    _API_CLIENTS[cache_key] = api_client
    return api_client


def _apps_api(order=None):
    return client.AppsV1Api(_api_client(order))


def _core_api(order=None):
    return client.CoreV1Api(_api_client(order))


def list_cluster_configs():
    """列出 kube/clusters 下已配置的集群（文件名即集群名）"""
    base = os.getenv('KUBECONFIG_DIR', '/root/.kube/clusters')
    result = {}
    try:
        for fn in sorted(os.listdir(base)):
            if fn.endswith(('.yaml', '.yml')) and not fn.startswith('.'):
                result[os.path.splitext(fn)[0]] = os.path.join(base, fn)
    except Exception:
        pass
    return result


def check_cluster(name, timeout=3):
    """检查单个集群连通性：读节点列表 + kubelet 版本"""
    path = cluster_config_file(name)
    if not path:
        return {'name': name, 'configured': False, 'reachable': False, 'node_count': 0,
                'version': '', 'kubeconfig': '', 'error': '未找到 kubeconfig'}

    class Probe:
        cluster = name
        namespace = 'default'

    try:
        core = client.CoreV1Api(_api_client(Probe()))
        nodes = core.list_node(_request_timeout=timeout)
        versions = []
        for n in nodes.items:
            info = n.status.node_info if n.status else None
            if info and info.kubelet_version:
                versions.append(info.kubelet_version)
        versions = sorted(set(versions), reverse=True)
        return {'name': name, 'configured': True, 'reachable': True,
                'node_count': len(nodes.items), 'version': versions[0] if versions else '',
                'kubeconfig': os.path.basename(path), 'error': ''}
    except Exception as e:
        return {'name': name, 'configured': True, 'reachable': False, 'node_count': 0,
                'version': '', 'kubeconfig': os.path.basename(path), 'error': str(e)[:240]}


def check_clusters(names=None):
    """并行检查多个集群，避免 8 台里有一台离线时串行等待"""
    names = list(names or list_cluster_configs().keys())
    if not names:
        return []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        return list(pool.map(lambda n: check_cluster(n), names))


def expected_cluster_count():
    """目标集群数量（默认 8，可通过 K8S_EXPECTED_CLUSTERS_COUNT 覆盖）"""
    try:
        return max(int(os.getenv('K8S_EXPECTED_CLUSTERS_COUNT', '8')), 0)
    except Exception:
        return 8


def deployment_name(order):
    """发布单对应的 Deployment 名称（执行成功后持久化，避免中文/大小写问题）"""
    return order.k8s_deployment or safe_name(order.app_name, 'app')


def ensure_namespace(order):
    """确保目标命名空间存在：dev/test 自动创建，prod 要求管理员预先创建。"""
    core = _core_api(order)
    ns = order.namespace or 'default'
    try:
        core.read_namespace(ns, _request_timeout=5)
        return {'name': ns, 'created': False}
    except ApiException as e:
        if e.status != 404:
            raise ReleaseError('读取命名空间失败：%s' % _api_message(e))
    if (order.env or '').lower() == 'prod':
        raise ReleaseError('生产环境命名空间不存在：%s，请先由管理员创建' % ns)
    try:
        body = client.V1Namespace(metadata=client.V1ObjectMeta(
            name=ns,
            labels={'xgsz.io/managed-by': 'xgsz-admin', 'xgsz.io/env': order.env or ''},
        ))
        core.create_namespace(body, _request_timeout=5)
        return {'name': ns, 'created': True}
    except ApiException as e:
        raise ReleaseError('自动创建命名空间失败：%s' % _api_message(e))


def read_deployment(order):
    """读取目标 Deployment；不存在返回 None，其他异常抛出"""
    apps = _apps_api(order)
    try:
        return apps.read_namespaced_deployment(name=deployment_name(order),
                                               namespace=order.namespace or 'default')
    except ApiException as e:
        if e.status == 404:
            return None
        raise ReleaseError('读取 Deployment 失败：%s' % _api_message(e))


def _api_message(ex):
    body = getattr(ex, 'body', None)
    if body:
        try:
            data = json.loads(body)
            return data.get('message') or body[:200]
        except Exception:
            return str(body)[:200]
    return str(ex)[:200]


def _container_of(dep):
    containers = (dep.spec.template.spec.containers or []) if dep and dep.spec else []
    return containers[0] if containers else None


def _fmt_time(dt):
    if not dt:
        return ''
    try:
        from django.utils import timezone
        return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)


def _age(dt):
    if not dt:
        return ''
    try:
        from datetime import datetime, timezone as dt_timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        sec = int((datetime.now(dt_timezone.utc) - dt).total_seconds())
        if sec < 60:
            return '%ds' % max(sec, 0)
        if sec < 3600:
            return '%dm' % (sec // 60)
        if sec < 86400:
            return '%dh' % (sec // 3600)
        return '%dd' % (sec // 86400)
    except Exception:
        return ''


def deployment_summary(dep):
    """把 K8s Deployment 转成前端易读的状态摘要"""
    if not dep:
        return {
            'exists': False, 'name': '', 'replicas': 0, 'ready_replicas': 0,
            'updated_replicas': 0, 'available_replicas': 0, 'unavailable_replicas': 0,
            'image': '', 'conditions': [], 'generation': 0, 'observed_generation': 0,
            'healthy': False, 'progressing': False,
        }
    status = dep.status
    spec_replicas = int(dep.spec.replicas or 0)
    ready = int((status.ready_replicas if status else 0) or 0)
    updated = int((status.updated_replicas if status else 0) or 0)
    available = int((status.available_replicas if status else 0) or 0)
    unavailable = int((status.unavailable_replicas if status else 0) or 0)
    generation = int(dep.metadata.generation or 0)
    observed = int((status.observed_generation if status else 0) or 0)
    conditions = []
    for c in ((status.conditions if status else None) or []):
        conditions.append({
            'type': c.type, 'status': c.status, 'reason': c.reason or '',
            'message': c.message or '', 'last_update_time': _fmt_time(c.last_update_time),
        })
    container = _container_of(dep)
    strategy = dep.spec.strategy
    rolling = getattr(strategy, 'rolling_update', None) if strategy else None
    progressing = any(c['type'] == 'Progressing' and c['status'] == 'True' for c in conditions)
    failed_progress = any(c['type'] == 'Progressing' and c['status'] == 'False'
                          and c['reason'] == 'ProgressDeadlineExceeded' for c in conditions)
    healthy = (not failed_progress) and observed >= generation and (
        spec_replicas == 0 or (updated >= spec_replicas and ready >= spec_replicas and available >= spec_replicas)
    )
    return {
        'exists': True,
        'name': dep.metadata.name,
        'namespace': dep.metadata.namespace,
        'replicas': spec_replicas,
        'ready_replicas': ready,
        'updated_replicas': updated,
        'available_replicas': available,
        'unavailable_replicas': unavailable,
        'image': container.image if container else '',
        'container': container.name if container else '',
        'generation': generation,
        'observed_generation': observed,
        'strategy': getattr(strategy, 'type', '') if strategy else '',
        'max_surge': getattr(rolling, 'max_surge', '') if rolling else '',
        'max_unavailable': getattr(rolling, 'max_unavailable', '') if rolling else '',
        'conditions': conditions,
        'healthy': healthy,
        'progressing': progressing,
    }


def list_pods(order, dep=None):
    """列出 Deployment 关联的 Pod（按 selector 或 app 标签）"""
    core = _core_api(order)
    ns = order.namespace or 'default'
    name = deployment_name(order)
    selector = None
    if dep is not None and dep.spec and dep.spec.selector:
        labels = dep.spec.selector.match_labels or {}
        if labels:
            selector = ','.join('%s=%s' % (k, v) for k, v in labels.items())
    selector = selector or ('app=%s' % safe_name(order.app_name, 'app'))
    try:
        pods = core.list_namespaced_pod(namespace=ns, label_selector=selector)
    except ApiException as e:
        raise ReleaseError('读取 Pod 列表失败：%s' % _api_message(e))
    result = []
    for pod in pods.items:
        status = pod.status
        spec = pod.spec
        containers = spec.containers or []
        cstatus = status.container_statuses or []
        ready_count = sum(1 for c in cstatus if c.ready)
        restarts = sum(int(c.restart_count or 0) for c in cstatus)
        deleted = bool(pod.metadata.deletion_timestamp)
        phase = 'Terminating' if deleted else (status.phase or '')
        result.append({
            'name': pod.metadata.name,
            'namespace': pod.metadata.namespace,
            'phase': phase,
            'pod_ip': status.pod_ip or '',
            'host_ip': status.host_ip or '',
            'node': spec.node_name or '',
            'ready': '%d/%d' % (ready_count, len(containers)),
            'ready_count': ready_count,
            'total': len(containers),
            'restarts': restarts,
            'image': containers[0].image if containers else '',
            'start_time': _fmt_time(pod.metadata.creation_timestamp),
            'age': _age(pod.metadata.creation_timestamp),
            'deleted': deleted,
            'reason': status.reason or '',
            'message': (status.message or '')[:300],
        })
    # 运行中优先、创建时间新的优先
    result.sort(key=lambda p: (p['phase'] != 'Running', p['start_time']), reverse=False)
    return result


def compare(order):
    """镜像版本对比：当前线上镜像 vs 本次发布镜像"""
    dep = read_deployment(order)
    target = order.image
    if dep is None:
        return {
            'exists': False,
            'deployment': deployment_name(order),
            'namespace': order.namespace or 'default',
            'current_image': '',
            'target_image': target,
            'changed': True,
            'current_replicas': 0,
            'target_replicas': int(order.replicas or 0),
            'message': '目标 Deployment 不存在，发布时将自动创建',
        }
    summary = deployment_summary(dep)
    changed = (summary['image'] or '') != (target or '')
    return {
        'exists': True,
        'deployment': summary['name'],
        'namespace': summary['namespace'],
        'current_image': summary['image'],
        'target_image': target,
        'changed': changed,
        'current_replicas': summary['replicas'],
        'target_replicas': int(order.replicas or 0),
        'current_health': summary,
        'message': '镜像有变化，将触发滚动更新' if changed else '镜像未变化，仅校验当前状态/副本数',
    }


def wait_for_rollout(order, dep, timeout=DEFAULT_TIMEOUT):
    """等待滚动更新完成，并返回健康检查结果"""
    apps = _apps_api(order)
    ns = order.namespace or 'default'
    name = deployment_name(order)
    target = int(order.replicas or 0)
    deadline = time.time() + max(int(timeout or DEFAULT_TIMEOUT), 5)
    last_summary = deployment_summary(dep)
    while time.time() < deadline:
        try:
            dep = apps.read_namespaced_deployment(name=name, namespace=ns)
        except ApiException as e:
            raise ReleaseError('读取滚动状态失败：%s' % _api_message(e))
        summary = deployment_summary(dep)
        last_summary = summary
        if target > 0 and summary['observed_generation'] >= summary['generation'] and summary['healthy']:
            break
        if target == 0 and summary['observed_generation'] >= summary['generation']:
            break
        # 明确失败：进度超时
        if any(c['type'] == 'Progressing' and c['status'] == 'False'
               and c['reason'] == 'ProgressDeadlineExceeded' for c in summary['conditions']):
            break
        time.sleep(2)
    pods = list_pods(order, dep)
    summary = last_summary
    healthy = bool(summary.get('healthy'))
    if target > 0 and not healthy:
        message = '滚动更新未在 %d 秒内达到 Ready（%d/%d）' % (
            int(timeout or DEFAULT_TIMEOUT), summary.get('ready_replicas', 0), target)
    elif target == 0:
        healthy = True
        message = '副本数已缩容至 0'
    else:
        message = '滚动更新完成，所有副本已就绪'
    detail = {
        'healthy': healthy,
        'message': message,
        'deployment': summary,
        'pods': pods,
        'checked_at': _fmt_time(_now()),
        'timeout_seconds': int(timeout or DEFAULT_TIMEOUT),
    }
    return detail


def _now():
    from django.utils import timezone
    return timezone.now()


def _build_deployment(order):
    name = deployment_name(order)
    ns = order.namespace or 'default'
    container_name = safe_name(order.app_name, 'app')
    annotations = {
        'xgsz.io/release-no': order.release_no,
        'xgsz.io/release-version': order.version or '',
        'xgsz.io/release-image': order.image,
        'xgsz.io/managed-by': 'xgsz-admin',
    }
    return {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {
            'name': name,
            'namespace': ns,
            'labels': {'app': name, 'xgsz.io/managed-by': 'xgsz-admin'},
            'annotations': annotations,
        },
        'spec': {
            'replicas': int(order.replicas or 1),
            'selector': {'matchLabels': {'app': name}},
            'strategy': {
                'type': 'RollingUpdate',
                'rollingUpdate': {'maxSurge': MAX_SURGE, 'maxUnavailable': MAX_UNAVAILABLE},
            },
            'template': {
                'metadata': {
                    'labels': {'app': name},
                    'annotations': dict(annotations, **{'xgsz.io/rollout-at': str(int(time.time()))}),
                },
                'spec': {
                    'containers': [{
                        'name': container_name,
                        'image': order.image,
                        'imagePullPolicy': 'IfNotPresent',
                    }],
                },
            },
        },
    }


def rollout(order, timeout=DEFAULT_TIMEOUT):
    """
    执行真实滚动更新：
    - Deployment 不存在 → 创建；
    - 已存在 → 记录上一版本镜像/副本数，按滚动策略 patch 镜像；
    - 等待 Ready/Available 并返回健康检查详情。
    """
    started = time.time()
    namespace_info = ensure_namespace(order)
    info = compare(order)
    ns = order.namespace or 'default'
    name = deployment_name(order)
    apps = _apps_api(order)
    dep = read_deployment(order) if info['exists'] else None

    changed = info['changed']
    previous_image = info['current_image'] or None
    previous_replicas = int(info['current_replicas'] or 0) if info['exists'] else None

    if dep is None:
        body = _build_deployment(order)
        try:
            apps.create_namespaced_deployment(namespace=ns, body=body)
        except ApiException as e:
            raise ReleaseError('创建 Deployment 失败：%s' % _api_message(e))
    elif changed or int(order.replicas or 0) != int(dep.spec.replicas or 0):
        container = _container_of(dep)
        container_name = container.name if container else safe_name(order.app_name, 'app')
        patch = {
            'metadata': {
                'annotations': {
                    'xgsz.io/release-no': order.release_no,
                    'xgsz.io/release-version': order.version or '',
                    'xgsz.io/release-image': order.image,
                    'xgsz.io/release-previous-image': previous_image or '',
                },
            },
            'spec': {
                'replicas': int(order.replicas or 1),
                'strategy': {
                    'type': 'RollingUpdate',
                    'rollingUpdate': {'maxSurge': MAX_SURGE, 'maxUnavailable': MAX_UNAVAILABLE},
                },
                'template': {
                    'metadata': {
                        'annotations': {
                            'xgsz.io/release-no': order.release_no,
                            'xgsz.io/release-image': order.image,
                            'xgsz.io/rollout-at': str(int(time.time())),
                        },
                    },
                    'spec': {'containers': [{'name': container_name, 'image': order.image}]},
                },
            },
        }
        try:
            apps.patch_namespaced_deployment(name=name, namespace=ns, body=patch)
        except ApiException as e:
            raise ReleaseError('更新 Deployment 失败：%s' % _api_message(e))
        # patch 后重新读取，拿到新 generation
        dep = read_deployment(order)

    dep = read_deployment(order)
    if dep is None:
        raise ReleaseError('Deployment 下发后未找到，请检查命名空间/权限')
    health = wait_for_rollout(order, dep, timeout=timeout)
    health['comparison'] = info
    health['deployment_name'] = name
    health['namespace_info'] = namespace_info
    health['previous_image'] = previous_image
    health['previous_replicas'] = previous_replicas
    health['changed'] = changed
    health['duration_ms'] = int((time.time() - started) * 1000)
    health['ok'] = bool(health.get('healthy'))
    return health


def rollback(order, timeout=DEFAULT_TIMEOUT):
    """回滚到上一版本镜像与副本数；无上一版本时缩容到 0（保留原能力）。"""
    started = time.time()
    apps = _apps_api(order)
    ns = order.namespace or 'default'
    name = deployment_name(order)
    dep = read_deployment(order)
    if dep is None:
        raise ReleaseError('目标 Deployment 不存在，无法回滚')
    previous_image = order.previous_image
    if previous_image:
        container = _container_of(dep)
        container_name = container.name if container else safe_name(order.app_name, 'app')
        replicas = int(order.previous_replicas or dep.spec.replicas or 1)
        patch = {
            'metadata': {'annotations': {'xgsz.io/rollback-from': order.image,
                                          'xgsz.io/rollback-at': str(int(time.time()))}},
            'spec': {
                'replicas': replicas,
                'template': {
                    'metadata': {'annotations': {'xgsz.io/rollback-at': str(int(time.time()))}},
                    'spec': {'containers': [{'name': container_name, 'image': previous_image}]},
                },
            },
        }
        try:
            apps.patch_namespaced_deployment(name=name, namespace=ns, body=patch)
        except ApiException as e:
            raise ReleaseError('回滚 Deployment 失败：%s' % _api_message(e))
        dep = read_deployment(order)
        health = wait_for_rollout(order, dep, timeout=timeout)
        health['mode'] = 'restore_image'
        health['rolled_back_image'] = previous_image
        if health.get('healthy'):
            health['message'] = '已回滚到上一版本镜像 %s，副本已就绪' % previous_image
    else:
        try:
            apps.patch_namespaced_deployment(name=name, namespace=ns,
                                             body={'spec': {'replicas': 0}})
        except ApiException as e:
            raise ReleaseError('缩容失败：%s' % _api_message(e))
        dep = read_deployment(order)
        health = wait_for_rollout(order, dep, timeout=timeout)
        health['mode'] = 'scale_to_zero'
        health['message'] = '没有上一版本镜像记录，已将副本数缩容到 0'
    health['duration_ms'] = int((time.time() - started) * 1000)
    health['ok'] = bool(health.get('healthy'))
    return health


def state(order):
    """发布详情：K8s 实时状态（Deployment + Pods），失败不抛异常"""
    try:
        dep = read_deployment(order)
    except ReleaseError as e:
        return {'available': False, 'exists': False, 'error': str(e), 'pods': []}
    if dep is None:
        return {
            'available': True, 'exists': False,
            'message': '目标 Deployment 尚未创建（发布后自动创建）',
            'deployment': deployment_summary(None), 'pods': [],
        }
    summary = deployment_summary(dep)
    try:
        pods = list_pods(order, dep)
        pods_error = None
    except ReleaseError as e:
        pods, pods_error = [], str(e)
    return {'available': True, 'exists': True, 'deployment': summary, 'pods': pods,
            'pods_error': pods_error}


def pod_logs(order, pod=None, tail=200, container=None):
    """读取指定 Pod 日志；未指定 Pod 时取第一个 Pod"""
    core = _core_api(order)
    ns = order.namespace or 'default'
    if not pod:
        dep = read_deployment(order)
        pods = list_pods(order, dep)
        if not pods:
            raise ReleaseError('当前没有可读取日志的 Pod')
        pod = pods[0]['name']
    else:
        dep = read_deployment(order)
        names = [p['name'] for p in list_pods(order, dep)]
        if pod not in names:
            raise ReleaseError('Pod 不属于该发布单，禁止读取日志')
    try:
        text = core.read_namespaced_pod_log(
            name=pod, namespace=ns, container=container or None,
            tail_lines=int(tail or 200), timestamps=False,
        )
        return {'pod': pod, 'container': container or '', 'lines': (text or '').split('\n')}
    except ApiException as e:
        raise ReleaseError('读取 Pod 日志失败：%s' % _api_message(e))


def restart(order, timeout=60):
    """滚动重启线上应用：给 Deployment 模板打注解，触发新建 ReplicaSet（等价 kubectl rollout restart）

    只重启、不改镜像，用于「改完配置/环境变量后让线上应用生效」。
    返回前会等一段时间确认新 Pod 就绪，避免 health_status 一直停在 DEPLOYING。
    """
    name = (getattr(order, 'k8s_deployment', None) or deployment_name(order))
    ns = order.namespace or 'default'
    try:
        dep = read_deployment(order)
    except ReleaseError:
        dep = None
    if dep is None:
        raise ReleaseError('目标 Deployment 不存在，无法重启（先发布一次）')
    ts = _now().strftime('%Y-%m-%dT%H:%M:%SZ')
    try:
        _apps_api(order).patch_namespaced_deployment(
            name=name, namespace=ns,
            body={'spec': {'template': {'metadata': {'annotations': {'xgsz.io/restartedAt': ts}}}}},
        )
    except ApiException as e:
        raise ReleaseError('重启失败：%s' % _api_message(e))

    deadline = time.time() + max(int(timeout or 60), 5)
    healthy, summary = False, {}
    while time.time() < deadline:
        time.sleep(2)
        try:
            cur = _apps_api(order).read_namespaced_deployment(name=name, namespace=ns)
        except ApiException:
            break
        summary = deployment_summary(cur)
        if summary['observed_generation'] >= summary['generation'] and summary['healthy']:
            healthy = True
            break
    return {
        'deployment': name, 'namespace': ns, 'restarted_at': ts,
        'healthy': healthy,
        'ready': summary.get('ready_replicas'), 'replicas': summary.get('replicas'),
        'message': ('滚动重启完成，%s/%s 就绪' % (summary.get('ready_replicas'), summary.get('replicas'))
                    if healthy else '重启已触发，新 Pod 尚未在 60 秒内全部就绪'),
    }
