#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成自签 HTTPS 证书（本地/内网验证用；生产请用 Let's Encrypt）。

输出到 nginx/certs/live/<domain>/：
  fullchain.pem  —— 证书链（自签场景只有叶子证书）
  privkey.pem    —— 私钥
  cert.pem       —— 叶子证书
"""
import argparse
import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain', required=True, help='域名，如 local.test')
    parser.add_argument('--days', type=int, default=3650, help='有效期天数')
    parser.add_argument('--out', default='nginx/certs', help='证书根目录')
    args = parser.parse_args()

    domain = args.domain.strip()
    if not domain:
        raise SystemExit('域名不能为空')
    out_dir = Path(args.out) / 'live' / domain
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'CN'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'XGSZ'),
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
    ])
    san = [x509.DNSName(domain)]
    if domain != 'localhost':
        san.append(x509.DNSName('localhost'))
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=args.days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    (out_dir / 'privkey.pem').write_bytes(key_bytes)
    (out_dir / 'cert.pem').write_bytes(cert_bytes)
    (out_dir / 'fullchain.pem').write_bytes(cert_bytes)
    print('self-signed certificate written: %s' % out_dir)


if __name__ == '__main__':
    main()
