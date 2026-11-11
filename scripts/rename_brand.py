# -*- coding: utf-8 -*-
"""将品牌名 xgsz-admin 替换为 芯光数智（显示名），内部包名 xgsz_admin 保持不变"""
import io

files = [
    r"D:\WDXMGZ\xgsz-admin-web\index.html",
    r"D:\WDXMGZ\xgsz-admin-web\js\app.js",
    r"D:\WDXMGZ\xgsz-admin-web\js\9.js",
    r"D:\WDXMGZ\xgsz-admin\tasks\email.py",
    r"D:\WDXMGZ\xgsz-admin\README.md",
]

BRAND = "芯光数智"

for fp in files:
    with io.open(fp, "r", encoding="utf-8") as f:
        c = f.read()
    n = c.count("xgsz-admin")
    c = c.replace("xgsz-admin", BRAND)
    with io.open(fp, "w", encoding="utf-8") as f:
        f.write(c)
    print("%s: 替换 %d 处" % (fp.split("\\")[-1], n))
print("done")
