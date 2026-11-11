#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机器节点管理单元测试：PodDisruptionBudget 匹配/预检、drain 目标筛选、Eviction 结果映射、
标签/污点校验、metrics 用量换算。真实 K8s 行为在 VM 上冒烟，这里全部离线。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from kubernetes.client.rest import ApiException

from apps.k8s.views import node_manage as nm


def _pod(name, ns='xgsz-dev', labels=None, owner_kind=None, phase='Running', annotations=None):
    refs = [SimpleNamespace(kind=owner_kind)] if owner_kind else []
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=ns, labels=labels or {},
                                 owner_references=refs, annotations=annotations or {},
                                 creation_timestamp=None),
        status=SimpleNamespace(phase=phase, container_statuses=[]),
        spec=SimpleNamespace(node_name='node-a'),
    )


def _node(cpu='4', memory='16Gi'):
    return SimpleNamespace(status=SimpleNamespace(allocatable={'cpu': cpu, 'memory': memory}),
                           metadata=SimpleNamespace(name='node-a'))


class SelectorMatchTest(SimpleTestCase):
    def test_match_labels(self):
        self.assertTrue(nm._selector_matches({'matchLabels': {'app': 'web'}}, {'app': 'web', 'x': '1'}))
        self.assertFalse(nm._selector_matches({'matchLabels': {'app': 'web'}}, {'app': 'api'}))

    def test_match_expressions(self):
        sel = {'matchExpressions': [{'key': 'tier', 'operator': 'In', 'values': ['gold', 'silver']}]}
        self.assertTrue(nm._selector_matches(sel, {'tier': 'gold'}))
        self.assertFalse(nm._selector_matches(sel, {'tier': 'bronze'}))
        self.assertTrue(nm._selector_matches({'matchExpressions': [
            {'key': 'tier', 'operator': 'NotIn', 'values': ['bronze']}]}, {'tier': 'gold'}))
        self.assertTrue(nm._selector_matches({'matchExpressions': [
            {'key': 'tier', 'operator': 'Exists'}]}, {'tier': 'gold'}))
        self.assertFalse(nm._selector_matches({'matchExpressions': [
            {'key': 'tier', 'operator': 'DoesNotExist'}]}, {'tier': 'gold'}))

    def test_empty_selector_matches_nothing(self):
        # K8s 语义：空 selector 不选中任何 Pod，否则 drain 预检会误报
        self.assertFalse(nm._selector_matches({}, {'app': 'web'}))
        self.assertFalse(nm._selector_matches(None, {'app': 'web'}))


class PdbPlanTest(SimpleTestCase):
    def _pdb(self, allowed, min_available=2, name='demo-pdb'):
        return {'namespace': 'xgsz-dev', 'name': name, 'min_available': min_available,
                'max_unavailable': None, 'current_healthy': 2, 'desired_healthy': 2,
                'disruptions_allowed': allowed,
                'selector': {'matchLabels': {'app': 'web'}}}

    def test_allowed_disruption_does_not_block(self):
        pods = [_pod('web-1', labels={'app': 'web'})]
        rows, blocks = nm._pdb_plan([self._pdb(allowed=1)], pods)
        self.assertEqual(len(rows), 1)
        self.assertEqual(blocks, [])

    def test_zero_allowed_blocks(self):
        pods = [_pod('web-1', labels={'app': 'web'}), _pod('web-2', labels={'app': 'web'})]
        _rows, blocks = nm._pdb_plan([self._pdb(allowed=0)], pods)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['name'], 'demo-pdb')
        self.assertEqual(len(blocks[0]['pods']), 2)

    def test_allowed_lower_than_target_count_blocks(self):
        pods = [_pod('web-1', labels={'app': 'web'}), _pod('web-2', labels={'app': 'web'})]
        _rows, blocks = nm._pdb_plan([self._pdb(allowed=1)], pods)
        self.assertEqual(len(blocks), 1)

    def test_other_namespace_pdb_ignored(self):
        pods = [_pod('web-1', labels={'app': 'web'})]
        pdb = self._pdb(allowed=0)
        pdb['namespace'] = 'default'
        _rows, blocks = nm._pdb_plan([pdb], pods)
        self.assertEqual(blocks, [])


class DrainTargetTest(SimpleTestCase):
    def test_skip_daemonset_mirror_and_finished(self):
        pods = [
            _pod('app-1', owner_kind='ReplicaSet'),
            _pod('ds-1', owner_kind='DaemonSet'),
            _pod('static-1', annotations={'kubernetes.io/config.mirror': 'abc'}),
            _pod('done-1', phase='Succeeded'),
        ]
        targets, skipped = nm._drain_targets(pods)
        self.assertEqual([p.metadata.name for p in targets], ['app-1'])
        self.assertEqual(len(skipped), 3)
        reasons = {s['name']: s['reason'] for s in skipped}
        self.assertIn('DaemonSet', reasons['ds-1'])
        self.assertIn('静态', reasons['static-1'])
        self.assertIn('已结束', reasons['done-1'])


