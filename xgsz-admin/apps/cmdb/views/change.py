#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资产变更申请单：提交 → 审批 → 执行 → 留痕。

- 提交：管理员 / 交付主管；只能改「模型真实存在且非主键」的字段
- 审批 / 执行：管理员；执行时逐字段写入并记 AssetChangeLog
- 状态机：PENDING → APPROVED/REJECTED；APPROVED → EXECUTED；PENDING → CANCELED
"""
import json
import logging
import random
from datetime import datetime

from django.core.exceptions import FieldDoesNotExist
from django.db import models as dj_models
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView

from apps.cmdb.models import (AssetChangeRequest, CHANGE_REQUEST_STATUS, Server, GPUNode,
                              K8sCluster, NetworkSwitch, OpticalModule)
from apps.cmdb.views.asset import ASSET_TYPES, record_change
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.pagination import MyPageNumberPagination
from utils.permissions import MyPermission

logger = logging.getLogger('default')

MODELS = {
    'server': Server,
    'gpu_node': GPUNode,
    'k8s_cluster': K8sCluster,
    'switch': NetworkSwitch,
    'optical_module': OpticalModule,
}
STATUS_LABEL = dict(CHANGE_REQUEST_STATUS)
CHANGE_TYPES = {'update': '变更字段'}

# 不允许通过变更单改的字段
PROTECTED_FIELDS = {'id', 'pk', 'instance_id', 'asset_no', 'created_at', 'updated_at'}


def _can_submit(user):
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin', 'lead')


def _can_approve(user):
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin')


def _user_name(user):
    return getattr(user, 'name', None) or getattr(user, 'username', None) or ''


def _audit(user, action, detail, result='成功'):
    try:
        from apps.ops.views import record_audit
        record_audit(_user_name(user), action, resource='asset-change', detail=detail, result=result)
    except Exception:
        pass


def _get_asset(asset_type, asset_id):
    model = MODELS.get(asset_type)
    if not model or asset_id in (None, ''):
        return None, None
    try:
        return model.objects.filter(pk=asset_id).first(), model
    except Exception:
        return None, model


def _asset_title(obj):
    return getattr(obj, 'hostname', None) or getattr(obj, 'name', None) or str(obj.pk)


def _time(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else ''


def _row(r):
    try:
        payload = json.loads(r.payload or '{}')
    except Exception:
        payload = {}
    return {
        'id': r.id,
        'request_no': r.request_no,
        'asset_type': r.asset_type,
        'asset_id': r.asset_id,
        'asset_no': r.asset_no,
        'asset_name': r.asset_name,
        'title': r.title,
        'change_type': r.change_type,
        'payload': payload,
        'reason': r.reason,
        'status': r.status,
        'status_label': STATUS_LABEL.get(r.status, r.status),
        'creator': r.creator,
        'approver': r.approver,
        'approve_comment': r.approve_comment,
        'result': r.result,
        'created_at': _time(r.created_at),
        'approved_at': _time(r.approved_at),
        'executed_at': _time(r.executed_at),
    }


def _validate_payload(model, payload):
    """返回 (清洗后的 payload, 错误列表)"""
    if not isinstance(payload, dict) or not payload:
        return {}, ['变更内容不能为空（对象：字段 -> 新值）']
    clean, errors = {}, []
    for k, v in payload.items():
        k = str(k).strip()
        if not k or k in PROTECTED_FIELDS:
            errors.append('字段不可修改：%s' % k)
            continue
        try:
            field = model._meta.get_field(k)
        except FieldDoesNotExist:
            errors.append('字段不存在：%s' % k)
            continue
        if field.primary_key or not getattr(field, 'concrete', True):
            errors.append('字段不可修改：%s' % k)
            continue
        clean[k] = v
    return clean, errors


def _cast(field, value):
    if value is None or value == '':
        return None if field.null else ''
    try:
        if isinstance(field, dj_models.BooleanField):
            return str(value).lower() in ('1', 'true', 'yes', 'on', '是')
        if isinstance(field, dj_models.IntegerField):
            return int(float(value))
        if isinstance(field, dj_models.DecimalField):
            return value
        if isinstance(field, dj_models.DateField):
            return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError('字段 %s 的值不合法：%s' % (getattr(field, 'name', ''), value))
    return str(value)


class ChangeRequestView(APIView):
    """GET 列表 / POST 提交变更申请"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        qs = AssetChangeRequest.objects.all()
        status = request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        asset_type = request.query_params.get('asset_type')
        if asset_type:
            qs = qs.filter(asset_type=asset_type)
        asset_id = request.query_params.get('asset_id')
        if asset_id:
            qs = qs.filter(asset_id=asset_id)
        keyword = request.query_params.get('keyword')
        if keyword:
            from django.db.models import Q
            qs = qs.filter(Q(request_no__contains=keyword) | Q(title__contains=keyword) |
                           Q(asset_name__contains=keyword))
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = paginator.get_paginated_response([_row(r) for r in page]).data
        data['pending_count'] = AssetChangeRequest.objects.filter(status='PENDING').count()
        return APIResponse(data=data)

    def post(self, request, *args, **kwargs):
        if not _can_submit(request.user):
            return APIResponse(errcode=403, errmsg='当前角色不能提交变更申请（管理员 / 交付主管可提交）')
        asset_type = (request.data.get('asset_type') or '').strip()
        asset_id = str(request.data.get('asset_id') or '').strip()
        title = (request.data.get('title') or '').strip()[:128]
        change_type = (request.data.get('change_type') or 'update').strip()
        reason = (request.data.get('reason') or '')[:2000]
        payload = request.data.get('payload')

        if asset_type not in MODELS:
            return APIResponse(errcode=400, errmsg='资产类型不合法：%s' % asset_type)
        if not title:
            return APIResponse(errcode=400, errmsg='缺少变更标题')
        if change_type not in CHANGE_TYPES:
            return APIResponse(errcode=400, errmsg='变更类型不合法：%s' % change_type)
        obj, model = _get_asset(asset_type, asset_id)
        if not obj:
            return APIResponse(errcode=404, errmsg='资产不存在：%s/%s' % (asset_type, asset_id))

        clean, errors = _validate_payload(model, payload)
        if errors:
            return APIResponse(errcode=400, errmsg='；'.join(errors[:5]))

        request_no = None
        for _ in range(5):
            candidate = 'CR-%s-%04d' % (timezone.now().strftime('%Y%m%d%H%M%S'), random.randint(0, 9999))
            if not AssetChangeRequest.objects.filter(request_no=candidate).exists():
                request_no = candidate
                break
        if not request_no:
            return APIResponse(errcode=5001, errmsg='申请单号生成失败，请重试')

        rec = AssetChangeRequest.objects.create(
            request_no=request_no, asset_type=asset_type, asset_id=asset_id,
            asset_no=getattr(obj, 'asset_no', None) or getattr(obj, 'instance_id', None),
            asset_name=_asset_title(obj), title=title, change_type=change_type,
            payload=json.dumps(clean, ensure_ascii=False, default=str),
            reason=reason, creator=_user_name(request.user),
        )
        _audit(request.user, 'change-request-create', '%s %s:%s %s' % (request_no, asset_type, asset_id, title))
        return APIResponse(data=_row(rec))


