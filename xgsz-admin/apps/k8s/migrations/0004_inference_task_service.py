# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('k8s', '0003_inferencetask_probe'),
    ]

    operations = [
        migrations.AddField(
            model_name='inferencetask',
            name='cluster',
            field=models.CharField(blank=True, default='', max_length=64, verbose_name='目标集群',
                                   help_text='kube/clusters/<集群名>.yaml；为空时用默认集群'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='task_type',
            field=models.CharField(choices=[('SERVICE', '在线服务'), ('BATCH', '批任务')], default='BATCH',
                                   max_length=16, verbose_name='任务形态'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='env_vars',
            field=models.TextField(blank=True, null=True, verbose_name='环境变量',
                                   help_text='JSON 对象，如 {"A":"1"}'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='service_name',
            field=models.CharField(blank=True, max_length=128, null=True, verbose_name='K8s Service 名'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='service_port',
            field=models.IntegerField(default=80, verbose_name='服务端口'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='node_port',
            field=models.IntegerField(blank=True, null=True, verbose_name='NodePort'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='replicas',
            field=models.IntegerField(default=1, verbose_name='副本数'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='timeout_seconds',
            field=models.IntegerField(default=3600, verbose_name='超时秒数'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='image_pull_secret',
            field=models.CharField(blank=True, max_length=128, null=True, verbose_name='镜像拉取密钥'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='failure_reason',
            field=models.TextField(blank=True, null=True, verbose_name='失败原因'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='exit_code',
            field=models.IntegerField(blank=True, null=True, verbose_name='退出码'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='last_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='最近同步时间'),
        ),
        migrations.AlterField(
            model_name='inferencetask',
            name='job_name',
            field=models.CharField(blank=True, max_length=128, null=True, verbose_name='K8s 资源名'),
        ),
    ]
