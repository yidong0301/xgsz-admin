#!/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
from datetime import date

import requests
from decouple import config

from xgsz_admin.celery import app

logger = logging.getLogger('default')


def send_webhook(content):
    """发送钉钉/企微机器人消息，返回是否成功"""
    webhook = config('NOTIFY_WEBHOOK_URL', default='')
    if not webhook:
        return False
    try:
        payload = {'msgtype': 'text', 'text': {'content': content}}
        resp = requests.post(webhook, json=payload, timeout=10)
        return resp.status_code == 200 and resp.json().get('errcode', 0) == 0
    except Exception as e:
        logger.warning('webhook 推送失败: %s' % str(e))
        return False


@app.task
def run_inspection():
    """定时巡检：采集节点/任务状态，标记异常并推送"""
    from apps.cmdb.models import Server, GPUNode, NetworkSwitch, OpticalModule
    from apps.k8s.models import InferenceTask
    from apps.workflow.models import TaskExecution, PipelineExecution
    from apps.ops.models import InspectionRecord

    anomalies = []
    for s in Server.objects.filter(status='Stopped'):
        anomalies.append('服务器已停机：%s' % (s.hostname or s.instance_id))
    for t in InferenceTask.objects.filter(status__in=['FAILED', 'SUBMIT_ERROR']):
        anomalies.append('推理任务失败：%s' % t.name)
    for e in TaskExecution.objects.filter(status__in=['FAILED', 'PARTIAL'])[:5]:
        anomalies.append('任务编排异常：%s' % e.name)
    for e in PipelineExecution.objects.filter(status='FAILED')[:5]:
        anomalies.append('流水线失败：%s' % e.name)

    today = date.today()
    for g in list(GPUNode.objects.filter(warranty_expire__isnull=False)) + \
             list(NetworkSwitch.objects.filter(warranty_expire__isnull=False)) + \
             list(OpticalModule.objects.filter(warranty_expire__isnull=False)):
        if g.warranty_expire and (g.warranty_expire - today).days <= 30:
            anomalies.append('维保即将到期：%s' % g.name)

    status = 'WARNING' if anomalies else 'HEALTHY'
    InspectionRecord.objects.create(status=status, anomaly_count=len(anomalies),
                                    anomalies=json.dumps(anomalies, ensure_ascii=False))
    if anomalies:
        content = '【芯光数智】定时巡检发现 %d 条异常：\n%s' % (len(anomalies), '\n'.join(anomalies[:10]))
        send_webhook(content)
    return status
