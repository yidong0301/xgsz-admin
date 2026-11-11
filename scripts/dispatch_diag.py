# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
print("STEP1 django setup ok", flush=True)

import redis
r = redis.Redis(host='127.0.0.1', port=6379, db=4)
r.ping()
print("STEP2 redis ping ok", flush=True)
r.publish('xgsz_test_chan', 'hello')
print("STEP3 redis publish ok", flush=True)

from tasks.email import send_email
print("STEP4 import send_email ok", flush=True)
