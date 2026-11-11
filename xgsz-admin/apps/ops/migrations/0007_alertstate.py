# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0006_release_rollout'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlertState',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alert_key', models.CharField(max_length=64, unique=True, verbose_name='告警指纹')),
                ('title', models.CharField(max_length=256, verbose_name='告警标题')),
                ('status', models.CharField(choices=[('OPEN', '待认领'), ('ACKED', '已认领'), ('CLOSED', '已关闭')],
                                            default='OPEN', max_length=16, verbose_name='状态')),
                ('claimed_by', models.CharField(blank=True, max_length=64, null=True, verbose_name='认领人')),
                ('claimed_at', models.DateTimeField(blank=True, null=True, verbose_name='认领时间')),
                ('closed_by', models.CharField(blank=True, max_length=64, null=True, verbose_name='关闭人')),
                ('closed_at', models.DateTimeField(blank=True, null=True, verbose_name='关闭时间')),
                ('note', models.TextField(blank=True, null=True, verbose_name='处理结果')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '告警处理状态',
                'verbose_name_plural': '告警处理状态',
                'db_table': 'ops_alert_state',
                'ordering': ['-updated_at'],
            },
        ),
    ]
