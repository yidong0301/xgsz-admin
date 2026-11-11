#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通知已读：未读红点 / 已读绿点，按用户记录，全部已读后不再亮铃铛红点。"""
import hashlib
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User
from apps.k8s.models import InferenceTask
from apps.ops.models import NotificationRead

TASK_NAME = '图像分类-030'
TASK_TITLE = '推理任务失败：%s' % TASK_NAME
TASK_KEY = hashlib.md5(('task|%s' % TASK_TITLE).encode('utf-8')).hexdigest()[:32]


@patch('apps.account.views.alerts._check_component_with_retry', return_value=('ok', '连接正常', False))
class NotificationReadApiTest(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='nr_admin', password='test-pass-123', name='通知管理员', mobile='13800000010')
        self.other = User.objects.create_superuser(
            username='nr_other', password='test-pass-124', name='另一位管理员', mobile='13800000011')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.task = InferenceTask.objects.create(
            name=TASK_NAME, image='nginx:alpine', status='FAILED', error_msg='OOMKilled')

    def _alerts(self, client=None):
        body = (client or self.client).get('/api/account/v1/alerts').json()
        self.assertEqual(body['errcode'], 0)
        return body['data']

    def test_unread_by_default(self, _check):
        data = self._alerts()
        alert = next(a for a in data['alerts'] if a['key'] == TASK_KEY)
        self.assertFalse(alert['read'])
        self.assertEqual(data['unread'], 1)

    def test_mark_read_updates_flag_and_unread(self, _check):
        resp = self.client.post('/api/account/v1/alerts/read', {'keys': [TASK_KEY]}, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        self.assertEqual(resp['data']['marked'], 1)
        data = self._alerts()
        alert = next(a for a in data['alerts'] if a['key'] == TASK_KEY)
        self.assertTrue(alert['read'])
        self.assertEqual(data['unread'], 0)
        # 幂等：重复标记不再新增
        resp2 = self.client.post('/api/account/v1/alerts/read', {'keys': [TASK_KEY]}, format='json').json()
        self.assertEqual(resp2['data']['marked'], 0)
        self.assertEqual(NotificationRead.objects.filter(alert_key=TASK_KEY).count(), 1)

    def test_read_state_is_per_user(self, _check):
        self.client.post('/api/account/v1/alerts/read', {'keys': [TASK_KEY]}, format='json')
        other = APIClient()
        other.force_authenticate(user=self.other)
        data = self._alerts(other)
        alert = next(a for a in data['alerts'] if a['key'] == TASK_KEY)
        self.assertFalse(alert['read'])
        self.assertEqual(data['unread'], 1)

    def test_no_alerts_means_zero_unread(self, _check):
        self.task.delete()
        cache.clear()
        data = self._alerts()
        self.assertEqual(data['alerts'], [])
        self.assertEqual(data['unread'], 0)

    def test_read_rejects_empty_keys(self, _check):
        resp = self.client.post('/api/account/v1/alerts/read', {'keys': []}, format='json').json()
        self.assertEqual(resp['errcode'], 400)

    def test_close_alert_clears_read_state(self, _check):
        self.client.post('/api/account/v1/alerts/read', {'keys': [TASK_KEY]}, format='json')
        self.assertTrue(NotificationRead.objects.filter(alert_key=TASK_KEY).exists())
        self.client.post('/api/account/v1/alerts/claim', {'key': TASK_KEY, 'title': TASK_TITLE}, format='json')
        resp = self.client.post('/api/account/v1/alerts/close', {'key': TASK_KEY, 'note': '已处理'}, format='json').json()
        self.assertEqual(resp['errcode'], 0)
        self.assertFalse(NotificationRead.objects.filter(alert_key=TASK_KEY).exists())
