#!/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import traceback
from datetime import date

import requests
from django.db.models import Sum
from rest_framework.views import APIView

from apps.cmdb.models import Server, GPUNode, K8sCluster, NetworkSwitch, OpticalModule
from apps.k8s.models import InferenceTask
from apps.workflow.models import TaskExecution, PipelineExecution
from apps.ops.models import InspectionRecord, AuditLog, OpsLog, ReleaseOrder
from apps.ops import k8s_release
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission

logger = logging.getLogger('default')

RELEASE_STATUS_LABEL = {
    'PENDING': '待审批', 'APPROVED': '已审批', 'RELEASING': '发布中',
    'RELEASED': '已发布', 'FAILED': '发布失败', 'ROLLED_BACK': '已回滚', 'REJECTED': '已拒绝',
}


def _rate(total, ok):
    if not total:
        return 0.0
    return round(ok * 100.0 / total, 1)


class OpsDashboardView(APIView):
    """
    数据看板：资产统计 / 任务成功率 / 算力使用率 / 流水线统计
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        # 1. 资产统计
        assets = {
            'server': Server.objects.count(),
            'gpu_node': GPUNode.objects.count(),
            'k8s_cluster': K8sCluster.objects.count(),
            'switch': NetworkSwitch.objects.count(),
            'optical_module': OpticalModule.objects.count(),
        }
        assets['total'] = sum(assets.values())

        # 2. 推理任务成功率
        infer_total = InferenceTask.objects.count()
        infer_ok = InferenceTask.objects.filter(status='SUCCEEDED').count()
        infer_fail = InferenceTask.objects.filter(status__in=['FAILED', 'SUBMIT_ERROR']).count()
        infer_running = InferenceTask.objects.filter(status__in=['SUBMITTED', 'RUNNING', 'PENDING']).count()

        # 3. 任务编排成功率
        wf_total = TaskExecution.objects.count()
        wf_ok = TaskExecution.objects.filter(status='SUCCEEDED').count()
        wf_fail = TaskExecution.objects.filter(status__in=['FAILED', 'PARTIAL']).count()

        # 4. 流水线统计
        pl_total = PipelineExecution.objects.count()
        pl_ok = PipelineExecution.objects.filter(status='SUCCEEDED').count()
        pl_fail = PipelineExecution.objects.filter(status='FAILED').count()

        # 5. 算力使用率（GPU）
        total_gpu = GPUNode.objects.aggregate(s=Sum('gpu_count'))['s'] or 0
        used_gpu = InferenceTask.objects.filter(status__in=['SUBMITTED', 'RUNNING'], gpu__gt=0).aggregate(s=Sum('gpu'))['s'] or 0

        data = {
            'assets': assets,
            'inference': {'total': infer_total, 'ok': infer_ok, 'fail': infer_fail, 'running': infer_running,
                          'success_rate': _rate(infer_total, infer_ok)},
            'workflow': {'total': wf_total, 'ok': wf_ok, 'fail': wf_fail, 'success_rate': _rate(wf_total, wf_ok)},
            'pipeline': {'total': pl_total, 'ok': pl_ok, 'fail': pl_fail, 'success_rate': _rate(pl_total, pl_ok)},
            'gpu_usage': {'total_gpu': total_gpu, 'used_gpu': used_gpu,
                          'usage_rate': round(used_gpu * 100.0 / total_gpu, 1) if total_gpu else 0.0},
        }
        return APIResponse(data=data)


class InspectionView(APIView):
    """
    运维巡检：定时/手动采集节点状态，标记异常
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        anomalies = []

        # 1. 已停机服务器
        for s in Server.objects.filter(status='Stopped'):
            anomalies.append({'type': 'server', 'level': 'warning',
                              'title': '服务器已停机：%s' % (s.hostname or s.instance_id),
                              'detail': '负责人：%s' % (s.owner or '未指定')})

        # 2. 失败推理任务（error_msg 可能很长，截断成人话，避免公告被撑爆）
        for t in InferenceTask.objects.filter(status__in=['FAILED', 'SUBMIT_ERROR']):
            err = ((t.error_msg or '') + ' ' + (t.failure_reason or '')).strip()
            if 'no command specified' in err:
                detail = '镜像没有默认启动命令，且任务未填写命令'
            elif 'CreateContainerError' in err or 'CreateContainerConfigError' in err:
                detail = '容器创建失败（检查镜像/命令/配置）'
            elif 'ImagePullBackOff' in err or 'ErrImagePull' in err:
                detail = '镜像拉取失败（检查镜像地址/拉取密钥）'
            elif 'CrashLoopBackOff' in err:
                detail = '容器反复退出（查看任务日志与事件）'
            elif '422' in err or 'Unprocessable' in err:
                detail = 'K8s 拒绝了任务配置（检查镜像/名称）'
            elif 'kubeconfig' in err or 'K8s 集群' in err:
                detail = 'K8s 集群连接异常'
            elif err:
                detail = err[:50] + ('…' if len(err) > 50 else '')
            else:
                detail = '状态：%s' % t.status
            anomalies.append({'type': 'inference', 'level': 'error',
                              'title': '推理任务失败：%s' % t.name,
                              'detail': detail})

        # 3. 失败流水线/任务编排
        for e in TaskExecution.objects.filter(status__in=['FAILED', 'PARTIAL'])[:5]:
            anomalies.append({'type': 'workflow', 'level': 'error',
                              'title': '任务编排异常：%s' % e.name, 'detail': e.status})
        for e in PipelineExecution.objects.filter(status='FAILED')[:5]:
            anomalies.append({'type': 'pipeline', 'level': 'error',
                              'title': '流水线失败：%s' % e.name, 'detail': e.status})

        # 4. 维保到期（30 天内）
        from django.db.models import Q
        today = date.today()
        for g in list(GPUNode.objects.filter(warranty_expire__isnull=False)) + \
                 list(NetworkSwitch.objects.filter(warranty_expire__isnull=False)) + \
                 list(OpticalModule.objects.filter(warranty_expire__isnull=False)):
            if g.warranty_expire and (g.warranty_expire - today).days <= 30:
                anomalies.append({'type': 'asset', 'level': 'warning',
                                  'title': '维保即将到期：%s' % g.name,
                                  'detail': '到期日 %s' % g.warranty_expire})

        status = 'WARNING' if anomalies else 'HEALTHY'
        InspectionRecord.objects.create(status=status, anomaly_count=len(anomalies),
                                        anomalies=json.dumps(anomalies, ensure_ascii=False))
        record_ops_log('WARN' if anomalies else 'INFO', 'inspection',
                       '巡检完成：%s，异常 %d 条' % (status, len(anomalies)),
                       detail=json.dumps(anomalies[:3], ensure_ascii=False) if anomalies else None)
        return APIResponse(data={'status': status, 'anomaly_count': len(anomalies), 'anomalies': anomalies})


