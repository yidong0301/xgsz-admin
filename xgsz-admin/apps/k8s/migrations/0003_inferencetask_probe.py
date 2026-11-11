# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('k8s', '0002_auto_20261105_1545'),
    ]

    operations = [
        migrations.AddField(
            model_name='inferencetask',
            name='probe_port',
            field=models.IntegerField(blank=True, null=True, verbose_name='存活探针端口',
                                      help_text='填写后生成 livenessProbe(httpGet)，假死自动重启'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='probe_path',
            field=models.CharField(blank=True, default='/healthz', max_length=128,
                                   null=True, verbose_name='存活探针路径'),
        ),
    ]
