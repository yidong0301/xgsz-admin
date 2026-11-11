# -*- coding: utf-8 -*-
import io
from docx import Document

path = r"C:\Users\Admin1\Desktop\芯光数智-小程序端PRD-v1.0.docx"
out = r"D:\WDXMGZ\prd_extract.txt"
doc = Document(path)
lines = []
lines.append("=== 段落 ===")
for p in doc.paragraphs:
    t = p.text.strip()
    if t:
        lines.append(t)
lines.append("\n=== 表格 ===")
for ti, table in enumerate(doc.tables):
    lines.append("--- 表 %d ---" % (ti + 1))
    for row in table.rows:
        lines.append(" | ".join(c.text.strip() for c in row.cells))
with io.open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved:", out, "lines:", len(lines))
