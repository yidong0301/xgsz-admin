#!/bin/env python3
# -*- coding: utf-8 -*-

import logging
import random
import traceback
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from rest_framework.views import APIView

from apps.cmdb.models import (Server, GPUNode, K8sCluster, NetworkSwitch, OpticalModule,
                              AssetChangeLog, AssetRelation)
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission
from utils.pagination import MyPageNumberPagination

logger = logging.getLogger('default')

# 资产类型注册表：type -> 模型/编号前缀
ASSET_TYPES = {
    'server': {'model': Server, 'prefix': 'SRV'},
    'gpu_node': {'model': GPUNode, 'prefix': 'GPU'},
    'k8s_cluster': {'model': K8sCluster, 'prefix': 'K8S'},
    'switch': {'model': NetworkSwitch, 'prefix': 'SW'},
    'optical_module': {'model': OpticalModule, 'prefix': 'OM'},
}

COMMON_FIELDS = ['asset_no', 'name', 'owner', 'department', 'tags', 'location', 'status',
                 'purchase_date', 'warranty_expire', 'remark']

TYPE_FIELDS = {
    'server': ['instance_id', 'hostname', 'private_ip', 'public_ip', 'cpu', 'memory', 'os_name', 'cloud_type', 'environment'],
    'gpu_node': ['ip', 'gpu_model', 'gpu_count', 'gpu_memory', 'cpu', 'memory', 'os_name'],
    'k8s_cluster': ['api_server', 'version', 'node_count'],
    'switch': ['ip', 'model', 'port_count'],
    'optical_module': ['module_type', 'rate', 'wavelength'],
}


def generate_asset_no(prefix):
    return '%s-%s-%04d' % (prefix, datetime.now().strftime('%Y%m%d%H%M%S'), random.randint(0, 9999))


def serialize_asset(obj, asset_type):
    """把资产对象序列化为 dict（通用字段 + 类型特有字段 + id）"""
    d = {'id': obj.pk, 'asset_type': asset_type}
    for f in COMMON_FIELDS:
        v = getattr(obj, f, None)
        if hasattr(v, 'isoformat'):
            v = v.isoformat()
        d[f] = v
    # 服务器：资产编号/名称缺失时用 instance_id/hostname 兜底，避免前端显示 "-"
    if asset_type == 'server':
        if not d.get('asset_no'):
            d['asset_no'] = getattr(obj, 'instance_id', None)
        if not d.get('name'):
            d['name'] = getattr(obj, 'hostname', None)
    for f in TYPE_FIELDS.get(asset_type, []):
        v = getattr(obj, f, None)
        if hasattr(v, 'isoformat'):
            v = v.isoformat()
        d[f] = v
    d['created_at'] = obj.created_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(obj, 'created_at', None) else ''
    d['updated_at'] = obj.updated_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(obj, 'updated_at', None) else ''
    return d


def record_change(asset_type, asset_id, asset_no, change_type, operator, field=None, old=None, new=None):
    try:
        AssetChangeLog.objects.create(
            asset_type=asset_type, asset_id=str(asset_id), asset_no=asset_no,
            change_type=change_type, field=field, old_value=old, new_value=new, operator=operator)
    except Exception as e:
        logger.warning('记录资产变更失败: %s' % str(e))


def _get_model(asset_type):
    info = ASSET_TYPES.get(asset_type)
    return info['model'] if info else None


def _build_kwargs(asset_type, data):
    """从请求数据中提取该资产类型可用且模型真实存在的字段"""
    allowed = COMMON_FIELDS + TYPE_FIELDS.get(asset_type, [])
    model = _get_model(asset_type)
    model_fields = {f.name for f in model._meta.get_fields()} if model else set()
    kwargs = {}
    for k, v in data.items():
        if k in allowed and k in model_fields and v is not None and k not in ('id', 'asset_no', 'created_at', 'updated_at'):
            kwargs[k] = v
    return kwargs


def _can_write_asset(user):
    """只有超级管理员可以新增/修改/删除资产；交付主管和工程师只读"""
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin')


