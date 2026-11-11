# -*- coding: utf-8 -*-
"""真实推理任务演示：走平台 API，把「真的跑得起来」的推理任务下发到 K8s。

与之前写死状态的假任务不同，这里提交的任务：
  * 镜像 xgsz/infer-demo:1.1 里带着构建期在真实数据集上训练好的模型（sklearn MLP）；
  * BATCH 任务以 K8s Job 运行，真在容器里做推理，日志里是逐条预测/置信度/真实准确率；
  * SERVICE 任务以 Deployment + NodePort 运行 /predict，可真实调用在线打分。

用法（平台已启动、镜像已 load 进 kind）：
  python scripts/real_inference_demo.py            # 提交缺失任务 + 等结果 + 打印日志
  python scripts/real_inference_demo.py --list     # 只看现状
  python scripts/real_inference_demo.py --logs     # 只打印日志
环境变量：XGSZ_BASE（默认 http://localhost:8080）/ XGSZ_USER / XGSZ_PWD / XGSZ_CLUSTER / XGSZ_NS

镜像准备（只需一次）：
  cd k8s/infer-demo && docker build -t xgsz/infer-demo:1.1 .
  docker save xgsz/infer-demo:1.1 -o infer-demo.tar
  docker cp infer-demo.tar xgsz-k8s-control-plane:/root/infer-demo.tar
  docker exec xgsz-k8s-control-plane ctr -n k8s.io images import /root/infer-demo.tar
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get('XGSZ_BASE', 'http://localhost:8080').rstrip('/')
USER = os.environ.get('XGSZ_USER', 'admin')
PWD = os.environ.get('XGSZ_PWD', 'admin123456')
NS = os.environ.get('XGSZ_NS', 'xgsz-dev')
IMAGE = os.environ.get('XGSZ_INFER_IMAGE', 'xgsz/infer-demo:1.1')

TASKS = [
    {
        'name': '手写数字识别-批量推理（UCI digits 8×8）',
        'task_type': 'BATCH',
        'namespace': NS,
        'image': IMAGE,
        'command': ['python', '/infer/infer.py'],
        'args': ['--mode', 'batch', '--kind', 'digits'],
        'cpu': '1', 'memory': '1Gi', 'gpu': 0, 'timeout_seconds': 600,
        'desc': 'UCI 手写数字（8x8 真实灰度图）MLP，对留出测试集 360 张逐张真实推理',
    },
    {
        'name': '鸢尾花分类-批量推理（Fisher Iris）',
        'task_type': 'BATCH',
        'namespace': NS,
        'image': IMAGE,
        'command': ['python', '/infer/infer.py'],
        'args': ['--mode', 'batch', '--kind', 'iris'],
        'cpu': '1', 'memory': '1Gi', 'gpu': 0, 'timeout_seconds': 600,
        'desc': 'Fisher Iris 150 条真实样本，4 特征 3 分类，真实推理 30 条测试样本',
    },
    {
        'name': '手写数字识别-在线推理服务（NodePort）',
        'task_type': 'SERVICE',
        'namespace': NS,
        'image': IMAGE,
        'command': ['python', '/infer/infer.py'],
        'args': ['--mode', 'serve', '--port', '8080'],
        'cpu': '1', 'memory': '1Gi', 'gpu': 0, 'timeout_seconds': 3600,
        'replicas': 1, 'service_port': 8080, 'probe_port': 8080, 'probe_path': '/healthz',
        'desc': 'Deployment + NodePort，/healthz /info /predict 真实在线打分',
    },
]


def _req(method, path, token=None, body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'JWT ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def login():
    j = _req('POST', '/api/account/v1/user/login', body={'username': USER, 'password': PWD})
    if j.get('errcode') != 0:
        raise SystemExit('登录失败：%s' % j.get('errmsg'))
    return j['data']['token']


def list_tasks(token, keyword=''):
    q = urllib.parse.urlencode({'page': 1, 'pageSize': 100, 'keyword': keyword})
    j = _req('GET', '/api/k8s/v1/inference/task?' + q, token)
    if j.get('errcode') != 0:
        raise SystemExit('查询任务失败：%s' % j.get('errmsg'))
    return (j.get('data') or {}).get('results') or []


def detail(token, pk):
    j = _req('GET', '/api/k8s/v1/inference/task/%s' % pk, token)
    return j.get('data') or {}


def logs(token, pk):
    j = _req('GET', '/api/k8s/v1/inference/task/%s/logs' % pk, token, timeout=60)
    return (j.get('data') or {}).get('log') or ''


def submit(token, spec):
    body = {k: v for k, v in spec.items() if k != 'desc'}
    body['cluster'] = os.environ.get('XGSZ_CLUSTER', 'kind')
    body['owner'] = USER
    j = _req('POST', '/api/k8s/v1/inference/task', token, body)
    if j.get('errcode') != 0:
        raise SystemExit('提交失败：%s' % j.get('errmsg'))
    return j.get('data') or {}


def _wait(token, pk, stops, timeout):
    end = time.time() + timeout
    last = ''
    while time.time() < end:
        d = detail(token, pk)
        st = d.get('status')
        if st != last:
            print('  · #%s %s → %s' % (pk, d.get('name'), st), flush=True)
            last = st
        if st in stops:
            return d
        time.sleep(2 if 'RUNNING' in stops else 3)
    return detail(token, pk)


def wait_terminal(token, pk, timeout=180):
    return _wait(token, pk, ('SUCCEEDED', 'FAILED', 'STOPPED', 'SUBMIT_ERROR'), timeout)


def wait_running(token, pk, timeout=120):
    """在线服务：等 Deployment 至少 1 个副本可用（RUNNING）"""
    return _wait(token, pk, ('RUNNING', 'FAILED', 'SUBMIT_ERROR', 'STOPPED'), timeout)


def print_logs(token, d, tail=18):
    text = logs(token, d['id'])
    lines = [x for x in text.splitlines() if x.strip()]
    print('  日志 %s（Pod %s，共 %d 行）：' % (d.get('name'), d.get('pod_name') or '-', len(lines)))
    for line in lines[-tail:]:
        print('    ' + line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true', help='只列出现状')
    ap.add_argument('--logs', action='store_true', help='只打印任务日志')
    ap.add_argument('--timeout', type=int, default=180, help='等待任务就绪的最长秒数')
    args = ap.parse_args()

    token = login()
    existing = list_tasks(token)
    by_name = {}
    for t in existing:
        by_name.setdefault(t['name'], t)

    if args.list or args.logs:
        if not existing:
            print('当前没有任何推理任务（告警中心不会再出现假失败）')
            return 0
        for t in existing:
            print('#%-3s %-22s %-8s %-6s %-24s %s' % (
                t['id'], t['name'], t.get('task_type'), t.get('status'),
                t.get('image'), t.get('created_at', '')[:19]))
            if args.logs:
                print_logs(token, t)
        return 0

    created = []
    for spec in TASKS:
        t = by_name.get(spec['name'])
        if t:
            print('已存在：#%s %s（%s），跳过提交' % (t['id'], t['name'], t.get('status')))
            created.append(t)
            continue
        print('提交：%s（%s）…' % (spec['name'], spec['desc']))
        t = submit(token, spec)
        print('  · 已下发 #%s，K8s 资源 %s' % (t.get('id'), t.get('job_name')))
        created.append(t)

    print('\n等待任务就绪（最多 %d 秒）…' % args.timeout)
    ok = True
    for t in created:
        d = wait_running(token, t['id'], args.timeout) if t.get('task_type') == 'SERVICE' \
            else wait_terminal(token, t['id'], args.timeout)
        st = d.get('status')
        print('\n#%s %s → %s' % (d.get('id'), d.get('name'), st))
        if d.get('task_type') == 'SERVICE':
            print('  在线服务：NodePort %s（容器端口 %s）' % (d.get('node_port') or '-', d.get('service_port')))
            print('  健康检查：/healthz；推理接口：POST /predict')
        if st == 'SUCCEEDED' or (d.get('task_type') == 'SERVICE' and st == 'RUNNING'):
            print_logs(token, d)
        else:
            ok = False
            err = (d.get('error_msg') or '').strip()
            print('  未成功：%s %s' % (st, ('| ' + err[:200]) if err else ''))
            print_logs(token, d)
    print('\n结论：%s' % ('全部真实跑通 ✅' if ok else '有任务未成功，请查看日志 ❌'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
