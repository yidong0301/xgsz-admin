# -*- coding: utf-8 -*-
"""生成 PWA 应用图标（192x192 / 512x512）"""
from PIL import Image, ImageDraw, ImageFont
import os

root = r"D:\WDXMGZ\xgsz-admin-web"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"
BG = (23, 43, 92)
FG = (255, 255, 255, 255)

def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size-1, size-1], radius=int(size*0.18), fill=BG)
    text = "芯光数智"
    fs = int(size * 0.30)
    while fs > 10:
        f = ImageFont.truetype(FONT, fs)
        bb = d.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= size * 0.78:
            break
        fs -= 2
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    d.text(((size-tw)/2 - bb[0], (size-th)/2 - bb[1]), text, font=f, fill=FG)
    p = os.path.join(root, "icon-%d.png" % size)
    img.save(p)
    print("saved:", p)

make(192)
make(512)
