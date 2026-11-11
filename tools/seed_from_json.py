# -*- coding: utf-8 -*-
"""从 data/demo_data.json 加载演示数据到数据库（逻辑与数据分离）

用法：python tools/seed_from_json.py
可重复执行（幂等），不会产生重复数据。
"""
import os, sys, json
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from apps.cmdb.models import Server, GPUNode, K8sCluster, NetworkSwitch, OpticalModule
from apps.account.models import User

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_path = os.path.join(BASE, 'data', 'demo_data.json')
with open(data_path, encoding='utf-8') as f:
    data = json.load(f)


def _clean(record, key):
    """去掉主键 / 外键 id 冲突字段，避免导入时冲突"""
    d = dict(record)
    d.pop('id', None) if key != 'id' else None
    return d


# 1) 用户
for u in data.get('users', []):
    fields = _clean(u, 'username')
    User.objects.update_or_create(username=u['username'], defaults=fields)

# 2) 服务器（主键 instance_id）
for s in data.get('servers', []):
    fields = _clean(s, 'instance_id')
    Server.objects.update_or_create(instance_id=s['instance_id'], defaults=fields)

# 3) GPU 节点（按 asset_no）
for g in data.get('gpu_nodes', []):
    fields = _clean(g, 'asset_no')
    GPUNode.objects.update_or_create(asset_no=g.get('asset_no'), defaults=fields)

# 4) K8s 集群
for c in data.get('k8s_clusters', []):
    fields = _clean(c, 'asset_no')
    K8sCluster.objects.update_or_create(asset_no=c.get('asset_no'), defaults=fields)

# 5) 交换机
for n in data.get('switches', []):
    fields = _clean(n, 'asset_no')
    NetworkSwitch.objects.update_or_create(asset_no=n.get('asset_no'), defaults=fields)

# 6) 光模块
for m in data.get('optical_modules', []):
    fields = _clean(m, 'asset_no')
    OpticalModule.objects.update_or_create(asset_no=m.get('asset_no'), defaults=fields)

# 7) 推理任务：不从 JSON 造（假任务会把告警中心刷成「推理任务失败」）
#    真实推理任务：python scripts/real_inference_demo.py（走平台 API 真下发 K8s）
print('loaded demo_data.json done')
print(' users=%d servers=%d gpu=%d k8s=%d switch=%d optical=%d' % (
    User.objects.count(), Server.objects.count(), GPUNode.objects.count(),
    K8sCluster.objects.count(), NetworkSwitch.objects.count(),
    OpticalModule.objects.count()))
