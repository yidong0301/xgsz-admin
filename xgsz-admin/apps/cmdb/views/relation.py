#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置关系与拓扑：AssetRelation 增删查 + BFS 拓扑图。

定位：(asset_type, asset_id)。Server 的主键是字符串 instance_id，其余资产是自增主键。
"""
import logging

from django.db import IntegrityError
from django.db.models import Q
from rest_framework.views import APIView

from apps.cmdb.models import (AssetRelation, RELATION_TYPE_CHOICES, Server, GPUNode,
                              K8sCluster, NetworkSwitch, OpticalModule)
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission
from utils.pagination import MyPageNumberPagination

logger = logging.getLogger('default')

MODELS = {
    'server': Server,
    'gpu_node': GPUNode,
    'k8s_cluster': K8sCluster,
    'switch': NetworkSwitch,
    'optical_module': OpticalModule,
}
TYPE_LABEL = {
    'server': '服务器',
    'gpu_node': 'GPU 节点',
    'k8s_cluster': 'K8s 集群',
    'switch': '交换机',
    'optical_module': '光模块',
}
RELATION_LABEL = dict(RELATION_TYPE_CHOICES)
MAX_DEPTH = 3
# 单次拓扑最多返回的节点数：集群节点上百个时，前端 1 个叶子 1 行会把画布撑到上万像素
MAX_NODES = 150


def _can_write(user):
    return bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', '') in ('superadmin', 'admin')


def _get_asset(asset_type, asset_id):
    model = MODELS.get(asset_type)
    if not model or asset_id in (None, ''):
        return None
    try:
        return model.objects.filter(pk=asset_id).first()
    except Exception:
        return None


def _asset_stub(asset_type, asset_id, depth=0):
    """资产展示信息；资产已删除时返回 missing 占位，避免拓扑断链报错"""
    obj = _get_asset(asset_type, asset_id)
    type_label = TYPE_LABEL.get(asset_type, asset_type)
    if not obj:
        return {'type': asset_type, 'id': str(asset_id), 'depth': depth,
                'label': '%s#%s' % (type_label, asset_id), 'type_label': type_label,
                'missing': True, 'status': None, 'owner': None}
    return {
        'type': asset_type,
        'id': str(obj.pk),
        'depth': depth,
        'label': getattr(obj, 'hostname', None) or getattr(obj, 'name', None) or str(obj.pk),
        'type_label': type_label,
        'asset_no': getattr(obj, 'asset_no', None) or getattr(obj, 'instance_id', None),
        'status': getattr(obj, 'status', None),
        'owner': getattr(obj, 'owner', None),
        'location': getattr(obj, 'location', None),
        'missing': False,
    }


def _relation_row(r):
    return {
        'id': r.id,
        'source_type': r.source_type, 'source_id': r.source_id,
        'target_type': r.target_type, 'target_id': r.target_id,
        'source_label': _asset_stub(r.source_type, r.source_id)['label'],
        'target_label': _asset_stub(r.target_type, r.target_id)['label'],
        'relation_type': r.relation_type,
        'relation_label': RELATION_LABEL.get(r.relation_type, r.relation_type),
        'remark': r.remark,
        'created_by': r.created_by,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _audit(user, action, detail, result='成功'):
    try:
        from apps.ops.views import record_audit
        record_audit(getattr(user, 'name', None) or getattr(user, 'username', None), action,
                     resource='asset-relation', detail=detail, result=result)
    except Exception:
        pass


class RelationView(APIView):
    """GET 列表（可按资产过滤）/ POST 新增关系"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        qs = AssetRelation.objects.all()
        asset_type = request.query_params.get('type')
        asset_id = request.query_params.get('id')
        if asset_type and asset_id:
            qs = qs.filter(Q(source_type=asset_type, source_id=asset_id) |
                           Q(target_type=asset_type, target_id=asset_id))
        relation_type = request.query_params.get('relation_type')
        if relation_type:
            qs = qs.filter(relation_type=relation_type)
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return APIResponse(data=paginator.get_paginated_response([_relation_row(r) for r in page]).data)

    def post(self, request, *args, **kwargs):
        if not _can_write(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可维护资产关系')
        source_type = (request.data.get('source_type') or '').strip()
        target_type = (request.data.get('target_type') or '').strip()
        source_id = str(request.data.get('source_id') or '').strip()
        target_id = str(request.data.get('target_id') or '').strip()
        relation_type = (request.data.get('relation_type') or 'depends_on').strip()
        remark = (request.data.get('remark') or '')[:256]

        if source_type not in MODELS or target_type not in MODELS:
            return APIResponse(errcode=400, errmsg='资产类型不合法：%s / %s' % (source_type, target_type))
        if relation_type not in RELATION_LABEL:
            return APIResponse(errcode=400, errmsg='关系类型不合法：%s' % relation_type)
        if not source_id or not target_id:
            return APIResponse(errcode=400, errmsg='缺少源/目标资产 ID')
        if source_type == target_type and source_id == target_id:
            return APIResponse(errcode=400, errmsg='不能把资产关联到自己')
        if not _get_asset(source_type, source_id):
            return APIResponse(errcode=404, errmsg='源资产不存在：%s/%s' % (source_type, source_id))
        if not _get_asset(target_type, target_id):
            return APIResponse(errcode=404, errmsg='目标资产不存在：%s/%s' % (target_type, target_id))

        if AssetRelation.objects.filter(source_type=source_type, source_id=source_id,
                                        target_type=target_type, target_id=target_id,
                                        relation_type=relation_type).exists():
            return APIResponse(errcode=4090, errmsg='该关系已存在')

        try:
            rel = AssetRelation.objects.create(
                source_type=source_type, source_id=source_id,
                target_type=target_type, target_id=target_id,
                relation_type=relation_type, remark=remark,
                created_by=getattr(request.user, 'name', None) or getattr(request.user, 'username', None),
            )
        except IntegrityError:
            return APIResponse(errcode=4090, errmsg='该关系已存在')
        _audit(request.user, 'relation-create', '%s:%s -%s-> %s:%s' % (source_type, source_id, relation_type,
                                                                       target_type, target_id))
        return APIResponse(data=_relation_row(rel))


class RelationDetailView(APIView):
    """DELETE 删除关系"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def delete(self, request, pk, *args, **kwargs):
        if not _can_write(request.user):
            return APIResponse(errcode=403, errmsg='仅超级管理员/管理员可维护资产关系')
        rel = AssetRelation.objects.filter(pk=pk).first()
        if not rel:
            return APIResponse(errcode=404, errmsg='关系不存在')
        detail = '%s:%s -%s-> %s:%s' % (rel.source_type, rel.source_id, rel.relation_type,
                                        rel.target_type, rel.target_id)
        rel.delete()
        _audit(request.user, 'relation-delete', detail)
        return APIResponse(data={'deleted': True})


class TopologyView(APIView):
    """GET 以某个资产为中心的拓扑（BFS，depth 1-3）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        asset_type = request.query_params.get('type')
        asset_id = str(request.query_params.get('id') or '').strip()
        if asset_type not in MODELS:
            return APIResponse(errcode=400, errmsg='资产类型不合法：%s' % asset_type)
        if not asset_id:
            return APIResponse(errcode=400, errmsg='缺少资产 ID')
        if not _get_asset(asset_type, asset_id):
            return APIResponse(errcode=404, errmsg='资产不存在：%s/%s' % (asset_type, asset_id))
        try:
            depth = int(request.query_params.get('depth') or 2)
        except ValueError:
            depth = 2
        depth = max(1, min(depth, MAX_DEPTH))

        root = (asset_type, asset_id)
        depths = {root: 0}
        edges, seen = [], set()
        node_cut = False
        frontier = [root]
        while frontier and not node_cut:
            nxt = []
            for node in frontier:
                d = depths[node]
                if d >= depth:
                    continue
                rels = AssetRelation.objects.filter(
                    Q(source_type=node[0], source_id=node[1]) | Q(target_type=node[0], target_id=node[1]))
                for r in rels:
                    key = (r.source_type, r.source_id, r.target_type, r.target_id, r.relation_type)
                    goes_out = (r.source_type == node[0] and r.source_id == node[1])
                    other = (r.target_type, r.target_id) if goes_out else (r.source_type, r.source_id)
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            'id': r.id,
                            'from': {'type': r.source_type, 'id': r.source_id},
                            'to': {'type': r.target_type, 'id': r.target_id},
                            'relation_type': r.relation_type,
                            'relation_label': RELATION_LABEL.get(r.relation_type, r.relation_type),
                            'direction': 'out' if goes_out else 'in',
                        })
                    if other not in depths:
                        if len(depths) >= MAX_NODES:
                            node_cut = True
                            break
                        depths[other] = d + 1
                        nxt.append(other)
                if node_cut:
                    break
            frontier = nxt

        # 截断后丢掉一端不在结果里的边，避免前端画出悬空连线
        edges = [e for e in edges
                 if (e['from']['type'], e['from']['id']) in depths
                 and (e['to']['type'], e['to']['id']) in depths]

        nodes = [_asset_stub(t, i, depths[(t, i)]) for (t, i) in depths]
        nodes.sort(key=lambda n: (n['depth'], n['type'], n['label']))
        return APIResponse(data={
            'root': {'type': asset_type, 'id': asset_id},
            'depth': depth,
            'max_depth': MAX_DEPTH,
            'max_nodes': MAX_NODES,
            'node_truncated': node_cut,
            'nodes': nodes,
            'edges': edges,
            'truncated': any(v >= depth for v in depths.values()) and len(depths) > 1,
        })
