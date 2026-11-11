#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确保平台管理员账号存在（幂等，供 Ubuntu 一键部署调用）。"""
from django.core.management.base import BaseCommand

from apps.account.models import User


class Command(BaseCommand):
    help = '确保管理员账号存在（幂等）'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--password', default='admin123456')
        parser.add_argument('--name', default='管理员')
        parser.add_argument('--mobile', default='13800000000')
        parser.add_argument('--reset-password', action='store_true',
                            help='已存在时是否重置密码（默认不重置）')

    def handle(self, *args, **options):
        username = options['username']
        user, created = User.objects.get_or_create(username=username)
        changed = created
        if created:
            user.name = options['name']
            user.mobile = options['mobile']
            user.set_password(options['password'])
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if getattr(user, 'role', '') != 'admin':
            user.role = 'admin'
            changed = True
        # 演示数据里可能已有 admin 但密码为空，这里补一个可用密码
        if not user.password or not user.has_usable_password():
            user.set_password(options['password'])
            changed = True
        if options['reset_password']:
            user.set_password(options['password'])
            changed = True
        if changed:
            user.save()
            self.stdout.write(self.style.SUCCESS('管理员账号已就绪：%s' % username))
        else:
            self.stdout.write('管理员账号已存在：%s（未修改密码）' % username)