class InspectionHistoryView(APIView):
    """巡检记录列表"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from utils.pagination import MyPageNumberPagination
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(InspectionRecord.objects.all(), request, view=self)
        data = [{'id': r.id, 'status': r.status, 'anomaly_count': r.anomaly_count,
                 'checked_at': r.checked_at.strftime('%Y-%m-%d %H:%M:%S')} for r in page]
        return APIResponse(data=paginator.get_paginated_response(data).data)


class NotifyView(APIView):
    """
    消息推送：对接钉钉/企微机器人，测试发送 + 任务失败/资源超限推送
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        from decouple import config
        webhook = request.data.get('webhook') or config('NOTIFY_WEBHOOK_URL', default='')
        content = request.data.get('content', '【芯光数智】测试消息：平台消息推送已接入')
        if not webhook:
            return APIResponse(errcode=400, errmsg='未配置钉钉/企微 webhook 地址')
        try:
            payload = {'msgtype': 'text', 'text': {'content': content}}
            resp = requests.post(webhook, json=payload, timeout=10)
            ok = resp.status_code == 200 and resp.json().get('errcode', 0) == 0
            return APIResponse(data={'sent': ok, 'status_code': resp.status_code,
                                     'response': resp.text[:200]})
        except Exception as e:
            logger.error('消息推送失败: %s' % traceback.format_exc())
            return APIResponse(errcode=5001, errmsg='推送失败: %s' % str(e))


def record_audit(user, action, resource=None, detail=None, request=None, result='成功'):
    """记录操作审计日志（失败不阻塞主流程）"""
    try:
        ip = None
        if request is not None:
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        AuditLog.objects.create(user=user, action=action, resource=resource, detail=detail, ip=ip, result=result)
    except Exception as e:
        logger.warning('记录审计日志失败: %s' % str(e))


