# -*- coding: utf-8 -*-
"""修复测试数据中的负责人乱码，并用 UTF-8 请求验证"""
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

import requests
from apps.k8s.models import InferenceTask

# 1) 修复历史乱码负责人
bad = InferenceTask.objects.filter(owner__in=['??', '?', ''])
print('待修复乱码任务数:', bad.count())
bad.update(owner='张三')

# 2) 用 UTF-8 请求真实提交，验证负责人正确落库
s = requests.Session()
lg = s.post('http://localhost:8080/api/account/v1/user/login',
            json={'username': 'admin', 'password': 'admin123456'}, timeout=15)
token = lg.json()['data']['token']
h = {'Authorization': 'JWT ' + token}
resp = s.post('http://localhost:8080/api/k8s/v1/inference/task',
              json={'name': 'utf8-owner-test', 'namespace': 'default',
                    'image': 'nginx:alpine', 'cpu': '1', 'memory': '2Gi', 'gpu': 0,
                    'owner': '张三'},
              headers=h, timeout=30)
print('提交:', resp.status_code, resp.json().get('errcode'))
tid = resp.json().get('data', {}).get('id')
t = InferenceTask.objects.get(id=tid)
print('落库 owner hex:', t.owner.encode('utf-8').hex(), '(e5bca0e4b889=张三)')
