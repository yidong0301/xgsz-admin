# -*- coding: utf-8 -*-
"""交付角色划分：超级管理员 / 交付主管 / 交付工程师"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0006_auto_20261109_1146'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[('superadmin', '超级管理员'), ('lead', '交付主管'),
                         ('engineer', '交付工程师'), ('admin', '管理员'),
                         ('technician', '技术员')],
                default='engineer', max_length=16, verbose_name='平台角色'),
        ),
    ]