class AuditLogView(APIView):
    """操作审计日志列表"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from utils.pagination import MyPageNumberPagination
        from django.db.models import Q
        from datetime import datetime
        qs = AuditLog.objects.all()
        kw = request.query_params.get('keyword')
        if kw:
            qs = qs.filter(Q(resource__contains=kw) | Q(detail__contains=kw))
        ip = request.query_params.get('ip')
        if ip:
            qs = qs.filter(ip__contains=ip)
        action = request.query_params.get('action')
        if action:
            qs = qs.filter(action=action)
        result = request.query_params.get('result')
        if result:
            qs = qs.filter(result=result)
        start = request.query_params.get('start')
        if start:
            try:
                qs = qs.filter(created_at__gte=datetime.strptime(start, '%Y-%m-%d'))
            except Exception:
                pass
        end = request.query_params.get('end')
        if end:
            try:
                qs = qs.filter(created_at__lte=datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            except Exception:
                pass
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [{'id': l.id, 'user': l.user, 'action': l.action, 'resource': l.resource,
                 'detail': l.detail, 'ip': l.ip, 'result': l.result,
                 'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S')} for l in page]
        resp = paginator.get_paginated_response(data).data
        try:
            from django.utils import timezone as _tz
            resp['stats'] = {
                'today': AuditLog.objects.filter(created_at__date=_tz.now().date()).count(),
                'total': AuditLog.objects.count(),
                'users': AuditLog.objects.exclude(user__isnull=True).exclude(user='').values('user').distinct().count(),
            }
        except Exception:
            resp['stats'] = {'today': 0, 'total': 0, 'users': 0}
        return APIResponse(data=resp)


class OverviewView(APIView):
    """小程序概览聚合接口（P1 运行概览）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from apps.cmdb.models import Server, GPUNode
        from apps.k8s.models import InferenceTask
        from apps.ops.models import InspectionRecord
        from django.db.models import Sum, Count

        server_total = Server.objects.count()
        server_online = Server.objects.exclude(status='Stopped').count()
        gpu_total = GPUNode.objects.aggregate(s=Sum('gpu_count'))['s'] or 0
        gpu_used = InferenceTask.objects.filter(status__in=['SUBMITTED', 'RUNNING'], gpu__gt=0).aggregate(s=Sum('gpu'))['s'] or 0
        task_running = InferenceTask.objects.filter(status__in=['SUBMITTED', 'RUNNING']).count()
        task_pending = InferenceTask.objects.filter(status='PENDING').count()

        finished = InferenceTask.objects.filter(status__in=['SUCCEEDED', 'FAILED', 'SUBMIT_ERROR']).count()
        ok = InferenceTask.objects.filter(status='SUCCEEDED').count()
        success_rate = round(ok / finished * 100) if finished else 100

        status_labels = {
            'PENDING': '排队中', 'SUBMITTED': '运行中', 'RUNNING': '运行中',
            'SUCCEEDED': '已成功', 'FAILED': '已失败', 'SUBMIT_ERROR': '已失败', 'STOPPED': '已停止',
        }
        task_counts = {}
        for row in InferenceTask.objects.values('status').annotate(value=Count('id')):
            label = status_labels.get(row['status'], row['status'])
            task_counts[label] = task_counts.get(label, 0) + row['value']
        task_by_status = [{'name': k, 'value': v} for k, v in task_counts.items()]

        def dist(field):
            rows = Server.objects.values(field).annotate(value=Count('instance_id'))
            return [{'name': (r[field] or '未指定'), 'value': r['value']} for r in rows]

        recent = list(InferenceTask.objects.order_by('-id')[:3].values('id', 'name', 'status', 'gpu', 'created_at'))
        for r in recent:
            r['created_at'] = r['created_at'].strftime('%m-%d %H:%M') if r.get('created_at') else ''

        last = InspectionRecord.objects.order_by('-id').first()
        anomalies = []
        if last and last.anomalies:
            import json as _json
            try:
                anomalies = _json.loads(last.anomalies)
            except Exception:
                anomalies = []
        top_alert = anomalies[0] if anomalies else None

        return APIResponse(data={
            'server': {'online': server_online, 'total': server_total},
            'gpu': {'used': gpu_used, 'total': gpu_total},
            'task': {'running': task_running, 'pending': task_pending},
            'alert_unread': len(anomalies),
            'success_rate': success_rate,
            'task_by_status': task_by_status,
            'server_by_cloud_type': dist('cloud_type'),
            'server_by_owner': dist('owner'),
            'server_by_environment': dist('environment'),
            'recent_tasks': recent,
            'top_alert': top_alert,
        })


