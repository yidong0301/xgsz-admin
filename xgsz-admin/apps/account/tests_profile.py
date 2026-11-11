#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个人设置：资料 / 角色 / 登录日志 / 改密码。"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User
from apps.ops.models import AuditLog


class ProfileApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='pf_admin', password='old-pass-123', name='资料管理员',
            mobile='13800000012', email='pf@example.com', department='平台运维部',
            role='superadmin')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        AuditLog.objects.create(user='资料管理员', action='login', resource='登录',
                                detail='用户登录', ip='10.0.0.1', result='成功')
        AuditLog.objects.create(user='资料管理员', action='login', resource='登录',
                                detail='用户登录', ip='10.0.0.2', result='成功')
        AuditLog.objects.create(user='其他人', action='login', resource='登录',
                                detail='用户登录', ip='10.0.0.3', result='成功')
        AuditLog.objects.create(user='资料管理员', action='other', resource='修改配置',
                                detail='无关操作', ip='10.0.0.4', result='成功')

    def test_get_profile_returns_role_and_own_login_records(self):
        d = self.client.get('/api/account/v1/user/profile').json()['data']
        self.assertEqual(d['role'], 'superadmin')
        self.assertEqual(d['role_label'], '超级管理员')
        self.assertEqual([r['ip'] for r in d['login_records']], ['10.0.0.2', '10.0.0.1'])
        self.assertEqual(len(d['login_records']), 2)

    def test_update_profile_fields(self):
        resp = self.client.post('/api/account/v1/user/profile', {
            'name': '新名字', 'department': '资产部',
            'email': 'new@example.com', 'mobile': '13900000000',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, '新名字')
        self.assertEqual(self.user.department, '资产部')
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertEqual(self.user.mobile, '13900000000')

    def test_change_password_requires_correct_old_password(self):
        resp = self.client.post('/api/account/v1/user/profile', {
            'new_password': 'new-pass-123', 'old_password': 'wrong',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 4001)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('old-pass-123'))

    def test_change_password_success(self):
        resp = self.client.post('/api/account/v1/user/profile', {
            'new_password': 'new-pass-123', 'old_password': 'old-pass-123',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('new-pass-123'))
