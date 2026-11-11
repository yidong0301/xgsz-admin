#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通知已读状态：按用户 + 告警指纹记录，铃铛红点按未读数显示。"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0010_metrics_periodic'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationRead',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.CharField(max_length=64, verbose_name='用户')),
                ('alert_key', models.CharField(max_length=64, verbose_name='通知指纹')),
                ('read_at', models.DateTimeField(auto_now_add=True, verbose_name='已读时间')),
            ],
            options={
                'verbose_name': '通知已读状态',
                'verbose_name_plural': '通知已读状态',
                'db_table': 'ops_notification_read',
                'ordering': ['-read_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='notificationread',
            unique_together={('user', 'alert_key')},
        ),
    ]
