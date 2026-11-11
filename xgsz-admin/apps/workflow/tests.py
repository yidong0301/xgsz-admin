#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务编排：K8s Job 目标参数与命令解析（离线用例，不连集群）。"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.account.models import User
from apps.workflow.k8s_job import _command_parts, _safe, run_step_job
from apps.workflow.models import TaskTemplate


class CommandParseTest(TestCase):
    def test_shell_string(self):
        self.assertEqual(_command_parts('echo hi'), ['/bin/sh', '-c', 'echo hi'])

    def test_json_array(self):
        self.assertEqual(_command_parts('["sh","-c","echo hi"]'), ['sh', '-c', 'echo hi'])

    def test_bad_json_falls_back_to_shell(self):
        self.assertEqual(_command_parts('["sh",'), ['/bin/sh', '-c', '["sh",'])

    def test_safe_name(self):
        self.assertTrue(_safe('机器巡检 Step#1').startswith('step'))
        self.assertLessEqual(len(_safe('x' * 100)), 36)


class TemplateTargetTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='wf_admin', password='test-pass-123',
                                                  name='编排管理员', mobile='13800000004')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_k8s_template(self):
        body = self.client.post('/api/workflow/v1/task/template', {
            'name': '巡检-K8s', 'steps': [{'name': '磁盘', 'command': 'df -h'}],
            'target_type': 'k8s', 'cluster': 'kind', 'namespace': 'xgsz-dev',
            'image': 'busybox:1.36', 'cpu': '200m', 'memory': '64Mi', 'gpu': 1,
        }, format='json').json()
        self.assertEqual(body['errcode'], 0)
        tpl = TaskTemplate.objects.get(id=body['data']['id'])
        self.assertEqual(tpl.target_type, 'k8s')
        self.assertEqual(tpl.gpu, 1)
        self.assertEqual(body['data']['namespace'], 'xgsz-dev')

    def test_invalid_target_rejected(self):
        body = self.client.post('/api/workflow/v1/task/template', {
            'name': 'bad', 'steps': [], 'target_type': 'ssh'}, format='json').json()
        self.assertEqual(body['errcode'], 400)

    def test_default_target_is_local(self):
        body = self.client.post('/api/workflow/v1/task/template', {
            'name': '默认', 'steps': [{'name': 's', 'command': 'echo ok'}]}, format='json').json()
        self.assertEqual(body['data']['target_type'], 'local')


class RunJobTest(TestCase):
    """用 mock 校验 Job 规格：镜像 / 命令 / 资源 / 超时，避免真连集群"""

    @patch('apps.workflow.k8s_job._pod_output', return_value='hello')
    @patch('apps.workflow.k8s_job.core_v1')
    @patch('apps.workflow.k8s_job.batch_v1')
    def test_job_spec_and_success(self, batch_f, core_f, _out):
        from types import SimpleNamespace
        api = SimpleNamespace()
        api.create_namespaced_job = lambda namespace, body: None
        cond = SimpleNamespace(type='Complete', status='True')
        api.read_namespaced_job_status = lambda name, namespace: SimpleNamespace(
            status=SimpleNamespace(conditions=[cond]))
        batch_f.return_value = api
        core_f.return_value = SimpleNamespace()

        with patch('apps.workflow.k8s_job.time.sleep', return_value=None):
            r = run_step_job(cluster='kind', namespace='xgsz-dev', step_name='disk check',
                             image='busybox:1.36', command='df -h',
                             cpu='200m', memory='64Mi', gpu=1, timeout=30)
        self.assertTrue(r['ok'])
        self.assertEqual(r['output'], 'hello')
        self.assertTrue(r['job'].startswith('xgsz-wf-disk-check-'))

    @patch('apps.workflow.k8s_job.batch_v1')
    def test_create_failure_raises(self, batch_f):
        from kubernetes.client.rest import ApiException
        from apps.workflow.k8s_job import StepJobError
        api = batch_f.return_value
        api.create_namespaced_job.side_effect = ApiException(status=404)
        with self.assertRaises(StepJobError):
            run_step_job(cluster='kind', namespace='nope', step_name='x', command='echo hi')