class EvictPodTest(SimpleTestCase):
    @patch('apps.k8s.views.node_manage._call')
    def test_evicted(self, call):
        self.assertEqual(nm._evict_pod('kind', 'ns', 'p1'), ('evicted', ''))

    @patch('apps.k8s.views.node_manage._call')
    def test_pdb_block_returns_reason(self, call):
        body = json.dumps({'kind': 'Status', 'status': 'Failure', 'reason': 'TooManyRequests',
                           'message': "Cannot evict pod as it would violate the pod's disruption budget.",
                           'details': {'causes': [{'reason': 'DisruptionBudget',
                                                   'message': 'The disruption budget demo-pdb needs 2 healthy pods'}]},
                           'code': 429})
        err = ApiException(status=429, reason='Too Many Requests')
        err.body = body  # 真实请求里 body 来自 http_resp.data
        call.side_effect = err
        state, msg = nm._evict_pod('kind', 'ns', 'p1')
        self.assertEqual(state, 'blocked')
        self.assertIn('demo-pdb', msg)

    @patch('apps.k8s.views.node_manage._call')
    def test_missing_pod_is_gone(self, call):
        call.side_effect = ApiException(status=404, reason='Not Found')
        state, _msg = nm._evict_pod('kind', 'ns', 'p1')
        self.assertEqual(state, 'gone')

    @patch('apps.k8s.views.node_manage._call')
    def test_other_error_is_failed(self, call):
        err = ApiException(status=500, reason='InternalError')
        err.body = '{"message":"boom"}'
        call.side_effect = err
        state, msg = nm._evict_pod('kind', 'ns', 'p1')
        self.assertEqual(state, 'failed')
        self.assertIn('boom', msg)


class ValidationTest(SimpleTestCase):
    def test_label_ok(self):
        self.assertTrue(nm._validate_label('team', 'ai')[0])
        self.assertTrue(nm._validate_label('example.com/team', 'ai')[0])
        self.assertTrue(nm._validate_label('team', '')[0])

    def test_label_bad(self):
        self.assertFalse(nm._validate_label('', 'x')[0])
        self.assertFalse(nm._validate_label('-bad', 'x')[0])
        self.assertFalse(nm._validate_label('team', 'x' * 64)[0])
        self.assertFalse(nm._validate_label('Example.com/team', 'x')[0])

    def test_taint_effect(self):
        self.assertTrue(nm._validate_taint('dedicated', 'gpu', 'NoSchedule')[0])
        self.assertFalse(nm._validate_taint('dedicated', 'gpu', 'NoSuch')[0])


class AdminGuardTest(SimpleTestCase):
    def test_admin_roles(self):
        self.assertTrue(nm._is_admin(SimpleNamespace(is_superuser=True, role='engineer')))
        self.assertTrue(nm._is_admin(SimpleNamespace(is_superuser=False, role='admin')))
        self.assertTrue(nm._is_admin(SimpleNamespace(is_superuser=False, role='superadmin')))
        self.assertFalse(nm._is_admin(SimpleNamespace(is_superuser=False, role='lead')))
        self.assertFalse(nm._is_admin(SimpleNamespace(is_superuser=False, role='engineer')))
        self.assertFalse(nm._is_admin(SimpleNamespace(is_superuser=False)))


class MetricsTest(SimpleTestCase):
    def test_cpu_and_memory_parsing(self):
        self.assertEqual(nm._cpu_milli('250m'), 250.0)
        self.assertEqual(nm._cpu_milli('2'), 2000.0)
        self.assertEqual(nm._mem_bytes('1Gi'), 1024 ** 3)
        self.assertEqual(nm._mem_bytes('512Mi'), 512 * 1024 ** 2)

    def test_usage_percent(self):
        payload = nm._usage_payload({'cpu': '500m', 'memory': '2Gi'}, _node(cpu='4', memory='16Gi'))
        self.assertEqual(payload['cpu_percent'], 12.5)
        self.assertEqual(payload['memory_percent'], 12.5)
        self.assertEqual(payload['cpu'], '500m')
        self.assertEqual(payload['memory'], '2.0Gi')

    def test_usage_none_when_no_metrics(self):
        self.assertIsNone(nm._usage_payload({}, _node()))
