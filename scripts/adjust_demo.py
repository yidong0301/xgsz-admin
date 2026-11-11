# -*- coding: utf-8 -*-
"""把演示数据调整到首页工作台验收数值（只重建 GPU 节点，不再造假的推理任务）"""
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from datetime import date, timedelta
from apps.cmdb.models import GPUNode, Server

# 重建 GPU 节点
GPUNode.objects.all().delete()

g1 = GPUNode.objects.create(asset_no='GPU-DEMO-001', name='A100-推理节点-01', ip='10.0.3.11',
                            gpu_model='A100', gpu_count=4, gpu_memory=80, cpu=32, memory=256,
                            owner='王五', status='in_use', location='机房A-3排',
                            warranty_expire=date.today() + timedelta(days=20))
g2 = GPUNode.objects.create(asset_no='GPU-DEMO-002', name='A100-推理节点-02', ip='10.0.3.12',
                            gpu_model='A100', gpu_count=4, gpu_memory=80, cpu=32, memory=256,
                            owner='李四', status='in_use', location='机房A-3排')

gpu_total = sum(g.gpu_count for g in GPUNode.objects.all())
print('GPU 总卡数:', gpu_total)
print('服务器:', Server.objects.count())
print('推理任务：真实任务由 scripts/real_inference_demo.py 提交到 K8s，不再本地造数')
