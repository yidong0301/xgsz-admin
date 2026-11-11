#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前连通性自检（一次性把三段链路都跑一遍）。

用法（在平台容器里执行）：

    docker compose exec backend python manage.py check_access
    docker compose exec backend python manage.py check_access --json
    docker compose exec backend python manage.py check_access --cluster prod-01 --namespace xgsz-prod
    docker compose exec backend python manage.py check_access --registry harbor.corp.local:443

检查内容：
  1) 平台自身组件：MySQL / Redis / MongoDB / Celery worker
  2) 各 K8s 集群：kubeconfig 是否存在、能否连上、节点数、版本
  3) 集群权限：能否在目标命名空间创建 Deployment（SelfSubjectAccessReview）
  4) 指标：metrics-server（metrics.k8s.io/v1beta1）是否可用
  5) 镜像仓库：从集群里 Deployment 的镜像地址提取仓库，做 TCP 连通性探测

退出码：0 = 全部通过；1 = 有 FAIL
"""
import json
import os
import socket
import sys

from django.core.management.base import BaseCommand


STATUS_OK = 'OK'
STATUS_FAIL = 'FAIL'
STATUS_WARN = 'WARN'
STATUS_SKIP = 'SKIP'


def _registry_host(image):
    """从镜像地址推断仓库 host:port（Docker 规则：含 . 或 : 或 localhost 才算仓库域名）"""
    img = (image or '').strip()
    if not img:
        return None
    if '/' not in img:                      # 如 nginx:alpine → 走 Docker Hub
        return None
    first = img.split('/')[0]
    if first == 'localhost' or '.' in first or ':' in first:
        return first if ':' in first else '%s:443' % first
    return None


def _tcp_check(host, port, timeout=3):
    """TCP 连通性探测，返回 (ok, detail)"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, 'TCP %s:%s 可达' % (host, port)
    except Exception as e:
        return False, 'TCP %s:%s 不可达：%s' % (host, port, str(e)[:120])


