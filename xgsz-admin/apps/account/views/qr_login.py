#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机手机扫码登录：桌面生成一次性二维码，手机打开确认页登录后桌面换取 token。

不依赖钉钉 / 企业微信：二维码指向平台自己的 /qr.html，手机端用账号密码确认，
桌面轮询票据状态，确认后拿到登录 token 并进入平台。票据存 Redis，2 分钟有效。
"""
import secrets
from collections import defaultdict
from urllib.parse import urlparse

from django.contrib.auth import authenticate
from django.core.cache import cache
from rest_framework.views import APIView

from apps.rbac.models import Role
from utils.http_response import APIResponse
from utils.jwt_token import create_token

QR_TTL = 120
QR_KEY = 'xgsz_qr_login:%s'


def _cache_key(ticket):
    return QR_KEY % ticket


def _login_payload(user):
    permissions_list = Role.objects.filter(user__id=user.id).values(
        'permissions__method', 'permissions__path')
    permissions = defaultdict(list)
    for item in permissions_list:
        permissions[item.get('permissions__path')].append(item.get('permissions__method'))
    for key in list(permissions.keys()):
        permissions[key] = list(set(permissions[key]))
    token = create_token({'username': user.username, 'permissions': permissions}, 1440)
    return {
        'token': token,
        'name': user.name,
        'avatar': user.avatar,
        'id': user.id,
        'role': user.role,
        'is_superuser': user.is_superuser,
    }


def _is_local_host(host):
    name = (host or '').split(':')[0].strip('[]').lower()
    return name in ('localhost', '127.0.0.1', '0.0.0.0', '::1')


class QrCreateView(APIView):
    """创建扫码登录票据，返回二维码内容 URL（二维码由前端本地生成）"""

    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        ticket = secrets.token_urlsafe(24)
        cache.set(_cache_key(ticket), {'status': 'pending'}, QR_TTL)
        scheme = request.META.get('HTTP_X_FORWARDED_PROTO') or request.scheme
        host = request.META.get('HTTP_X_FORWARDED_HOST') or request.get_host()
        base = '%s://%s' % (scheme, host)
        origin = (request.data.get('origin') or '').strip().rstrip('/')
        parsed = urlparse(origin)
        if parsed.scheme in ('http', 'https') and parsed.netloc == host:
            base = origin
        url = '%s/qr.html?t=%s' % (base, ticket)
        return APIResponse(data={
            'ticket': ticket,
            'url': url,
            'expires_in': QR_TTL,
            'localhost': _is_local_host(host),
        })


class QrStatusView(APIView):
    """桌面轮询票据状态：pending / approved（返回登录 payload）/ expired"""

    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        ticket = (request.query_params.get('ticket') or '').strip()
        if not ticket:
            return APIResponse(data={'status': 'expired'})
        key = _cache_key(ticket)
        data = cache.get(key)
        if not data:
            return APIResponse(data={'status': 'expired'})
        if data.get('status') == 'approved' and data.get('payload'):
            cache.delete(key)  # 一次性
            return APIResponse(data={'status': 'approved', 'payload': data['payload']})
        return APIResponse(data={'status': 'pending'})


class QrApproveView(APIView):
    """手机端确认页：校验账号密码后批准票据，桌面端随后拿到 token（无需登录）"""

    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        ticket = (request.data.get('ticket') or '').strip()
        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        if not ticket:
            return APIResponse(errcode=400, errmsg='二维码无效，请刷新后重试')
        key = _cache_key(ticket)
        data = cache.get(key)
        if not data:
            return APIResponse(errcode=410, errmsg='二维码已过期，请在电脑上刷新')
        if data.get('status') == 'approved':
            return APIResponse(errcode=409, errmsg='该二维码已被确认，请在电脑上刷新')
        if not username or not password:
            return APIResponse(errcode=400, errmsg='请输入账号和密码')
        user = authenticate(username=username, password=password)
        if not user:
            return APIResponse(errcode=400, errmsg='账号或密码错误')
        if not user.is_active:
            return APIResponse(errcode=403, errmsg='账号已被禁用，请联系管理员')
        payload = _login_payload(user)
        cache.set(key, {'status': 'approved', 'payload': payload}, 60)
        try:
            from apps.ops.views import record_audit
            record_audit(user.name, 'login', '扫码登录', '手机端确认登录', request)
        except Exception:
            pass
        return APIResponse(data={'status': 'approved', 'name': user.name})
