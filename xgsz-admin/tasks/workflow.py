#!/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import subprocess
from datetime import datetime

from xgsz_admin.celery import app
from apps.workflow.models import TaskExecution, PipelineExecution

logger = logging.getLogger('default')


def _run_command(command, timeout=60):
    """运行 shell 命令，返回 (returncode, output)"""
    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True,
                              timeout=timeout, encoding='utf-8', errors='replace')
        return proc.returncode, (proc.stdout or '') + (proc.stderr or '')
    except subprocess.TimeoutExpired:
        return -1, '命令执行超时'
    except Exception as e:
        return -1, '命令执行异常: %s' % str(e)


@app.task
def execute_task_template(execution_id):
    """执行任务编排模板（串行步骤，支持失败重试）"""
    execution = TaskExecution.objects.filter(id=execution_id).first()
    if not execution:
        return 'execution not found'

    template = execution.template
    try:
        steps = json.loads(template.steps) if template and template.steps else []
    except Exception:
        steps = []

    target = (getattr(template, 'target_type', 'local') or 'local') if template else 'local'
    cluster = (getattr(template, 'cluster', '') or 'kind') if template else 'kind'
    namespace = (getattr(template, 'namespace', '') or 'default') if template else 'default'
    execution.status = 'RUNNING'
    execution.target_type = target
    execution.cluster = cluster if target == 'k8s' else None
    execution.namespace = namespace if target == 'k8s' else None
    execution.started_at = datetime.now()
    execution.save()

    results = []
    full_log = []
    failed_count = 0
    full_log.append('执行方式：%s%s' % ('K8s Job（真实调度）' if target == 'k8s' else '本机执行（演示）',
                                    ('，目标 %s/%s' % (cluster, namespace)) if target == 'k8s' else ''))

    for i, step in enumerate(steps):
        name = step.get('name', '步骤%d' % (i + 1))
        command = step.get('command', '')
        retry = int(step.get('retry', 0) or 0)
        timeout = int(step.get('timeout', 60 if target == 'local' else 300) or 300)

        full_log.append('[步骤 %d/%d] %s: %s' % (i + 1, len(steps), name, command))

        ok, output, job_name = False, '', ''
        if target == 'k8s':
            from apps.workflow.k8s_job import run_step_job, StepJobError
            image = (step.get('image') or getattr(template, 'image', '') or 'nginx:alpine').strip()
            cpu = (step.get('cpu') or getattr(template, 'cpu', '') or '500m').strip()
            mem = (step.get('memory') or getattr(template, 'memory', '') or '256Mi').strip()
            gpu = step.get('gpu', getattr(template, 'gpu', 0))
            full_log.append('  镜像 %s · CPU %s · 内存 %s · GPU %s' % (image, cpu, mem, gpu))
            for attempt in range(retry + 1):
                try:
                    r = run_step_job(cluster=cluster, namespace=namespace, step_name=name,
                                     image=image, command=command, cpu=cpu, memory=mem,
                                     gpu=gpu, timeout=timeout)
                    ok, job_name = r['ok'], r['job']
                    output = 'Job %s（%s，%ss）\n%s' % (r['job'], r['phase'], r['elapsed'], r.get('output') or '')
                except StepJobError as e:
                    ok, output, job_name = False, str(e), ''
                except Exception as e:
                    logger.error('K8s 步骤执行异常: %s' % str(e))
                    ok, output, job_name = False, 'K8s 步骤执行异常：%s' % str(e)[:200], ''
                if ok or attempt >= retry:
                    break
                full_log.append('  失败，重试 %d/%d ...' % (attempt + 1, retry))
        else:
            rc = -1
            for attempt in range(retry + 1):
                rc, output = _run_command(command, timeout)
                if rc == 0:
                    break
                if attempt < retry:
                    full_log.append('  失败，重试 %d/%d ...' % (attempt + 1, retry))
            ok = (rc == 0)

        step_status = 'SUCCEEDED' if ok else 'FAILED'
        if step_status == 'FAILED':
            failed_count += 1

        results.append({'name': name, 'command': command, 'status': step_status,
                        'job': job_name, 'output': (output or '')[:2000]})
        full_log.append('  结果: %s' % step_status)
        if output:
            full_log.append(output[:2000])

    execution.steps_result = json.dumps(results, ensure_ascii=False)
    execution.log = '\n'.join(full_log)
    if failed_count == 0:
        execution.status = 'SUCCEEDED'
    elif failed_count == len(steps):
        execution.status = 'FAILED'
    else:
        execution.status = 'PARTIAL'
    execution.finished_at = datetime.now()
    execution.save()
    if execution.status in ('FAILED', 'PARTIAL'):
        try:
            from tasks.ops import send_webhook
            send_webhook('【芯光数智】任务编排执行异常：%s（状态 %s）' % (execution.name, execution.status))
        except Exception:
            pass
    return execution.status


@app.task
def execute_pipeline(pipeline_execution_id):
    """执行 CI/CD 流水线（阶段串行，失败即停）"""
    pe = PipelineExecution.objects.filter(id=pipeline_execution_id).first()
    if not pe:
        return 'execution not found'

    pipeline = pe.pipeline
    try:
        stages = json.loads(pipeline.stages) if pipeline and pipeline.stages else []
    except Exception:
        stages = []

    log = []
    failed = False
    for i, stage in enumerate(stages):
        name = stage.get('name', '阶段%d' % (i + 1))
        command = stage.get('command', '')
        log.append('[阶段 %d/%d] %s: %s' % (i + 1, len(stages), name, command))
        pe.status = 'BUILDING' if i == 0 else 'DEPLOYING'
        pe.save()
        rc, output = _run_command(command, 120)
        log.append('  结果: %s' % ('成功' if rc == 0 else '失败'))
        if output:
            log.append(output[:2000])
        if rc != 0:
            failed = True
            break

    pe.log = '\n'.join(log)
    pe.status = 'FAILED' if failed else 'SUCCEEDED'
    pe.finished_at = datetime.now()
    pe.save()
    if pe.status == 'FAILED':
        try:
            from tasks.ops import send_webhook
            send_webhook('【芯光数智】流水线执行失败：%s（版本 %s）' % (pe.name, pe.version or '-'))
        except Exception:
            pass
    return pe.status
