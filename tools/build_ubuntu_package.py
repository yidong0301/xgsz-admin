#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 Ubuntu 离线部署包（Docker 镜像 + compose + 前端 + 脚本 + 文档）。

用法（Windows/Linux 均可，需已启动 Docker）：
  python tools/build_ubuntu_package.py
  python tools/build_ubuntu_package.py --version 20261110_1300
  python tools/build_ubuntu_package.py --skip-images   # 只打文件，不导入镜像（调试用）

产物：
  dist/xgsz-admin-ubuntu-<version>.tar.gz
  dist/xgsz-admin-ubuntu-<version>.tar.gz.sha256
"""
import argparse
import datetime
import hashlib
import shutil
import subprocess
import tarfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DIST = BASE / 'dist'


def log(msg):
    print('\n>>> %s' % msg, flush=True)


def run(cmd, **kwargs):
    print('$ ' + ' '.join(str(x) for x in cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def copytree(src, dst, ignore=None):
    src = BASE / src
    dst = Path(dst)
    if not src.exists():
        print('  [skip] missing %s' % src)
        return
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


IGNORE = shutil.ignore_patterns(
    '__pycache__', '*.pyc', '*.pyo', '*.log', '.git', '.idea', 'venv', '.venv',
    'node_modules', 'dist', 'archive', 'ansible_pkg', 'cpolar', '*.tar.gz',
    '.env', '.env.*', 'celerybeat.pid', 'metrices', 'logs', '*.sqlite3',
)


def build_backend_image(version):
    image = 'xgsz/admin-backend:%s' % version
    log('构建后端镜像：%s' % image)
    run(['docker', 'build', '-t', image, '-t', 'xgsz/admin-backend:latest', str(BASE / 'xgsz-admin')])
    return image


def ensure_images():
    base = ['mysql:5.7', 'redis:6-alpine', 'mongo:4.4', 'nginx:alpine', 'certbot/certbot:latest']
    for img in base:
        try:
            subprocess.run(['docker', 'image', 'inspect', img],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            log('拉取基础镜像：%s' % img)
            run(['docker', 'pull', img])
    return base


def save_images(images, out_dir, version):
    out_dir.mkdir(parents=True, exist_ok=True)
    tar_path = out_dir / ('xgsz-admin-images-%s.tar' % version)
    log('导出镜像：%s（约 1~3 分钟）' % tar_path.name)
    run(['docker', 'save', '-o', str(tar_path)] + images)
    return tar_path


def copy_files(stage, version):
    log('复制部署文件')
    copytree('xgsz-admin-web', stage / 'xgsz-admin-web', ignore=IGNORE)
    copytree('docs', stage / 'docs', ignore=IGNORE)
    copytree('data', stage / 'data', ignore=IGNORE)
    copytree('xgsz-admin', stage / 'xgsz-admin', ignore=IGNORE)

    # nginx：只带生产模板 + 空证书/ACME 目录
    (stage / 'nginx' / 'prod').mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE / 'nginx' / 'prod', stage / 'nginx' / 'prod', dirs_exist_ok=True)
    (stage / 'nginx' / 'certs').mkdir(parents=True, exist_ok=True)
    (stage / 'nginx' / 'www').mkdir(parents=True, exist_ok=True)
    (stage / 'nginx' / 'certs' / '.gitkeep').write_text('', encoding='utf-8')
    (stage / 'nginx' / 'www' / '.gitkeep').write_text('', encoding='utf-8')

    # 脚本：只带 Ubuntu 需要的
    (stage / 'scripts').mkdir(parents=True, exist_ok=True)
    for name in ('deploy_ubuntu.sh', 'init_https.sh'):
        src = BASE / 'scripts' / name
        if src.exists():
            shutil.copy2(src, stage / 'scripts' / name)
    (stage / 'tools').mkdir(parents=True, exist_ok=True)
    for name in ('gen_self_signed_cert.py', 'seed_from_json.py'):
        src = BASE / 'tools' / name
        if src.exists():
            shutil.copy2(src, stage / 'tools' / name)

    # kube：只保留目录与说明，绝不打包真实 kubeconfig
    (stage / 'kube' / 'clusters').mkdir(parents=True, exist_ok=True)
    (stage / 'kube' / 'clusters' / '.gitkeep').write_text('', encoding='utf-8')
    (stage / 'kube' / 'README.md').write_text(
        '# K8s 多集群 kubeconfig\n\n'
        '把每台集群的 kubeconfig 放到本目录的 `clusters/<集群名>.yaml`，\n'
        '然后重启 backend/celery 即可在「环境管理 → K8s 集群接入状态」看到。\n'
        '注意：kubeconfig 含敏感凭据，不要提交到 Git。\n',
        encoding='utf-8',
    )

    # compose / 环境变量 / README
    shutil.copy2(BASE / 'docker-compose.ubuntu.yml', stage / 'docker-compose.ubuntu.yml')
    shutil.copy2(BASE / 'README-UBUNTU.md', stage / 'README-UBUNTU.md')
    env_text = (BASE / '.env.ubuntu.example').read_text(encoding='utf-8')
    env_text = env_text.replace('XGSZ_VERSION=latest', 'XGSZ_VERSION=%s' % version)
    (stage / '.env.ubuntu.example').write_text(env_text, encoding='utf-8')


def make_archive(stage, version):
    out = DIST / ('xgsz-admin-ubuntu-%s.tar.gz' % version)
    log('打包：%s' % out.name)
    with tarfile.open(out, 'w:gz', compresslevel=6) as tar:
        tar.add(stage, arcname=stage.name)
    sha = hashlib.sha256()
    with open(out, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)
    (out.with_suffix(out.suffix + '.sha256')).write_text(
        '%s  %s\n' % (sha.hexdigest(), out.name), encoding='utf-8')
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=datetime.datetime.now().strftime('%Y%m%d_%H%M'))
    parser.add_argument('--skip-images', action='store_true', help='不构建/导出镜像（仅调试）')
    args = parser.parse_args()
    version = args.version

    DIST.mkdir(parents=True, exist_ok=True)
    stage = DIST / ('xgsz-admin-ubuntu-%s' % version)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    if args.skip_images:
        images = []
        log('跳过镜像构建与导出')
    else:
        backend = build_backend_image(version)
        images = [backend] + ensure_images()
        tar_path = save_images(images, stage / 'images', version)
        print('  镜像包：%s（%.1f MB）' % (tar_path.name, tar_path.stat().st_size / 1024 / 1024))

    copy_files(stage, version)
    out = make_archive(stage, version)

    # 保留解压目录便于检查；也可手动删除
    print('\n完成：%s' % out)
    print('大小：%.1f MB' % (out.stat().st_size / 1024 / 1024))
    print('SHA256：%s' % out.with_suffix(out.suffix + '.sha256').read_text(encoding='utf-8').split()[0])
    print('解压目录：%s' % stage)


if __name__ == '__main__':
    main()
