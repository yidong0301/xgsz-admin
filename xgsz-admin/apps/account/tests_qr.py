#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机手机扫码登录：票据创建 / 轮询 / 手机端确认。"""
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User


class QrLoginApiTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='qr_user', password='qr-pass-123', name='扫码用户',
            mobile='13800000031', role='engineer')
        self.client = APIClient()

    def _create(self):
        resp = self.client.post('/api/account/v1/user/qr/create', {}, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        return resp['data']

    def test_create_returns_ticket_and_pending_status(self):
        data = self._create()
        self.assertTrue(data['ticket'])
        self.assertIn('/qr.html?t=', data['url'])
        status = self.client.get('/api/account/v1/user/qr/status?ticket=%s' % data['ticket']).json()
        self.assertEqual(status['data']['status'], 'pending')

    def test_wrong_password_rejected(self):
        data = self._create()
        resp = self.client.post('/api/account/v1/user/qr/approve', {
            'ticket': data['ticket'], 'username': 'qr_user', 'password': 'wrong',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 400)

    def test_approve_then_status_returns_one_time_payload(self):
        data = self._create()
        resp = self.client.post('/api/account/v1/user/qr/approve', {
            'ticket': data['ticket'], 'username': 'qr_user', 'password': 'qr-pass-123',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        self.assertEqual(resp['data']['status'], 'approved')
        status = self.client.get('/api/account/v1/user/qr/status?ticket=%s' % data['ticket']).json()['data']
        self.assertEqual(status['status'], 'approved')
        self.assertTrue(status['payload']['token'])
        self.assertEqual(status['payload']['id'], self.user.id)
        self.assertEqual(status['payload']['role'], 'engineer')
        # 一次性：取走后再次轮询即为过期
        again = self.client.get('/api/account/v1/user/qr/status?ticket=%s' % data['ticket']).json()['data']
        self.assertEqual(again['status'], 'expired')

    def test_expired_ticket_rejected(self):
        data = self._create()
        cache.delete('xgsz_qr_login:%s' % data['ticket'])
        resp = self.client.post('/api/account/v1/user/qr/approve', {
            'ticket': data['ticket'], 'username': 'qr_user', 'password': 'qr-pass-123',
        }, format='json').json()
        self.assertEqual(resp['errcode'], 410)

    def test_missing_ticket_status_expired(self):
        data = self.client.get('/api/account/v1/user/qr/status').json()['data']
        self.assertEqual(data['status'], 'expired')
