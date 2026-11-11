# -*- coding: utf-8 -*-
"""把 logo 内嵌为 base64，让 app.html 成为完全自包含的单文件"""
import base64, io

app = r"D:\WDXMGZ\xgsz-admin-web\app.html"
logo = r"D:\WDXMGZ\xgsz-admin-web\img\logo.a1b84216.png"

with open(logo, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")
data_uri = "data:image/png;base64," + b64

with io.open(app, "r", encoding="utf-8") as f:
    c = f.read()

n = c.count('src="/img/logo.a1b84216.png"')
c = c.replace('src="/img/logo.a1b84216.png"', 'src="' + data_uri + '"')

with io.open(app, "w", encoding="utf-8") as f:
    f.write(c)

print("logo 内嵌 %d 处，base64 长度 %d" % (n, len(b64)))
print("app.html 已自包含")
