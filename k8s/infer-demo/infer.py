#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""芯光数智 · 真实推理运行时（CPU，无假数据）。

两种形态：
  batch  批量推理：加载构建期训练的真实模型，对留出测试集的真实样本逐条推理，
         打印每条的预测/置信度、真实准确率、单条延迟与吞吐，结束码 0。
  serve  在线推理：HTTP 服务，/healthz、/info、/predict，真实模型在线打分。

模型来自 /models（构建期由 train.py 在真实数据集上训练并落盘）。
"""
import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import joblib
import numpy as np
from sklearn.datasets import load_digits, load_iris

MODEL_DIR = os.environ.get('MODEL_DIR', '/models')
VERSION = '1.1'


def log(msg):
    print('[%s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg), flush=True)


def load_model(name):
    path = os.path.join(MODEL_DIR, name + '.joblib')
    report_path = os.path.join(MODEL_DIR, name + '.json')
    model = joblib.load(path)
    report = {}
    if os.path.exists(report_path):
        with open(report_path, encoding='utf-8') as f:
            report = json.load(f)
    return model, report


def _digits_test_set():
    """真实留出测试集（与训练时同一随机种子切分，未参与训练）"""
    d = load_digits()
    from sklearn.model_selection import train_test_split
    _, Xte, _, yte = train_test_split(
        d.data, d.target, test_size=0.2, random_state=42, stratify=d.target)
    return Xte, yte


def _iris_test_set():
    d = load_iris()
    from sklearn.model_selection import train_test_split
    _, Xte, _, yte = train_test_split(
        d.data, d.target, test_size=0.2, random_state=42, stratify=d.target)
    return Xte, yte


def run_batch(kind='digits', samples=None):
    model, report = load_model(kind)
    if kind == 'digits':
        X, y = _digits_test_set()
        names = [str(i) for i in range(10)]
    else:
        X, y = _iris_test_set()
        names = ['setosa', 'versicolor', 'virginica']
    if samples and samples > 0:
        X, y = X[:samples], y[:samples]

    log('芯光数智 · 真实推理运行时 v%s（%s）' % (VERSION, report.get('name', kind)))
    log('模型：%s，算法 %s' % (report.get('name', kind), report.get('algorithm', '-')))
    log('训练：真实数据集 %s → 训练 %s 条 / 测试 %s 条，构建期测试准确率 %.2f%%' % (
        report.get('dataset', '-'), report.get('train_samples', '-'),
        report.get('test_samples', '-'), float(report.get('test_accuracy', 0)) * 100))
    log('本次样本：%d 条（真实留出测试集，未参与训练）' % len(X))

    lat = []
    hits = 0
    t0 = time.perf_counter()
    for i in range(len(X)):
        s = time.perf_counter()
        pred = int(model.predict([X[i]])[0])
        proba = model.predict_proba([X[i]])[0]
        lat.append((time.perf_counter() - s) * 1000.0)
        truth = int(y[i])
        hits += int(pred == truth)
        if i < 12:
            label = names[pred] if pred < len(names) else str(pred)
            suffix = '' if str(label) == str(pred) else '（%s）' % label
            log('  #%03d 真实标签 %s → 预测 %s%s 置信度 %.4f' % (
                i + 1, truth, pred, suffix, float(proba[pred])))
    total = time.perf_counter() - t0
    acc = hits / max(len(X), 1)
    lat_sorted = sorted(lat)
    p50 = lat_sorted[len(lat_sorted) // 2] if lat_sorted else 0.0
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))] if lat_sorted else 0.0
    log('结果：%d/%d 正确，准确率 %.2f%%（构建期 %.2f%%）' % (
        hits, len(X), acc * 100, float(report.get('test_accuracy', 0)) * 100))
    log('延迟：单条均值 %.3f ms，P50 %.3f ms，P95 %.3f ms；总耗时 %.2f s，吞吐 %.0f 条/秒' % (
        sum(lat) / max(len(lat), 1), p50, p95, total, len(X) / max(total, 1e-9)))
    log('推理完成，退出码 0')
    return 0


class Handler(BaseHTTPRequestHandler):
    models = {}
    stats = {'requests': 0, 'errors': 0, 'latency_ms': []}

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/healthz':
            return self._send(200, {'status': 'ok', 'version': VERSION,
                                    'models': sorted(self.models.keys())})
        if u.path == '/info':
            return self._send(200, {'version': VERSION, 'runtime': 'CPU',
                                    'models': {k: v[1] for k, v in self.models.items()}})
        if u.path == '/metrics':
            lat = self.stats['latency_ms']
            return self._send(200, {
                'requests': self.stats['requests'], 'errors': self.stats['errors'],
                'avg_latency_ms': round(sum(lat) / len(lat), 3) if lat else 0,
                'p95_latency_ms': round(sorted(lat)[min(len(lat) - 1, int(len(lat) * 0.95))], 3) if lat else 0,
            })
        if u.path == '/sample':
            q = parse_qs(u.query)
            idx = int((q.get('i') or ['0'])[0])
            X, y = _digits_test_set()
            if idx < 0 or idx >= len(X):
                return self._send(400, {'error': '样本下标越界'})
            model, _ = self.models['digits']
            pred = int(model.predict([X[idx]])[0])
            proba = model.predict_proba([X[idx]])[0]
            return self._send(200, {'index': idx, 'truth': int(y[idx]), 'prediction': pred,
                                    'confidence': round(float(proba[pred]), 4),
                                    'pixels': [float(v) for v in X[idx]]})
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/predict':
            return self._send(404, {'error': 'not found'})
        try:
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            kind = body.get('model') or 'digits'
            if kind not in self.models:
                return self._send(400, {'error': '未知模型：%s' % kind})
            model, report = self.models[kind]
            if kind == 'digits':
                pixels = body.get('pixels')
                if not pixels:
                    X, y = _digits_test_set()
                    pixels = [float(v) for v in X[int(body.get('index', 0))]]
                x = np.asarray(pixels, dtype=float).reshape(1, -1)
                names = [str(i) for i in range(10)]
            else:
                feats = body.get('features')
                if not feats:
                    X, y = _iris_test_set()
                    feats = [float(v) for v in X[int(body.get('index', 0))]]
                x = np.asarray(feats, dtype=float).reshape(1, -1)
                names = ['setosa', 'versicolor', 'virginica']
            if x.shape[1] != int(report.get('features', x.shape[1])):
                return self._send(400, {'error': '特征维度应为 %s' % report.get('features')})
            t0 = time.perf_counter()
            pred = int(model.predict(x)[0])
            proba = model.predict_proba(x)[0]
            ms = (time.perf_counter() - t0) * 1000.0
            self.stats['requests'] += 1
            self.stats['latency_ms'].append(ms)
            self.stats['latency_ms'] = self.stats['latency_ms'][-500:]
            log('POST /predict model=%s -> %s (%.3f ms)' % (kind, names[pred], ms))
            return self._send(200, {'model': kind, 'prediction': pred,
                                    'label': names[pred] if pred < len(names) else str(pred),
                                    'confidence': round(float(proba[pred]), 4),
                                    'latency_ms': round(ms, 3),
                                    'model_test_accuracy': report.get('test_accuracy')})
        except Exception as e:  # noqa: BLE001
            self.stats['errors'] += 1
            return self._send(500, {'error': str(e)})

    def log_message(self, fmt, *args):  # 统一走我们的日志格式
        pass


def run_serve(port):
    Handler.models = {
        'digits': load_model('digits'),
        'iris': load_model('iris'),
    }
    for k, (_, rep) in Handler.models.items():
        log('加载模型 %s：%s，测试准确率 %.2f%%' % (
            k, rep.get('name', k), float(rep.get('test_accuracy', 0)) * 100))
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    log('在线推理服务已启动，端口 %d（真实模型，CPU）' % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='batch', choices=['batch', 'serve'])
    ap.add_argument('--kind', default='digits', choices=['digits', 'iris'])
    ap.add_argument('--samples', type=int, default=0, help='批量推理样本数，0=全部留出测试集')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    args = ap.parse_args()
    try:
        if args.mode == 'serve':
            return run_serve(args.port)
        return run_batch(args.kind, args.samples)
    except Exception as e:  # noqa: BLE001
        log('推理失败：%s' % e)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
