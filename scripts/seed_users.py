# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()

from apps.account.models import User

u = User.objects.filter(username='admin').first()
if u:
    u.department = u.department or '平台运维部'
    u.position = u.position or '平台管理员'
    u.name = u.name or '管理员'
    u.save()
    print('admin updated:', u.department, u.position)

demos = [
    ('zhangsan', '张三', '运维部', '运维工程师', '13800000002'),
    ('lisi', '李四', '算法部', '算法工程师', '13800000003'),
    ('wangwu', '王五', '资产部', '资产管理员', '13800000004'),
]
for username, name, dept, pos, mobile in demos:
    obj, created = User.objects.get_or_create(username=username, defaults={
        'name': name, 'department': dept, 'position': pos,
        'mobile': mobile, 'email': username + '@local'})
    if created:
        obj.set_password('admin123456')
        obj.save()
        print('created', username)
print('users:', User.objects.count())