class AssetView(APIView):
    """
    统一资产：GET 列表(按类型) / POST 录入
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        asset_type = request.query_params.get('type', 'server')
        model = _get_model(asset_type)
        if not model:
            return APIResponse(errcode=400, errmsg='未知资产类型: %s' % asset_type)
        search = request.query_params.get('keyword')
        qs = model.objects.all()
        if search:
            from django.db.models import Q
            # 只对模型实际存在的字段做模糊搜索，避免 FieldError（如 server 没有 name 字段）
            candidates = ['name', 'hostname', 'asset_no', 'owner', 'tags', 'location',
                          'department', 'private_ip', 'public_ip', 'ip', 'gpu_model',
                          'cloud_type', 'environment', 'model', 'module_type', 'rate']
            model_fields = {f.name for f in model._meta.get_fields()}
            q = Q()
            for f in candidates:
                if f in model_fields:
                    q |= Q(**{f + '__icontains': search})
            if q:
                qs = qs.filter(q)
        status_f = request.query_params.get('status')
        if status_f:
            qs = qs.filter(status=status_f)
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [serialize_asset(o, asset_type) for o in page]
        resp = paginator.get_paginated_response(data).data
        try:
            from django.db.models import Count
            st_rows = model.objects.order_by().values('status').annotate(c=Count('pk'))
            resp['stats'] = {str(s['status']): s['c'] for s in st_rows}
            resp['type_total'] = model.objects.count()
        except Exception:
            resp['stats'] = {}
            resp['type_total'] = 0
        return APIResponse(data=resp)

    def post(self, request, *args, **kwargs):
        if not _can_write_asset(request.user):
            return APIResponse(errcode=403, errmsg='当前角色不能新增资产（仅超级管理员可录入）')
        asset_type = request.data.get('asset_type') or request.data.get('type') or 'server'
        info = ASSET_TYPES.get(asset_type)
        if not info:
            return APIResponse(errcode=400, errmsg='未知资产类型: %s' % asset_type)
        model = info['model']
        kwargs = _build_kwargs(asset_type, request.data)
        model_fields = {f.name for f in model._meta.get_fields()}
        display_name = (request.data.get('name') or '').strip()
        # Server 没有 name 字段，主键是 instance_id（由阿里云实例 ID 或自动生成）
        if 'name' in model_fields:
            kwargs['name'] = kwargs.get('name') or display_name or ('%s-未命名' % asset_type)
        if asset_type == 'server':
            if not kwargs.get('instance_id'):
                kwargs['instance_id'] = request.data.get('instance_id') or generate_asset_no('SRV')
            if not kwargs.get('hostname'):
                kwargs['hostname'] = display_name or kwargs['instance_id']
        if not kwargs.get('asset_no'):
            kwargs['asset_no'] = generate_asset_no(info['prefix'])
        try:
            obj = model.objects.create(**kwargs)
            record_change(asset_type, obj.pk, obj.asset_no, 'create', getattr(request.user, 'name', None),
                          old=None, new='创建资产')
            return APIResponse(data=serialize_asset(obj, asset_type))
        except Exception as e:
            logger.error('创建资产失败: %s' % traceback.format_exc())
            return APIResponse(errcode=500, errmsg='创建资产失败: %s' % str(e))


class AssetDetailView(APIView):
    """
    统一资产：GET 详情 / PUT 更新 / DELETE 删除（变更留痕）
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def _get_obj(self, asset_type, pk):
        model = _get_model(asset_type)
        if not model:
            return None, None
        return model.objects.filter(pk=pk).first(), model

    def get(self, request, *args, **kwargs):
        obj, _ = self._get_obj(kwargs.get('type'), kwargs.get('pk'))
        if not obj:
            return APIResponse(errcode=404, errmsg='资产不存在')
        return APIResponse(data=serialize_asset(obj, kwargs.get('type')))

    def put(self, request, *args, **kwargs):
        if not _can_write_asset(request.user):
            return APIResponse(errcode=403, errmsg='当前角色不能修改资产（仅超级管理员可编辑）')
        asset_type = kwargs.get('type')
        obj, model = self._get_obj(asset_type, kwargs.get('pk'))
        if not obj:
            return APIResponse(errcode=404, errmsg='资产不存在')
        kwargs_data = _build_kwargs(asset_type, request.data)
        changes = []
        for k, v in kwargs_data.items():
            old = getattr(obj, k, None)
            if str(old) != str(v):
                changes.append((k, str(old), str(v)))
                setattr(obj, k, v)
        try:
            obj.save()
            for field, old, new in changes:
                record_change(asset_type, obj.pk, obj.asset_no, 'update', getattr(request.user, 'name', None),
                              field=field, old=old, new=new)
            return APIResponse(data=serialize_asset(obj, asset_type))
        except Exception as e:
            logger.error('更新资产失败: %s' % traceback.format_exc())
            return APIResponse(errcode=500, errmsg='更新资产失败: %s' % str(e))

    def delete(self, request, *args, **kwargs):
        if not _can_write_asset(request.user):
            return APIResponse(errcode=403, errmsg='当前角色不能删除资产（仅超级管理员可删除）')
        asset_type = kwargs.get('type')
        obj, _ = self._get_obj(asset_type, kwargs.get('pk'))
        if not obj:
            return APIResponse(errcode=404, errmsg='资产不存在')
        asset_id, asset_no = obj.pk, obj.asset_no
        try:
            # 资产删除时清理它参与的关系，避免拓扑里出现悬空边
            AssetRelation.objects.filter(
                Q(source_type=asset_type, source_id=str(asset_id)) |
                Q(target_type=asset_type, target_id=str(asset_id))).delete()
            obj.delete()
            record_change(asset_type, asset_id, asset_no, 'delete', getattr(request.user, 'name', None),
                          old='删除资产', new=None)
            return APIResponse(data={'deleted': True})
        except Exception as e:
            logger.error('删除资产失败: %s' % traceback.format_exc())
            return APIResponse(errcode=500, errmsg='删除资产失败: %s' % str(e))


