# -*- coding: utf-8 -*-
"""补充各资产类型演示数据：GPU 节点 / K8s 集群 / 交换机 / 光模块 → 各 15 条（1-2 页）"""
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from datetime import date, timedelta
from apps.cmdb.models import GPUNode, K8sCluster, NetworkSwitch, OpticalModule

owners = ['王五', '李四', '赵六', '孙七', '周八', '张三']

# GPU 节点 → 15
for i in range(1, 16):
    asset_no = 'GPU-DEMO-%03d' % i
    if GPUNode.objects.filter(asset_no=asset_no).exists():
        continue
    GPUNode.objects.create(
        asset_no=asset_no, name='A100-推理节点-%02d' % i,
        ip='10.0.3.%d' % (10 + i),
        gpu_model=['A100', 'V100', 'H100'][i % 3],
        gpu_count=[4, 8][i % 2],
        gpu_memory=[80, 32, 80][i % 3],
        cpu=32, memory=256, owner=owners[i % 6],
        status=['in_use', 'idle'][i % 2],
        location='机房A-%d排' % (i % 3 + 1),
        warranty_expire=date.today() + timedelta(days=100 + i * 10),
    )

# K8s 集群 → 10
for i in range(1, 11):
    asset_no = 'K8S-DEMO-%03d' % i
    if K8sCluster.objects.filter(asset_no=asset_no).exists():
        continue
    K8sCluster.objects.create(
        asset_no=asset_no, name='业务集群-%02d' % i,
        api_server='https://10.0.%d.1:6443' % (20 + i),
        version='v1.%d.%d' % (29 - i % 3, i % 10),
        node_count=3 + i % 5, owner=owners[i % 6],
        status=['in_use', 'idle'][i % 2],
        location='机房%d' % (i % 3 + 1),
    )

# 交换机 → 15
for i in range(1, 16):
    asset_no = 'SW-DEMO-%03d' % i
    if NetworkSwitch.objects.filter(asset_no=asset_no).exists():
        continue
    NetworkSwitch.objects.create(
        asset_no=asset_no, name='交换机-%02d' % i,
        ip='10.0.0.%d' % (10 + i),
        model=['CE6857', 'CE8850', 'S5560'][i % 3],
        port_count=[48, 64][i % 2], owner='网络组',
        status=['in_use', 'idle'][i % 2],
        location='机房A-机柜%d' % (i % 5 + 1),
    )

# 光模块 → 15
for i in range(1, 16):
    asset_no = 'OM-DEMO-%03d' % i
    if OpticalModule.objects.filter(asset_no=asset_no).exists():
        continue
    OpticalModule.objects.create(
        asset_no=asset_no, name='光模块-%02d' % i,
        module_type=['QSFP28', 'QSFP+', 'SFP+'][i % 3],
        rate=['100G', '40G', '10G'][i % 3],
        wavelength=['1310nm', '850nm', '1550nm'][i % 3],
        owner='网络组',
        status=['in_use', 'idle'][i % 2],
        location='机房A-机柜%d' % (i % 5 + 1),
    )

print('gpu_nodes=%d k8s_clusters=%d switches=%d optical_modules=%d' % (
    GPUNode.objects.count(), K8sCluster.objects.count(),
    NetworkSwitch.objects.count(), OpticalModule.objects.count()))
