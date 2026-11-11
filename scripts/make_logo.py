# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import os

root = r"D:\WDXMGZ\xgsz-admin-web"
logo_path = os.path.join(root, "img", "logo.a1b84216.png")

FONT = r"C:\Windows\Fonts\msyhbd.ttc"   # 微软雅黑粗体
BG = (23, 43, 92)           # 深蓝
FG = (255, 255, 255, 255)   # 白

def make_logo():
    W, H = 240, 64
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=BG)
    text = "芯光数智"
    size = 34
    while size > 14:
        f = ImageFont.truetype(FONT, size)
        bb = d.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= W - 24:
            break
        size -= 2
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((W - tw) / 2 - bb[0], (H - th) / 2 - bb[1]), text, font=f, fill=FG)
    img.save(logo_path)
    print("logo saved:", logo_path, img.size)

def make_favicon():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, 31, 31], radius=8, fill=BG)
    f = ImageFont.truetype(FONT, 20)
    d.text((16, 15), "芯", font=f, fill=FG, anchor="mm")
    ico_path = os.path.join(root, "favicon.ico")
    img.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48)])
    print("favicon saved:", ico_path)

make_logo()
make_favicon()