class AssetImportView(APIView):
    """
    批量导入：POST 一个资产数组 [{asset_type, name, ...}, ...]
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _can_write_asset(request.user):
            return APIResponse(errcode=403, errmsg='当前角色不能导入资产（仅超级管理员可导入）')
        items = request.data.get('assets', request.data if isinstance(request.data, list) else [])
        if not items:
            return APIResponse(errcode=400, errmsg='缺少导入数据')
        created = 0
        errors = []
        operator = getattr(request.user, 'name', None)
        try:
            with transaction.atomic():
                for item in items:
                    asset_type = item.get('asset_type') or item.get('type') or 'server'
                    info = ASSET_TYPES.get(asset_type)
                    if not info:
                        errors.append('未知类型: %s' % asset_type)
                        continue
                    model = info['model']
                    kwargs = _build_kwargs(asset_type, item)
                    model_fields = {f.name for f in model._meta.get_fields()}
                    display_name = (item.get('name') or '').strip()
                    if 'name' in model_fields:
                        kwargs['name'] = kwargs.get('name') or display_name or ('%s-未命名' % asset_type)
                    if asset_type == 'server':
                        if not kwargs.get('instance_id'):
                            kwargs['instance_id'] = item.get('instance_id') or generate_asset_no('SRV')
                        if not kwargs.get('hostname'):
                            kwargs['hostname'] = display_name or kwargs['instance_id']
                    if not kwargs.get('asset_no'):
                        kwargs['asset_no'] = generate_asset_no(info['prefix'])
                    obj = model.objects.create(**kwargs)
                    record_change(asset_type, obj.pk, obj.asset_no, 'create', operator, old=None, new='批量导入')
                    created += 1
        except Exception as e:
            logger.error('批量导入失败: %s' % traceback.format_exc())
            return APIResponse(errcode=500, errmsg='批量导入失败: %s' % str(e))
        return APIResponse(data={'created': created, 'errors': errors})


class AssetChangeLogView(APIView):
    """
    资产变更记录：GET 按资产类型/ID 查询留痕
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        asset_type = request.query_params.get('type')
        asset_id = request.query_params.get('id')
        qs = AssetChangeLog.objects.all()
        if asset_type:
            qs = qs.filter(asset_type=asset_type)
        if asset_id:
            qs = qs.filter(asset_id=asset_id)
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [{
            'id': c.id, 'asset_type': c.asset_type, 'asset_id': c.asset_id, 'asset_no': c.asset_no,
            'change_type': c.change_type, 'field': c.field, 'old_value': c.old_value,
            'new_value': c.new_value, 'operator': c.operator,
            'changed_at': c.changed_at.strftime('%Y-%m-%d %H:%M:%S'),
        } for c in page]
        return APIResponse(data=paginator.get_paginated_response(data).data)


class AssetStatsView(APIView):
    """
    资产统计：按类型统计数量 + 按状态统计
    """
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        by_type = {}
        total = 0
        for asset_type, info in ASSET_TYPES.items():
            count = info['model'].objects.count()
            by_type[asset_type] = count
            total += count
        # 按状态统计（仅对继承 BaseAsset 的类型）
        by_status = {}
        for asset_type, info in ASSET_TYPES.items():
            if asset_type == 'server':
                continue
            for row in info['model'].objects.values('status').order_by():
                st = row['status'] or 'unknown'
                by_status[st] = by_status.get(st, 0) + 1
        return APIResponse(data={'total': total, 'by_type': by_type, 'by_status': by_status})
