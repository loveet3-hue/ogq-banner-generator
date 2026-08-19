# -*- coding: utf-8 -*-
"""브라우저 캔버스 편집기 (fabric.js) — 생성된 배너의 레이어를 드래그/크기/회전/텍스트 편집 후 PNG 다운로드"""
import base64
import io
import json
import os

from PIL import Image

_FONT_CACHE = {}


def _b64_png(im, max_side=None):
    if max_side and max(im.size) > max_side:
        sc = max_side / max(im.size)
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


FONT_CDN = "https://cdn.jsdelivr.net/gh/loveet3-hue/ogq-banner-generator@main/build/fonts/"

def _font_face_css(font_dir):
    """폰트는 GitHub CDN(jsDelivr)에서 로드 (base64 내장 시 8MB+ 라 무거움). 로컬 실행 시 파일이 있으면 그대로 CDN 사용."""
    css = []
    for fname, family in [("Jua-Regular.ttf", "Jua"), ("Gaegu-Bold.ttf", "Gaegu"),
                          ("Pretendard-ExtraBold.otf", "Pretendard")]:
        fmt = "opentype" if fname.endswith(".otf") else "truetype"
        css.append(f"@font-face{{font-family:'{family}';src:url('{FONT_CDN}{fname}') format('{fmt}');font-display:swap;}}")
    return "\n".join(css)


def build_editor_html(layers, pack_stickers, font_dir, file_stem):
    """layers: {"bg": PIL, "stickers": [(PIL,x,y)], "texts":[...], "size":(w,h)}"""
    w, h = layers["size"]
    bg_b64 = _b64_png(layers["bg"])
    stickers = [{"src": _b64_png(im), "x": x, "y": y} for im, x, y in layers.get("stickers", [])]
    texts = []
    for t in layers.get("texts", []):
        fam = "Jua" if "Jua" in t.get("font", "") else ("Gaegu" if "Gaegu" in t.get("font", "") else "Pretendard")
        texts.append({"text": t["text"], "x": t["x"], "y": t["y"], "size": t["size"],
                      "stroke": t["stroke"], "font": fam, "anchor": t.get("anchor", "top")})
    pack = [_b64_png(im, max_side=480) for im in pack_stickers]
    data = json.dumps({"w": w, "h": h, "bg": bg_b64, "stickers": stickers, "texts": texts,
                       "pack": pack, "name": file_stem}, ensure_ascii=False)
    css = _font_face_css(font_dir)
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor_template.html"), encoding="utf-8").read()
    return tpl.replace("__CSS__", css).replace("__DATA__", data)
