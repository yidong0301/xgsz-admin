#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建期真实训练：手写数字识别（UCI digits 8x8 真实灰度图）+ 鸢尾花分类。

训练产物写入 /models：
  digits.joblib / digits.json   真实 MLP 模型 + 训练报告（样本数、测试集准确率等）
  iris.joblib   / iris.json     真实鸢尾花分类模型 + 训练报告
"""
import argparse
import json
import os
import time

import joblib
from sklearn.datasets import load_digits, load_iris
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def _report(name, algorithm, X_train, X_test, y_train, y_test, model, extra=None):
    t0 = time.perf_counter()
    pred = model.predict(X_test)
    elapsed = time.perf_counter() - t0
    acc = float(accuracy_score(y_test, pred))
    rep = {
        'name': name,
        'algorithm': algorithm,
        'train_samples': int(len(X_train)),
        'test_samples': int(len(X_test)),
        'features': int(X_train.shape[1]),
        'classes': [str(c) for c in sorted(set(y_test.tolist()))],
        'test_accuracy': round(acc, 4),
        'predict_ms_total': round(elapsed * 1000, 2),
        'predict_ms_per_sample': round(elapsed * 1000 / max(len(X_test), 1), 4),
        'trained_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if extra:
        rep.update(extra)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/models')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    # ---- 1. 手写数字（真实 UCI digits 数据集：1797 张 8x8 灰度图，标签 0-9）----
    digits = load_digits()
    Xtr, Xte, ytr, yte = train_test_split(
        digits.data, digits.target, test_size=0.2, random_state=42, stratify=digits.target)
    digits_model = Pipeline([
        ('scaler', StandardScaler()),
        ('mlp', MLPClassifier(hidden_layer_sizes=(64,), max_iter=600, random_state=42)),
    ])
    t0 = time.perf_counter()
    digits_model.fit(Xtr, ytr)
    train_s = time.perf_counter() - t0
    joblib.dump(digits_model, os.path.join(args.out, 'digits.joblib'))
    digits_rep = _report('手写数字识别', 'MLPClassifier(64) + StandardScaler',
                         Xtr, Xte, ytr, yte, digits_model, {
        'dataset': 'sklearn.datasets.load_digits（UCI 手写数字 8x8）',
        'train_seconds': round(train_s, 2),
        'weights_bytes': os.path.getsize(os.path.join(args.out, 'digits.joblib')),
    })
    with open(os.path.join(args.out, 'digits.json'), 'w', encoding='utf-8') as f:
        json.dump(digits_rep, f, ensure_ascii=False, indent=2)

    # ---- 2. 鸢尾花（真实 Iris 数据集：150 条 4 特征 3 分类）----
    iris = load_iris()
    Itr, Ite, itr, ite = train_test_split(
        iris.data, iris.target, test_size=0.2, random_state=42, stratify=iris.target)
    iris_model = Pipeline([
        ('scaler', StandardScaler()),
        ('mlp', MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=600, random_state=42)),
    ])
    iris_model.fit(Itr, itr)
    joblib.dump(iris_model, os.path.join(args.out, 'iris.joblib'))
    iris_rep = _report('鸢尾花分类', 'MLPClassifier(32,16) + StandardScaler',
                       Itr, Ite, itr, ite, iris_model, {
        'dataset': 'sklearn.datasets.load_iris（Fisher Iris）',
        'train_seconds': round(time.perf_counter() - t0, 2),
        'weights_bytes': os.path.getsize(os.path.join(args.out, 'iris.joblib')),
    })
    with open(os.path.join(args.out, 'iris.json'), 'w', encoding='utf-8') as f:
        json.dump(iris_rep, f, ensure_ascii=False, indent=2)

    print('训练完成：digits 准确率 %.2f%%（%d 张测试样本），iris 准确率 %.2f%%（%d 条测试样本）' % (
        digits_rep['test_accuracy'] * 100, digits_rep['test_samples'],
        iris_rep['test_accuracy'] * 100, iris_rep['test_samples']))


if __name__ == '__main__':
    main()
