#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户管理：删除用户 / 管理员重置密码。"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User


class UserManageApiTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='um_admin', password='admin-pass-123', name='用户管理员',
            mobile='13800000021', role='superadmin')
        self.target = User.objects.create_user(
            username='um_target', password='old-pass-123', name='目标用户',
            mobile='13800000022', role='engineer')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_delete_user(self):
        resp = self.client.delete('/api/account/v1/users?id=%s' % self.target.id).json()
        self.assertEqual(resp['errcode'], 0)
        self.assertFalse(User.objects.filter(id=self.target.id).exists())

    def test_cannot_delete_self(self):
        resp = self.client.delete('/api/account/v1/users?id=%s' % self.admin.id).json()
        self.assertEqual(resp['errcode'], 400)
        self.assertTrue(User.objects.filter(id=self.admin.id).exists())

    def test_delete_missing_user(self):
        resp = self.client.delete('/api/account/v1/users?id=999999').json()
        self.assertEqual(resp['errcode'], 404)

    def test_admin_reset_password(self):
        resp = self.client.post('/api/account/v1/user/reset_password', {
            'id': self.target.id, 'password': 'new-temp-123',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('new-temp-123'))

    def test_reset_password_too_short(self):
        resp = self.client.post('/api/account/v1/user/reset_password', {
            'id': self.target.id, 'password': '123',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 400)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('old-pass-123'))
