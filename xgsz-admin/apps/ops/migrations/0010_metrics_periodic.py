#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册指标采样定时任务（每分钟一次），用于趋势曲线。"""
from django.db import migrations

TASK_NAME = 'metrics_sample'
TASK_PATH = 'tasks.metrics.sample_node_metrics'


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    schedule, _ = IntervalSchedule.objects.get_or_create(every=60, period='seconds')
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={'task': TASK_PATH, 'interval': schedule, 'enabled': True},
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0009_metric_sample'),
        ('django_celery_beat', '0015_edit_solarschedule_events_choices'),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
