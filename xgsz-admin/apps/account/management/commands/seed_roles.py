#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初始化三种交付角色与权限矩阵（幂等，可重复执行）。

角色划分：
  超级管理员  1 人   全平台：账号、角色、系统配置，全平台任务 / 账单 / 审计
  交付主管    1 人   本组数据：本组任务管理、审批本组资源、查看导出本组账单
  交付工程师  不限   自己负责项目：提交/管理自有任务、申请资源、查看自有项目资源
"""
from django.core.management.base import BaseCommand

from apps.account.models import User
from apps.rbac.models import Role, Permission

ESSENTIAL = [
    (r'/api/account/v1/user/profile', 'GET'), (r'/api/account/v1/user/profile', 'POST'),
    (r'/api/account/v1/alerts', 'GET'),
    (r'/api/account/v1/alerts/read', 'POST'),
    (r'/api/account/v1/alerts/claim', 'POST'),
    (r'/api/account/v1/alerts/close', 'POST'),
    (r'/api/account/v1/health', 'GET'),
    (r'/api/ops/v1/overview', 'GET'),
]
RELEASE_BASE = [
    (r'/api/ops/v1/release', 'GET'), (r'/api/ops/v1/release', 'POST'),
    (r'/api/ops/v1/release/\d+', 'GET'),
    (r'/api/ops/v1/release/\d+/compare', 'GET'),
    (r'/api/ops/v1/release/\d+/logs', 'GET'),
]
ENGINEER_PERMS = ESSENTIAL + RELEASE_BASE + [
    (r'/api/ops/v1/release/\d+/execute', 'POST'),
    (r'/api/cmdb/v1/asset', 'GET'),
    (r'/api/k8s/v1/inference/task', 'GET'), (r'/api/k8s/v1/inference/task', 'POST'),
    (r'/api/k8s/v1/inference/task/\d+', 'GET'),
    (r'/api/k8s/v1/inference/task/\d+/logs', 'GET'),
    (r'/api/k8s/v1/inference/task/\d+/usage', 'GET'),
    (r'/api/k8s/v1/inference/task/\d+/stop', 'POST'),
    (r'/api/k8s/v1/inference/meta', 'GET'),
]
LEAD_PERMS = ENGINEER_PERMS + [
    (r'/api/ops/v1/release/\d+/approve', 'POST'),
    (r'/api/ops/v1/release/\d+/reject', 'POST'),
    (r'/api/ops/v1/release/\d+/rollback', 'POST'),
    (r'/api/ops/v1/clusters', 'GET'),
    (r'/api/ops/v1/audit', 'GET'),
    (r'/api/ops/v1/opslog', 'GET'),
]

ROLE_DEFS = [
    ('超级管理员', 'superadmin', '全平台：账号、角色、系统配置，全平台任务 / 账单 / 审计',
     [(r'/api/.*', '*')]),
    ('交付主管', 'lead', '本组数据：本组任务管理、审批本组资源、查看导出本组账单', LEAD_PERMS),
    ('交付工程师', 'engineer', '自己负责项目：提交 / 管理自有任务、发起资源申请、查看自有项目资源', ENGINEER_PERMS),
]


class Command(BaseCommand):
    help = '初始化三种交付角色（超级管理员 / 交付主管 / 交付工程师）及权限矩阵'

    def handle(self, *args, **options):
        for name, key, desc, perms in ROLE_DEFS:
            role, _ = Role.objects.update_or_create(name=name, defaults={'desc': desc[:50]})
            role.permissions.clear()
            for path, method in perms:
                perm, _ = Permission.objects.get_or_create(
                    name='%s %s' % (method, path), defaults={'path': path, 'method': method})
                role.permissions.add(perm)
            self.stdout.write('角色就绪：%s（%s，权限 %d 条）' % (name, key, len(perms)))

        admin = User.objects.filter(username='admin').first()
        if admin:
            admin.role = 'superadmin'
            admin.roles.set([Role.objects.get(name='超级管理员')])
            admin.save(update_fields=['role'])
            self.stdout.write('admin 已设为超级管理员')

        # 演示账号（已存在则校正角色与密码）
        demos = [
            ('abc1', '交付主管-张工', 'lead', '交付主管', 'admin123456'),
            ('guxinjie', '顾新杰', 'engineer', '交付工程师', 'Xgsz@123456'),
        ]
        for username, name, key, label, pwd in demos:
            u, _ = User.objects.get_or_create(username=username, defaults={'name': name, 'mobile': ''})
            u.name = name
            u.role = key
            u.department = '平台运维部'
            u.set_password(pwd)
            u.save()
            u.roles.set([Role.objects.get(name=label)])
            self.stdout.write('演示账号：%s / %s（%s）' % (username, pwd, label))

        # 历史账号（旧角色 admin / technician）统一归到交付工程师，避免名额统计错乱
        engineer_role = Role.objects.get(name='交付工程师')
        legacy = User.objects.filter(role__in=['admin', 'technician']).exclude(username='admin')
        for u in legacy:
            u.role = 'engineer'
            u.roles.set([engineer_role])
            u.save(update_fields=['role'])
            self.stdout.write('历史账号 %s 已归入交付工程师' % u.username)

        self.stdout.write(self.style.SUCCESS('角色初始化完成'))
