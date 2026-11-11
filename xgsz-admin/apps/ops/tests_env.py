#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境运行配置参数：保存 / 校验 / 权限 / 下发到 K8s（ConfigMap + 重启引用它的应用）。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase
from kubernetes.client.rest import ApiException
from rest_framework.test import APIClient

from apps.account.models import User
from apps.ops.models import EnvConfig


class EnvConfigApiTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='env_admin', password='test-pass-123',
                                                   name='环境管理员', mobile='13800000003')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _create(self, **kwargs):
        payload = {'env': 'dev', 'cluster': 'kind', 'namespace': 'xgsz-dev',
                   'key': 'APP_MODE', 'value': 'debug', 'remark': '运行模式'}
        payload.update(kwargs)
        return self.client.post('/api/ops/v1/env-config', payload, format='json')

    def test_create_and_upsert(self):
        body = self._create().json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(EnvConfig.objects.count(), 1)

        body = self._create(value='release').json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(EnvConfig.objects.count(), 1)
        self.assertEqual(EnvConfig.objects.first().value, 'release')

    def test_invalid_key_rejected(self):
        body = self._create(key='bad key').json()
        self.assertEqual(body['errcode'], 400)

    def test_empty_key_rejected(self):
        body = self._create(key='').json()
        self.assertEqual(body['errcode'], 400)

    def test_list_filter(self):
        self._create()
        self._create(key='DB_POOL', value='10')
        self._create(env='test', key='APP_MODE', value='test')
        data = self.client.get('/api/ops/v1/env-config?env=dev&namespace=xgsz-dev').json()['data']
        self.assertEqual(data['count'], 2)
        self.assertEqual([r['key'] for r in data['results']], ['APP_MODE', 'DB_POOL'])

    def test_update_and_delete(self):
        cid = self._create().json()['data']['id']
        body = self.client.put('/api/ops/v1/env-config/%s' % cid, {'value': 'prod-like'}, format='json').json()
        self.assertEqual(body['data']['value'], 'prod-like')
        body = self.client.delete('/api/ops/v1/env-config/%s' % cid).json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(EnvConfig.objects.count(), 0)

    def test_engineer_forbidden(self):
        eng = User.objects.create_user(username='env_eng', password='x-123456', role='engineer')
        client = APIClient()
        client.force_authenticate(user=eng)
        resp = client.post('/api/ops/v1/env-config', {'env': 'dev', 'key': 'A', 'value': '1'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_apply_requires_config(self):
        body = self.client.post('/api/ops/v1/env-config/apply',
                                {'env': 'dev', 'cluster': 'kind', 'namespace': 'xgsz-dev'}, format='json').json()
        self.assertEqual(body['errcode'], 400)

    @patch('apps.ops.views_env.apps_v1')
    @patch('apps.ops.views_env.core_v1')
    def test_apply_writes_configmap_and_restarts_referencing_deployment(self, core_f, apps_f):
        self._create(key='APP_MODE', value='release')
        self._create(key='DB_POOL', value='20')

        core = MagicMock()
        core.read_namespaced_config_map.side_effect = ApiException(status=404)
        core_f.return_value = core

        ref_dep = SimpleNamespace(
            metadata=SimpleNamespace(name='demo-app'),
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(
                containers=[SimpleNamespace(env_from=[SimpleNamespace(
                    config_map_ref=SimpleNamespace(name='xgsz-env-config'))], env=[])],
                init_containers=[], volumes=[]))),
        )
        plain_dep = SimpleNamespace(
            metadata=SimpleNamespace(name='other-app'),
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(
                containers=[SimpleNamespace(env_from=[], env=[])], init_containers=[], volumes=[]))),
        )
        apps = MagicMock()
        apps.list_namespaced_deployment.return_value = SimpleNamespace(items=[ref_dep, plain_dep])
        apps_f.return_value = apps

        body = self.client.post('/api/ops/v1/env-config/apply',
                                {'env': 'dev', 'cluster': 'kind', 'namespace': 'xgsz-dev', 'restart': True},
                                format='json').json()
        self.assertEqual(body['errcode'], 0)
        self.assertEqual(body['data']['keys'], 2)
        self.assertEqual(body['data']['restarted'], ['demo-app'])
        self.assertEqual(body['data']['skipped'], ['other-app'])
        cm = core.create_namespaced_config_map.call_args[0][1]
        self.assertEqual(cm.data, {'APP_MODE': 'release', 'DB_POOL': '20'})
        apps.patch_namespaced_deployment.assert_called_once()
