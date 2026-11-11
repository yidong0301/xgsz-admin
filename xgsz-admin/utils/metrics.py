#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K8s 指标读取（metrics-server）+ 资源量换算。

统一给「告警与自检」页面与采样任务使用：节点 CPU/内存使用率、Pod 用量 Top N。
"""
import logging
import os

from kubernetes import client
from kubernetes.client.rest import ApiException

from utils.k8s_client import core_v1, get_api_client

logger = logging.getLogger('default')


def cpu_milli(q):
    """K8s 数量转毫核：'201838822n'(纳核) / '2277u'(微核) / '250m' / '2'"""
    s = str(q or '').strip()
    try:
        if s.endswith('n'):
            return float(s[:-1]) / 1e6
        if s.endswith('u'):
            return float(s[:-1]) / 1e3
        if s.endswith('m'):
            return float(s[:-1])
        return float(s) * 1000.0
    except Exception:
        return 0.0


def mem_bytes(q):
    s = str(q or '').strip()
    units = {'Ki': 1024, 'Mi': 1024 ** 2, 'Gi': 1024 ** 3, 'Ti': 1024 ** 4,
             'K': 1000, 'M': 1000 ** 2, 'G': 1000 ** 3, 'T': 1000 ** 4}
    for u, m in units.items():
        if s.endswith(u):
            try:
                return int(float(s[:-len(u)]) * m)
            except Exception:
                return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def fmt_cpu(milli):
    return '%.2f 核' % (milli / 1000.0) if milli >= 100 else '%.0fm' % milli


def fmt_mem(b):
    for unit, size in (('Gi', 1024 ** 3), ('Mi', 1024 ** 2), ('Ki', 1024)):
        if b >= size:
            return '%.1f%s' % (b / float(size), unit)
    return '%dB' % b


def cluster_names():
    """可用集群：KUBECONFIG_DIR 下的 *.yaml，没有则用默认 kubeconfig（记为 default）"""
    base = os.getenv('KUBECONFIG_DIR', '/root/.kube/clusters')
    names = []
    try:
        if os.path.isdir(base):
            names = sorted(f[:-5] for f in os.listdir(base) if f.endswith('.yaml'))
    except Exception:
        names = []
    return names or ['default']


def _metrics_nodes(cluster):
    api = client.CustomObjectsApi(api_client=get_api_client(cluster if cluster != 'default' else None))
    data = api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'nodes')
    return (data or {}).get('items', [])


def node_usage(cluster=''):
    """节点用量：返回 (rows, error)；metrics-server 未安装时 error 有值"""
    label = cluster or 'default'
    kw = {} if label == 'default' else {'cluster': label}
    try:
        items = _metrics_nodes(label)
    except ApiException as e:
        if getattr(e, 'status', None) == 404:
            return [], '未安装 metrics-server（metrics.k8s.io/v1beta1 不可用）'
        return [], '指标读取失败：%s' % str(getattr(e, 'reason', '') or e)[:160]
    except Exception as e:
        return [], '指标读取失败：%s' % str(e)[:160]

    try:
        nodes = {n.metadata.name: n for n in core_v1(**kw).list_node().items}
    except Exception:
        nodes = {}

    rows = []
    for item in items:
        name = (item.get('metadata') or {}).get('name', '')
        usage = item.get('usage') or {}
        node = nodes.get(name)
        alloc = (node.status.allocatable if node and node.status else {}) or {}
        cpu_total = cpu_milli(alloc.get('cpu')) or 0.0
        mem_total = mem_bytes(alloc.get('memory')) or 0
        cpu = cpu_milli(usage.get('cpu'))
        mem = mem_bytes(usage.get('memory'))
        rows.append({
            'cluster': label,
            'name': name,
            'cpu': round(cpu / 1000.0, 2),
            'cpu_text': fmt_cpu(cpu),
            'cpu_total': round(cpu_total / 1000.0, 2),
            'cpu_total_text': fmt_cpu(cpu_total),
            'cpu_pct': round(cpu * 100.0 / cpu_total, 1) if cpu_total else None,
            'mem': mem,
            'mem_text': fmt_mem(mem),
            'mem_total': mem_total,
            'mem_total_text': fmt_mem(mem_total),
            'mem_pct': round(mem * 100.0 / mem_total, 1) if mem_total else None,
            'gpu': int(alloc.get('nvidia.com/gpu', 0) or 0),
        })
    rows.sort(key=lambda r: r['name'])
    return rows, ''


def pod_usage(cluster='', top=10):
    """Pod 用量 Top N（按 CPU 降序）"""
    label = cluster or 'default'
    api = client.CustomObjectsApi(api_client=get_api_client(None if label == 'default' else label))
    try:
        data = api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'pods')
    except Exception:
        return []
    rows = []
    for item in (data or {}).get('items', []):
        meta = item.get('metadata') or {}
        # Pod 用量在 containers[] 里（节点用量才是顶层 usage）
        cpu, mem = 0.0, 0
        for c in (item.get('containers') or []):
            u = c.get('usage') or {}
            cpu += cpu_milli(u.get('cpu'))
            mem += mem_bytes(u.get('memory'))
        if not cpu and not mem:
            usage = item.get('usage') or {}
            cpu, mem = cpu_milli(usage.get('cpu')), mem_bytes(usage.get('memory'))
        rows.append({
            'namespace': meta.get('namespace', ''),
            'name': meta.get('name', ''),
            'cpu': round(cpu / 1000.0, 3),
            'cpu_text': fmt_cpu(cpu),
            'mem_text': fmt_mem(mem),
            'cpu_pct_raw': cpu,
        })
    rows.sort(key=lambda r: r['cpu_pct_raw'], reverse=True)
    for r in rows:
        r.pop('cpu_pct_raw', None)
    return rows[:top]
