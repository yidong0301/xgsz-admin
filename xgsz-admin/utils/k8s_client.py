#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 K8s 客户端：按集群名加载 kube/clusters/<name>.yaml，找不到直接失败。

所有需要访问 K8s 的模块（推理任务、节点、发布单）都应走这里，
避免各视图在模块导入时固定默认集群。
"""
import os
import re

from kubernetes import client, config

_CLIENTS = {}


def _safe(name):
    return re.sub(r'[^a-z0-9-]', '-', (name or '').lower()).strip('-')


def _kubeconfig_path(cluster):
    base = os.getenv('KUBECONFIG_DIR', '/root/.kube/clusters')
    if cluster:
        for name in (cluster, _safe(cluster)):
            path = os.path.join(base, '%s.yaml' % name)
            if os.path.exists(path):
                return path
        raise RuntimeError('未找到目标集群 kubeconfig：kube/clusters/%s.yaml' % cluster)
    # 未指定集群：沿用默认 kubeconfig（兼容旧任务）
    for path in (os.path.expanduser('~/.kube/config'), os.path.join(base, 'kind.yaml')):
        if os.path.exists(path):
            return path
    return None


def get_api_client(cluster=None):
    key = cluster or '__default__'
    if key in _CLIENTS:
        return _CLIENTS[key]
    cfg = client.Configuration()
    path = _kubeconfig_path(cluster)
    if path:
        config.load_kube_config(config_file=path, client_configuration=cfg)
    else:
        try:
            config.load_incluster_config(client_configuration=cfg)
        except Exception as e:
            raise RuntimeError('未找到可用 kubeconfig（cluster=%s）：%s' % (cluster or '默认', e))
    api = client.ApiClient(configuration=cfg)
    _CLIENTS[key] = api
    return api


def core_v1(cluster=None):
    return client.CoreV1Api(api_client=get_api_client(cluster))


def apps_v1(cluster=None):
    return client.AppsV1Api(api_client=get_api_client(cluster))


def batch_v1(cluster=None):
    return client.BatchV1Api(api_client=get_api_client(cluster))
