#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/demo_data.json 导入演示数据（容器内可执行，幂等）。"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from apps.account.models import User
from apps.cmdb.models import Server, GPUNode, K8sCluster, NetworkSwitch, OpticalModule


class Command(BaseCommand):
    help = '导入演示数据（幂等，可重复执行）'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=os.environ.get('DEMO_DATA_PATH', '/app/data/demo_data.json'))

    def handle(self, *args, **options):
        path = options['path']
        if not os.path.exists(path):
            raise CommandError('演示数据文件不存在：%s' % path)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        for u in data.get('users', []):
            fields = dict(u)
            fields.pop('id', None)
            User.objects.update_or_create(username=u['username'], defaults=fields)

        for s in data.get('servers', []):
            fields = dict(s)
            fields.pop('id', None)
            Server.objects.update_or_create(instance_id=s['instance_id'], defaults=fields)

        for g in data.get('gpu_nodes', []):
            fields = dict(g)
            fields.pop('id', None)
            GPUNode.objects.update_or_create(asset_no=g.get('asset_no'), defaults=fields)

        for c in data.get('k8s_clusters', []):
            fields = dict(c)
            fields.pop('id', None)
            K8sCluster.objects.update_or_create(asset_no=c.get('asset_no'), defaults=fields)

        for n in data.get('switches', []):
            fields = dict(n)
            fields.pop('id', None)
            NetworkSwitch.objects.update_or_create(asset_no=n.get('asset_no'), defaults=fields)

        for m in data.get('optical_modules', []):
            fields = dict(m)
            fields.pop('id', None)
            OpticalModule.objects.update_or_create(asset_no=m.get('asset_no'), defaults=fields)

        # 推理任务不再从 JSON 造：假任务会把告警中心刷成「推理任务失败」
        # 真实推理任务用 scripts/real_inference_demo.py 走 API 下发到 K8s。
        self.stdout.write(self.style.SUCCESS(
            '演示数据导入完成：users=%d servers=%d gpu=%d k8s=%d switch=%d optical=%d' % (
                User.objects.count(), Server.objects.count(), GPUNode.objects.count(),
                K8sCluster.objects.count(), NetworkSwitch.objects.count(),
                OpticalModule.objects.count())))