def record_ops_log(level, source, message, detail=None, operator=None):
    """记录运维日志（失败不阻塞主流程）"""
    try:
        OpsLog.objects.create(level=level, source=source, message=(message or '')[:255],
                              detail=detail, operator=operator)
    except Exception as e:
        logger.warning('记录运维日志失败: %s' % str(e))


class OpsLogView(APIView):
    """运维日志列表（支持 level / source 筛选）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from utils.pagination import MyPageNumberPagination
        from datetime import datetime
        qs = OpsLog.objects.all()
        level = request.query_params.get('level')
        if level:
            qs = qs.filter(level=level)
        source = request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)
        start = request.query_params.get('start')
        if start:
            try:
                qs = qs.filter(created_at__gte=datetime.strptime(start, '%Y-%m-%d'))
            except Exception:
                pass
        end = request.query_params.get('end')
        if end:
            try:
                qs = qs.filter(created_at__lte=datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            except Exception:
                pass
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [{'id': l.id, 'level': l.level, 'source': l.source, 'message': l.message,
                 'detail': l.detail, 'operator': l.operator,
                 'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S')} for l in page]
        return APIResponse(data=paginator.get_paginated_response(data).data)

class ClusterHealthView(APIView):
    """K8s 集群接入状态：扫描 kube/clusters 并检查连通性（P2-4）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        try:
            configured = k8s_release.list_cluster_configs()
            clusters = k8s_release.check_clusters(list(configured.keys()))
            online = sum(1 for c in clusters if c.get('reachable'))
            return APIResponse(data={
                'clusters': clusters,
                'configured_count': len(configured),
                'online_count': online,
                'expected_count': k8s_release.expected_cluster_count(),
            })
        except Exception as e:
            logger.error('集群状态检查失败: %s' % traceback.format_exc())
            return APIResponse(errcode=5002, errmsg='集群状态检查失败：%s' % str(e)[:200])


def _release_dict(r, with_health_detail=True):
    """发布单统一序列化"""
    health = None
    if with_health_detail and r.health_detail:
        try:
            health = json.loads(r.health_detail)
        except Exception:
            health = {'raw': r.health_detail}
    return {
        'id': r.id, 'release_no': r.release_no, 'app_name': r.app_name, 'env': r.env,
        'namespace': r.namespace, 'cluster': r.cluster, 'image': r.image, 'version': r.version,
        'replicas': r.replicas, 'status': r.status, 'reason': r.reason, 'creator': r.creator,
        'approver': r.approver, 'approver_remark': r.approver_remark,
        'k8s_deployment': r.k8s_deployment or k8s_release.safe_name(r.app_name, 'app'),
        'previous_image': r.previous_image, 'previous_replicas': r.previous_replicas,
        'health_status': r.health_status or 'UNKNOWN', 'health_detail': health,
        'executed_by': r.executed_by, 'duration_ms': r.duration_ms,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else '',
        'approved_at': r.approved_at.strftime('%Y-%m-%d %H:%M:%S') if r.approved_at else '',
        'released_at': r.released_at.strftime('%Y-%m-%d %H:%M:%S') if r.released_at else '',
    }


def _is_full_scope(user):
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin')


def visible_release_qs(user, qs):
    """按角色做数据范围过滤：超级管理员全部；交付主管本组；交付工程师仅自己创建的"""
    if _is_full_scope(user):
        return qs
    role = getattr(user, 'role', '')
    if role == 'lead' and getattr(user, 'department', ''):
        from apps.account.models import User as AccountUser
        names = list(AccountUser.objects.filter(department=user.department).values_list('name', flat=True))
        return qs.filter(creator__in=names)
    return qs.filter(creator=getattr(user, 'name', '') or '')


