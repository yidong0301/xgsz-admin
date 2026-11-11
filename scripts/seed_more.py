# -*- coding: utf-8 -*-
"""批量补充演示数据：30 台服务器（每页10条 → 3页）

推理任务不再在这里造：假任务会污染告警中心，真实的推理任务请用
`scripts/real_inference_demo.py`（走平台 API 真下发到 K8s）。
"""
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from apps.cmdb.models import Server, GPUNode

owners = ['张三', '李四', '王五', '赵六', '孙七', '周八']
envs = ['prod', 'test', 'dev']
clouds = ['server', 'virtual_machine', 'aliyun']

# === 服务器：补齐到 30 台 ===
existing = Server.objects.count()
need = 30 - existing
for i in range(need):
    idx = existing + i + 1
    iid = 'i-demo-%03d' % idx
    if Server.objects.filter(instance_id=iid).exists():
        continue
    Server.objects.create(
        instance_id=iid,
        hostname='node-%03d' % idx,
        private_ip='10.0.%d.%d' % (idx // 200 + 1, idx % 200 + 10),
        cpu=[4, 8, 16, 32][idx % 4],
        memory=[8, 16, 32, 64][idx % 4],
        os_name=['CentOS 7.9', 'Ubuntu 20.04', 'Ubuntu 22.04'][idx % 3],
        status='Running',
        cloud_type=clouds[idx % 3],
        region_id='cn-hangzhou',
        owner=owners[idx % len(owners)],
        environment=envs[idx % 3],
    )

print('servers:', Server.objects.count())
