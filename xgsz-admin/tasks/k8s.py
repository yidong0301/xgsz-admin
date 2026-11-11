#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推理任务状态同步：Celery beat 每 15 秒调用一次。"""
import logging

from xgsz_admin.celery import app
from apps.k8s.models import InferenceTask
from apps.k8s.services import sync_status

logger = logging.getLogger('default')


@app.task
def sync_inference_tasks():
    tasks = InferenceTask.objects.filter(
        status__in=['SUBMITTED', 'RUNNING', 'PENDING']).order_by('id')[:200]
    synced = 0
    for task in tasks:
        try:
            sync_status(task)
            synced += 1
        except Exception as e:
            logger.warning('同步推理任务 %s 失败: %s' % (task.id, e))
    return synced
