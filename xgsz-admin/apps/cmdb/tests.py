#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CMDB 配置关系与拓扑单元测试（离线，不依赖集群）。"""
from rest_framework.test import APIClient

from django.test import TestCase

from apps.account.models import User
from apps.cmdb.models import (Server, GPUNode, K8sCluster, NetworkSwitch, AssetRelation,
                              AssetChangeRequest, AssetChangeLog)


class RelationApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='cmdb_tester', password='test-pass-123',
                                                  name='测试管理员', mobile='13800000001')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.srv = Server.objects.create(instance_id='SRV-T-001', hostname='gpu-node-01',
                                         private_ip='10.0.0.11', owner='张三', cpu=64, memory=256)
        self.gpu = GPUNode.objects.create(name='A100-节点1', asset_no='GPU-T-001', gpu_count=8)
        self.cluster = K8sCluster.objects.create(name='cluster-a', asset_no='K8S-T-001', version='v1.31.0')
        self.switch = NetworkSwitch.objects.create(name='sw-core-1', asset_no='SW-T-001')

    def _rel(self, **kwargs):
        payload = {'source_type': 'server', 'source_id': self.srv.pk,
                   'target_type': 'gpu_node', 'target_id': self.gpu.pk,
                   'relation_type': 'contains'}
        payload.update(kwargs)
        return self.client.post('/api/cmdb/v1/relation', payload, format='json')

    # ---------- 新增 ----------
    def test_create_relation(self):
        resp = self._rel()
        body = resp.json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(AssetRelation.objects.count(), 1)
        self.assertEqual(body['data']['source_label'], 'gpu-node-01')
        self.assertEqual(body['data']['relation_label'], '包含')

    def test_duplicate_relation_rejected(self):
        self._rel()
        body = self._rel().json()
        self.assertEqual(body['errcode'], 4090)
        self.assertEqual(AssetRelation.objects.count(), 1)

    def test_self_relation_rejected(self):
        body = self._rel(target_type='server', target_id=self.srv.pk).json()
        self.assertEqual(body['errcode'], 400)
        self.assertIn('自己', body['errmsg'])

    def test_unknown_asset_rejected(self):
        body = self._rel(target_id='999999').json()
        self.assertEqual(body['errcode'], 404)

    def test_bad_type_rejected(self):
        body = self._rel(relation_type='likes').json()
        self.assertEqual(body['errcode'], 400)

    def test_engineer_cannot_write(self):
        eng = User.objects.create_user(username='cmdb_eng', password='x-123456', role='engineer')
        client = APIClient()
        client.force_authenticate(user=eng)
        resp = client.post('/api/cmdb/v1/relation', {
            'source_type': 'server', 'source_id': self.srv.pk,
            'target_type': 'gpu_node', 'target_id': self.gpu.pk}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(AssetRelation.objects.count(), 0)

    # ---------- 列表 / 删除 ----------
    def test_list_filtered_by_asset_both_directions(self):
        self._rel()  # server -> gpu
        self.client.post('/api/cmdb/v1/relation', {
            'source_type': 'k8s_cluster', 'source_id': self.cluster.pk,
            'target_type': 'server', 'target_id': self.srv.pk,
            'relation_type': 'runs_on'}, format='json')
        data = self.client.get('/api/cmdb/v1/relation?type=server&id=%s' % self.srv.pk).json()['data']
        self.assertEqual(data['count'], 2)
        rows = data['results']
        self.assertEqual({r['relation_type'] for r in rows}, {'contains', 'runs_on'})

    def test_delete_relation(self):
        rel_id = self._rel().json()['data']['id']
        body = self.client.delete('/api/cmdb/v1/relation/%s' % rel_id).json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(AssetRelation.objects.count(), 0)

    # ---------- 拓扑 ----------
    def _chain(self):
        self._rel()  # server -contains-> gpu
        AssetRelation.objects.create(source_type='gpu_node', source_id=str(self.gpu.pk),
                                     target_type='server', target_id=self.srv.pk,
                                     relation_type='depends_on')
        AssetRelation.objects.create(source_type='k8s_cluster', source_id=str(self.cluster.pk),
                                     target_type='server', target_id=self.srv.pk,
                                     relation_type='runs_on')

    def test_topology_depth(self):
        self._chain()
        d1 = self.client.get('/api/cmdb/v1/topology?type=server&id=%s&depth=1' % self.srv.pk).json()['data']
        self.assertEqual(len(d1['nodes']), 3)     # 自己 + gpu + cluster
        self.assertEqual(len(d1['edges']), 3)
        d2 = self.client.get('/api/cmdb/v1/topology?type=server&id=%s&depth=2' % self.srv.pk).json()['data']
        self.assertGreaterEqual(len(d2['nodes']), 3)

    def test_topology_handles_cycle(self):
        AssetRelation.objects.create(source_type='server', source_id=str(self.srv.pk),
                                     target_type='gpu_node', target_id=str(self.gpu.pk),
                                     relation_type='contains')
        AssetRelation.objects.create(source_type='gpu_node', source_id=str(self.gpu.pk),
                                     target_type='server', target_id=str(self.srv.pk),
                                     relation_type='depends_on')
        data = self.client.get('/api/cmdb/v1/topology?type=server&id=%s&depth=3' % self.srv.pk).json()['data']
        self.assertEqual(len(data['nodes']), 2)
        self.assertEqual(len(data['edges']), 2)

    def test_topology_marks_missing_asset(self):
        AssetRelation.objects.create(source_type='server', source_id=str(self.srv.pk),
                                     target_type='gpu_node', target_id=str(self.gpu.pk),
                                     relation_type='contains')
        self.gpu.delete()
        data = self.client.get('/api/cmdb/v1/topology?type=server&id=%s&depth=2' % self.srv.pk).json()['data']
        missing = [n for n in data['nodes'] if n['missing']]
        self.assertEqual(len(missing), 1)

    def test_topology_node_cap(self):
        """节点数超过 MAX_NODES 时截断，且返回的边两端都在节点里（不出现悬空连线）"""
        from unittest import mock
        for i in range(1, 6):
            g = GPUNode.objects.create(name='A100-节点%d' % i, asset_no='GPU-CAP-%03d' % i, gpu_count=1)
            AssetRelation.objects.create(source_type='k8s_cluster', source_id=str(self.cluster.pk),
                                         target_type='gpu_node', target_id=str(g.pk),
                                         relation_type='contains')
        with mock.patch('apps.cmdb.views.relation.MAX_NODES', 3):
            data = self.client.get('/api/cmdb/v1/topology?type=k8s_cluster&id=%s&depth=2'
                                   % self.cluster.pk).json()['data']
        self.assertTrue(data['node_truncated'])
        self.assertEqual(len(data['nodes']), 3)
        ids = {(n['type'], n['id']) for n in data['nodes']}
        for e in data['edges']:
            self.assertIn((e['from']['type'], e['from']['id']), ids)
            self.assertIn((e['to']['type'], e['to']['id']), ids)

    def test_topology_not_truncated_when_small(self):
        self._chain()
        data = self.client.get('/api/cmdb/v1/topology?type=server&id=%s&depth=2' % self.srv.pk).json()['data']
        self.assertFalse(data['node_truncated'])
        self.assertEqual(data['max_nodes'], 150)

    def test_asset_delete_cleans_relations(self):
        self._rel()
        self.assertEqual(AssetRelation.objects.count(), 1)
        self.client.delete('/api/cmdb/v1/asset/server/%s' % self.srv.pk)
        self.assertEqual(AssetRelation.objects.count(), 0)


class ChangeRequestApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='cr_admin', password='test-pass-123',
                                                  name='变更管理员', mobile='13800000002')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.srv = Server.objects.create(instance_id='SRV-CR-001', hostname='cr-node-01',
                                         private_ip='10.0.0.21', owner='李四', cpu=32, memory=128)

    def _submit(self, **kwargs):
        payload = {'asset_type': 'server', 'asset_id': self.srv.pk, 'title': '调整负责人与内存',
                   'reason': '扩容', 'payload': {'owner': '王五', 'memory': 256}}
        payload.update(kwargs)
        return self.client.post('/api/cmdb/v1/change-request', payload, format='json')

    def _approve(self, pk):
        return self.client.post('/api/cmdb/v1/change-request/%s/action' % pk,
                                {'action': 'approve', 'comment': '同意'}, format='json')

    # ---------- 提交 ----------
    def test_submit(self):
        body = self._submit().json()
        self.assertEqual(body['errcode'], 0)
        rec = AssetChangeRequest.objects.get(id=body['data']['id'])
        self.assertTrue(rec.request_no.startswith('CR-'))
        self.assertEqual(rec.status, 'PENDING')
        self.assertEqual(rec.asset_name, 'cr-node-01')
        self.assertEqual(body['data']['payload']['memory'], 256)

    def test_submit_unknown_field_rejected(self):
        body = self._submit(payload={'nope': 1}).json()
        self.assertEqual(body['errcode'], 400)
        self.assertIn('字段不存在', body['errmsg'])

    def test_submit_protected_field_rejected(self):
        body = self._submit(payload={'instance_id': 'HACK'}).json()
        self.assertEqual(body['errcode'], 400)

    def test_submit_empty_payload_rejected(self):
        body = self._submit(payload={}).json()
        self.assertEqual(body['errcode'], 400)

    def test_submit_unknown_asset_rejected(self):
        body = self._submit(asset_id='999999').json()
        self.assertEqual(body['errcode'], 404)

    # ---------- 审批 / 执行 ----------
    def test_approve_then_execute_applies_changes(self):
        pk = self._submit().json()['data']['id']
        approved = self._approve(pk).json()
        self.assertEqual(approved['data']['status'], 'APPROVED')
        self.assertEqual(approved['data']['approver'], '变更管理员')

        body = self.client.post('/api/cmdb/v1/change-request/%s/action' % pk,
                                {'action': 'execute'}, format='json').json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['status'], 'EXECUTED')
        self.srv.refresh_from_db()
        self.assertEqual(self.srv.owner, '王五')
        self.assertEqual(self.srv.memory, 256)
        self.assertTrue(AssetChangeLog.objects.filter(asset_id=self.srv.pk, field='owner').exists())
        self.assertIn('已执行', body['data']['result'])

    def test_execute_requires_approval(self):
        pk = self._submit().json()['data']['id']
        body = self.client.post('/api/cmdb/v1/change-request/%s/action' % pk,
                                {'action': 'execute'}, format='json').json()
        self.assertEqual(body['errcode'], 4090)
        self.srv.refresh_from_db()
        self.assertEqual(self.srv.owner, '李四')

    def test_approve_twice_rejected(self):
        pk = self._submit().json()['data']['id']
        self._approve(pk)
        body = self._approve(pk).json()
        self.assertEqual(body['errcode'], 4090)

    def test_reject(self):
        pk = self._submit().json()['data']['id']
        body = self.client.post('/api/cmdb/v1/change-request/%s/action' % pk,
                                {'action': 'reject', 'comment': '信息不全'}, format='json').json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['status'], 'REJECTED')
        self.srv.refresh_from_db()
        self.assertEqual(self.srv.owner, '李四')

    def test_cancel_by_creator(self):
        pk = self._submit().json()['data']['id']
        body = self.client.post('/api/cmdb/v1/change-request/%s/action' % pk,
                                {'action': 'cancel'}, format='json').json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['status'], 'CANCELED')

    def test_engineer_cannot_approve(self):
        pk = self._submit().json()['data']['id']
        eng = User.objects.create_user(username='cr_eng', password='x-123456', role='engineer')
        client = APIClient()
        client.force_authenticate(user=eng)
        resp = client.post('/api/cmdb/v1/change-request/%s/action' % pk, {'action': 'approve'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_list_filter_and_pending_count(self):
        self._submit()
        self._submit(title='第二条')
        data = self.client.get('/api/cmdb/v1/change-request?status=PENDING').json()['data']
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['pending_count'], 2)