class Command(BaseCommand):
    help = '上线前连通性自检：平台组件 → 各 K8s 集群 → RBAC → metrics → 镜像仓库'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='以 JSON 输出（便于脚本/CI 判断）')
        parser.add_argument('--namespace', default='xgsz-test', help='权限检查用的命名空间（默认 xgsz-test）')
        parser.add_argument('--cluster', action='append', default=None,
                            help='只检查指定集群（可多次）；默认检查 kube/clusters 下全部')
        parser.add_argument('--registry', action='append', default=[],
                            help='额外探测的镜像仓库 host:port（可多次）')
        parser.add_argument('--skip-registry', action='store_true', help='跳过镜像仓库探测')
        parser.add_argument('--timeout', type=int, default=5, help='单次调用超时秒数（默认 5）')

    # ---------- 各项检查 ----------

    def _components(self):
        rows = []
        from django.db import connection

        def mysql():
            with connection.cursor() as c:
                c.execute('SELECT 1')
                c.fetchone()
        rows.append(self._run('平台 · MySQL', mysql))

        def redis():
            from django_redis import get_redis_connection
            get_redis_connection('default').ping()
        rows.append(self._run('平台 · Redis', redis))

        def mongo():
            import pymongo
            from decouple import config
            cli = pymongo.MongoClient(host=config('MONGO_HOST'), port=int(config('MONGO_PORT')),
                                      serverSelectionTimeoutMS=2000)
            cli.admin.command('ping')
        rows.append(self._run('平台 · MongoDB', mongo))

        def celery():
            from xgsz_admin.celery import app as celery_app
            insp = celery_app.control.inspect(timeout=1)
            if not insp.ping():
                raise RuntimeError('没有 worker 响应（celery-worker 未启动？）')
        rows.append(self._run('平台 · Celery', celery))
        return rows

    def _run(self, name, fn):
        try:
            fn()
            return {'name': name, 'status': STATUS_OK, 'detail': '连接正常'}
        except Exception as e:
            return {'name': name, 'status': STATUS_FAIL, 'detail': str(e)[:200]}

    def _clusters(self, names, namespace, timeout):
        from apps.ops import k8s_release as kr
        configured = kr.list_cluster_configs()
        if names:
            targets = list(names)
        else:
            targets = sorted(configured.keys())

        rows = []
        target_count = kr.expected_cluster_count()
        rows.append({'name': '集群 · 配置数量', 'status': STATUS_OK if targets else STATUS_FAIL,
                     'detail': '已配置 %d 台 / 目标 %d 台：%s' % (
                         len(configured), target_count, ', '.join(sorted(configured.keys())) or '（空）')})

        for name in targets:
            info = kr.check_cluster(name, timeout=timeout)
            if not info.get('configured'):
                rows.append({'name': '集群 · %s' % name, 'status': STATUS_FAIL,
                             'detail': '未找到 kube/clusters/%s.yaml' % name})
                continue
            if not info.get('reachable'):
                rows.append({'name': '集群 · %s' % name, 'status': STATUS_FAIL,
                             'detail': 'API 不可达：%s' % (info.get('error') or '-')})
                continue
            rows.append({'name': '集群 · %s' % name, 'status': STATUS_OK,
                         'detail': '在线 · 节点 %s · 版本 %s · %s' % (
                             info.get('node_count'), info.get('version') or '-', info.get('kubeconfig'))})
            rows.extend(self._cluster_deep(name, namespace, timeout))
        return rows

    def _cluster_deep(self, name, namespace, timeout):
        """集群内部的进一步检查：RBAC 权限 + metrics-server"""
        from kubernetes import client as kclient
        from apps.ops import k8s_release as kr

        class Probe:
            cluster = name

        rows = []
        api = kr._api_client(Probe())

        # RBAC：能否在目标命名空间创建 Deployment
        try:
            auth = kclient.AuthorizationV1Api(api)
            review = kclient.V1SelfSubjectAccessReview(
                spec=kclient.V1SelfSubjectAccessReviewSpec(
                    resource_attributes=kclient.V1ResourceAttributes(
                        namespace=namespace, verb='create', group='apps', resource='deployments')))
            resp = auth.create_self_subject_access_review(review, _request_timeout=timeout)
            allowed = bool(getattr(resp.status, 'allowed', False))
            rows.append({'name': '权限 · %s @ %s' % (name, namespace),
                         'status': STATUS_OK if allowed else STATUS_FAIL,
                         'detail': '可创建 Deployment' if allowed else
                                   '无权限（%s），请给 ServiceAccount 绑定 ClusterRole' % (
                                       getattr(resp.status, 'reason', '') or 'denied')})
        except Exception as e:
            rows.append({'name': '权限 · %s @ %s' % (name, namespace), 'status': STATUS_FAIL,
                         'detail': '权限检查失败：%s' % str(e)[:160]})

        # metrics-server
        try:
            kclient.CustomObjectsApi(api).list_cluster_custom_object(
                group='metrics.k8s.io', version='v1beta1', plural='nodes', _request_timeout=timeout)
            rows.append({'name': '指标 · %s' % name, 'status': STATUS_OK,
                         'detail': 'metrics-server 可用（指标页/节点用量能显示）'})
        except Exception as e:
            rows.append({'name': '指标 · %s' % name, 'status': STATUS_FAIL,
                         'detail': 'metrics.k8s.io 不可用：%s（节点用量/Pod Top 会显示不可用）' % str(e)[:140]})
        return rows

    def _registries(self, names, extra, timeout):
        """从集群 Deployment 的镜像地址里提取仓库域名，做 TCP 探测

        - 显式 --registry：不可达记 FAIL（说明你明确要用这个仓库）
        - 从镜像自动推断：不可达记 WARN（可能只是没拉过、或内网镜像已预热）
        """
        from kubernetes import client as kclient
        from apps.ops import k8s_release as kr

        explicit = set()
        for spec in list(extra or []):
            explicit.add(spec if ':' in spec else '%s:443' % spec)
        hosts = set(explicit)

        if not extra:
            try:
                for name in (names or sorted(kr.list_cluster_configs().keys())):
                    class Probe:
                        cluster = name
                    api = kr._api_client(Probe())
                    deps = kclient.AppsV1Api(api).list_deployment_for_all_namespaces(
                        limit=200, _request_timeout=timeout)
                    for d in deps.items:
                        for c in ((d.spec.template.spec.containers) or []):
                            host = _registry_host(c.image or '')
                            if host:
                                hosts.add(host)
            except Exception:
                pass

        rows = []
        if not hosts:
            rows.append({'name': '镜像仓库', 'status': STATUS_SKIP,
                         'detail': '集群里没有带仓库域名的镜像（或无法读取 Deployment），可加 --registry 指定'})
            return rows
        for h in sorted(hosts):
            host, port = h.rsplit(':', 1) if ':' in h else (h, '443')
            ok, detail = _tcp_check(host, port, timeout=timeout)
            if ok:
                rows.append({'name': '镜像仓库 · %s' % h, 'status': STATUS_OK, 'detail': detail})
            else:
                rows.append({'name': '镜像仓库 · %s' % h,
                             'status': STATUS_FAIL if h in explicit else STATUS_WARN,
                             'detail': detail + '（该仓库拉不到镜像会导致 ImagePullBackOff）'})
        return rows

    # ---------- 主入口 ----------

    def handle(self, *args, **options):
        namespace = options.get('namespace') or 'xgsz-test'
        timeout = int(options.get('timeout') or 5)
        names = options.get('cluster') or None

        # kind 自签证书会刷一屏 urllib3 警告，这里静音
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

        rows = []
        rows.extend(self._components())
        rows.extend(self._clusters(names, namespace, timeout))
        if not options.get('skip_registry'):
            rows.extend(self._registries(names, options.get('registry') or [], timeout))

        failed = [r for r in rows if r['status'] == STATUS_FAIL]
        summary = {
            'total': len(rows),
            'ok': sum(1 for r in rows if r['status'] == STATUS_OK),
            'warn': sum(1 for r in rows if r['status'] == STATUS_WARN),
            'fail': len(failed),
            'skip': sum(1 for r in rows if r['status'] == STATUS_SKIP),
            'namespace': namespace,
            'results': rows,
        }

        if options.get('json'):
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            self.stdout.write('')
            self.stdout.write('连通性自检（权限命名空间：%s）' % namespace)
            self.stdout.write('=' * 96)
            for r in rows:
                mark = {'OK': '[ OK ]', 'FAIL': '[FAIL]', 'WARN': '[WARN]', 'SKIP': '[SKIP]'}.get(r['status'], '[    ]')
                self.stdout.write('%s %-30s %s' % (mark, r['name'], r['detail']))
            self.stdout.write('=' * 96)
            self.stdout.write('共 %d 项：通过 %d，警告 %d，失败 %d，跳过 %d' % (
                summary['total'], summary['ok'], summary['warn'], summary['fail'], summary['skip']))
            if failed:
                self.stdout.write(self.style.ERROR(
                    '有 %d 项失败，按上面的提示逐项处理（详见 docs/11-真实集群与服务器接入手册.md）' % len(failed)))
            elif summary['warn']:
                self.stdout.write(self.style.WARNING(
                    '有 %d 项警告（多为镜像仓库从公网走不通），确认内网仓库/离线镜像即可' % summary['warn']))
            else:
                self.stdout.write(self.style.SUCCESS('全部通过：平台、集群、权限、指标、镜像仓库都正常'))

        if failed:
            sys.exit(1)
