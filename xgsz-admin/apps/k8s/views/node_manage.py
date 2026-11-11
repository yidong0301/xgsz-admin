#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节点/机器管理：列表、详情、cordon/uncordon、drain（Eviction + PDB）、标签/污点、CMDB 关联。

复用 utils.k8s_client，不再使用模块导入时固定的默认集群。
注意：kubernetes-python 12.0.1 只提供 policy/v1beta1 的 Eviction 模型，而 1.22+ 集群以
policy/v1 为准，因此驱逐与 PDB 读取都直接走 REST（call_api），避免被客户端版本限制。
"""
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone as dt_timezone

from kubernetes import client
from kubernetes.client.rest import ApiException
from rest_framework.views import APIView

from utils.authorization import MyAuthentication
from utils.permissions import MyPermission
from utils.http_response import APIResponse
from utils.k8s_client import core_v1, get_api_client

logger = logging.getLogger('default')

TAINT_EFFECTS = ('NoSchedule', 'PreferNoSchedule', 'NoExecute')

# 这些标签由 K8s/运行时维护，允许查看但不允许平台改写，避免把节点改坏
RESERVED_LABEL_PREFIXES = (
    'node-role.kubernetes.io/', 'kubernetes.io/', 'node.kubernetes.io/',
    'k8s.io/', 'beta.kubernetes.io/', 'pod-security.kubernetes.io/',
)

_LABEL_NAME = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$')
_DNS_SUBDOMAIN = re.compile(r'^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$')


# ---------------------------------------------------------------- 基础工具

def _is_admin(user):
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin')


def _audit(user, action, detail, result='成功'):
    try:
        from apps.ops.views import record_audit
        record_audit(getattr(user, 'name', None) or getattr(user, 'username', None), action,
                     resource='k8s-node', detail=detail, result=result)
    except Exception:
        pass


def _status_message(e):
    """从 ApiException 里取出可读原因（含 PDB 的 causes）"""
    body = getattr(e, 'body', None)
    if body:
        try:
            data = json.loads(body) if isinstance(body, str) else body
            msg = (data or {}).get('message') or ''
            causes = ((data or {}).get('details') or {}).get('causes') or []
            extra = '；'.join(c.get('message', '') for c in causes if c.get('message'))
            if extra:
                msg = (msg + ' ' + extra).strip()
            if msg:
                return msg
        except Exception:
            pass
    return str(getattr(e, 'reason', '') or e)


def _call(cluster, path, method='GET', body=None, path_params=None, content_type='application/json'):
    """直接调用 K8s REST（用于 policy/v1 Eviction / PDB 等客户端模型不全的接口）"""
    api = get_api_client(cluster)
    return api.call_api(
        path, method,
        path_params=path_params or {},
        query_params=[],
        header_params={'Accept': 'application/json', 'Content-Type': content_type},
        body=body,
        post_params=[], files={},
        response_type='object',
        auth_settings=['BearerToken'],
        _return_http_data_only=True,
    )


def _merge_patch_node(cluster, name, body):
    """JSON Merge Patch：数组整体替换、null 删除键。

    Node 的 spec.taints 在 Go 结构里没有 patchMergeKey，走 strategic-merge 会在
    列表项里报「unknown field $patch」；用 merge-patch 才是「整体替换」的语义。
    """
    return _call(cluster, '/api/v1/nodes/{name}', 'PATCH', body, {'name': name},
                 content_type='application/merge-patch+json')


def _age(ts):
    if not ts:
        return '-'
    try:
        now = datetime.now(dt_timezone.utc)
        days = int((now - ts).total_seconds() // 86400)
        return '%dd' % days if days else '%dh' % int((now - ts).total_seconds() // 3600)
    except Exception:
        return '-'


def _fmt_mem(v):
    """16336856Ki -> 15.6Gi"""
    try:
        s = str(v or '').strip()
        units = {'Ki': 1 / 1024 / 1024, 'Mi': 1 / 1024, 'Gi': 1.0, 'Ti': 1024.0,
                 'K': 1 / 1000 / 1000, 'M': 1 / 1000, 'G': 1.0}
        for u, f in units.items():
            if s.endswith(u):
                return '%.1fGi' % (float(s[:-len(u)]) * f)
        return s
    except Exception:
        return str(v or '')


def _cpu_milli(q):
    """'250m' -> 250.0；'2' -> 2000.0"""
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


def _mem_bytes(q):
    s = str(q or '').strip()
    units = {'Ki': 1024, 'Mi': 1024 ** 2, 'Gi': 1024 ** 3, 'Ti': 1024 ** 4,
             'K': 1000, 'M': 1000 ** 2, 'G': 1000 ** 3, 'T': 1000 ** 4}
    for u, m in units.items():
        if s.endswith(u):
            try:
                return float(s[:-len(u)]) * m
            except Exception:
                return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _fmt_cpu(milli):
    if milli >= 1000:
        return '%.1f' % (milli / 1000.0)
    return '%.0fm' % milli


def _fmt_bytes(n):
    for unit, size in (('Gi', 1024 ** 3), ('Mi', 1024 ** 2), ('Ki', 1024)):
        if n >= size:
            return '%.1f%s' % (n / float(size), unit)
    return '%.0f' % n


def _usage_payload(usage, node):
    """usage 来自 metrics.k8s.io，转成人类可读 + 占 allocatable 的百分比"""
    if not usage:
        return None
    alloc = node.status.allocatable or {}
    ac, am = _cpu_milli(alloc.get('cpu')), _mem_bytes(alloc.get('memory'))
    uc, um = _cpu_milli(usage.get('cpu')), _mem_bytes(usage.get('memory'))
    payload = {'cpu': _fmt_cpu(uc), 'memory': _fmt_bytes(um),
               'cpu_percent': round(uc * 100.0 / ac, 1) if ac else None,
               'memory_percent': round(um * 100.0 / am, 1) if am else None}
    return payload


def _metrics_map(cluster):
    """返回 (按节点名的 usage, 错误信息)；未安装 metrics-server 时给明确原因"""
    try:
        api = client.CustomObjectsApi(api_client=get_api_client(cluster))
        data = api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'nodes')
        return {i['metadata']['name']: i.get('usage', {}) for i in (data or {}).get('items', [])}, ''
    except ApiException as e:
        if getattr(e, 'status', None) == 404:
            return {}, '未安装 metrics-server（metrics.k8s.io/v1beta1 不可用）'
        return {}, '指标读取失败：%s' % _status_message(e)[:160]
    except Exception as e:
        return {}, '指标读取失败：%s' % str(e)[:160]


# ---------------------------------------------------------------- drain / PDB

def _selector_matches(selector, labels):
    """实现 PodDisruptionBudget 的 labelSelector 匹配（matchLabels + matchExpressions）"""
    selector = selector or {}
    labels = labels or {}
    match_labels = selector.get('matchLabels') or {}
    exprs = selector.get('matchExpressions') or []
    if not match_labels and not exprs:
        return False  # 空 selector 不选中任何 Pod
    for k, v in match_labels.items():
        if str(labels.get(k, '')) != str(v):
            return False
    for expr in exprs:
        key = expr.get('key')
        op = expr.get('operator')
        values = [str(v) for v in (expr.get('values') or [])]
        cur = labels.get(key)
        if op == 'In' and (cur is None or str(cur) not in values):
            return False
        elif op == 'NotIn' and cur is not None and str(cur) in values:
            return False
        elif op == 'Exists' and key not in labels:
            return False
        elif op == 'DoesNotExist' and key in labels:
            return False
    return True


def _list_pdbs(cluster):
    """读取全部 PodDisruptionBudget（policy/v1，旧集群回退 v1beta1）"""
    data = None
    for path in ('/apis/policy/v1/poddisruptionbudgets',
                 '/apis/policy/v1beta1/poddisruptionbudgets'):
        try:
            data = _call(cluster, path)
            break
        except Exception:
            continue
    rows = []
    for item in (data or {}).get('items', []):
        meta = item.get('metadata') or {}
        spec = item.get('spec') or {}
        status = item.get('status') or {}
        rows.append({
            'namespace': meta.get('namespace', ''),
            'name': meta.get('name', ''),
            'min_available': spec.get('minAvailable'),
            'max_unavailable': spec.get('maxUnavailable'),
            'current_healthy': status.get('currentHealthy', 0),
            'desired_healthy': status.get('desiredHealthy', 0),
            'disruptions_allowed': status.get('disruptionsAllowed', 0),
            'selector': spec.get('selector') or {},
        })
    return rows


def _pdb_plan(pdbs, pods):
    """算出哪些 PDB 命中这些 Pod；allowed < 命中数量 即为阻断"""
    matched = {}
    for p in pods:
        ns = p.metadata.namespace
        labels = p.metadata.labels or {}
        for pd in pdbs:
            if pd['namespace'] != ns:
                continue
            if not _selector_matches(pd.get('selector'), labels):
                continue
            key = '%s/%s' % (ns, pd['name'])
            matched.setdefault(key, dict(pd, pods=[]))['pods'].append(p.metadata.name)
    rows, blocks = [], []
    for row in matched.values():
        rows.append(row)
        if int(row.get('disruptions_allowed') or 0) < len(row['pods']):
            blocks.append(row)
    return rows, blocks


def _drain_targets(pods):
    """拆出可驱逐 Pod 与跳过 Pod（DaemonSet / 静态镜像 Pod / 已结束）"""
    targets, skipped = [], []
    for p in pods:
        refs = p.metadata.owner_references or []
        reasons = []
        if any(ref.kind == 'DaemonSet' for ref in refs):
            reasons.append('DaemonSet')
        if (p.metadata.annotations or {}).get('kubernetes.io/config.mirror'):
            reasons.append('静态 Pod')
        if p.status.phase in ('Succeeded', 'Failed'):
            reasons.append('已结束')
        if reasons:
            skipped.append({'namespace': p.metadata.namespace, 'name': p.metadata.name,
                            'reason': '、'.join(reasons)})
        else:
            targets.append(p)
    return targets, skipped


def _evict_pod(cluster, namespace, name, grace=30):
    """用 Eviction API 驱逐（尊重 PDB）。返回 (状态, 说明)

    状态：evicted / blocked(PDB 429) / gone(已不存在) / failed
    """
    body = {
        'apiVersion': 'policy/v1',
        'kind': 'Eviction',
        'metadata': {'name': name, 'namespace': namespace},
        'deleteOptions': {'gracePeriodSeconds': int(grace)},
    }
    try:
        _call(cluster, '/api/v1/namespaces/{namespace}/pods/{name}/eviction', 'POST', body,
              {'namespace': namespace, 'name': name})
        return 'evicted', ''
    except ApiException as e:
        status = getattr(e, 'status', None)
        if status == 429:
            return 'blocked', _status_message(e)
        if status == 404:
            return 'gone', 'Pod 已不存在'
        return 'failed', _status_message(e)
    except Exception as e:
        return 'failed', str(e)[:200]


# ---------------------------------------------------------------- CMDB 关联

_ASSET_FIELDS = ('instance_id', 'hostname', 'private_ip', 'owner', 'department', 'location',
                 'asset_no', 'environment', 'status', 'cpu', 'memory')


def _asset_index():
    """一次性读取服务器资产，按内网 IP / 主机名建索引（DB 异常不影响节点列表）"""
    idx = {'ip': {}, 'host': {}}
    try:
        from apps.cmdb.models import Server
        for row in Server.objects.all().values(*_ASSET_FIELDS):
            if row.get('private_ip'):
                idx['ip'].setdefault(str(row['private_ip']), row)
            if row.get('hostname'):
                idx['host'].setdefault(str(row['hostname']), row)
    except Exception as e:
        logger.warning('读取服务器资产失败（节点页将不显示资产信息）: %s' % str(e))
    return idx


def _find_asset(idx, name, ip):
    if ip and str(ip) in idx['ip']:
        return idx['ip'][str(ip)]
    if name and name in idx['host']:
        return idx['host'][name]
    return None


def _server_row(obj):
    """Server 对象 -> 与 _ASSET_FIELDS 对齐的 dict"""
    return dict((f, getattr(obj, f, None)) for f in _ASSET_FIELDS)


def _asset_payload(row):
    if not row:
        return None
    return {
        'instance_id': row.get('instance_id'),
        'asset_no': row.get('asset_no') or row.get('instance_id'),
        'hostname': row.get('hostname'),
        'owner': row.get('owner'),
        'department': row.get('department'),
        'location': row.get('location'),
        'environment': row.get('environment'),
        'status': row.get('status'),
        'private_ip': row.get('private_ip'),
        'cpu': row.get('cpu'),
        'memory': row.get('memory'),
    }


# ---------------------------------------------------------------- 校验

def _validate_label(key, value):
    key = (key or '').strip()
    value = '' if value is None else str(value)
    if not key:
        return False, '标签键不能为空'
    prefix, _, name = key.partition('/')
    if '/' in key:
        if not _DNS_SUBDOMAIN.match(prefix):
            return False, '标签前缀不合法：%s' % key
    else:
        name = prefix
    if not _LABEL_NAME.match(name or ''):
        return False, '标签键不合法：%s' % key
    if len(value) > 63 or (value and not _LABEL_NAME.match(value)):
        return False, '标签值不合法：%s=%s' % (key, value)
    return True, ''


def _validate_taint(key, value, effect):
    ok, msg = _validate_label(key, value)
    if not ok:
        return False, msg
    if effect not in TAINT_EFFECTS:
        return False, '污点效果必须是 %s 之一' % '/'.join(TAINT_EFFECTS)
    return True, ''


# ---------------------------------------------------------------- 序列化

def _node_row(node, pod_count=0, usage=None, asset=None):
    meta = node.metadata
    status = node.status
    ready = False
    for cond in (status.conditions or []):
        if cond.type == 'Ready':
            ready = cond.status == 'True'
    roles = [k.split('/')[-1] for k in (meta.labels or {}) if k.startswith('node-role.kubernetes.io/')]
    if not roles:
        roles = ['<none>']
    alloc = status.allocatable or {}
    internal_ip = ''
    for addr in (status.addresses or []):
        if addr.type == 'InternalIP':
            internal_ip = addr.address
    taints = [{'key': t.key, 'value': t.value, 'effect': t.effect} for t in (node.spec.taints or [])]
    return {
        'name': meta.name,
        'ready': ready,
        'status': 'Ready' if ready else 'NotReady',
        'roles': roles,
        'version': status.node_info.kubelet_version if status.node_info else '',
        'internal_ip': internal_ip,
        'cpu': alloc.get('cpu', ''),
        'memory': _fmt_mem(alloc.get('memory', '')),
        'gpu': int(alloc.get('nvidia.com/gpu', 0) or 0),
        'pods': pod_count,
        'unschedulable': bool(node.spec.unschedulable),
        'age': _age(meta.creation_timestamp),
        'taints': taints,
        'labels': meta.labels or {},
        'usage': _usage_payload(usage, node),
        'asset': _asset_payload(asset),
    }


def _pod_rows(pods):
    rows = []
    for p in pods:
        restarts = sum((c.restart_count or 0) for c in (p.status.container_statuses or []))
        rows.append({
            'name': p.metadata.name,
            'namespace': p.metadata.namespace,
            'phase': p.status.phase,
            'ready': all(c.ready for c in (p.status.container_statuses or [])) if p.status.container_statuses else False,
            'restarts': restarts,
            'age': _age(p.metadata.creation_timestamp),
            'daemonset': any(ref.kind == 'DaemonSet' for ref in (p.metadata.owner_references or [])),
            'labels': p.metadata.labels or {},
        })
    return rows


def _node_pods(cluster, node_name):
    try:
        return core_v1(cluster).list_pod_for_all_namespaces(
            field_selector='spec.nodeName=%s' % node_name).items
    except Exception:
        return []


def _read_node(core, name):
    return core.read_node(name=name)


# ---------------------------------------------------------------- 视图

class ManagedNodeListView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        cluster = request.query_params.get('cluster') or ''
        try:
            core = core_v1(cluster)
            nodes = core.list_node().items
            pods = core.list_pod_for_all_namespaces().items
        except Exception as e:
            return APIResponse(errcode=4090, errmsg='集群不可用（%s）：%s' % (cluster or '默认', str(e)[:200]))
        counts = Counter(p.spec.node_name for p in pods)
        metrics, metrics_error = _metrics_map(cluster)
        assets = _asset_index()
        rows = []
        for n in nodes:
            ip = ''
            for addr in (n.status.addresses or []):
                if addr.type == 'InternalIP':
                    ip = addr.address
            rows.append(_node_row(n, counts.get(n.metadata.name, 0),
                                  metrics.get(n.metadata.name),
                                  _find_asset(assets, n.metadata.name, ip)))
        rows.sort(key=lambda x: x['name'])
        return APIResponse(data={'cluster': cluster, 'nodes': rows,
                                 'metrics': {'available': bool(metrics), 'error': metrics_error}})


class ManagedNodeDetailView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        cluster = request.query_params.get('cluster') or ''
        name = request.query_params.get('name') or ''
        if not name:
            return APIResponse(errcode=400, errmsg='缺少节点名')
        try:
            core = core_v1(cluster)
            node = core.read_node(name=name)
            pods = _node_pods(cluster, name)
            try:
                events = core.list_event_for_all_namespaces(
                    field_selector='involvedObject.name=%s' % name).items
            except Exception:
                events = []
        except Exception as e:
            return APIResponse(errcode=404, errmsg='节点读取失败：%s' % str(e)[:200])
        conditions = [{'type': c.type, 'status': c.status, 'reason': c.reason,
                       'message': c.message, 'last_transition': c.last_transition_time.strftime('%Y-%m-%d %H:%M:%S')
                       if c.last_transition_time else ''} for c in (node.status.conditions or [])]

        metrics, metrics_error = _metrics_map(cluster)
        usage = metrics.get(name, {})
        pdbs, _blocks = _pdb_plan(_list_pdbs(cluster), pods)
        ip = ''
        for addr in (node.status.addresses or []):
            if addr.type == 'InternalIP':
                ip = addr.address
        assets = _asset_index()
        reserved = [{'key': k, 'value': v} for k, v in (node.metadata.labels or {}).items()
                    if any(k.startswith(p) for p in RESERVED_LABEL_PREFIXES)]
        targets, skipped = _drain_targets(pods)
        return APIResponse(data={
            'node': _node_row(node, len(pods), usage, _find_asset(assets, name, ip)),
            'conditions': conditions,
            'pods': sorted(_pod_rows(pods), key=lambda x: (x['namespace'], x['name'])),
            'events': [{'type': e.type, 'reason': e.reason, 'message': e.message,
                        'last_seen': e.last_timestamp.strftime('%Y-%m-%d %H:%M:%S') if e.last_timestamp else ''}
                       for e in sorted(events, key=lambda x: x.last_timestamp or datetime.min.replace(tzinfo=dt_timezone.utc),
                                       reverse=True)[:50]],
            'usage': _usage_payload(usage, node),
            'metrics': {'available': bool(usage), 'error': metrics_error},
            'pdbs': pdbs,
            'reserved_labels': reserved,
            'drain': {
                'targets': [{'namespace': p.metadata.namespace, 'name': p.metadata.name} for p in targets],
                'skipped': skipped,
            },
        })


class ManagedNodeCordonView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可修改调度状态')
        cluster = request.data.get('cluster') or ''
        name = request.data.get('name') or ''
        unschedulable = bool(request.data.get('unschedulable', True))
        if not name:
            return APIResponse(errcode=400, errmsg='缺少节点名')
        try:
            core = core_v1(cluster)
            node = core.read_node(name=name)
            node.spec.unschedulable = unschedulable
            core.patch_node(name=name, body=node)
            _audit(request.user, 'cordon' if unschedulable else 'uncordon',
                   '%s/%s' % (cluster or '默认', name))
            return APIResponse(data={'name': name, 'unschedulable': unschedulable})
        except Exception as e:
            _audit(request.user, 'cordon', '%s/%s 失败：%s' % (cluster or '默认', name, str(e)[:160]), result='失败')
            return APIResponse(errcode=5001, errmsg='修改节点调度状态失败：%s' % str(e)[:200])


class ManagedNodeDrainView(APIView):
    """排空节点：先做 PDB 预检，再用 Eviction API 驱逐（尊重 PDB），最后保持 cordon"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可排空节点')
        cluster = request.data.get('cluster') or ''
        name = request.data.get('name') or ''
        dry_run = bool(request.data.get('dry_run', False))
        grace = int(request.data.get('grace_period', 30) or 30)
        if not name:
            return APIResponse(errcode=400, errmsg='缺少节点名')
        try:
            core = core_v1(cluster)
            node = _read_node(core, name)
            pods = _node_pods(cluster, name)
        except Exception as e:
            return APIResponse(errcode=404, errmsg='节点不可用（%s/%s）：%s' % (cluster or '默认', name, str(e)[:200]))

        targets, skipped = _drain_targets(pods)
        pdbs, blocks = _pdb_plan(_list_pdbs(cluster), targets)
        target_names = ['%s/%s' % (p.metadata.namespace, p.metadata.name) for p in targets]
        base = {'node': name, 'pods': target_names, 'count': len(targets),
                'skipped': skipped, 'pdbs': pdbs, 'blocked_by_pdb': blocks}

        if dry_run:
            return APIResponse(data=dict(base, dry_run=True))

        if blocks:
            detail = '；'.join('%s/%s（允许中断 %s，需驱逐 %d）' % (b['namespace'], b['name'],
                                                              b['disruptions_allowed'], len(b['pods']))
                              for b in blocks)
            _audit(request.user, 'drain', '%s/%s 被 PDB 阻止：%s' % (cluster or '默认', name, detail), result='失败')
            return APIResponse(errcode=5003, errmsg='PodDisruptionBudget 阻止驱逐：%s' % detail,
                               data=dict(base, evicted=[], blocked=[], failed=[], aborted=None))

        # 预检通过后再 cordon，避免「排空失败但节点已被禁止调度」
        try:
            node.spec.unschedulable = True
            core.patch_node(name=name, body=node)
        except Exception as e:
            return APIResponse(errcode=5001, errmsg='设置不可调度失败：%s' % str(e)[:200])

        evicted, blocked, failed = [], [], []
        aborted = None
        idx = 0
        for p in targets:
            idx += 1
            state, msg = _evict_pod(cluster, p.metadata.namespace, p.metadata.name, grace)
            item = {'namespace': p.metadata.namespace, 'name': p.metadata.name}
            if state in ('evicted', 'gone'):
                evicted.append(item)
            elif state == 'blocked':
                blocked.append(dict(item, reason=msg))
                aborted = idx
                break
            else:
                failed.append(dict(item, reason=msg))

        remaining = [{'namespace': p.metadata.namespace, 'name': p.metadata.name}
                     for p in targets[(aborted or len(targets)):]]
        data = dict(base, unschedulable=True, evicted=evicted, deleted=len(evicted),
                    blocked=blocked, failed=failed, aborted=aborted, remaining=remaining)

        if blocked:
            _audit(request.user, 'drain',
                   '%s/%s 驱逐 %d 个后被 PDB 阻止：%s' % (cluster or '默认', name, len(evicted),
                                                   blocked[0].get('reason', '')[:120]), result='失败')
            return APIResponse(errcode=5003, errmsg='驱逐过程中被 PDB 阻止：%s' % blocked[0].get('reason', ''),
                               data=data)
        if failed:
            _audit(request.user, 'drain', '%s/%s 驱逐 %d 个，%d 个失败' % (cluster or '默认', name,
                                                                    len(evicted), len(failed)), result='失败')
            return APIResponse(errcode=5001, errmsg='%d 个 Pod 驱逐失败：%s' % (
                len(failed), failed[0].get('reason', '')), data=data)

        _audit(request.user, 'drain', '%s/%s 驱逐 %d 个 Pod（Eviction，尊重 PDB）' % (cluster or '默认', name,
                                                                              len(evicted)))
        return APIResponse(data=data)


