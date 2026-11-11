# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from xgsz_admin.celery import app
print("broker_url:", app.conf.broker_url, flush=True)
print("result_backend:", app.conf.result_backend, flush=True)
print("task_always_eager:", app.conf.task_always_eager, flush=True)
print("task_ignore_result:", app.conf.task_ignore_result, flush=True)
print("before send_task", flush=True)
r = app.send_task('tasks.email.send_email', args=['a@b.c','n','t','m','me','http://x'])
print("after send_task id=" + str(r.id), flush=True)
os._exit(0)
