# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from apps.k8s.models import InferenceTask
for t in InferenceTask.objects.filter(id__in=[34,35,36,38]).order_by('id'):
    o = t.owner or ''
    print(t.id, '| owner_hex=', o.encode('utf-8').hex()[:40], '| owner_len=', len(o))
