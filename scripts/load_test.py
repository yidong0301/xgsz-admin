# -*- coding: utf-8 -*-
"""芯光数智平台 简单并发压测"""
import time
import concurrent.futures
import requests

BASE = 'http://127.0.0.1:8000'
N = 100          # 总请求数
CONCURRENCY = 20  # 并发线程数

# 登录拿 token
r = requests.post(BASE + '/api/account/v1/user/login',
                  json={'username': 'admin', 'password': 'admin123456'}, timeout=15)
token = r.json()['data']['token']
headers = {'Authorization': 'JWT ' + token}


def hit_dashboard(i):
    t0 = time.time()
    try:
        resp = requests.get(BASE + '/api/ops/v1/dashboard', headers=headers, timeout=20)
        return resp.status_code, time.time() - t0
    except Exception:
        return None, time.time() - t0


def hit_assets(i):
    t0 = time.time()
    try:
        resp = requests.get(BASE + '/api/cmdb/v1/asset?type=server', headers=headers, timeout=20)
        return resp.status_code, time.time() - t0
    except Exception:
        return None, time.time() - t0


for name, fn in [('数据看板', hit_dashboard), ('资产列表', hit_assets)]:
    results = []
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        for code, dur in ex.map(fn, range(N)):
            results.append((code, dur))
    total = time.time() - t0
    ok = sum(1 for c, _ in results if c == 200)
    ds = [d for _, d in results]
    avg = sum(ds) / len(ds) if ds else 0
    print('[%s] 请求 %d | 成功 %d | 失败 %d | 平均 %.3fs | 最大 %.3fs | QPS %.1f'
          % (name, N, ok, N - ok, avg, max(ds), N / total))
