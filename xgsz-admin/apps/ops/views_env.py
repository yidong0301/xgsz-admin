#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境运行配置参数：平台保存 + 真实下发到 K8s（ConfigMap）+ 重启引用它的应用。

不是演示数据：`apply` 会真的写 ConfigMap，并对 spec 里引用了该 ConfigMap 的
Deployment 打 `xgsz.io/restartedAt` 注解触发滚动重启（等价 kubectl rollout restart）。
"""
import logging

from django.utils import timezone
from kubernetes import client
from kubernetes.client.rest import ApiException
from rest_framework.views import APIView

from apps.ops.models import EnvConfig
from apps.ops.views import record_audit
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.k8s_client import apps_v1, core_v1
from utils.permissions import MyPermission

logger = logging.getLogger('default')

CONFIGMAP_NAME = 'xgsz-env-config'
RESTART_ANNOTATION = 'xgsz.io/restartedAt'


def _can_write(user):
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin')


def _who(user):
    return getattr(user, 'name', None) or getattr(user, 'username', None) or ''


def _row(c):
    return {
        'id': c.id, 'env': c.env, 'cluster': c.cluster, 'namespace': c.namespace,
        'key': c.key, 'value': c.value, 'remark': c.remark,
        'updated_by': c.updated_by,
        'updated_at': c.updated_at.strftime('%Y-%m-%d %H:%M:%S') if c.updated_at else '',
    }


def _validate_key(key):
    key = (key or '').strip()
    if not key:
        return None, '配置键不能为空'
    if len(key) > 128:
        return None, '配置键过长（≤128）'
    # ConfigMap 的 key 只允许 [-._a-zA-Z0-9]
    import re
    if not re.match(r'^[-._a-zA-Z0-9]+$', key):
        return None, '配置键只能包含字母、数字、- _ .（ConfigMap 规范）'
    return key, ''


def _references(dep, cm_name):
    """判断 Deployment 是否引用了指定 ConfigMap（envFrom / env.valueFrom / volumes）"""
    spec = (dep.spec.template.spec if dep and dep.spec and dep.spec.template else None)
    if not spec:
        return False
    for c in (spec.containers or []) + (spec.init_containers or []):
        for ef in (c.env_from or []):
            if ef.config_map_ref and ef.config_map_ref.name == cm_name:
                return True
        for env in (c.env or []):
            if env.value_from and env.value_from.config_map_key_ref and \
                    env.value_from.config_map_key_ref.name == cm_name:
                return True
    for v in (spec.volumes or []):
        if v.config_map and v.config_map.name == cm_name:
            return True
    return False


def _restart(apps, name, namespace, ts):
    apps.patch_namespaced_deployment(
        name=name, namespace=namespace,
        body={'spec': {'template': {'metadata': {'annotations': {RESTART_ANNOTATION: ts}}}}},
    )


class EnvConfigView(APIView):
    """GET 列表（按环境/集群/命名空间）/ POST 新增或覆盖一条配置"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        qs = EnvConfig.objects.all()
        env = request.query_params.get('env')
        cluster = request.query_params.get('cluster')
        namespace = request.query_params.get('namespace')
        if env:
            qs = qs.filter(env=env)
        if cluster:
            qs = qs.filter(cluster=cluster)
        if namespace:
            qs = qs.filter(namespace=namespace)
        rows = [_row(c) for c in qs]
        return APIResponse(data={
            'count': len(rows),
            'results': rows,
            'configmap': CONFIGMAP_NAME,
            'envs': [{'value': k, 'label': v} for k, v in EnvConfig.ENV_CHOICES],
        })

    def post(self, request, *args, **kwargs):
        if not _can_write(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可修改环境配置')
        env = (request.data.get('env') or 'dev').strip()
        if env not in dict(EnvConfig.ENV_CHOICES):
            return APIResponse(errcode=400, errmsg='环境不合法：%s' % env)
        cluster = (request.data.get('cluster') or 'kind').strip()
        namespace = (request.data.get('namespace') or 'default').strip()
        key, err = _validate_key(request.data.get('key'))
        if err:
            return APIResponse(errcode=400, errmsg=err)
        value = request.data.get('value')
        value = '' if value is None else str(value)
        remark = (request.data.get('remark') or '')[:256]
        try:
            obj, created = EnvConfig.objects.update_or_create(
                env=env, cluster=cluster, namespace=namespace, key=key,
                defaults={'value': value, 'remark': remark, 'updated_by': _who(request.user)},
            )
        except Exception as e:
            logger.error('保存环境配置失败: %s' % str(e))
            return APIResponse(errcode=5001, errmsg='保存失败：%s' % str(e)[:200])
        record_audit(_who(request.user), 'env-config', resource='环境配置 %s/%s/%s' % (env, cluster, namespace),
                     detail='%s %s：%s' % ('新增' if created else '更新', key, value[:80]), request=request)
        return APIResponse(data=_row(obj))


class EnvConfigDetailView(APIView):
    """PUT 更新单条 / DELETE 删除"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def put(self, request, pk, *args, **kwargs):
        if not _can_write(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可修改环境配置')
        obj = EnvConfig.objects.filter(pk=pk).first()
        if not obj:
            return APIResponse(errcode=404, errmsg='配置不存在')
        if 'value' in request.data:
            obj.value = str(request.data.get('value') or '')
        if 'remark' in request.data:
            obj.remark = (request.data.get('remark') or '')[:256]
        obj.updated_by = _who(request.user)
        obj.save()
        record_audit(_who(request.user), 'env-config', resource='环境配置 %s' % obj.key,
                     detail='更新值：%s' % obj.value[:80], request=request)
        return APIResponse(data=_row(obj))

    def delete(self, request, pk, *args, **kwargs):
        if not _can_write(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可修改环境配置')
        obj = EnvConfig.objects.filter(pk=pk).first()
        if not obj:
            return APIResponse(errcode=404, errmsg='配置不存在')
        record_audit(_who(request.user), 'env-config', resource='环境配置 %s' % obj.key, detail='删除', request=request)
        obj.delete()
        return APIResponse(data={'deleted': True})


class EnvConfigApplyView(APIView):
    """POST 把当前环境的配置真实下发到 K8s：写 ConfigMap → 重启引用它的 Deployment"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _can_write(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可下发配置')
        env = (request.data.get('env') or 'dev').strip()
        cluster = (request.data.get('cluster') or 'kind').strip()
        namespace = (request.data.get('namespace') or 'default').strip()
        restart = request.data.get('restart', True) not in (False, 'false', 0, '0')

        rows = list(EnvConfig.objects.filter(env=env, cluster=cluster, namespace=namespace))
        if not rows:
            return APIResponse(errcode=400, errmsg='当前环境还没有配置项，先添加再下发')
        data = {r.key: (r.value or '') for r in rows}

        try:
            core = core_v1(cluster)
            body = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=CONFIGMAP_NAME, namespace=namespace,
                                             labels={'app.kubernetes.io/managed-by': 'xgsz-admin'}),
                data=data,
            )
            try:
                core.read_namespaced_config_map(CONFIGMAP_NAME, namespace)
                core.replace_namespaced_config_map(CONFIGMAP_NAME, namespace, body)
                action = '更新'
            except ApiException as e:
                if e.status != 404:
                    raise
                core.create_namespaced_config_map(namespace, body)
                action = '创建'

            restarted, skipped, failed = [], [], []
            if restart:
                apps = apps_v1(cluster)
                ts = timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ')
                for dep in apps.list_namespaced_deployment(namespace).items:
                    name = dep.metadata.name
                    if not _references(dep, CONFIGMAP_NAME):
                        skipped.append(name)
                        continue
                    try:
                        _restart(apps, name, namespace, ts)
                        restarted.append(name)
                    except Exception as e:
                        failed.append({'name': name, 'error': str(e)[:160]})
        except Exception as e:
            logger.error('下发环境配置失败: %s' % str(e))
            return APIResponse(errcode=5001, errmsg='下发失败：%s' % str(e)[:200])

        msg = '%s ConfigMap %s/%s（%d 个键）' % (action, namespace, CONFIGMAP_NAME, len(data))
        if restart:
            msg += '；重启应用 %d 个' % len(restarted)
            if not restarted:
                msg += '（该命名空间没有引用它的应用，配置已写入但不会自动生效）'
        record_audit(_who(request.user), 'env-config-apply', resource='环境配置 %s/%s' % (env, namespace),
                     detail=msg, request=request)
        try:
            from apps.ops.views import record_ops_log
            record_ops_log('INFO', 'workflow', '下发环境配置 %s/%s' % (env, namespace),
                           detail=msg, operator=_who(request.user))
        except Exception:
            pass
        return APIResponse(data={
            'configmap': CONFIGMAP_NAME, 'namespace': namespace, 'cluster': cluster,
            'keys': len(data), 'action': action,
            'restarted': restarted, 'skipped': skipped, 'failed': failed,
            'message': msg,
        })
