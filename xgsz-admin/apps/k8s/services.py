#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推理任务的 K8s 资源编排与状态同步。

SERVICE：Deployment + NodePort Service（在线推理）
BATCH  ：Job（离线批任务，保留 7 天日志）
"""
import json
import logging
import re

import pytz
from django.conf import settings
from django.utils import timezone
from kubernetes import client
from kubernetes.client.rest import ApiException

from utils.k8s_client import apps_v1, batch_v1, core_v1

logger = logging.getLogger('default')

JOB_TTL_SECONDS = 7 * 24 * 3600
MAX_SLUG = 32


def local_naive(dt):
    """K8s 返回的是 UTC aware 时间；平台 USE_TZ=False，落库前统一换成本地 naive 时间"""
    if not dt:
        return None
    try:
        if timezone.is_aware(dt):
            return dt.astimezone(pytz.timezone(settings.TIME_ZONE)).replace(tzinfo=None)
    except Exception as e:
        logger.warning('时间转换失败: %s' % e)
    return dt


def safe_name(value, fallback='task'):
    s = re.sub(r'[^a-z0-9-]', '-', (value or '').lower())
    s = re.sub(r'-+', '-', s).strip('-')
    return (s[:MAX_SLUG].strip('-') or fallback)


def task_labels(task):
    return {'app': 'xgsz-infer', 'xgsz-task-id': str(task.id)}


def resource_names(task):
    suffix = '%s-%s' % (safe_name(task.name), task.id)
    return {
        'deployment': 'infer-%s' % suffix,
        'service': 'infer-%s-svc' % suffix,
        'job': 'infer-%s-job' % suffix,
    }


def _json(value, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _env(task):
    data = _json(task.env_vars, {})
    if not isinstance(data, dict):
        return None
    return [client.V1EnvVar(name=str(k), value=str(v)) for k, v in data.items()]


def _container(task, with_port=False):
    limits = {'cpu': task.cpu, 'memory': task.memory}
    if task.gpu and task.gpu > 0:
        limits['nvidia.com/gpu'] = str(task.gpu)
    ports = None
    if with_port and task.service_port:
        ports = [client.V1ContainerPort(container_port=int(task.service_port))]
    container = client.V1Container(
        name=safe_name(task.name, 'infer'),
        image=task.image,
        command=_json(task.command, None),
        args=_json(task.args, None),
        env=_env(task),
        ports=ports,
        resources=client.V1ResourceRequirements(
            limits=limits,
            requests={'cpu': task.cpu, 'memory': task.memory},
        ),
    )
    if task.probe_port:
        container.liveness_probe = client.V1Probe(
            http_get=client.V1HTTPGetAction(path=task.probe_path or '/healthz', port=int(task.probe_port)),
            initial_delay_seconds=30,
            period_seconds=10,
            timeout_seconds=3,
            failure_threshold=3,
        )
    return container


def _pod_spec(task, with_port=False):
    spec = client.V1PodSpec(
        containers=[_container(task, with_port=with_port)],
        restart_policy='Always' if task.task_type == 'SERVICE' else 'Never',
    )
    if task.image_pull_secret:
        spec.image_pull_secrets = [client.V1LocalObjectReference(name=task.image_pull_secret)]
    selector = _json(task.node_selector, None)
    if isinstance(selector, dict) and selector:
        spec.node_selector = selector
    return spec


def build_deployment(task):
    names = resource_names(task)
    return client.V1Deployment(
        api_version='apps/v1',
        kind='Deployment',
        metadata=client.V1ObjectMeta(name=names['deployment'], labels=task_labels(task)),
        spec=client.V1DeploymentSpec(
            replicas=max(int(task.replicas or 1), 1),
            selector=client.V1LabelSelector(match_labels=task_labels(task)),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=task_labels(task)),
                spec=_pod_spec(task, with_port=True),
            ),
        ),
    )


def build_service(task):
    names = resource_names(task)
    return client.V1Service(
        api_version='v1',
        kind='Service',
        metadata=client.V1ObjectMeta(name=names['service'], labels=task_labels(task)),
        spec=client.V1ServiceSpec(
            type='NodePort',
            selector=task_labels(task),
            ports=[client.V1ServicePort(
                name='http',
                port=int(task.service_port or 80),
                target_port=int(task.service_port or 80),
                protocol='TCP',
            )],
        ),
    )


def build_job(task):
    names = resource_names(task)
    return client.V1Job(
        api_version='batch/v1',
        kind='Job',
        metadata=client.V1ObjectMeta(name=names['job'], labels=task_labels(task)),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=JOB_TTL_SECONDS,
            backoff_limit=0,
            active_deadline_seconds=int(task.timeout_seconds or 3600),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=task_labels(task)),
                spec=_pod_spec(task, with_port=False),
            ),
        ),
    )


def ensure_quota(task):
    """给命名空间补一个默认 ResourceQuota（失败不阻塞任务）"""
    try:
        core = core_v1(task.cluster)
        name = 'xgsz-quota'
        try:
            core.read_namespaced_resource_quota(name, task.namespace)
            return
        except ApiException as e:
            if e.status != 404:
                raise
        core.create_namespaced_resource_quota(task.namespace, client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(name=name, labels={'managed-by': 'xgsz-admin'}),
            spec=client.V1ResourceQuotaSpec(hard={
                'requests.cpu': '64', 'requests.memory': '256Gi',
                'limits.cpu': '128', 'limits.memory': '512Gi', 'nvidia.com/gpu': '16',
            }),
        ))
    except Exception as e:
        logger.warning('创建 ResourceQuota 失败（忽略）: %s' % e)


def create_resources(task):
    """创建 SERVICE（Deployment+Service）或 BATCH（Job），失败抛异常"""
    names = resource_names(task)
    if task.task_type == 'SERVICE':
        deployment = build_deployment(task)
        svc = build_service(task)
        node_port = None
        apps = apps_v1(task.cluster)
        core = core_v1(task.cluster)
        apps.create_namespaced_deployment(namespace=task.namespace, body=deployment)
        try:
            created = core.create_namespaced_service(namespace=task.namespace, body=svc)
            node_port = (created.spec.ports or [None])[0].node_port if created.spec.ports else None
        except Exception:
            apps.delete_namespaced_deployment(name=names['deployment'], namespace=task.namespace)
            raise
        task.job_name = names['deployment']
        task.service_name = names['service']
        task.node_port = node_port
    else:
        job = build_job(task)
        batch_v1(task.cluster).create_namespaced_job(namespace=task.namespace, body=job)
        task.job_name = names['job']
        task.service_name = None
        task.node_port = None
    task.pod_name = get_pod_name(task)
    task.last_synced_at = timezone.now()
    task.save()
    return task


def get_pod_name(task):
    try:
        pods = core_v1(task.cluster).list_namespaced_pod(
            namespace=task.namespace, label_selector='xgsz-task-id=%s' % task.id)
        if pods.items:
            pods.items.sort(key=lambda p: p.metadata.creation_timestamp or 0)
            return pods.items[-1].metadata.name
        # 兼容改造前创建的旧 Job（没有 xgsz-task-id 标签）
        if task.task_type != 'SERVICE' and task.job_name:
            pods = core_v1(task.cluster).list_namespaced_pod(
                namespace=task.namespace, label_selector='job-name=%s' % task.job_name)
            if pods.items:
                pods.items.sort(key=lambda p: p.metadata.creation_timestamp or 0)
                return pods.items[-1].metadata.name
    except Exception as e:
        logger.warning('查找 Pod 失败: %s' % e)
    return None


POD_FAIL_REASONS = {
    'CreateContainerError': '容器创建失败',
    'CreateContainerConfigError': '容器配置错误',
    'ErrImagePull': '镜像拉取失败',
    'ImagePullBackOff': '镜像拉取失败',
    'InvalidImageName': '镜像名不合法',
    'RunContainerError': '容器启动失败',
    'CrashLoopBackOff': '容器反复退出',
}
IMAGE_PULL_REASONS = ('ErrImagePull', 'ImagePullBackOff')
POD_GRACE_SECONDS = 60   # 镜像拉取 / 调度类问题先给 60 秒重试窗口，避免误杀


def _pod_age(pod):
    try:
        created = local_naive(pod.metadata.creation_timestamp)
        if not created:
            return 9999
        return max((timezone.now() - created).total_seconds(), 0)
    except Exception:
        return 9999


def pod_failure_reason(task):
    """读 Pod 层的真实失败原因。

    平台原来只看 Deployment 的 available_replicas，容器根本起不来时会一直显示
    「已提交」，直到 600 秒 ProgressDeadlineExceeded。这里提前把真实原因取回来，
    例如：
      - CreateContainerError / no command specified（镜像没有 CMD 且任务没填命令）
      - ImagePullBackOff（镜像地址错 / 拉不到）
      - CrashLoopBackOff（容器一启动就退出）
      - Unschedulable（资源不够 / 节点选择器无匹配）
    """
    try:
        pods = core_v1(task.cluster).list_namespaced_pod(
            namespace=task.namespace, label_selector='xgsz-task-id=%s' % task.id)
    except Exception as e:
        logger.warning('查询任务 %s 的 Pod 失败: %s' % (task.id, e))
        return None
    for p in pods.items:
        age = _pod_age(p)
        for cs in (p.status.container_statuses or []):
            state = cs.state
            waiting = state.waiting if state else None
            if waiting and waiting.reason in POD_FAIL_REASONS:
                if waiting.reason in IMAGE_PULL_REASONS and age < POD_GRACE_SECONDS:
                    continue
                if waiting.reason == 'CrashLoopBackOff' and (cs.restart_count or 0) < 2:
                    continue
                msg = (waiting.message or '').strip()
                return '%s（%s）%s' % (POD_FAIL_REASONS[waiting.reason], waiting.reason,
                                      '：' + msg[:160] if msg else '')
            term = state.terminated if state else None
            if term and (term.exit_code or 0) != 0 and (cs.restart_count or 0) >= 2:
                return '容器反复退出（退出码 %s）：%s' % (term.exit_code, (term.reason or '')[:80])
        if age >= POD_GRACE_SECONDS:
            for cond in (p.status.conditions or []):
                if cond.type == 'PodScheduled' and cond.status == 'False' and cond.reason == 'Unschedulable':
                    return '调度失败：%s' % (cond.message or '')[:200]
        if age >= POD_GRACE_SECONDS and p.status.phase == 'Pending' and \
                not (p.status.container_statuses or []) and getattr(p.status, 'reason', None) == 'Evicted':
            return 'Pod 被驱逐（Evicted）'
    return None


def _terminated_info(task):
    pod_name = task.pod_name or get_pod_name(task)
    if not pod_name:
        return None, None
    try:
        pod = core_v1(task.cluster).read_namespaced_pod(name=pod_name, namespace=task.namespace)
        for cs in (pod.status.container_statuses or []):
            term = cs.state.terminated if cs.state else None
            if term:
                return term.exit_code, (term.reason or '')
    except Exception:
        pass
    return None, None


def _save(task, status=None, failure=None, started=None, finished=None):
    if status:
        task.status = status
    if failure is not None:
        task.failure_reason = failure[:2000]
    if started is not None and not task.started_at:
        task.started_at = started
    if finished is not None and not task.finished_at:
        task.finished_at = finished
    task.pod_name = get_pod_name(task) or task.pod_name
    task.last_synced_at = timezone.now()
    task.save()


def sync_status(task):
    """从 K8s 同步一次状态；终态直接返回

    顺带记录真实时间点（started_at / finished_at），用于界面显示「耗时」：
      BATCH  → Job 的 startTime / completionTime
      SERVICE→ Deployment 创建时间 / 失败判定时间
    """
    if task.status in ('SUCCEEDED', 'FAILED', 'STOPPED', 'SUBMIT_ERROR'):
        return task
    if not task.job_name:
        return task
    if task.task_type == 'SERVICE':
        try:
            dep = apps_v1(task.cluster).read_namespaced_deployment(
                name=task.job_name, namespace=task.namespace)
        except ApiException as e:
            if e.status == 404:
                _save(task, 'FAILED', 'Deployment 不存在（可能被删除）', finished=timezone.now())
            return task
        status = dep.status
        available = status.available_replicas or 0
        if available >= 1:
            _save(task, 'RUNNING', started=local_naive(dep.metadata.creation_timestamp))
        else:
            # 容器根本起不来时，Deployment 要等 600 秒才报 ProgressDeadlineExceeded；
            # 先从 Pod 读真实原因（CreateContainerError / ImagePullBackOff / CrashLoopBackOff…）
            reason = pod_failure_reason(task)
            if reason:
                _save(task, 'FAILED', reason,
                      started=local_naive(dep.metadata.creation_timestamp),
                      finished=timezone.now())
                return task
            for cond in (status.conditions or []):
                if cond.type == 'Progressing' and cond.reason == 'ProgressDeadlineExceeded':
                    _save(task, 'FAILED', cond.message or '发布进度超时',
                          started=local_naive(dep.metadata.creation_timestamp),
                          finished=timezone.now())
                    return task
            _save(task, 'SUBMITTED', started=local_naive(dep.metadata.creation_timestamp))
    else:
        try:
            job = batch_v1(task.cluster).read_namespaced_job_status(
                name=task.job_name, namespace=task.namespace)
        except ApiException as e:
            if e.status == 404:
                _save(task, 'FAILED', 'Job 不存在（可能被删除或已过保留期）', finished=timezone.now())
            return task
        status = job.status
        started = local_naive(status.start_time)
        if status.succeeded and status.succeeded >= 1:
            code, reason = _terminated_info(task)
            if code is not None:
                task.exit_code = code
            _save(task, 'SUCCEEDED', started=started,
                  finished=local_naive(status.completion_time) or timezone.now())
        elif status.failed and status.failed >= 1:
            code, reason = _terminated_info(task)
            if code is not None:
                task.exit_code = code
            _save(task, 'FAILED', reason or 'Job 执行失败',
                  started=started, finished=local_naive(status.completion_time) or timezone.now())
        elif status.active and status.active >= 1:
            _save(task, 'RUNNING', started=started)
        else:
            _save(task, 'SUBMITTED', started=started)
    return task


def delete_resources(task):
    """删除任务对应的 K8s 资源（404 视为已删除）"""
    names = resource_names(task)
    if task.task_type == 'SERVICE':
        dep_name = task.job_name or names['deployment']
        svc_name = task.service_name or names['service']
        try:
            apps_v1(task.cluster).delete_namespaced_deployment(
                name=dep_name, namespace=task.namespace, propagation_policy='Background')
        except ApiException as e:
            if e.status != 404:
                raise
        try:
            core_v1(task.cluster).delete_namespaced_service(name=svc_name, namespace=task.namespace)
        except ApiException as e:
            if e.status != 404:
                raise
    else:
        job_name = task.job_name or names['job']
        try:
            batch_v1(task.cluster).delete_namespaced_job(
                name=job_name, namespace=task.namespace, propagation_policy='Background')
        except ApiException as e:
            if e.status != 404:
                raise


def list_events(task):
    """Pod 事件（排障用），最多 50 条"""
    pod_name = task.pod_name or get_pod_name(task)
    if not pod_name:
        return []
    try:
        events = core_v1(task.cluster).list_namespaced_event(
            namespace=task.namespace, field_selector='involvedObject.name=%s' % pod_name)
    except Exception:
        return []
    rows = []
    for e in events.items:
        rows.append({
            'type': e.type,
            'reason': e.reason,
            'message': e.message,
            'count': e.count,
            'last_seen': e.last_timestamp.strftime('%Y-%m-%d %H:%M:%S') if e.last_timestamp else '',
        })
    rows.sort(key=lambda x: x.get('last_seen') or '', reverse=True)
    return rows[:50]
