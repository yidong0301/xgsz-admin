#!/bin/env python3
# -*- coding: utf-8 -*-

import logging

from django.db import connection
from django.utils import timezone
from django_redis import get_redis_connection
from rest_framework.views import APIView

from apps.cmdb.models import Server
from apps.k8s.models import InferenceTask
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission

logger = logging.getLogger('default')


def _check_component_with_retry(name, check_fn, retries=2):
    """
    组件检查 + 自动纠错：失败后自动重试，重试成功视为"自动纠错"恢复
    返回 (status, detail, auto_fixed)
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            check_fn()
            return ('ok', '连接正常' if attempt == 0 else '自动纠错恢复（重试 %d 次后正常）' % attempt, attempt > 0)
        except Exception as e:
            last_err = e
    return ('error', str(last_err)[:200], False)


def _user_label(request):
    """通知已读按用户隔离：优先登录名（唯一），其次显示名"""
    user = getattr(request, 'user', None)
    label = getattr(user, 'username', '') or getattr(user, 'name', '')
    return (label or 'admin')[:64]


def _with_read_state(request, data):
    """给告警列表注入当前用户的已读状态，并返回未读数量"""
    from apps.ops.models import NotificationRead
    alerts = [dict(a) for a in (data.get('alerts') or [])]
    keys = [a.get('key') for a in alerts if a.get('key')]
    read_keys = set()
    if keys:
        read_keys = set(NotificationRead.objects.filter(
            user=_user_label(request), alert_key__in=keys,
        ).values_list('alert_key', flat=True))
    for a in alerts:
        a['read'] = a.get('key') in read_keys
    data = dict(data)
    data['alerts'] = alerts
    data['unread'] = sum(1 for a in alerts if not a['read'])
    return data


class AlertView(APIView):
    """
    告警中心 + 自检自动纠错：聚合 组件/任务/服务器 告警，组件检查自动重试纠错
    """

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from django.core.cache import cache
        _cache_key = 'xgsz_alerts_v1'
        cached = cache.get(_cache_key)
        if cached is not None:
            return APIResponse(data=_with_read_state(request, cached))

        alerts = []
        auto_fixed = 0

        # 1. 组件告警（带自动纠错重试）
        components = {}

        def _mysql():
            with connection.cursor() as c:
                c.execute("SELECT 1")
                c.fetchone()
        st, dt, fixed = _check_component_with_retry('mysql', _mysql)
        components['mysql'] = {'status': st, 'detail': dt}
        if fixed:
            auto_fixed += 1

        def _redis():
            get_redis_connection('default').ping()
        st, dt, fixed = _check_component_with_retry('redis', _redis)
        components['redis'] = {'status': st, 'detail': dt}
        if fixed:
            auto_fixed += 1

        def _mongo():
            import pymongo
            from decouple import config
            c = pymongo.MongoClient(host=config('MONGO_HOST'), port=int(config('MONGO_PORT')), serverSelectionTimeoutMS=2000)
            c.admin.command('ping')
        st, dt, fixed = _check_component_with_retry('mongodb', _mongo)
        components['mongodb'] = {'status': st, 'detail': dt}
        if fixed:
            auto_fixed += 1

        def _k8s():
            from kubernetes import config as kconfig, client as kclient
            kconfig.load_kube_config(config_file=None)
            kclient.CoreV1Api().list_namespace(limit=1)
        st, dt, fixed = _check_component_with_retry('k8s', _k8s)
        components['k8s'] = {'status': st, 'detail': dt}
        if fixed:
            auto_fixed += 1

        def _celery():
            from xgsz_admin.celery import app as celery_app
            insp = celery_app.control.inspect(timeout=1)
            if not insp.ping():
                raise RuntimeError('无 worker 响应')
        st, dt, fixed = _check_component_with_retry('celery', _celery, retries=1)
        components['celery'] = {'status': st, 'detail': dt}
        if fixed:
            auto_fixed += 1

        for name, c in components.items():
            if c['status'] != 'ok':
                alerts.append({
                    'level': 'error',
                    'type': 'component',
                    'title': '组件异常：%s' % name,
                    'detail': c['detail'],
                    'time': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                })

        # 2. 任务告警（失败/提交失败）
        failed_tasks = InferenceTask.objects.filter(status__in=['SUBMIT_ERROR', 'FAILED'])
        STATUS_CN = {'FAILED': '已失败', 'SUBMIT_ERROR': '提交失败', 'RUNNING': '运行中',
                     'SUCCEEDED': '已成功', 'PENDING': '排队中', 'SUBMITTED': '已提交',
                     'STOPPED': '已停止'}
        for t in failed_tasks:
            err = (t.error_msg or '') + ' ' + (t.failure_reason or '')
            err = err.strip()
            if 'no command specified' in err:
                detail = '镜像没有默认启动命令，且任务未填写命令（请填「命令」或换带 CMD 的镜像）'
            elif 'CreateContainerError' in err or 'CreateContainerConfigError' in err:
                detail = '容器创建失败（请检查镜像、命令与配置）'
            elif 'ImagePullBackOff' in err or 'ErrImagePull' in err:
                detail = '镜像拉取失败（请检查镜像地址与拉取密钥）'
            elif 'CrashLoopBackOff' in err:
                detail = '容器反复退出（请查看任务日志与事件）'
            elif '422' in err or 'Unprocessable' in err:
                detail = 'K8s 拒绝了任务配置（请检查镜像地址 / 任务名称）'
            elif 'kubeconfig' in err or 'K8s 集群' in err:
                detail = 'K8s 集群连接异常（请检查 kubeconfig）'
            elif err:
                detail = err[:50] + ('…' if len(err) > 50 else '')
            else:
                detail = '状态：%s' % STATUS_CN.get(t.status, t.status)
            alerts.append({
                'level': 'error',
                'type': 'task',
                'title': '推理任务失败：%s' % t.name,
                'detail': detail,
                'time': t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else '',
            })

        # 3. 服务器告警（已停机）
        stopped = Server.objects.filter(status='Stopped')
        for s in stopped:
            ts = ''
            for attr in ('create_time', 'updated_at', 'created_at', 'purchase_date'):
                v = getattr(s, attr, None)
                if not v:
                    continue
                try:
                    ts = v.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    ts = str(v)[:19]
                if ts:
                    break
            alerts.append({
                'level': 'warning',
                'type': 'server',
                'title': '服务器已停机：%s' % (s.hostname or s.instance_id),
                'detail': '负责人：%s' % (s.owner or '未指定'),
                'time': ts,
            })

        # 4. 告警状态机：注入认领/关闭状态，已关闭的不再展示
        import hashlib
        from apps.ops.models import AlertState
        for a in alerts:
            raw = '%s|%s' % (a.get('type', ''), a.get('title', ''))
            a['key'] = hashlib.md5(raw.encode('utf-8')).hexdigest()[:32]
        keys = [a['key'] for a in alerts]
        states = {s.alert_key: s for s in AlertState.objects.filter(alert_key__in=keys)}
        active = []
        for a in alerts:
            st = states.get(a['key'])
            a['state'] = st.status if st else 'OPEN'
            a['claimed_by'] = (st.claimed_by or '') if st else ''
            a['claimed_at'] = st.claimed_at.strftime('%Y-%m-%d %H:%M:%S') if st and st.claimed_at else ''
            a['closed_by'] = (st.closed_by or '') if st else ''
            a['note'] = (st.note or '') if st else ''
            if a['state'] != 'CLOSED':
                active.append(a)
        alerts = active

        ok_count = sum(1 for c in components.values() if c['status'] == 'ok')
        data = {
            'total': len(alerts),
            'auto_fixed': auto_fixed,
            'components': components,
            'components_ok': ok_count,
            'components_total': len(components),
            'alerts': alerts,
        }
        try:
            cache.set(_cache_key, data, 5)
        except Exception:
            pass
        return APIResponse(data=_with_read_state(request, data))


class AlertReadView(APIView):
    """标记通知已读（按用户记录）：未读红点、已读绿点，全部已读后铃铛不亮红点"""

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        from apps.ops.models import NotificationRead
        raw = request.data.get('keys') or []
        if isinstance(raw, str):
            raw = [raw]
        keys = []
        for item in raw:
            key = str(item or '').strip()
            if key and key not in keys:
                keys.append(key)
        keys = keys[:500]
        if not keys:
            return APIResponse(errcode=400, errmsg='缺少通知 key')
        who = _user_label(request)
        exists = set(NotificationRead.objects.filter(
            user=who, alert_key__in=keys,
        ).values_list('alert_key', flat=True))
        pending = [NotificationRead(user=who, alert_key=k) for k in keys if k not in exists]
        if pending:
            NotificationRead.objects.bulk_create(pending, ignore_conflicts=True)
        return APIResponse(data={'marked': len(pending), 'already': len(exists)})


class AlertClaimView(APIView):
    """认领告警：OPEN -> ACKED（认领即锁定，其他人不能再关）"""

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        from apps.ops.models import AlertState
        from apps.ops.views import record_audit
        key = (request.data.get('key') or '').strip()
        title = (request.data.get('title') or '').strip()
        if not key:
            return APIResponse(errcode=400, errmsg='缺少告警 key')
        who = getattr(request.user, 'name', None) or 'admin'
        st = AlertState.objects.filter(alert_key=key).first()
        if st and st.status == 'CLOSED':
            return APIResponse(errcode=400, errmsg='该告警已关闭，不能重复认领')
        if st and st.status == 'ACKED' and st.claimed_by and st.claimed_by != who:
            return APIResponse(errcode=400, errmsg='该告警已被 %s 认领锁定' % st.claimed_by)
        if not st:
            st = AlertState(alert_key=key, title=title[:256] or key)
        st.title = title[:256] or st.title
        st.status = 'ACKED'
        st.claimed_by = who
        st.claimed_at = timezone.now()
        st.save()
        record_audit(who, 'alert', resource='告警认领：%s' % st.title, detail='状态 OPEN → ACKED')
        return APIResponse(data={'status': 'ACKED', 'claimed_by': who})


class AlertCloseView(APIView):
    """关闭告警：ACKED -> CLOSED，必须填写处理结果（填单关闭）"""

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        from apps.ops.models import AlertState
        from apps.ops.views import record_audit
        key = (request.data.get('key') or '').strip()
        note = (request.data.get('note') or '').strip()
        if not key:
            return APIResponse(errcode=400, errmsg='缺少告警 key')
        if not note:
            return APIResponse(errcode=400, errmsg='关闭告警必须填写处理结果')
        st = AlertState.objects.filter(alert_key=key).first()
        if not st or st.status != 'ACKED':
            return APIResponse(errcode=400, errmsg='请先认领告警，再关闭')
        who = getattr(request.user, 'name', None) or 'admin'
        if st.claimed_by and st.claimed_by != who:
            return APIResponse(errcode=400, errmsg='该告警由 %s 认领，需本人关闭' % st.claimed_by)
        st.status = 'CLOSED'
        st.closed_by = who
        st.closed_at = timezone.now()
        st.note = note[:2000]
        st.save()
        # 关闭后通知从列表移除；清掉已读记录，避免同名告警再次出现时误判为已读
        from apps.ops.models import NotificationRead
        NotificationRead.objects.filter(alert_key=key).delete()
        record_audit(who, 'alert', resource='告警关闭：%s' % st.title,
                     detail='处理结果：%s' % note[:200])
        return APIResponse(data={'status': 'CLOSED', 'note': st.note})
