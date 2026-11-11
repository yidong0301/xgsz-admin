# -*- coding: utf-8 -*-
"""芯光数智 演示数据种子脚本"""
import sys, os
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from apps.cmdb.models import Server, GPUNode, K8sCluster, NetworkSwitch, OpticalModule
from apps.workflow.models import Pipeline, TaskTemplate, PipelineExecution, TaskExecution
from apps.account.models import User

# 1. 服务器
servers = [
    dict(instance_id='i-demo-001', hostname='web-prod-01', private_ip='10.0.1.11', cpu=8, memory=16, os_name='CentOS 7.9', status='Running', cloud_type='server', region_id='cn-hangzhou', owner='张三', environment='prod'),
    dict(instance_id='i-demo-002', hostname='web-prod-02', private_ip='10.0.1.12', cpu=8, memory=16, os_name='CentOS 7.9', status='Running', cloud_type='server', region_id='cn-hangzhou', owner='张三', environment='prod'),
    dict(instance_id='i-demo-003', hostname='db-test-01', private_ip='10.0.2.21', cpu=4, memory=32, os_name='Ubuntu 20.04', status='Running', cloud_type='virtual_machine', region_id='cn-shanghai', owner='李四', environment='test'),
    dict(instance_id='i-demo-004', hostname='gpu-dev-01', private_ip='10.0.3.31', cpu=16, memory=64, os_name='Ubuntu 22.04', status='Running', cloud_type='aliyun', region_id='cn-beijing', owner='王五', environment='dev'),
    dict(instance_id='i-demo-005', hostname='old-server-01', private_ip='10.0.1.99', cpu=2, memory=8, os_name='CentOS 6.10', status='Retired', cloud_type='server', region_id='cn-hangzhou', owner='张三', environment='prod'),
]
for s in servers:
    if not Server.objects.filter(instance_id=s['instance_id']).exists():
        Server.objects.create(**s)

# 2. GPU 节点
gpus = [
    dict(asset_no='GPU-DEMO-001', name='A100-训练节点-01', ip='10.0.3.11', gpu_model='A100', gpu_count=8, gpu_memory=80, cpu=32, memory=256, owner='王五', status='in_use', location='机房A-3排'),
    dict(asset_no='GPU-DEMO-002', name='A100-训练节点-02', ip='10.0.3.12', gpu_model='A100', gpu_count=8, gpu_memory=80, cpu=32, memory=256, owner='王五', status='in_use', location='机房A-3排'),
    dict(asset_no='GPU-DEMO-003', name='V100-推理节点-01', ip='10.0.3.21', gpu_model='V100', gpu_count=4, gpu_memory=32, cpu=16, memory=128, owner='李四', status='idle', location='机房B-1排'),
]
for g in gpus:
    if not GPUNode.objects.filter(asset_no=g['asset_no']).exists():
        GPUNode.objects.create(**g)

# 3. K8s 集群
if not K8sCluster.objects.filter(asset_no='K8S-DEMO-001').exists():
    K8sCluster.objects.create(asset_no='K8S-DEMO-001', name='生产集群', api_server='https://10.0.0.1:6443', version='v1.29.2', node_count=3, owner='运维组', status='in_use', location='机房A')

# 4. 交换机 + 光模块
if not NetworkSwitch.objects.filter(asset_no='SW-DEMO-001').exists():
    NetworkSwitch.objects.create(asset_no='SW-DEMO-001', name='核心交换机', ip='10.0.0.10', model='CE6857', port_count=48, owner='网络组', status='in_use', location='机房A-机柜1')
if not OpticalModule.objects.filter(asset_no='OM-DEMO-001').exists():
    OpticalModule.objects.create(asset_no='OM-DEMO-001', name='光模块-100G-01', module_type='QSFP28', rate='100G', wavelength='1310nm', owner='网络组', status='in_use', location='机房A-机柜1')

# 5. 推理任务：不再造假数据（假任务会把告警中心刷成一堆「推理任务失败」）
#    真实推理任务：python scripts/real_inference_demo.py（真下发 K8s Job/Deployment）

# 6. 流水线 + 编排
if not Pipeline.objects.filter(name='推理镜像发布').exists():
    Pipeline.objects.create(name='推理镜像发布', stages='[{"name":"构建镜像","command":"echo build"},{"name":"部署服务","command":"echo deploy"}]')
if not TaskTemplate.objects.filter(name='机器巡检').exists():
    TaskTemplate.objects.create(name='机器巡检', steps='[{"name":"检查磁盘","command":"echo disk-ok"},{"name":"检查进程","command":"echo process-ok"}]')

print('seed done: servers=%d gpu=%d k8s=%d switch=%d om=%d' % (
    Server.objects.count(), GPUNode.objects.count(), K8sCluster.objects.count(),
    NetworkSwitch.objects.count(), OpticalModule.objects.count()))