class ChangeRequestDetailView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, pk, *args, **kwargs):
        rec = AssetChangeRequest.objects.filter(pk=pk).first()
        if not rec:
            return APIResponse(errcode=404, errmsg='申请单不存在')
        return APIResponse(data=_row(rec))


class ChangeRequestActionView(APIView):
    """POST {action: approve|reject|execute|cancel, comment: ''}"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, pk, *args, **kwargs):
        rec = AssetChangeRequest.objects.filter(pk=pk).first()
        if not rec:
            return APIResponse(errcode=404, errmsg='申请单不存在')
        action = (request.data.get('action') or '').strip()
        comment = (request.data.get('comment') or '')[:2000]
        operator = _user_name(request.user)

        if action in ('approve', 'reject', 'execute') and not _can_approve(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可审批或执行')
        if action == 'cancel' and not (_can_approve(request.user) or rec.creator == operator):
            return APIResponse(errcode=403, errmsg='只有申请人本人或管理员可撤销')

        if action in ('approve', 'reject'):
            if rec.status != 'PENDING':
                return APIResponse(errcode=4090, errmsg='当前状态（%s）不能审批' % STATUS_LABEL.get(rec.status))
            rec.status = 'APPROVED' if action == 'approve' else 'REJECTED'
            rec.approver = operator
            rec.approve_comment = comment
            rec.approved_at = timezone.now()
            rec.save(update_fields=['status', 'approver', 'approve_comment', 'approved_at'])
            _audit(request.user, 'change-request-%s' % action, '%s %s' % (rec.request_no, comment[:80]))
            return APIResponse(data=_row(rec))

        if action == 'cancel':
            if rec.status != 'PENDING':
                return APIResponse(errcode=4090, errmsg='当前状态（%s）不能撤销' % STATUS_LABEL.get(rec.status))
            rec.status = 'CANCELED'
            rec.approve_comment = comment or '申请人撤销'
            rec.save(update_fields=['status', 'approve_comment'])
            _audit(request.user, 'change-request-cancel', rec.request_no)
            return APIResponse(data=_row(rec))

        if action == 'execute':
            if rec.status != 'APPROVED':
                return APIResponse(errcode=4090, errmsg='只有「已批准」的申请单可执行（当前：%s）'
                                   % STATUS_LABEL.get(rec.status))
            obj, model = _get_asset(rec.asset_type, rec.asset_id)
            if not obj:
                return APIResponse(errcode=404, errmsg='资产已不存在，无法执行')
            try:
                payload = json.loads(rec.payload or '{}')
            except Exception:
                return APIResponse(errcode=400, errmsg='申请单内容已损坏，无法执行')
            try:
                with transaction.atomic():
                    changed = []
                    for field, value in payload.items():
                        f = model._meta.get_field(field)
                        old = getattr(obj, field, None)
                        new = _cast(f, value)
                        if str(old) != str(new):
                            changed.append((field, old, new))
                            setattr(obj, field, new)
                    obj.save()
                    for field, old, new in changed:
                        record_change(rec.asset_type, obj.pk,
                                      getattr(obj, 'asset_no', None) or getattr(obj, 'instance_id', None),
                                      'update', operator, field=field, old=str(old), new=str(new))
                    rec.status = 'EXECUTED'
                    rec.executed_at = timezone.now()
                    rec.result = '已执行：' + ('；'.join('%s=%s' % (f, n) for f, _o, n in changed) or '无字段变化')
                    rec.save(update_fields=['status', 'executed_at', 'result'])
            except ValueError as e:
                return APIResponse(errcode=400, errmsg=str(e))
            except Exception as e:
                logger.error('变更单执行失败: %s' % str(e))
                return APIResponse(errcode=5001, errmsg='执行失败：%s' % str(e)[:200])
            _audit(request.user, 'change-request-execute', '%s %s' % (rec.request_no, rec.result[:100]))
            return APIResponse(data=_row(rec))

        return APIResponse(errcode=400, errmsg='未知操作：%s' % action)
