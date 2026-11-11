# -*- coding: utf-8 -*-
r"""一键打包交付：把平台源码/文档/数据/脚本打成 zip，方便别人解压测试

用法：python tools/export_package.py
产物：D:\WDXMGZ\dist\xgsz-admin-交付包-<日期>.zip
"""
import os, zipfile, datetime

BASE = r'D:\WDXMGZ'
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M')
OUT_DIR = os.path.join(BASE, 'dist')
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, 'xgsz-admin-交付包-%s.zip' % STAMP)

# 需要打包的内容（相对 BASE）
INCLUDE = [
    'xgsz-admin', 'xgsz-admin-web', 'xgsz-miniprogram',
    'nginx', 'data', 'docs', 'devlog', 'scripts', 'tools',
    'docker-compose.yml', 'docker-compose.prod.yml', '启动平台.bat', '停止平台.bat',
    'CLAUDE.md', '上线部署文档.md', 'xgsz-admin-运行说明.md',
    'xgsz-admin-初步思路与处理流程.md',
]
# 排除的目录/文件
EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', 'venv', '.idea',
                'dist', '.pytest_cache', 'kube', 'archive', 'ansible_pkg', 'cpolar'}
EXCLUDE_FILES = {'tools/cpolar.zip', 'tools/cloudflared.zip'}
EXCLUDE_EXTS = ('.pyc', '.tar.gz', '.log')


def skip(rel):
    parts = rel.split(os.sep)
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if rel.replace(os.sep, '/') in EXCLUDE_FILES:
        return True
    # 证书/私钥属于机器相关文件，由服务器上用 init_https.sh 重新生成
    if rel.startswith(os.path.join('nginx', 'certs') + os.sep):
        return True
    return rel.endswith(EXCLUDE_EXTS)


count = 0
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for item in INCLUDE:
        src = os.path.join(BASE, item)
        if not os.path.exists(src):
            print('  [跳过] 不存在:', item)
            continue
        if os.path.isfile(src):
            z.write(src, item)
            count += 1
        else:
            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    fp = os.path.join(root, f)
                    rel = os.path.relpath(fp, BASE)
                    if skip(rel):
                        continue
                    z.write(fp, rel)
                    count += 1

size_mb = os.path.getsize(OUT) / 1024 / 1024
print('打包完成:', OUT)
print('文件数: %d | 大小: %.1f MB' % (count, size_mb))
