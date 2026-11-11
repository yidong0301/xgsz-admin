#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务编排的 K8s Job 执行器（真实调度 + 资源分配）。

每个步骤 = 一个 Job：指定镜像 / 命令 / CPU / 内存 / GPU，带超时与 TTL，
执行完读取 Pod 日志作为步骤输出；不再在 backend 容器里跑 shell。
"""
import json
import logging
import re
import time
import uuid

from kubernetes import client
from kubernetes.client.rest import ApiException

from utils.k8s_client import batch_v1, core_v1

logger = logging.getLogger('default')

JOB_LABEL = 'xgsz-workflow'


class StepJobError(Exception):
    pass


def _safe(name):
    s = re.sub(r'[^a-z0-9-]', '-', (name or '').lower()).strip('-')
    return (s or 'step')[:36]


def _command_parts(cmd):
    """支持 JSON 数组（完整覆盖 entrypoint）或 shell 字符串（sh -c）"""
    cmd = (cmd or '').strip()
    if not cmd:
        return ['/bin/sh', '-c', 'echo "（空命令）"']
    if cmd.startswith('['):
        try:
            parts = json.loads(cmd)
            if isinstance(parts, list) and parts:
                return [str(x) for x in parts]
        except Exception:
            pass
    return ['/bin/sh', '-c', cmd]


def _resources(cpu, memory, gpu):
    limits = {}
    if cpu:
        limits['cpu'] = str(cpu)
    if memory:
        limits['memory'] = str(memory)
    try:
        n = int(gpu or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        limits['nvidia.com/gpu'] = str(n)
    if not limits:
        return None
    return client.V1ResourceRequirements(requests=dict(limits), limits=dict(limits))


def _job_pod_name(cluster, namespace, job_name):
    try:
        pods = core_v1(cluster).list_namespaced_pod(
            namespace, label_selector='job-name=%s' % job_name).items
    except Exception:
        return None
    return pods[0].metadata.name if pods else None


def _pod_output(cluster, namespace, job_name):
    """取 Job 的 Pod 日志；拿不到就返回空串（不让日志影响结果判断）"""
    pod = _job_pod_name(cluster, namespace, job_name)
    if not pod:
        return ''
    try:
        return core_v1(cluster).read_namespaced_pod_log(
            name=pod, namespace=namespace, container='step', tail_lines=500) or ''
    except Exception:
        return ''


BAD_WAITING = ('ImagePullBackOff', 'ErrImagePull', 'InvalidImageName', 'CrashLoopBackOff',
               'CreateContainerConfigError', 'CreateContainerError')


def _pod_problem(cluster, namespace, job_name):
    """容器卡住的原因（镜像拉不到 / 配置错误等）：返回 (原因, 详情)，正常则 ('','')"""
    try:
        pods = core_v1(cluster).list_namespaced_pod(
            namespace, label_selector='job-name=%s' % job_name).items
    except Exception:
        return '', ''
    for p in pods:
        for cs in (p.status.container_statuses or []):
            waiting = getattr(cs.state, 'waiting', None) if cs.state else None
            if waiting and waiting.reason in BAD_WAITING:
                return waiting.reason, (waiting.message or '')[:400]
    return '', ''


def run_step_job(cluster='kind', namespace='default', step_name='step', image='nginx:alpine',
                 command='', cpu='500m', memory='256Mi', gpu=0, timeout=300):
    """创建 Job 并等待结束，返回 dict(ok, output, job, phase, elapsed, message)"""
    namespace = (namespace or 'default').strip() or 'default'
    image = (image or '').strip() or 'nginx:alpine'
    timeout = max(int(timeout or 300), 10)
    job_name = 'xgsz-wf-%s-%s' % (_safe(step_name), uuid.uuid4().hex[:6])

    container = client.V1Container(
        name='step',
        image=image,
        command=_command_parts(command),
        resources=_resources(cpu, memory, gpu),
    )
    body = client.V1Job(
        api_version='batch/v1',
        kind='Job',
        metadata=client.V1ObjectMeta(
            name=job_name, namespace=namespace,
            labels={'app': JOB_LABEL, 'xgsz.io/step': _safe(step_name)},
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=timeout,
            ttl_seconds_after_finished=3600,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={'app': JOB_LABEL, 'job-name': job_name}),
                spec=client.V1PodSpec(restart_policy='Never', containers=[container]),
            ),
        ),
    )

    started = time.time()
    try:
        batch_v1(cluster).create_namespaced_job(namespace=namespace, body=body)
    except ApiException as e:
        msg = ''
        try:
            msg = json.loads(e.body).get('message', '')
        except Exception:
            msg = str(e)
        raise StepJobError('创建 Job 失败（%s/%s）：%s' % (cluster, namespace, msg[:200]))

    api = batch_v1(cluster)
    phase, ok = 'Running', False
    problem = ('', '')
    deadline = started + timeout + 60
    while time.time() < deadline:
        time.sleep(3)
        try:
            job = api.read_namespaced_job_status(name=job_name, namespace=namespace)
        except ApiException as e:
            raise StepJobError('查询 Job 状态失败：%s' % str(e)[:160])
        for cond in (job.status.conditions or []):
            if cond.type == 'Complete' and cond.status == 'True':
                ok, phase = True, 'Succeeded'
                break
            if cond.type == 'Failed' and cond.status == 'True':
                ok, phase = False, 'Failed'
                break
        if phase != 'Running':
            break
        # 镜像拉不到 / 容器起不来：立即失败并给出原因，不白等到超时
        reason, detail = _pod_problem(cluster, namespace, job_name)
        if reason:
            phase, ok, problem = reason, False, (reason, detail)
            break

    output = _pod_output(cluster, namespace, job_name)
    if problem[0]:
        output = ('容器无法启动：%s\n%s\n' % (problem[0], problem[1])) + output
    elapsed = round(time.time() - started, 1)
    if phase == 'Running':
        phase = 'Timeout'
    return {
        'ok': ok,
        'output': output,
        'job': job_name,
        'phase': phase,
        'elapsed': elapsed,
        'message': ('步骤完成（%s）' % phase) if phase != 'Timeout' else '步骤超时（%ss）' % timeout,
    }
