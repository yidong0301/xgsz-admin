#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指标总览：节点用量、Pod Top、趋势、阈值告警（K8s 侧全部 mock）。"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User
from apps.ops.models import MetricSample

NODES = [
    {'cluster': 'kind', 'name': 'node-a', 'cpu': 2.0, 'cpu_text': '2.00 核', 'cpu_total': 4.0,
     'cpu_total_text': '4.00 核', 'cpu_pct': 50.0, 'mem': 4 * 1024 ** 3, 'mem_text': '4.0Gi',
     'mem_total': 16 * 1024 ** 3, 'mem_total_text': '16.0Gi', 'mem_pct': 25.0, 'gpu': 0},
]


class MetricsOverviewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='mx_admin', password='test-pass-123',
                                                  name='指标管理员', mobile='13800000005')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.ops.views_metrics.pod_usage', return_value=[{'namespace': 'xgsz-dev', 'name': 'p1',
                                                              'cpu_text': '100m', 'mem_text': '64Mi'}])
    @patch('apps.ops.views_metrics.node_usage', return_value=(NODES, ''))
    def test_overview_with_metrics(self, _n, _p):
        MetricSample.objects.create(cluster='kind', node='node-a', cpu_pct=40, mem_pct=20)
        MetricSample.objects.create(cluster='kind', node='node-a', cpu_pct=50, mem_pct=25)
        body = self.client.get('/api/ops/v1/metrics/overview').json()
        self.assertEqual(body['errcode'], 0)
        d = body['data']
        self.assertTrue(d['available'])
        self.assertEqual(len(d['nodes']), 1)
        self.assertEqual(len(d['top_pods']), 1)
        self.assertEqual(len(d['trend']['node-a']), 2)
        self.assertEqual(d['alerts'], [])

    @patch('apps.ops.views_metrics.pod_usage', return_value=[])
    @patch('apps.ops.views_metrics.node_usage')
    def test_threshold_alerts(self, node_usage, _p):
        hot = dict(NODES[0], cpu_pct=92.0, mem_pct=95.0)
        node_usage.return_value = ([hot], '')
        d = self.client.get('/api/ops/v1/metrics/overview').json()['data']
        kinds = {a['kind'] for a in d['alerts']}
        self.assertEqual(kinds, {'cpu', 'mem'})
        self.assertTrue(all(a['node'] == 'node-a' for a in d['alerts']))

    @patch('apps.ops.views_metrics.node_usage', return_value=([], '未安装 metrics-server（metrics.k8s.io/v1beta1 不可用）'))
    def test_overview_without_metrics_server(self, _n):
        d = self.client.get('/api/ops/v1/metrics/overview').json()['data']
        self.assertFalse(d['available'])
        self.assertIn('metrics-server', d['error'])
        self.assertEqual(d['nodes'], [])

    def test_engineer_forbidden(self):
        eng = User.objects.create_user(username='mx_eng', password='x-123456', role='engineer')
        c = APIClient()
        c.force_authenticate(user=eng)
        resp = c.get('/api/ops/v1/metrics/overview')
        self.assertEqual(resp.status_code, 403)
