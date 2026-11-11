#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging

from kubernetes import client
from kubernetes.client.rest import ApiException
from rest_framework.views import APIView

from apps.k8s.models import InferenceTask
from apps.k8s.serializers.inference import InferenceTaskSerializer
from apps.k8s import services
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission
from utils.pagination import MyPageNumberPagination
from utils.k8s_client import core_v1

logger = logging.getLogger('default')


def _audit(action, resource, detail, operator, result='成功'):
    try:
        from apps.ops.views import record_audit
        record_audit(operator, action, resource=resource, detail=detail, result=result)
    except Exception:
        pass


def _ops_log(level, source, message, detail=None, operator=None):
    try:
        from apps.ops.views import record_ops_log
        record_ops_log(level, source, message, detail=detail, operator=operator)
    except Exception:
        pass


def _parse_cpu(v):
    try:
        s = str(v or '0').strip()
        if s.endswith('m'):
            return float(s[:-1]) / 1000.0
        return float(s)
    except Exception:
        return 0.0


def _parse_mem(v):
    try:
        s = str(v or '0').strip()
        units = {'Ki': 1 / 1024 / 1024, 'Mi': 1 / 1024, 'Gi': 1.0, 'Ti': 1024.0,
                 'K': 1 / 1024 / 1024, 'M': 1 / 1024, 'G': 1.0}
        for u, f in units.items():
            if s.endswith(u):
                return float(s[:-len(u)]) * f
        return float(s) / (1024 ** 3)
    except Exception:
        return 0.0


def _check_capacity(task):
    """下发前查询目标集群剩余资源；不可查询时放行并提示"""
    try:
        core = core_v1(task.cluster)
        total_cpu = total_mem = total_gpu = 0.0
        for n in core.list_node().items:
            alloc = n.status.allocatable or {}
            total_cpu += _parse_cpu(alloc.get('cpu'))
            total_mem += _parse_mem(alloc.get('memory'))
            total_gpu += int(alloc.get('nvidia.com/gpu', 0) or 0)
        used_cpu = used_mem = used_gpu = 0.0
        for p in core.list_pod_for_all_namespaces(field_selector='status.phase=Running').items:
            for c in (p.spec.containers or []):
                req = (c.resources.requests or {}) if c.resources else {}
                used_cpu += _parse_cpu(req.get('cpu'))
                used_mem += _parse_mem(req.get('memory'))
                used_gpu += int(req.get('nvidia.com/gpu', 0) or 0)
        need_cpu = _parse_cpu(task.cpu)
        need_mem = _parse_mem(task.memory)
        need_gpu = int(task.gpu or 0)
        shortage = []
        if total_cpu - used_cpu < need_cpu:
            shortage.append('CPU 剩余 %.2f 核，需要 %.2f 核' % (total_cpu - used_cpu, need_cpu))
        if total_mem - used_mem < need_mem:
            shortage.append('内存剩余 %.1f Gi，需要 %.1f Gi' % (total_mem - used_mem, need_mem))
        if need_gpu and total_gpu - used_gpu < need_gpu:
            shortage.append('GPU 剩余 %d 卡，需要 %d 卡' % (total_gpu - used_gpu, need_gpu))
        if shortage:
            return False, '集群资源不足：' + '；'.join(shortage)
        return True, '资源充足（剩余 CPU %.2f 核 / 内存 %.1f Gi / GPU %d 卡）' % (
            total_cpu - used_cpu, total_mem - used_mem, total_gpu - used_gpu)
    except Exception as e:
        logger.warning('资源校验不可用（放行）: %s' % e)
        return True, '资源校验不可用，已放行：%s' % str(e)[:120]


def _task_qs_for(user):
    qs = InferenceTask.objects.all()
    if getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ('superadmin', 'admin', 'lead'):
        return qs
    return qs.filter(owner=getattr(user, 'name', '') or '')


