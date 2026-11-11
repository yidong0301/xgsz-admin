# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from apps.account.models import User
for u in User.objects.all():
    print(u.username, 'dept_len=', len(u.department or ''), 'pos_len=', len(u.position or ''))