class ReleaseOrderView(APIView):
    """发布单：GET 列表 / POST 创建"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from utils.pagination import MyPageNumberPagination

        qs = visible_release_qs(request.user, ReleaseOrder.objects.all())
        status_f = request.query_params.get('status')
        if status_f:
            qs = qs.filter(status=status_f)
        env = request.query_params.get('env')
        if env:
            qs = qs.filter(env=env)
        cluster = request.query_params.get('cluster')
        if cluster:
            qs = qs.filter(cluster=cluster)
        kw = (request.query_params.get('keyword') or '').strip()
        if kw:
            from django.db.models import Q
            qs = qs.filter(Q(release_no__contains=kw) | Q(app_name__contains=kw) |
                           Q(image__contains=kw) | Q(cluster__contains=kw) | Q(namespace__contains=kw))
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [_release_dict(r, with_health_detail=False) for r in page]
        return APIResponse(data=paginator.get_paginated_response(data).data)

    def post(self, request, *args, **kwargs):
        import time
        data = request.data
        app_name = (data.get('app_name') or '').strip()
        image = (data.get('image') or '').strip()
        if not app_name or not image:
            return APIResponse(errcode=400, errmsg='应用名和镜像不能为空')
        try:
            replicas = int(data.get('replicas') or 1)
        except Exception:
            return APIResponse(errcode=400, errmsg='副本数必须是整数')
        if replicas < 0:
            return APIResponse(errcode=400, errmsg='副本数不能为负数')
        # 同一秒内多次创建时用自增 id 兜底，避免发布单号冲突
        no = 'REL%s%03d' % (time.strftime('%Y%m%d%H%M%S'), ReleaseOrder.objects.count() % 1000)
        who = getattr(getattr(request, 'user', None), 'name', None) or 'admin'
        while ReleaseOrder.objects.filter(release_no=no).exists():
            no = 'REL%s%03d' % (time.strftime('%Y%m%d%H%M%S'), ReleaseOrder.objects.count() % 1000)
            time.sleep(0.05)
        r = ReleaseOrder.objects.create(
            release_no=no, app_name=app_name, env=data.get('env', 'test'),
            namespace=data.get('namespace', 'default'), cluster=data.get('cluster', 'kind'),
            image=image, version=data.get('version'), replicas=replicas,
            reason=data.get('reason'), creator=who,
            k8s_deployment=k8s_release.safe_name(app_name, 'app'),
        )
        record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                     detail='创建发布单：%s → %s' % (r.app_name, r.image), request=request)
        return APIResponse(data={'id': r.id, 'release_no': r.release_no, 'status': r.status})


class ReleaseOrderDetailView(APIView):
    """发布单详情：基础信息 + K8s 实时状态 + 镜像对比"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, pk, *args, **kwargs):
        r = visible_release_qs(request.user, ReleaseOrder.objects.all()).filter(id=pk).first()
        if not r:
            return APIResponse(errcode=404, errmsg='发布单不存在')
        data = _release_dict(r)
        try:
            data['live'] = k8s_release.state(r)
        except Exception as e:
            logger.warning('读取发布单 K8s 状态失败: %s' % str(e))
            data['live'] = {'available': False, 'error': str(e)[:300], 'pods': []}
        try:
            data['comparison'] = k8s_release.compare(r)
        except Exception as e:
            data['comparison'] = {'error': str(e)[:300]}
        return APIResponse(data=data)


class ReleaseOrderCompareView(APIView):
    """发布前镜像版本对比（当前线上 vs 本次目标）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, pk, *args, **kwargs):
        r = visible_release_qs(request.user, ReleaseOrder.objects.all()).filter(id=pk).first()
        if not r:
            return APIResponse(errcode=404, errmsg='发布单不存在')
        try:
            return APIResponse(data=k8s_release.compare(r))
        except k8s_release.ReleaseError as e:
            return APIResponse(errcode=5002, errmsg=str(e))
        except Exception as e:
            logger.error('镜像对比失败: %s' % traceback.format_exc())
            return APIResponse(errcode=5002, errmsg='镜像对比失败：%s' % str(e)[:200])


class ReleaseOrderLogsView(APIView):
    """查看发布单关联 Pod 日志"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, pk, *args, **kwargs):
        r = visible_release_qs(request.user, ReleaseOrder.objects.all()).filter(id=pk).first()
        if not r:
            return APIResponse(errcode=404, errmsg='发布单不存在')
        try:
            tail = int(request.query_params.get('tail') or 200)
        except Exception:
            tail = 200
        try:
            data = k8s_release.pod_logs(
                r, pod=request.query_params.get('pod'),
                tail=max(min(tail, 2000), 10),
                container=request.query_params.get('container') or None,
            )
            return APIResponse(data=data)
        except k8s_release.ReleaseError as e:
            return APIResponse(errcode=5002, errmsg=str(e))
        except Exception as e:
            logger.error('读取发布日志失败: %s' % traceback.format_exc())
            return APIResponse(errcode=5002, errmsg='读取日志失败：%s' % str(e)[:200])