def _submit(task, request):
    """创建 K8s 资源；失败返回 False 并落库错误"""
    operator = getattr(request.user, 'name', None) or getattr(request.user, 'username', None)
    ok, msg = _check_capacity(task)
    if not ok:
        task.status = 'SUBMIT_ERROR'
        task.error_msg = msg
        task.save()
        _audit('task', '提交推理任务：%s' % task.name, '拦截：%s' % msg, operator, result='失败')
        return False
    try:
        services.ensure_quota(task)
        services.create_resources(task)
        task.status = 'SUBMITTED'
        task.error_msg = ''
        task.save()
        _ops_log('INFO', 'task', '提交推理任务：%s' % task.name,
                 detail='%s %s，镜像 %s，集群 %s' % (
                     task.task_type, task.job_name, task.image, task.cluster or '默认'), operator=operator)
        _audit('task', '提交推理任务：%s' % task.name,
               '%s %s 创建成功，镜像 %s' % (task.task_type, task.job_name, task.image), operator)
        return True
    except Exception as e:
        task.status = 'SUBMIT_ERROR'
        task.error_msg = str(e)[:2000]
        task.save()
        logger.error('推理任务提交失败: %s' % e)
        _audit('task', '提交推理任务：%s' % task.name, '失败：%s' % str(e)[:200], operator, result='失败')
        return False


def _create_task_from_payload(data, user):
    command = data.get('command')
    if isinstance(command, (list, dict)):
        command = json.dumps(command)
    args = data.get('args')
    if isinstance(args, (list, dict)):
        args = json.dumps(args)
    env_vars = data.get('env_vars')
    if isinstance(env_vars, dict):
        env_vars = json.dumps(env_vars)
    node_selector = data.get('node_selector')
    if isinstance(node_selector, dict):
        node_selector = json.dumps(node_selector)
    task_type = (data.get('task_type') or 'SERVICE').upper()
    if task_type not in ('SERVICE', 'BATCH'):
        task_type = 'SERVICE'
    owner = data.get('owner') or getattr(user, 'name', None)
    if getattr(user, 'role', '') == 'engineer':
        owner = getattr(user, 'name', None) or owner
    return InferenceTask.objects.create(
        name=(data.get('name') or '').strip(),
        cluster=(data.get('cluster') or '').strip(),
        task_type=task_type,
        namespace=data.get('namespace') or 'default',
        image=(data.get('image') or '').strip(),
        command=command,
        args=args,
        env_vars=env_vars,
        cpu=data.get('cpu', '1'),
        memory=data.get('memory', '2Gi'),
        gpu=int(data.get('gpu', 0) or 0),
        gpu_node_id=data.get('gpu_node_id') or None,
        node_selector=node_selector,
        replicas=int(data.get('replicas', 1) or 1),
        service_port=int(data.get('service_port', 80) or 80),
        timeout_seconds=int(data.get('timeout_seconds', 3600) or 3600),
        image_pull_secret=(data.get('image_pull_secret') or '').strip() or None,
        owner=owner,
        probe_port=(int(data.get('probe_port')) if data.get('probe_port') else None),
        probe_path=data.get('probe_path') or '/healthz',
    )


