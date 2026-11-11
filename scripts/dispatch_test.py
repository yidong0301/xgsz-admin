# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from tasks.email import send_email
r = send_email.delay('test@localhost', 'tester', 'title', 'msg', 'msgen', 'http://localhost')
print('DISPATCHED_ID=' + str(r.id), flush=True)
os._exit(0)