class ReleaseOrderActionView(APIView):
    """发布单操作：approve / reject / execute / rollback"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, pk, action, *args, **kwargs):
        from django.utils import timezone

        r = visible_release_qs(request.user, ReleaseOrder.objects.all()).filter(id=pk).first()
        if not r:
            return APIResponse(errcode=404, errmsg='发布单不存在')
        who = getattr(getattr(request, 'user', None), 'name', None) or 'admin'
        role = getattr(request.user, 'role', '')
        if action in ('approve', 'reject') and not _is_full_scope(request.user) and role != 'lead':
            return APIResponse(errcode=403, errmsg='只有交付主管 / 超级管理员可以审批发布单')
        if action == 'approve':
            if r.status != 'PENDING':
                return APIResponse(errcode=400, errmsg='只有待审批的发布单可以审批')
            r.status = 'APPROVED'
            r.approver = who
            r.approved_at = timezone.now()
            r.approver_remark = request.data.get('remark', '')
            r.save()
            record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                         detail='审批通过', request=request)
            record_ops_log('INFO', 'workflow', '发布单 %s 审批通过' % r.release_no,
                           detail='应用：%s，镜像：%s' % (r.app_name, r.image), operator=who)
            return APIResponse(data=_release_dict(r, with_health_detail=False))
        if action == 'reject':
            if r.status != 'PENDING':
                return APIResponse(errcode=400, errmsg='只有待审批的发布单可以拒绝')
            r.status = 'REJECTED'
            r.approver = who
            r.approver_remark = request.data.get('remark', '')
            r.save()
            record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                         detail='审批拒绝：%s' % (r.approver_remark or ''), request=request)
            record_ops_log('WARN', 'workflow', '发布单 %s 审批拒绝' % r.release_no,
                           detail=r.approver_remark, operator=who)
            return APIResponse(data=_release_dict(r, with_health_detail=False))
        if action == 'execute':
            if r.status not in ('APPROVED', 'FAILED', 'ROLLED_BACK'):
                return APIResponse(errcode=400, errmsg='只有已审批、发布失败或已回滚的发布单可以发布（当前：%s）'
                                   % RELEASE_STATUS_LABEL.get(r.status, r.status))
            old_status = r.status
            r.status = 'RELEASING'
            r.health_status = 'DEPLOYING'
            r.executed_by = who
            r.save()
            try:
                health = k8s_release.rollout(r)
            except k8s_release.ReleaseError as e:
                health = {'ok': False, 'healthy': False, 'message': str(e), 'pods': [],
                          'deployment': {}, 'comparison': {}, 'duration_ms': 0}
            except Exception as e:
                logger.error('发布执行异常: %s' % traceback.format_exc())
                health = {'ok': False, 'healthy': False, 'message': '发布执行异常：%s' % str(e)[:200],
                          'pods': [], 'deployment': {}, 'comparison': {}, 'duration_ms': 0}
            # 重试失败单时保留最早的上一版本，避免把“本次目标镜像”覆盖成回滚目标
            if health.get('previous_image'):
                if not (old_status == 'FAILED' and r.previous_image):
                    r.previous_image = health['previous_image']
            if health.get('previous_replicas') is not None:
                if not (old_status == 'FAILED' and r.previous_replicas is not None):
                    r.previous_replicas = health['previous_replicas']
            r.k8s_deployment = health.get('deployment_name') or k8s_release.deployment_name(r)
            r.health_status = 'HEALTHY' if health.get('ok') else 'UNHEALTHY'
            r.status = 'RELEASED' if health.get('ok') else 'FAILED'
            r.released_at = timezone.now()
            r.duration_ms = health.get('duration_ms') or 0
            r.health_detail = json.dumps(health, ensure_ascii=False, default=str)
            r.save()
            msg = health.get('message') or ('发布成功' if r.status == 'RELEASED' else '发布失败')
            level = 'INFO' if r.status == 'RELEASED' else 'ERROR'
            action_label = '重新发布' if old_status in ('FAILED', 'ROLLED_BACK') else '发布'
            result_label = action_label + ('成功' if r.status == 'RELEASED' else '失败')
            record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                         detail='%s：%s' % (result_label, msg), request=request)
            record_ops_log(level, 'workflow', '发布单 %s %s' % (r.release_no, result_label),
                           detail='应用：%s，镜像：%s，%s' % (r.app_name, r.image, msg), operator=who)
            return APIResponse(data={
                'id': r.id, 'status': r.status, 'health_status': r.health_status,
                'ok': bool(health.get('ok')), 'message': msg,
                'comparison': health.get('comparison') or {}, 'health': health,
            }, errcode=0 if r.status == 'RELEASED' else 5002,
                errmsg=None if r.status == 'RELEASED' else msg)
        if action == 'restart':
            # 只重启、不改镜像：改完配置/环境变量后让线上应用生效
            if r.status not in ('RELEASED', 'FAILED', 'ROLLED_BACK'):
                return APIResponse(errcode=400, errmsg='只有已发布/发布失败/已回滚的发布单可以重启应用')
            if not _is_full_scope(request.user) and role != 'lead':
                return APIResponse(errcode=403, errmsg='只有交付主管 / 超级管理员可以重启线上应用')
            try:
                info = k8s_release.restart(r)
            except k8s_release.ReleaseError as e:
                record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                             detail='重启失败：%s' % str(e), request=request, result='失败')
                return APIResponse(errcode=5002, errmsg=str(e))
            except Exception as e:
                logger.error('重启应用异常: %s' % traceback.format_exc())
                return APIResponse(errcode=5001, errmsg='重启异常：%s' % str(e)[:200])
            r.health_status = 'HEALTHY' if info.get('healthy') else 'UNHEALTHY'
            r.save(update_fields=['health_status'])
            record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                         detail='重启应用 %s/%s（%s）' % (info['namespace'], info['deployment'],
                                                      '就绪' if info.get('healthy') else '未全部就绪'),
                         request=request)
            record_ops_log('INFO', 'workflow', '发布单 %s 重启应用' % r.release_no,
                           detail='%s/%s %s' % (info['namespace'], info['deployment'], info.get('message') or ''),
                           operator=who)
            return APIResponse(data={'restarted': True, 'deployment': info['deployment'],
                                     'namespace': info['namespace'], 'restarted_at': info['restarted_at'],
                                     'healthy': info.get('healthy'),
                                     'message': info.get('message') or '已触发滚动重启'})
        if action == 'rollback':
            if r.status not in ('RELEASED', 'FAILED'):
                return APIResponse(errcode=400, errmsg='只有已发布/发布失败的发布单可以回滚')
            r.health_status = 'DEPLOYING'
            r.save()
            try:
                health = k8s_release.rollback(r)
            except k8s_release.ReleaseError as e:
                health = {'ok': False, 'healthy': False, 'message': str(e), 'pods': [],
                          'deployment': {}, 'duration_ms': 0}
            except Exception as e:
                logger.error('回滚执行异常: %s' % traceback.format_exc())
                health = {'ok': False, 'healthy': False, 'message': '回滚异常：%s' % str(e)[:200],
                          'pods': [], 'deployment': {}, 'duration_ms': 0}
            r.health_status = 'HEALTHY' if health.get('ok') else 'UNHEALTHY'
            r.status = 'ROLLED_BACK' if health.get('ok') else 'FAILED'
            r.duration_ms = health.get('duration_ms') or 0
            r.health_detail = json.dumps(health, ensure_ascii=False, default=str)
            r.save()
            msg = health.get('message') or ('回滚成功' if r.status == 'ROLLED_BACK' else '回滚失败')
            level = 'INFO' if r.status == 'ROLLED_BACK' else 'ERROR'
            record_audit(who, 'release', resource='发布单 %s' % r.release_no,
                         detail='%s：%s' % (r.status, msg), request=request)
            record_ops_log(level, 'workflow', '发布单 %s %s' % (r.release_no, ('回滚成功' if r.status == 'ROLLED_BACK' else '回滚失败')),
                           detail=msg, operator=who)
            return APIResponse(data={
                'id': r.id, 'status': r.status, 'health_status': r.health_status,
                'ok': bool(health.get('ok')), 'message': msg, 'health': health,
            }, errcode=0 if r.status == 'ROLLED_BACK' else 5002,
                errmsg=None if r.status == 'ROLLED_BACK' else msg)
        return APIResponse(errcode=400, errmsg='未知操作')
