#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把品牌方提供的 logo 原图切分成平台可用的透明 PNG / PWA 图标 / favicon。

源图：docs/brand/logo-source.jpg（白底，图标在上、文字在下）
输出：
  xgsz-admin-web/logo-icon.png   透明图标（顶栏 / 登录页 / 侧栏）
  xgsz-admin-web/logo-full.png   透明完整 logo（图标 + 芯光数智）
  xgsz-admin-web/icon-192.png    PWA 图标（白底、居中）
  xgsz-admin-web/icon-512.png    PWA 图标（白底、居中）
  xgsz-admin-web/favicon.ico     多尺寸 favicon
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgba(path):
    """白底 JPEG → RGBA（按亮度做平滑透明，保留蓝/青渐变）"""
    im = Image.open(path).convert('RGB')
    a = np.array(im)
    # 取 RGB 最小值：白底接近 255，彩色/深色主体接近 0
    minc = a.min(axis=2).astype(np.float32)
    # 248 以上完全透明；230~248 之间平滑过渡；230 以下完全保留
    alpha = np.clip((248.0 - minc) * 12.0, 0, 255).astype(np.uint8)
    alpha[alpha < 4] = 0
    rgba = np.dstack([a, alpha])
    return Image.fromarray(rgba, 'RGBA')


def content_boxes(rgba):
    """自动找图标/文字的分割线，返回 (icon_box, full_box)"""
    a = np.array(rgba)
    mask = a[:, :, 3] > 12
    ys, xs = np.where(mask)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    h = y1 - y0
    rows = mask.sum(axis=1)
    # 图标与文字之间通常有一条 20~80px 的空白带
    start = y0 + int(h * 0.45)
    end = y0 + int(h * 0.85)
    gap = [y for y in range(start, end) if rows[y] == 0]
    if gap:
        split = (gap[0] + gap[-1]) // 2
    else:
        split = y0 + int(h * 0.65)
    icon_mask = mask.copy()
    icon_mask[split:, :] = False
    iy, ix = np.where(icon_mask)
    if len(iy) == 0:
        icon_box = (x0, y0, x1 + 1, split)
    else:
        icon_box = (int(ix.min()), int(iy.min()), int(ix.max()) + 1, int(iy.max()) + 1)
    full_box = (x0, y0, x1 + 1, y1 + 1)
    return icon_box, full_box, split


def pad_box(box, margin, size):
    x0, y0, x1, y1 = box
    return (max(0, x0 - margin), max(0, y0 - margin),
            min(size[0], x1 + margin), min(size[1], y1 + margin))


def fit_width(im, width):
    if im.width == width:
        return im
    height = max(1, round(im.height * width / im.width))
    return im.resize((width, height), Image.Resampling.LANCZOS)


def square_icon(icon, size, padding_ratio=0.12, bg=(255, 255, 255, 255)):
    """把透明图标居中放进方形画布，用于 PWA / apple-touch-icon"""
    canvas = Image.new('RGBA', (size, size), bg)
    inner = int(size * (1 - padding_ratio * 2))
    w, h = icon.size
    scale = min(inner / w, inner / h)
    new = icon.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    canvas.alpha_composite(new, ((size - new.width) // 2, (size - new.height) // 2))
    return canvas.convert('RGB')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='docs/brand/logo-source.jpg')
    parser.add_argument('--out', default='xgsz-admin-web')
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rgba = load_rgba(source)
    icon_box, full_box, split = content_boxes(rgba)
    icon_box = pad_box(icon_box, 12, rgba.size)
    full_box = pad_box(full_box, 12, rgba.size)
    icon = rgba.crop(icon_box)
    full = rgba.crop(full_box)

    # 顶栏 / 登录页使用的图标：透明、宽 512
    icon_512 = fit_width(icon, 512)
    icon_512.save(out / 'logo-icon.png', optimize=True)

    # 完整 logo：透明、宽 800
    full_800 = fit_width(full, 800)
    full_800.save(out / 'logo-full.png', optimize=True)

    # PWA 图标：白底方形
    square_icon(icon, 192).save(out / 'icon-192.png', optimize=True)
    square_icon(icon, 512).save(out / 'icon-512.png', optimize=True)

    # favicon：透明方形，多尺寸 ICO
    fav = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    inner = 58
    w, h = icon.size
    scale = min(inner / w, inner / h)
    new = icon.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    fav.alpha_composite(new, ((64 - new.width) // 2, (64 - new.height) // 2))
    fav.save(out / 'favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

    print('source:', source, rgba.size)
    print('split y:', split)
    print('icon box:', icon_box, '->', icon_512.size)
    print('full box:', full_box, '->', full_800.size)
    print('wrote: logo-icon.png logo-full.png icon-192.png icon-512.png favicon.ico')


if __name__ == '__main__':
    main()