class InferenceTaskView(APIView):
    """推理任务：GET 列表 / POST 提交（SERVICE=Deployment+NodePort，BATCH=Job）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from django.db.models import Count
        search = request.query_params.get('keyword')
        status = request.query_params.get('status')
        base_qs = _task_qs_for(request.user)
        stats = {r['status']: r['c'] for r in base_qs.order_by().values('status').annotate(c=Count('pk'))}
        qs = base_qs
        if search:
            qs = qs.filter(name__icontains=search)
        if status:
            # ACTIVE = 前端「运行中」筛选口径（已提交 / 排队 / 运行）
            if status == 'ACTIVE':
                qs = qs.filter(status__in=['SUBMITTED', 'RUNNING', 'PENDING'])
            else:
                qs = qs.filter(status=status)
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        ser = InferenceTaskSerializer(page, many=True)
        data = paginator.get_paginated_response(ser.data).data
        data['stats'] = stats
        return APIResponse(data=data)

    def post(self, request, *args, **kwargs):
        data = request.data
        name = (data.get('name') or '').strip()
        image = (data.get('image') or '').strip()
        if not name:
            return APIResponse(errcode=4001, errmsg='任务名称不能为空')
        if not image:
            return APIResponse(errcode=4001, errmsg='镜像地址不能为空')
        cluster = (data.get('cluster') or '').strip()
        # 集群必须可用，不再回退默认集群（空值仅兼容旧调用）
        if cluster:
            try:
                core_v1(cluster).list_namespace(limit=1)
            except Exception as e:
                return APIResponse(errcode=4090, errmsg='目标集群不可用（%s）：%s' % (cluster, str(e)[:160]))
        task = _create_task_from_payload(data, request.user)
        _submit(task, request)
        task.refresh_from_db()
        return APIResponse(data=InferenceTaskSerializer(task).data)


class InferenceTaskDetailView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=kwargs.get('pk')).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        try:
            services.sync_status(task)
        except Exception as e:
            logger.warning('同步任务状态失败: %s' % e)
        task.refresh_from_db()
        return APIResponse(data=InferenceTaskSerializer(task).data)


class InferenceTaskStopView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=kwargs.get('pk')).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        operator = getattr(request.user, 'name', None) or getattr(request.user, 'username', None)
        try:
            services.delete_resources(task)
            from django.utils import timezone as _tz
            task.status = 'STOPPED'
            if not task.finished_at:
                task.finished_at = _tz.now()
            task.save()
            _ops_log('WARN', 'task', '停止推理任务：%s' % task.name, operator=operator)
            _audit('task', '停止推理任务：%s' % task.name, '资源已删除', operator)
            return APIResponse(data=InferenceTaskSerializer(task).data)
        except Exception as e:
            _audit('task', '停止推理任务：%s' % task.name, '失败：%s' % str(e)[:200], operator, result='失败')
            return APIResponse(errcode=5001, errmsg='停止失败: %s' % str(e))


class InferenceTaskLogsView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=kwargs.get('pk')).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        pod_name = task.pod_name or services.get_pod_name(task)
        if not pod_name:
            return APIResponse(data={'pod_name': '-', 'log': '任务尚未产生 Pod，或 Pod 已结束。'})
        try:
            log = core_v1(task.cluster).read_namespaced_pod_log(
                name=pod_name, namespace=task.namespace, tail_lines=300)
            return APIResponse(data={'pod_name': pod_name, 'log': log or '（暂无日志）'})
        except Exception as e:
            msg = str(e)
            if 'waiting to start' in msg or 'is waiting to start' in msg:
                hint = ('容器还没启动，暂时没有日志。\n\n'
                        '失败原因：%s\n\n'
                        '排障建议：看下方「事件」里的 Warning 记录（镜像拉取、命令缺失、权限等），'
                        '修正镜像/命令后点「重跑」。' % ((task.failure_reason or task.error_msg or '未知')[:500]))
                return APIResponse(data={'pod_name': pod_name, 'log': hint})
            logger.warning('读取任务 %s 日志失败: %s' % (task.id, msg[:200]))
            return APIResponse(data={'pod_name': pod_name, 'log': '日志读取失败：%s' % msg[:200]})


class InferenceTaskEventsView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=kwargs.get('pk')).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        return APIResponse(data={'events': services.list_events(task)})


class InferenceTaskRerunView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=kwargs.get('pk')).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        data = {
            'name': (task.name + '-retry')[:120],
            'cluster': task.cluster,
            'task_type': task.task_type,
            'namespace': task.namespace,
            'image': task.image,
            'command': task.command,
            'args': task.args,
            'env_vars': task.env_vars,
            'cpu': task.cpu,
            'memory': task.memory,
            'gpu': task.gpu,
            'node_selector': task.node_selector,
            'replicas': task.replicas,
            'service_port': task.service_port,
            'timeout_seconds': task.timeout_seconds,
            'image_pull_secret': task.image_pull_secret,
            'owner': task.owner,
            'probe_port': task.probe_port,
            'probe_path': task.probe_path,
        }
        new_task = _create_task_from_payload(data, request.user)
        _submit(new_task, request)
        new_task.refresh_from_db()
        return APIResponse(data=InferenceTaskSerializer(new_task).data)


class InferenceTaskRenameView(APIView):
    """任务改名：只改平台显示名，不动 K8s 资源（job_name / service_name 保持不变）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, pk, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=pk).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        name = (request.data.get('name') or '').strip()
        if not name:
            return APIResponse(errcode=4001, errmsg='任务名称不能为空')
        if len(name) > 120:
            return APIResponse(errcode=4001, errmsg='任务名称最多 120 个字符')
        old = task.name
        if name != old:
            task.name = name
            task.save(update_fields=['name', 'updated_at'])
            operator = getattr(request.user, 'name', None) or getattr(request.user, 'username', None)
            _audit('task', '推理任务改名：%s' % old,
                   '改为：%s（K8s 资源不变：%s）' % (name, task.job_name or '-'), operator)
            _ops_log('INFO', 'task', '推理任务改名：%s → %s' % (old, name), operator=operator)
        return APIResponse(data=InferenceTaskSerializer(task).data)


