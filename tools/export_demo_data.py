# -*- coding: utf-8 -*-
"""导出当前演示数据到 data/demo_data.json（逻辑与数据分离）"""
import os, sys, json
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from django.core.serializers.json import DjangoJSONEncoder
from apps.cmdb.models import Server, GPUNode, K8sCluster, NetworkSwitch, OpticalModule
from apps.k8s.models import InferenceTask
from apps.account.models import User

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, 'demo_data.json')

data = {
    'users': list(User.objects.values('username', 'name', 'department', 'position', 'mobile', 'email', 'is_superuser')),
    'servers': list(Server.objects.values()),
    'gpu_nodes': list(GPUNode.objects.values()),
    'k8s_clusters': list(K8sCluster.objects.values()),
    'switches': list(NetworkSwitch.objects.values()),
    'optical_modules': list(OpticalModule.objects.values()),
    'inference_tasks': list(InferenceTask.objects.values()),
}
with open(out, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder)
print('exported:', out)
for k, v in data.items():
    print(' ', k, '=', len(v))
