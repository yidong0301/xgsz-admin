# -*- coding: utf-8 -*-
import os, sys, django
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
django.setup()
from apps.cmdb.models import Server
print("expected: 张三 = e5bca0 e4b889")
for s in Server.objects.order_by('instance_id'):
    print(s.instance_id, "| owner_hex=", (s.owner or '').encode('utf-8').hex(), "| owner_repr=", repr(s.owner), "| env=", s.environment)