class InferenceTaskUsageView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        task = _task_qs_for(request.user).filter(id=kwargs.get('pk')).first()
        if not task:
            return APIResponse(errcode=404, errmsg='任务不存在')
        pod_name = task.pod_name or services.get_pod_name(task)
        if not pod_name:
            return APIResponse(errcode=404, errmsg='未找到 Pod')
        try:
            pod = core_v1(task.cluster).read_namespaced_pod(name=pod_name, namespace=task.namespace)
            containers = [{'name': c.name, 'image': c.image, 'ready': c.ready,
                           'restart_count': c.restart_count}
                          for c in (pod.status.container_statuses or [])]
            resources = [{'name': c.name,
                          'requests': c.resources.requests if c.resources else {},
                          'limits': c.resources.limits if c.resources else {}}
                         for c in (pod.spec.containers or [])]
            return APIResponse(data={
                'pod_name': pod_name,
                'node': pod.spec.node_name,
                'phase': pod.status.phase,
                'host_ip': pod.status.host_ip,
                'pod_ip': pod.status.pod_ip,
                'containers': containers,
                'resources': resources,
            })
        except Exception as e:
            return APIResponse(errcode=5001, errmsg='获取资源占用失败: %s' % str(e))


class InferenceMetaView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        import os
        images = set()
        namespaces = set()
        clusters = []
        base = os.getenv('KUBECONFIG_DIR', '/root/.kube/clusters')
        try:
            for fn in os.listdir(base):
                if fn.endswith('.yaml') and not fn.startswith('.'):
                    clusters.append(fn[:-5])
        except Exception:
            pass
        try:
            core = core_v1(None)
            for n in core.list_namespace().items:
                namespaces.add(n.metadata.name)
            for p in core.list_pod_for_all_namespaces().items:
                for c in (p.spec.containers or []):
                    if c.image:
                        images.add(c.image)
        except Exception:
            pass
        task_names = []
        task_images = []
        try:
            task_names = list(InferenceTask.objects.exclude(name__isnull=True).exclude(name='')
                              .values_list('name', flat=True).distinct()[:300])
            task_images = list(InferenceTask.objects.exclude(image__isnull=True).exclude(image='')
                               .values_list('image', flat=True).distinct()[:300])
        except Exception:
            pass
        for img in task_images:
            images.add(img)
        if not namespaces:
            namespaces = {'default'}
        return APIResponse(data={
            'namespaces': sorted(namespaces),
            'images': sorted(images),
            'task_names': task_names,
            'task_images': sorted(set(task_images)),
            'clusters': sorted(clusters),
        })
