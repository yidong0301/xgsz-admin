#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发布单 API 自动化测试（P2-5）

真实 K8s 行为在 apps.ops.k8s_release 中，单元测试用 mock 隔离集群：
- 创建 / 审批 / 拒绝 / 发布 / 回滚状态机
- 镜像对比、详情、Pod 日志接口
- 发布失败与健康检查失败落库
"""
import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from kubernetes.client.rest import ApiException
from rest_framework.test import APIClient

from apps.account.models import User
from apps.ops import k8s_release
from apps.ops.models import ReleaseOrder, AuditLog, OpsLog


class ReleaseApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='tester', password='test-pass-123', name='测试管理员',
            mobile='13800000000',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _create(self, **kwargs):
        payload = {
            'app_name': 'xgsz-demo-web', 'env': 'test', 'namespace': 'default',
            'cluster': 'kind', 'image': 'nginx:1.27-alpine', 'version': 'v1.27',
            'replicas': 2, 'reason': '单元测试',
        }
        payload.update(kwargs)
        return self.client.post('/api/ops/v1/release', payload, format='json')

    def _order(self, status='APPROVED', **kwargs):
        fields = dict(
            release_no='REL-TEST-001', app_name='xgsz-demo-web', env='test',
            namespace='default', cluster='kind', image='nginx:1.27-alpine',
            version='v1.27', replicas=2, status=status, creator='tester',
            k8s_deployment='xgsz-demo-web',
        )
        fields.update(kwargs)
        return ReleaseOrder.objects.create(**fields)

    # ---------- 创建 ----------
    def test_create_release(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        order = ReleaseOrder.objects.get(id=body['data']['id'])
        self.assertEqual(order.status, 'PENDING')
        self.assertEqual(order.k8s_deployment, 'xgsz-demo-web')
        self.assertTrue(AuditLog.objects.filter(action='release').exists())

    def test_create_release_requires_app_and_image(self):
        resp = self.client.post('/api/ops/v1/release', {'app_name': 'x'}, format='json')
        self.assertEqual(resp.json()['errcode'], 400)
        resp = self._create(replicas=-1)
        self.assertEqual(resp.json()['errcode'], 400)

    # ---------- 审批 ----------
    def test_approve_and_reject_state_machine(self):
        order = self._order(status='PENDING')
        resp = self.client.post('/api/ops/v1/release/%s/approve' % order.id, {}, format='json')
        self.assertEqual(resp.json()['errcode'], 0)
        order.refresh_from_db()
        self.assertEqual(order.status, 'APPROVED')
        self.assertEqual(order.approver, '测试管理员')

        # 已审批不能再次审批
        resp = self.client.post('/api/ops/v1/release/%s/approve' % order.id, {}, format='json')
        self.assertEqual(resp.json()['errcode'], 400)

        pending = self._order(status='PENDING', release_no='REL-TEST-002')
        resp = self.client.post('/api/ops/v1/release/%s/reject' % pending.id, {'remark': '不要'}, format='json')
        self.assertEqual(resp.json()['errcode'], 0)
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'REJECTED')

    def test_execute_requires_approved(self):
        order = self._order(status='PENDING')
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        self.assertEqual(resp.json()['errcode'], 400)

    # ---------- 真实发布 ----------
    @patch('apps.ops.views.k8s_release.rollout')
    def test_execute_success_saves_health_and_previous_version(self, rollout):
        rollout.return_value = {
            'ok': True, 'healthy': True, 'message': '滚动更新完成，所有副本已就绪',
            'deployment_name': 'xgsz-demo-web', 'previous_image': 'nginx:alpine',
            'previous_replicas': 1, 'duration_ms': 1234,
            'comparison': {'changed': True}, 'pods': [], 'deployment': {},
        }
        order = self._order(status='APPROVED')
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertTrue(body['data']['ok'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'RELEASED')
        self.assertEqual(order.health_status, 'HEALTHY')
        self.assertEqual(order.previous_image, 'nginx:alpine')
        self.assertEqual(order.previous_replicas, 1)
        self.assertEqual(order.duration_ms, 1234)
        self.assertEqual(json.loads(order.health_detail)['message'], '滚动更新完成，所有副本已就绪')
        self.assertTrue(OpsLog.objects.filter(message__contains='发布成功').exists())

    @patch('apps.ops.views.k8s_release.rollout')
    def test_execute_failure_marks_failed(self, rollout):
        rollout.side_effect = k8s_release.ReleaseError('K8s 集群连接不可用')
        order = self._order(status='APPROVED')
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        body = resp.json()
        self.assertEqual(body['errcode'], 5002)
        self.assertFalse(body['data']['ok'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'FAILED')
        self.assertEqual(order.health_status, 'UNHEALTHY')
        self.assertIn('K8s 集群连接不可用', json.loads(order.health_detail)['message'])

    @patch('apps.ops.views.k8s_release.rollout')
    def test_retry_failed_release_preserves_original_previous_version(self, rollout):
        # 第一次失败时已记录上一版本；重试不能把“本次目标镜像”覆盖成回滚目标
        rollout.return_value = {
            'ok': True, 'healthy': True, 'message': '滚动更新完成，所有副本已就绪',
            'deployment_name': 'test-123', 'previous_image': 'nginx:1.27-alpine',
            'previous_replicas': 2, 'duration_ms': 700,
            'comparison': {'changed': False}, 'pods': [], 'deployment': {},
        }
        order = self._order(status='FAILED', previous_image='nginx:alpine', previous_replicas=1)
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['status'], 'RELEASED')
        order.refresh_from_db()
        self.assertEqual(order.status, 'RELEASED')
        self.assertEqual(order.previous_image, 'nginx:alpine')
        self.assertEqual(order.previous_replicas, 1)

    @patch('apps.ops.views.k8s_release.rollout')
    def test_retry_failed_release_can_fail_again(self, rollout):
        rollout.side_effect = k8s_release.ReleaseError('仍然失败')
        order = self._order(status='FAILED')
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        self.assertEqual(resp.json()['errcode'], 5002)
        order.refresh_from_db()
        self.assertEqual(order.status, 'FAILED')

    @patch('apps.ops.views.k8s_release.rollout')
    def test_republish_after_rollback(self, rollout):
        rollout.return_value = {
            'ok': True, 'healthy': True, 'message': '滚动更新完成，所有副本已就绪',
            'deployment_name': 'xgsz-demo-web', 'previous_image': 'nginx:alpine',
            'previous_replicas': 2, 'duration_ms': 600,
            'comparison': {'changed': True}, 'pods': [], 'deployment': {},
        }
        order = self._order(status='ROLLED_BACK', previous_image='nginx:alpine', previous_replicas=2)
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['status'], 'RELEASED')
        order.refresh_from_db()
        self.assertEqual(order.status, 'RELEASED')

    def test_execute_rejects_released_state(self):
        order = self._order(status='RELEASED')
        resp = self.client.post('/api/ops/v1/release/%s/execute' % order.id, {}, format='json')
        self.assertEqual(resp.json()['errcode'], 400)

    @patch('apps.ops.k8s_release._core_api')
    def test_ensure_namespace_creates_for_dev(self, core_api):
        class Core:
            def __init__(self):
                self.created = None

            def read_namespace(self, ns, **kwargs):
                raise ApiException(status=404, reason='Not Found')

            def create_namespace(self, body, **kwargs):
                self.created = body

        core = Core()
        core_api.return_value = core
        order = self._order(status='APPROVED', env='dev', namespace='xgsz-dev')
        result = k8s_release.ensure_namespace(order)
        self.assertTrue(result['created'])
        self.assertEqual(core.created.metadata.name, 'xgsz-dev')

    @patch('apps.ops.k8s_release._core_api')
    def test_ensure_namespace_prod_missing_raises(self, core_api):
        class Core:
            def read_namespace(self, ns, **kwargs):
                raise ApiException(status=404, reason='Not Found')

        core_api.return_value = Core()
        order = self._order(status='APPROVED', env='prod', namespace='xgsz-prod')
        with self.assertRaises(k8s_release.ReleaseError):
            k8s_release.ensure_namespace(order)

    # ---------- 回滚 ----------
    @patch('apps.ops.views.k8s_release.rollback')
    def test_rollback_restores_previous_image(self, rollback):
        rollback.return_value = {
            'ok': True, 'healthy': True, 'message': '已回滚到上一版本镜像 nginx:alpine',
            'mode': 'restore_image', 'pods': [], 'deployment': {}, 'duration_ms': 800,
        }
        order = self._order(status='RELEASED', previous_image='nginx:alpine', previous_replicas=1)
        resp = self.client.post('/api/ops/v1/release/%s/rollback' % order.id, {}, format='json')
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['status'], 'ROLLED_BACK')
        order.refresh_from_db()
        self.assertEqual(order.status, 'ROLLED_BACK')
        self.assertEqual(order.health_status, 'HEALTHY')

    def test_rollback_requires_released_state(self):
        order = self._order(status='APPROVED')
        resp = self.client.post('/api/ops/v1/release/%s/rollback' % order.id, {}, format='json')
        self.assertEqual(resp.json()['errcode'], 400)

    # ---------- 详情 / 对比 / 日志 ----------
    @patch('apps.ops.views.k8s_release.state')
    @patch('apps.ops.views.k8s_release.compare')
    def test_detail_contains_live_k8s_and_comparison(self, compare, state):
        compare.return_value = {
            'exists': True, 'current_image': 'nginx:alpine', 'target_image': 'nginx:1.27-alpine',
            'changed': True, 'current_replicas': 1, 'target_replicas': 2,
        }
        state.return_value = {
            'available': True, 'exists': True,
            'deployment': {'replicas': 2, 'ready_replicas': 2, 'healthy': True, 'conditions': []},
            'pods': [{'name': 'xgsz-demo-web-abc', 'phase': 'Running', 'ready': '1/1'}],
        }
        order = self._order(status='RELEASED')
        resp = self.client.get('/api/ops/v1/release/%s' % order.id)
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertTrue(body['data']['comparison']['changed'])
        self.assertEqual(body['data']['live']['pods'][0]['phase'], 'Running')

    @patch('apps.ops.views.k8s_release.compare')
    def test_compare_endpoint(self, compare):
        compare.return_value = {'changed': False, 'current_image': 'nginx:alpine',
                                'target_image': 'nginx:alpine', 'exists': True}
        order = self._order()
        resp = self.client.get('/api/ops/v1/release/%s/compare' % order.id)
        self.assertEqual(resp.json()['errcode'], 0)
        self.assertFalse(resp.json()['data']['changed'])

    @patch('apps.ops.views.k8s_release.pod_logs')
    def test_logs_endpoint(self, pod_logs):
        pod_logs.return_value = {'pod': 'xgsz-demo-web-abc', 'lines': ['line1', 'line2']}
        order = self._order()
        resp = self.client.get('/api/ops/v1/release/%s/logs?pod=xgsz-demo-web-abc&tail=50' % order.id)
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['lines'], ['line1', 'line2'])
        pod_logs.assert_called_once()

    # ---------- 多集群 ----------
    def test_list_filter_by_cluster(self):
        self._order(cluster='cluster-01', release_no='REL-CLUSTER-01')
        self._order(cluster='cluster-02', release_no='REL-CLUSTER-02')
        resp = self.client.get('/api/ops/v1/release?cluster=cluster-01')
        results = resp.json()['data']['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['release_no'], 'REL-CLUSTER-01')

    def test_cluster_config_file_resolves_named_kubeconfig(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'cluster-01.yaml')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('apiVersion: v1\n')
            with patch.object(k8s_release.os, 'getenv', return_value=tmp):
                self.assertEqual(k8s_release.cluster_config_file('cluster-01'), path)
                self.assertIsNone(k8s_release.cluster_config_file('cluster-99'))
                self.assertIsNone(k8s_release.cluster_config_file(''))

    def test_missing_named_cluster_kubeconfig_raises(self):
        class Probe:
            cluster = 'cluster-99'
            namespace = 'default'

        with patch('apps.ops.k8s_release.cluster_config_file', return_value=None):
            with self.assertRaises(k8s_release.ReleaseError):
                k8s_release._api_client(Probe())

    @patch('apps.ops.views.k8s_release.expected_cluster_count', return_value=8)
    @patch('apps.ops.views.k8s_release.check_clusters')
    @patch('apps.ops.views.k8s_release.list_cluster_configs')
    def test_cluster_health_endpoint(self, list_configs, check_clusters, expected_count):
        list_configs.return_value = {'kind': '/root/.kube/clusters/kind.yaml'}
        check_clusters.return_value = [
            {'name': 'kind', 'configured': True, 'reachable': True,
             'node_count': 1, 'version': 'v1.24.6', 'kubeconfig': 'kind.yaml', 'error': ''},
        ]
        resp = self.client.get('/api/ops/v1/clusters')
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['configured_count'], 1)
        self.assertEqual(body['data']['online_count'], 1)
        self.assertEqual(body['data']['expected_count'], 8)
        self.assertTrue(body['data']['clusters'][0]['reachable'])

    @patch('apps.ops.k8s_release.cluster_config_file', return_value='/tmp/cluster-01.yaml')
    @patch('apps.ops.k8s_release._api_client', return_value=object())
    @patch('apps.ops.k8s_release.client.CoreV1Api')
    def test_check_cluster_online(self, core_cls, api_client, config_file):
        node = SimpleNamespace(status=SimpleNamespace(node_info=SimpleNamespace(kubelet_version='v1.24.6')))
        core_cls.return_value.list_node.return_value = SimpleNamespace(items=[node])
        result = k8s_release.check_cluster('cluster-01')
        self.assertTrue(result['reachable'])
        self.assertEqual(result['node_count'], 1)
        self.assertEqual(result['version'], 'v1.24.6')

    @patch('apps.ops.k8s_release.cluster_config_file', return_value='/tmp/cluster-01.yaml')
    @patch('apps.ops.k8s_release._api_client', side_effect=Exception('connection refused'))
    def test_check_cluster_offline(self, api_client, config_file):
        result = k8s_release.check_cluster('cluster-01')
        self.assertFalse(result['reachable'])
        self.assertIn('connection refused', result['error'])

    def test_safe_name_rfc1123(self):
        self.assertEqual(k8s_release.safe_name('My App 中文', 'fallback'), 'my-app')
        self.assertEqual(k8s_release.safe_name('', 'fallback'), 'fallback')
        self.assertLessEqual(len(k8s_release.safe_name('x' * 200)), 63)
