# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from tasks.email import send_email
print("before delay", flush=True)
r = send_email.delay('a@b.c', 'n', 't', 'm', 'me', 'http://x')
print("after delay id=" + str(r.id), flush=True)
os._exit(0)