class ManagedNodeLabelsView(APIView):
    """编辑节点标签：labels 为要设置的键值对，remove 为要删除的键（K8s 保留标签不可改）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可修改节点标签')
        cluster = request.data.get('cluster') or ''
        name = request.data.get('name') or ''
        payload = request.data.get('labels') or {}
        remove = request.data.get('remove') or []
        if not name:
            return APIResponse(errcode=400, errmsg='缺少节点名')
        if not isinstance(payload, dict) or not isinstance(remove, list):
            return APIResponse(errcode=400, errmsg='labels 必须是对象，remove 必须是数组')

        body, errors = {}, []
        for k, v in payload.items():
            ok, msg = _validate_label(k, v)
            if not ok:
                errors.append(msg)
                continue
            if any(str(k).startswith(p) for p in RESERVED_LABEL_PREFIXES):
                errors.append('保留标签不可修改：%s' % k)
                continue
            body[str(k).strip()] = '' if v is None else str(v)
        for k in remove:
            k = str(k or '').strip()
            if not k:
                continue
            if any(k.startswith(p) for p in RESERVED_LABEL_PREFIXES):
                errors.append('保留标签不可删除：%s' % k)
                continue
            body[k] = None
        if errors:
            return APIResponse(errcode=4000, errmsg='；'.join(errors[:5]))
        if not body:
            return APIResponse(errcode=4000, errmsg='没有需要变更的标签')

        try:
            core = core_v1(cluster)
            _merge_patch_node(cluster, name, {'metadata': {'labels': body}})
            labels = core.read_node(name=name).metadata.labels or {}
            added = [k for k, v in body.items() if v is not None]
            removed = [k for k, v in body.items() if v is None]
            _audit(request.user, 'node-labels',
                   '%s/%s 设置 %s；删除 %s' % (cluster or '默认', name, ','.join(added) or '-',
                                          ','.join(removed) or '-'))
            return APIResponse(data={'labels': labels, 'added': added, 'removed': removed})
        except ApiException as e:
            _audit(request.user, 'node-labels', '%s/%s 失败：%s' % (cluster or '默认', name, str(e)[:160]),
                   result='失败')
            return APIResponse(errcode=5001, errmsg='修改标签失败：%s' % _status_message(e)[:200])
        except Exception as e:
            return APIResponse(errcode=5001, errmsg='修改标签失败：%s' % str(e)[:200])


class ManagedNodeTaintsView(APIView):
    """整体替换节点污点：taints=[{key,value,effect}]（传空数组即清空）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可修改节点污点')
        cluster = request.data.get('cluster') or ''
        name = request.data.get('name') or ''
        taints = request.data.get('taints')
        if not name:
            return APIResponse(errcode=400, errmsg='缺少节点名')
        if not isinstance(taints, list):
            return APIResponse(errcode=400, errmsg='taints 必须是数组')

        desired, errors = {}, []
        for t in taints:
            if not isinstance(t, dict):
                errors.append('污点格式不正确')
                continue
            key = str(t.get('key') or '').strip()
            value = '' if t.get('value') is None else str(t.get('value'))
            effect = str(t.get('effect') or '').strip()
            ok, msg = _validate_taint(key, value, effect)
            if not ok:
                errors.append(msg)
                continue
            if key in desired:
                errors.append('污点键重复：%s' % key)
                continue
            desired[key] = {'key': key, 'value': value, 'effect': effect}
        if errors:
            return APIResponse(errcode=4000, errmsg='；'.join(errors[:5]))

        try:
            core = core_v1(cluster)
            node = core.read_node(name=name)
            current = [{'key': t.key, 'value': t.value or '', 'effect': t.effect}
                       for t in (node.spec.taints or [])]
            desired_rows = list(desired.values())
            if current == desired_rows:
                return APIResponse(data={'taints': current, 'changed': False})
            _merge_patch_node(cluster, name, {'spec': {'taints': desired_rows}})
            final = core.read_node(name=name).spec.taints or []
            _audit(request.user, 'node-taints', '%s/%s 污点改为 %s' % (
                cluster or '默认', name,
                ','.join('%s=%s:%s' % (t.key, t.value or '', t.effect) for t in final) or '（空）'))
            return APIResponse(data={'taints': [{'key': t.key, 'value': t.value, 'effect': t.effect}
                                                for t in final], 'changed': True})
        except ApiException as e:
            _audit(request.user, 'node-taints', '%s/%s 失败：%s' % (cluster or '默认', name, str(e)[:160]),
                   result='失败')
            return APIResponse(errcode=5001, errmsg='修改污点失败：%s' % _status_message(e)[:200])
        except Exception as e:
            return APIResponse(errcode=5001, errmsg='修改污点失败：%s' % str(e)[:200])


class ManagedNodeRegisterAssetView(APIView):
    """把节点一键登记为 CMDB 服务器资产（已存在则返回已有资产）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可登记资产')
        cluster = request.data.get('cluster') or ''
        name = request.data.get('name') or ''
        if not name:
            return APIResponse(errcode=400, errmsg='缺少节点名')
        try:
            core = core_v1(cluster)
            node = core.read_node(name=name)
        except Exception as e:
            return APIResponse(errcode=404, errmsg='节点读取失败：%s' % str(e)[:200])

        ip = ''
        for addr in (node.status.addresses or []):
            if addr.type == 'InternalIP':
                ip = addr.address

        try:
            from apps.cmdb.models import Server
            from apps.cmdb.views.asset import generate_asset_no, record_change
            from django.db import IntegrityError
        except Exception as e:
            return APIResponse(errcode=5001, errmsg='资产模块不可用：%s' % str(e)[:160])

        existing = None
        if ip:
            existing = Server.objects.filter(private_ip=ip).first()
        if not existing:
            existing = Server.objects.filter(hostname=name).first()
        if existing:
            return APIResponse(errcode=4090, errmsg='该节点已关联资产 %s' % existing.instance_id,
                               data={'asset': _asset_payload(_server_row(existing))})

        alloc = node.status.allocatable or {}
        info = node.status.node_info
        operator = getattr(request.user, 'name', None) or getattr(request.user, 'username', None)
        try:
            obj = Server.objects.create(
                instance_id=generate_asset_no('SRV'),
                hostname=name[:64],
                private_ip=ip or None,
                cpu=int(round(_cpu_milli(alloc.get('cpu')) / 1000.0)) or None,
                memory=int(round(_mem_bytes(alloc.get('memory')) / 1024.0 ** 3)) or None,
                os_name=(getattr(info, 'os_image', '') or '')[:64] or None,
                os_type=(getattr(info, 'operating_system', '') or '')[:16] or None,
                cloud_type='server',
                status='Running',
                environment='test' if (node.metadata.labels or {}).get('xgsz.io/env') == 'test' else 'prod',
                comment=('节点登记 %s/%s' % (cluster or '默认', name))[:64],
            )
        except IntegrityError as e:
            return APIResponse(errcode=5001, errmsg='登记失败（主键冲突）：%s' % str(e)[:160])
        except Exception as e:
            return APIResponse(errcode=5001, errmsg='登记失败：%s' % str(e)[:200])

        record_change('server', obj.instance_id, obj.instance_id, 'create', operator,
                      field='source', new='k8s-node:%s/%s' % (cluster or '默认', name))
        _audit(request.user, 'node-asset-register', '%s/%s -> %s' % (cluster or '默认', name, obj.instance_id))
        return APIResponse(data={'asset': _asset_payload(_server_row(obj))})
