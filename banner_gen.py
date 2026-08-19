#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OGQ 마켓 배너 자동 생성기
=========================
OGQ마켓 판매 링크(또는 artworkId)를 주면 아래 9종 배너를 자동 생성합니다.

  1. NOM  NAVER OGQ마켓 상단 배너      PC 824x464 / MO 640x360   (텍스트 없음 - 어드민 입력)
  2. COM  채팅+ OGQ마켓 메인 상단 배너  PC&MO 984x552             (타이틀 텍스트 포함)
  3. 크리에이터 스튜디오 대시보드       PC 1440x180 / MO 350x200  (텍스트 포함)
  4. 크리에이터 스튜디오 랜딩          PC 1020x680 / MO 660x440  (텍스트 포함)
  5. SOM  SOOP OGQ마켓 메인 상단 배너  PC 1344x260 / MO 672x440  (텍스트 없음 - 어드민 입력)

디자인 가이드 반영:
  - 배경 #FFFFFF(순백) 사용 금지, 테두리/라운딩 없음
  - SOM PC: 주요 오브제 중앙 960px 이내 + 좌측 텍스트 400px 영역 오브제 배치 지양
  - SOM MO: 상단 텍스트 영역 비움, 좌/우 10px 단색 + 자연스러운 그라데이션
  - NOM 상단배너: 카피 없이 이미지만 (뱃지 영역 좌상단 고려)
  - 실행할 때마다 랜덤 시드로 다른 디자인 (--seed 로 고정 가능)

사용법:
  python3 banner_gen.py "https://ogqmarket.naver.com/artworks/sticker/detail?artworkId=61bc52a6358f4"
  python3 banner_gen.py 61bc52a6358f4 --variants 3
  python3 banner_gen.py <url> --out ./banners --seed 42
"""

import warnings
warnings.filterwarnings("ignore")

import argparse
import colorsys
import glob
import io
import json
import math
import os
import random
import re
import shutil
import sys
import time
import urllib.parse

try:
    import requests
except ImportError:
    sys.exit("requests 가 필요합니다:  python3 -m pip install requests")

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

API_BASE = "https://api.ogqmarket.naver.com"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Google Drive 데스크톱 동기화 폴더 (있으면 결과물을 자동 복사)
DRIVE_PATTERNS = [
    os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/공유 드라이브/112_운영팀/08.기타 자료/Ai개발"),
]

def find_drive_dir():
    for pat in DRIVE_PATTERNS:
        for p in glob.glob(pat):
            if os.path.isdir(p):
                return p
    return None

# 텍스트 포함 여부 (기본: 텍스트 없이 스티커 이미지로만 구성)
TEXT_ENABLED = False
# SNS 홍보 이미지용 출시일 문구 (예: "8월 19일")
RELEASE_DATE = ""

# ----------------------------------------------------------------------------
# 배너 규격 정의
# ----------------------------------------------------------------------------
SPECS = [
    # (파일명, W, H, 레이아웃종류, 텍스트포함여부)
    ("NOM_상단배너_PC_824x464",        824,  464, "nom_main",  False),
    ("NOM_상단배너_MO_640x360",        640,  360, "nom_main",  False),
    ("COM_채팅플러스_메인_984x552",     984,  552, "com_main",  True),
    ("스튜디오_대시보드_PC_1440x180",  1440,  180, "strip",     True),
    ("스튜디오_대시보드_MO_350x200",    350,  200, "card_sm",   True),
    ("스튜디오_랜딩_PC_1020x680",      1020,  680, "landing",   True),
    ("스튜디오_랜딩_MO_660x440",        660,  440, "landing",   True),
    ("SOM_SOOP_메인_PC_1344x260",     1344,  260, "som_pc",    False),
    ("SOM_SOOP_메인_MO_672x440",       672,  440, "som_mo",    False),
    ("SNS_출시홍보_세로_1080x1350",     1080, 1350, "sns_promo", True),
    ("SNS_출시홍보_정사각_1080x1080",   1080, 1080, "sns_promo", True),
]

FONT_DIRS = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts", "/System/Library/Fonts"]

def find_font(names):
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None

BUNDLED_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "fonts")
def bundled(name):
    p = os.path.join(BUNDLED_FONT_DIR, name)
    return p if os.path.exists(p) else None
FONT_HAND = bundled("Gaegu-Bold.ttf") or bundled("Jua-Regular.ttf")
FONT_HAND_ALT = [f for f in [bundled("Gaegu-Bold.ttf"), bundled("Jua-Regular.ttf"),
                             bundled("NanumPenScript-Regular.ttf"), bundled("GamjaFlower-Regular.ttf")] if f]
FONT_BOLD = bundled("Pretendard-ExtraBold.otf") or find_font(["Pretendard-ExtraBold.otf", "Pretendard-Black.otf", "Pretendard-SemiBold.otf",
                       "GmarketSansTTFBold.ttf", "AppleSDGothicNeo.ttc"])
FONT_REG = find_font(["Pretendard-Medium.ttf", "Pretendard-Regular.otf", "AppleSDGothicNeo.ttc"])


# ----------------------------------------------------------------------------
# 1. OGQ마켓 데이터 가져오기
# ----------------------------------------------------------------------------
def parse_artwork_id(src: str) -> str:
    src = src.strip()
    if re.fullmatch(r"[0-9a-f]{10,16}", src):
        return src
    q = urllib.parse.urlparse(src)
    params = urllib.parse.parse_qs(q.query)
    if "artworkId" in params:
        return params["artworkId"][0]
    m = re.search(r"[0-9a-f]{12,14}", src)
    if m:
        return m.group(0)
    raise ValueError(f"artworkId 를 찾을 수 없습니다: {src}")


def fetch_artwork(artwork_id: str) -> dict:
    url = f"{API_BASE}/da/digital-assets/stickers/{artwork_id}"
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    d = r.json()
    art, creator = d["artwork"], d.get("creator", {})
    stickers = [s["imageLoc"] for s in art.get("stickerImages", []) if s.get("type") == "ITEM"]
    # 고해상도(o480_480)로 교체
    stickers = [re.sub(r"\?type=.*$", "?type=o480_480", u) for u in stickers]
    main = re.sub(r"\?type=.*$", "?type=o480_480", art.get("mainImageUrl", ""))
    return {
        "id": artwork_id,
        "title": art.get("defaultName", "").strip(),
        "description": art.get("defaultDescription", "").strip(),
        "creator": creator.get("nickname", "").strip(),
        "main_image": main,
        "stickers": stickers,
        "tags": art.get("tags", []),
    }


def download_images(urls, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    imgs = []
    for u in urls:
        fn = os.path.join(cache_dir, re.sub(r"[^0-9A-Za-z._-]", "_", u.split("/")[-1]))
        if not os.path.exists(fn):
            try:
                r = requests.get(u, headers=UA, timeout=15)
                r.raise_for_status()
                open(fn, "wb").write(r.content)
            except Exception as e:
                print(f"  ! 이미지 다운로드 실패: {u} ({e})")
                continue
        try:
            im = Image.open(fn).convert("RGBA")
            imgs.append(im)
        except Exception:
            pass
    return imgs


def load_local_source(path):
    """스티커 원본(zip / 폴더 / 이미지 파일)에서 이미지를 읽어온다."""
    import zipfile, tempfile
    exts = (".png", ".gif", ".webp", ".jpg", ".jpeg")
    files = []
    title = os.path.splitext(os.path.basename(path.rstrip("/")))[0]
    if os.path.isfile(path) and zipfile.is_zipfile(path):
        tmp = tempfile.mkdtemp(prefix="ogq_src_")
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                name = info.filename
                if info.flag_bits & 0x800 == 0:  # 한글 파일명(cp949) 복원
                    try:
                        name = name.encode("cp437").decode("cp949")
                    except Exception:
                        pass
                bn = os.path.basename(name)
                if info.is_dir() or "__MACOSX" in name or bn.startswith("."):
                    continue
                if not bn.lower().endswith(exts):
                    continue
                out = os.path.join(tmp, re.sub(r"[\\/]", "_", name))
                with open(out, "wb") as f:
                    f.write(z.read(info))
                files.append(out)
    elif os.path.isdir(path):
        files = [os.path.join(path, f) for f in sorted(os.listdir(path))
                 if f.lower().endswith(exts) and not f.startswith(".")]
    elif path.lower().endswith(exts):
        files = [path]
    else:
        raise ValueError(f"지원하지 않는 파일입니다 (zip/폴더/이미지만 가능): {path}")

    def sort_key(p):
        b = os.path.splitext(os.path.basename(p))[0]
        m = re.search(r"\d+", b)
        return (0, int(m.group()), b) if m else (1, 0, b)
    files.sort(key=sort_key)

    # tab / main 같은 안내용 이미지는 제외 (스티커가 따로 있을 때만)
    def stem(p):
        return os.path.splitext(os.path.basename(p))[0].lower()
    stickers = [p for p in files if stem(p) not in ("tab", "main", "탭", "메인")]
    if not stickers:
        stickers = files

    imgs = []
    for p in stickers:
        try:
            imgs.append(Image.open(p).convert("RGBA"))
        except Exception:
            pass
    if not imgs:
        raise ValueError("읽을 수 있는 이미지가 없습니다.")
    data = {"id": title, "title": title, "description": "", "creator": "",
            "main_image": "", "stickers": [], "tags": []}
    return data, imgs


# ----------------------------------------------------------------------------
# 2. 팔레트 추출 → 테마 생성
# ----------------------------------------------------------------------------
def dominant_hue(imgs):
    """스티커들의 대표 색상(hue)을 추출."""
    hues, weights = [], []
    for im in imgs[:8]:
        small = im.resize((48, 48))
        for r, g, b, a in small.getdata():
            if a < 200:
                continue
            h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            if s < 0.25 or l < 0.15 or l > 0.92:
                continue  # 무채색/너무 어둡/너무 밝음 제외
            hues.append(h)
            weights.append(s * (1 - abs(l - 0.5)))
    if not hues:
        return random.random()
    # 원형 평균 대신 히스토그램 최빈 구간
    bins = [0.0] * 24
    for h, w in zip(hues, weights):
        bins[int(h * 24) % 24] += w
    best = max(range(24), key=lambda i: bins[i])
    return (best + 0.5) / 24


def hls(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0, min(1, l)), max(0, min(1, s)))
    return (int(r * 255), int(g * 255), int(b * 255))


def make_theme(imgs, rng):
    """스티커 색상 기반 랜덤 테마 생성. 매번 다른 색 전략을 사용."""
    base_h = dominant_hue(imgs)
    # 색상 전략: 스티커와 비슷한 색 / 보색 / 삼각배색 / 완전 랜덤
    strategy = rng.choice(["analog", "complement", "complement", "triad", "random", "random"])
    if strategy == "analog":
        h = (base_h + rng.uniform(-0.06, 0.06)) % 1.0
    elif strategy == "complement":
        h = (base_h + 0.5 + rng.uniform(-0.06, 0.06)) % 1.0
    elif strategy == "triad":
        h = (base_h + rng.choice([0.33, -0.33]) + rng.uniform(-0.04, 0.04)) % 1.0
    else:
        h = rng.random()

    mode = rng.choice(["pastel", "pastel", "pastel", "duo", "cream", "cream", "mint", "sky", "peach", "lavender"])
    if mode == "pastel":
        bg1 = hls(h, rng.uniform(0.80, 0.88), rng.uniform(0.6, 0.85))
        bg2 = hls((h + rng.uniform(0.03, 0.08)) % 1, rng.uniform(0.74, 0.84), rng.uniform(0.55, 0.8))
    elif mode == "peach":
        bg1 = hls(rng.uniform(0.04, 0.09), rng.uniform(0.88, 0.93), rng.uniform(0.6, 0.85))
        bg2 = hls(rng.uniform(0.06, 0.11), rng.uniform(0.84, 0.90), rng.uniform(0.55, 0.8))
    elif mode == "lavender":
        bg1 = hls(rng.uniform(0.70, 0.78), rng.uniform(0.88, 0.93), rng.uniform(0.5, 0.75))
        bg2 = hls(rng.uniform(0.72, 0.80), rng.uniform(0.84, 0.90), rng.uniform(0.45, 0.7))
    elif mode == "vivid":
        bg1 = hls(h, rng.uniform(0.66, 0.76), rng.uniform(0.75, 0.9))
        bg2 = hls((h + rng.uniform(-0.05, 0.05)) % 1, rng.uniform(0.60, 0.70), rng.uniform(0.7, 0.9))
    elif mode == "duo":
        h2 = (h + rng.choice([0.08, 0.12, -0.08, -0.12, 0.16])) % 1.0
        bg1 = hls(h, rng.uniform(0.80, 0.88), rng.uniform(0.55, 0.75))
        bg2 = hls(h2, rng.uniform(0.78, 0.86), rng.uniform(0.55, 0.75))
    elif mode == "cream":
        bg1 = hls(rng.uniform(0.10, 0.15), rng.uniform(0.90, 0.93), rng.uniform(0.35, 0.6))
        bg2 = hls(rng.uniform(0.08, 0.16), rng.uniform(0.86, 0.90), rng.uniform(0.3, 0.55))
    elif mode == "dark":  # 진한 배경 (네이비/퍼플 계열만 — 갈색/올리브는 탁해서 제외)
        if not (0.55 <= h <= 0.80):
            h = rng.uniform(0.58, 0.75)
        bg1 = hls(h, rng.uniform(0.22, 0.30), rng.uniform(0.45, 0.65))
        bg2 = hls((h + rng.uniform(0.02, 0.06)) % 1, rng.uniform(0.15, 0.24), rng.uniform(0.4, 0.6))
    elif mode == "neon":
        bg1 = hls(h, rng.uniform(0.55, 0.65), 1.0)
        bg2 = hls((h + rng.choice([0.12, -0.12, 0.5])) % 1, rng.uniform(0.55, 0.65), 1.0)
    elif mode == "mint":
        bg1 = hls(rng.uniform(0.40, 0.48), rng.uniform(0.80, 0.88), rng.uniform(0.5, 0.75))
        bg2 = hls(rng.uniform(0.44, 0.52), rng.uniform(0.74, 0.84), rng.uniform(0.5, 0.75))
    else:  # sky
        bg1 = hls(rng.uniform(0.55, 0.62), rng.uniform(0.80, 0.90), rng.uniform(0.6, 0.9))
        bg2 = hls(rng.uniform(0.52, 0.60), rng.uniform(0.70, 0.82), rng.uniform(0.6, 0.9))

    is_dark = luminance(bg1) < 0.45
    accents = [
        hls((h + 0.5) % 1, 0.62, 0.8),
        hls((h + 0.33) % 1, 0.6, 0.8),
        hls((h - 0.33) % 1, 0.6, 0.8),
        hls(h, 0.7 if is_dark else 0.5, 0.9),
        (255, 255, 255),
        hls((h + 0.08) % 1, 0.75, 0.9),
    ]
    rng.shuffle(accents)
    text_dark = hls(h, 0.16, 0.45)
    # 배경 스타일: 그라데이션 or 패턴
    bg_style = rng.choice(["clouds", "clouds", "checker_frame", "checker_top", "halftone", "big_circle",
                           "burst_soft", "candy_stripes", "gingham", "polka", "confetti", "rainbow_arc",
                           "blobs", "grad"])
    decor_pool = ["star", "star", "sparkle", "sparkle", "heart", "heart", "circle", "ring", "flower", "music"]
    bg_fx = rng.choice(["none", "none", "halo"])
    # 포인트 색상 계열: 보색 / 삼각배색 (배경과 확실히 구분되도록)
    accent_hues = [(h + 0.5) % 1, (h + 0.33) % 1, (h - 0.33) % 1]
    rng.shuffle(accent_hues)
    decor_cols = [hls(accent_hues[0], 0.72, 0.85), hls(accent_hues[1], 0.72, 0.85), (255, 255, 255)]
    rng.shuffle(decor_cols)
    decor_cols = decor_cols[:rng.choice([1, 2, 2, 3])]
    return {
        "hue": h, "mode": mode, "strategy": strategy, "bg1": bg1, "bg2": bg2,
        "decor_cols": decor_cols, "accent_hues": accent_hues,
        "accents": accents, "text": text_dark, "is_dark": is_dark,
        "grad_dir": rng.choice(["v", "h", "d", "radial"]),
        "bg_style": bg_style, "bg_fx": bg_fx,
        "decor": rng.sample(decor_pool, k=rng.choice([1, 2, 2])),
        "outline_color": (255, 255, 255),
        "tilt": rng.choice([0, 0, 0, 1]),  # 스티커 살짝 기울이기
    }


# ----------------------------------------------------------------------------
# 3. 그리기 유틸
# ----------------------------------------------------------------------------
def gradient_bg(w, h, c1, c2, direction="v"):
    if direction == "radial":
        base = Image.new("RGB", (w, h), c2)
        mask = Image.new("L", (w * 2, h * 2), 0)
        d = ImageDraw.Draw(mask)
        d.ellipse([0, 0, w * 2, h * 2], fill=255)
        mask = mask.resize((w, h)).filter(ImageFilter.GaussianBlur(min(w, h) // 3))
        top = Image.new("RGB", (w, h), c1)
        base.paste(top, (0, 0), mask)
        return base
    if direction == "h":
        grad = Image.new("RGB", (256, 1))
        for x in range(256):
            t = x / 255
            grad.putpixel((x, 0), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
        return grad.resize((w, h))
    if direction == "d":
        grad = Image.new("RGB", (256, 256))
        for x in range(256):
            for y in range(256):
                t = (x + y) / 510
                grad.putpixel((x, y), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
        return grad.resize((w, h))
    grad = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    return grad.resize((w, h))


def draw_star(d, cx, cy, r, color, points=5, rot=0.0):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * 0.45
        a = rot + math.pi * i / points
        pts.append((cx + rr * math.sin(a), cy - rr * math.cos(a)))
    d.polygon(pts, fill=color)


def draw_sparkle(d, cx, cy, r, color, rot=0.0):
    pts = []
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.22
        a = rot + math.pi * i / 4
        pts.append((cx + rr * math.sin(a), cy - rr * math.cos(a)))
    d.polygon(pts, fill=color)


def draw_heart(d, cx, cy, r, color, rot=0.0):
    pts = []
    for i in range(40):
        t = 2 * math.pi * i / 40
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append((cx + xr * r / 16, cy - yr * r / 16))
    d.polygon(pts, fill=color)


def draw_confetti_piece(d, cx, cy, r, color, rot, rng):
    shape = rng.choice(["rect", "circle", "squig", "tri"])
    if shape == "rect":
        pts = []
        for ang in [0, 1, 2, 3]:
            a = rot + ang * math.pi / 2
            rr = r if ang % 2 == 0 else r * 0.45
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=color)
    elif shape == "circle":
        d.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], fill=color)
    elif shape == "tri":
        pts = [(cx + r * math.sin(rot + 2 * math.pi * i / 3),
                cy - r * math.cos(rot + 2 * math.pi * i / 3)) for i in range(3)]
        d.polygon(pts, fill=color)
    else:  # 곡선 리본
        w = max(2, int(r * 0.30))
        prev = None
        for i in range(9):
            t = i / 8
            x = cx + (t - 0.5) * 2 * r
            y = cy + math.sin(t * math.pi * 2) * r * 0.4
            xr = cx + (x - cx) * math.cos(rot) - (y - cy) * math.sin(rot)
            yr = cy + (x - cx) * math.sin(rot) + (y - cy) * math.cos(rot)
            if prev:
                d.line([prev, (xr, yr)], fill=color, width=w)
            prev = (xr, yr)


def scatter_zone(rng, w, h, zones, n):
    """zones: (x0,y0,x1,y1) 리스트 중 랜덤 위치 n개 생성"""
    out = []
    for _ in range(n):
        x0, y0, x1, y1 = rng.choice(zones)
        out.append((rng.uniform(x0, x1), rng.uniform(y0, y1)))
    return out


def add_decor(img, theme, rng, zones=None, density=1.0, big_ok=True):
    """배경 장식 요소 추가"""
    w, h = img.size
    if zones is None:
        zones = [(0, 0, w, h)]
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    unit = min(w, h)
    for kind in theme["decor"]:
        if kind == "dots":  # 폴카닷 패턴 (은은하게)
            step = int(unit * rng.uniform(0.16, 0.24))
            r = step * rng.uniform(0.10, 0.16)
            col = (*theme["accents"][0][:3], 26)
            off = rng.uniform(0, step)
            for yy in range(int(-step), h + step, step):
                for xx in range(int(-step), w + step, step):
                    sx = xx + (step // 2 if (yy // step) % 2 else 0) + off
                    d.ellipse([sx - r, yy - r, sx + r, yy + r], fill=col)
        elif kind == "halftone":  # 하프톤 도트 패치
            cx, cy = rng.choice(scatter_zone(rng, w, h, zones, 1))
            R = unit * rng.uniform(0.5, 0.8)
            col = (*theme["accents"][1][:3], 40)
            step = max(8, int(unit * 0.045))
            for yy in range(int(cy - R), int(cy + R), step):
                for xx in range(int(cx - R), int(cx + R), step):
                    dist = math.hypot(xx - cx, yy - cy)
                    if dist < R:
                        rr = max(1.2, (1 - dist / R) * step * 0.42)
                        d.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], fill=col)
        elif kind == "burst" and big_ok:  # 집중선/버스트 (흰색 삼각형)
            cx, cy = w * rng.uniform(0.3, 0.7), h * rng.uniform(0.35, 0.75)
            n = rng.randint(6, 10)
            for i in range(n):
                a = 2 * math.pi * i / n + rng.uniform(-0.15, 0.15)
                r1 = unit * rng.uniform(0.42, 0.62)
                r2 = r1 + unit * rng.uniform(0.10, 0.22)
                spread = rng.uniform(0.02, 0.045)
                p1 = (cx + r1 * math.cos(a - spread), cy + r1 * math.sin(a - spread))
                p2 = (cx + r1 * math.cos(a + spread), cy + r1 * math.sin(a + spread))
                p3 = (cx + r2 * math.cos(a), cy + r2 * math.sin(a))
                d.polygon([p1, p2, p3], fill=(255, 255, 255, rng.randint(160, 230)))
        elif kind == "rings":  # 링(도넛) 장식
            n = int(rng.randint(3, 6) * density)
            for cx, cy in scatter_zone(rng, w, h, zones, n):
                col = (*rng.choice(theme["accents"])[:3], rng.randint(120, 200))
                r = unit * rng.uniform(0.04, 0.10)
                lw = max(2, int(r * 0.28))
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=lw)
        elif kind == "plus":  # + 십자 장식
            n = int(rng.randint(6, 12) * density)
            for cx, cy in scatter_zone(rng, w, h, zones, n):
                col = (*rng.choice(theme["accents"])[:3], rng.randint(150, 230))
                r = unit * rng.uniform(0.015, 0.035)
                lw = max(2, int(r * 0.5))
                d.line([(cx - r, cy), (cx + r, cy)], fill=col, width=lw)
                d.line([(cx, cy - r), (cx, cy + r)], fill=col, width=lw)
        elif kind == "zigzag":  # 지그재그 라인
            n = int(rng.randint(2, 4) * density)
            for cx, cy in scatter_zone(rng, w, h, zones, n):
                col = (*rng.choice(theme["accents"])[:3], rng.randint(150, 220))
                seg = unit * rng.uniform(0.02, 0.035)
                lw = max(2, int(seg * 0.3))
                pts = [(cx + i * seg, cy + (seg if i % 2 else 0)) for i in range(rng.randint(5, 9))]
                d.line(pts, fill=col, width=lw, joint="curve")
        elif kind in ("confetti", "stars", "sparkle", "hearts"):
            n = int(rng.randint(8, 16) * density)
            for cx, cy in scatter_zone(rng, w, h, zones, n):
                col = (*rng.choice(theme["accents"])[:3], rng.randint(150, 235))
                r = unit * rng.uniform(0.018, 0.055)
                rot = rng.uniform(0, math.pi * 2)
                if kind == "confetti":
                    draw_confetti_piece(d, cx, cy, r * 1.4, col, rot, rng)
                elif kind == "stars":
                    draw_star(d, cx, cy, r * 1.3, col, rot=rot)
                elif kind == "sparkle":
                    draw_sparkle(d, cx, cy, r * 1.4, col, rot=rot)
                else:
                    draw_heart(d, cx, cy, r * 1.2, col, rot=rng.uniform(-0.5, 0.5))
    img.alpha_composite(overlay)
    return img


CURRENT_THEME = {}

def prep_sticker(im, target_h, outline=True, outline_ratio=0.035, max_w=None, max_upscale=1.55,
                 rot=None):
    """스티커 트리밍 + 아웃라인 + 박스핏 리사이즈 + (선택) 회전"""
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    scale = target_h / im.height
    if max_w:
        scale = min(scale, max_w / im.width)
    scale = min(scale, max_upscale)  # 원본 480px 기준 → 흐려짐 방지
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if outline:
        r = max(2, int(target_h * outline_ratio))
        oc = CURRENT_THEME.get("outline_color", (255, 255, 255))
        pad = r + 2
        # 패딩 먼저 → 아웃라인이 경계에서 직선으로 끊기지 않게
        padded = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
        padded.alpha_composite(im, (pad, pad))
        a = padded.split()[3]
        grown = a.filter(ImageFilter.MaxFilter(r * 2 + 1))
        stroke = Image.new("RGBA", padded.size, (*oc, 0))
        solid = Image.new("RGBA", padded.size, (*oc, 255))
        stroke.paste(solid, (0, 0), grown)
        stroke.alpha_composite(padded)
        im = stroke
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    return im


def tilt(rng, strength=1.0):
    """테마의 tilt 설정에 따라 살짝 기울인 각도 반환"""
    if not CURRENT_THEME.get("tilt"):
        return None
    return rng.uniform(-6, 6) * strength


def paste_with_shadow(base, sticker, x, y, shadow_alpha=60, blur=10, dy=8):
    # 그림자가 검은 배경처럼 보이는 문제로 그림자 없이 깔끔하게 합성
    base.alpha_composite(sticker, (int(x), int(y)))


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def fit_text(draw, text, font_path, max_w, start_size, min_size=14):
    size = start_size
    while size > min_size:
        f = load_font(font_path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f, size
        size -= 2
    return load_font(font_path, min_size), min_size


def luminance(c):
    r, g, b = [v / 255 for v in c[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ----------------------------------------------------------------------------
# 4. 구도(컴포지션) 엔진
#    원칙: 스티커는 크게 / 하나의 덩어리로 겹쳐 뭉치기 / 좌우·상단 잘림 없음
#          (하단으로만 자연스럽게 흘러나감) / 장식은 빈 곳에만 절제해서
# ----------------------------------------------------------------------------
def sticker_aspect(im):
    bbox = im.getbbox()
    if not bbox:
        return 1.0
    return (bbox[2] - bbox[0]) / max(1, bbox[3] - bbox[1])


_CLEAN_CACHE = {}

def is_clean(im):
    """원본 프레임에 잘리지 않은 스티커인지 (테두리에 불투명 픽셀이 많으면 잘린 컷)"""
    key = id(im)
    if key in _CLEAN_CACHE:
        return _CLEAN_CACHE[key]
    a = im.split()[3]
    w, h = a.size
    def cov(pixels):
        return sum(1 for p in pixels if p > 40) / max(1, len(pixels))
    top = cov([a.getpixel((x, 1)) for x in range(0, w, 2)])
    bot = cov([a.getpixel((x, h - 2)) for x in range(0, w, 2)])
    left = cov([a.getpixel((1, y)) for y in range(0, h, 2)])
    right = cov([a.getpixel((w - 2, y)) for y in range(0, h, 2)])
    clean = max(top, bot, left, right) < 0.12
    _CLEAN_CACHE[key] = clean
    return clean


def clean_pool(stickers, min_keep=4):
    """잘린 스티커 제외한 풀 (충분히 남을 때만)"""
    good = [s for s in stickers if is_clean(s)]
    return good if len(good) >= min_keep else list(stickers)


def pick_stickers(stickers, rng, n, prefer_square=False):
    pool = clean_pool(stickers)
    if prefer_square:
        sq = [s for s in pool if 0.6 <= sticker_aspect(s) <= 1.5]
        if len(sq) >= n:
            pool = sq
    if len(pool) <= n:
        return pool
    return rng.sample(pool, n)


def pick_hero(stickers, rng):
    """히어로용: 정사각형에 가깝고, 세로가 긴(캐릭터 전신) 스티커 우선"""
    pool = clean_pool(stickers)
    good = [s for s in pool if 0.7 <= sticker_aspect(s) <= 1.35]
    return rng.choice(good or pool)


def clamp_x(x, width, canvas_w, margin=8):
    return max(margin, min(canvas_w - width - margin, x))


def _soft_mask_shape(w, h, draw_fn, blur=0):
    m = Image.new("L", (w, h), 0)
    draw_fn(ImageDraw.Draw(m))
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return m


def _fill_with_mask(img, color, mask):
    ov = Image.new("RGBA", img.size, (*color[:3], 0))
    ov.putalpha(mask)
    img.alpha_composite(ov)


def _accent_light(theme, k=0):
    """배경 위에 올려도 튀지 않는 밝은 포인트색"""
    h = theme["accent_hues"][k % len(theme["accent_hues"])]
    return hls(h, 0.80, 0.85)


def _accent_vivid(theme, k=0):
    h = theme["accent_hues"][k % len(theme["accent_hues"])]
    return hls(h, 0.66, 0.85)


def render_base(w, h, theme, rng=None):
    """배경 = 디자인 요소. 파스텔 베이스 + 스타일별 큰 그래픽 요소"""
    rng = rng or random.Random(0)
    style = theme.get("bg_style", "grad")
    c1, c2 = theme["bg1"], theme["bg2"]
    bg = gradient_bg(w, h, c1, c2, theme["grad_dir"]).convert("RGBA")
    unit = min(w, h)
    white = (255, 255, 255)
    deeper = hls(theme["hue"], max(0.55, luminance(c1) - 0.22), 0.7)  # 베이스보다 한 톤 진한 색

    if style == "grad":
        pass

    elif style == "clouds":  # 하단 구름 (하늘 배경)
        base_y = h * rng.uniform(0.62, 0.78)
        def fn(d):
            d.rectangle([0, base_y + unit * 0.12, w, h], fill=255)
            x = -unit * 0.1
            while x < w + unit * 0.2:
                r = unit * rng.uniform(0.10, 0.20)
                d.ellipse([x - r, base_y - r * rng.uniform(0.6, 1.1), x + r, base_y + r], fill=255)
                x += r * rng.uniform(0.9, 1.4)
        _fill_with_mask(bg, white, _soft_mask_shape(w, h, fn, blur=unit * 0.006))
        # 위쪽에 작은 구름 2~3개
        for _ in range(rng.randint(2, 3)):
            cx, cy = rng.uniform(0.05, 0.95) * w, rng.uniform(0.08, 0.35) * h
            s = unit * rng.uniform(0.05, 0.09)
            def fn2(d, cx=cx, cy=cy, s=s):
                for dx, dy, k in [(-1.1, 0.2, 0.75), (0, 0, 1.0), (1.1, 0.25, 0.7), (0.4, 0.4, 0.8), (-0.5, 0.45, 0.7)]:
                    d.ellipse([cx + dx * s - s * k, cy + dy * s - s * k, cx + dx * s + s * k, cy + dy * s + s * k], fill=235)
            _fill_with_mask(bg, white, _soft_mask_shape(w, h, fn2, blur=unit * 0.004))

    elif style == "checker_frame":  # 좌우 체커보드 띠 (레퍼런스 스타일)
        cs = int(unit * rng.uniform(0.07, 0.10))
        band = cs * rng.choice([2, 3])
        col = deeper
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for yy in range(0, h + cs, cs):
            for xx in range(0, band, cs):
                if ((xx // cs) + (yy // cs)) % 2 == 0:
                    d.rectangle([xx, yy, xx + cs, yy + cs], fill=(*col, 255))
                    d.rectangle([w - xx - cs, yy, w - xx, yy + cs], fill=(*col, 255))
        bg.alpha_composite(ov)

    elif style == "checker_top":  # 상단 체커 띠 (얇게)
        cs = int(unit * rng.uniform(0.05, 0.07))
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for yy in range(0, cs * 2, cs):
            for xx in range(0, w + cs, cs):
                if ((xx // cs) + (yy // cs)) % 2 == 0:
                    d.rectangle([xx, yy, xx + cs, yy + cs], fill=(*deeper, 255))
        bg.alpha_composite(ov)

    elif style == "halftone":  # 코너 하프톤 (만화풍)
        corner = rng.choice([(0, 0), (w, 0), (0, h), (w, h)])
        R = unit * rng.uniform(0.7, 1.1)
        step = max(8, int(unit * 0.035))
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        col = deeper
        for yy in range(0, h + step, step):
            for xx in range(0, w + step, step):
                dist = math.hypot(xx - corner[0], yy - corner[1])
                if dist < R:
                    rr = (1 - dist / R) * step * 0.45
                    if rr > 1: d.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], fill=(*col, 200))
        bg.alpha_composite(ov)

    elif style == "big_circle":  # 큰 원 스포트라이트 (크리스프)
        cx, cy = w * rng.uniform(0.35, 0.65), h * rng.uniform(0.55, 0.9)
        r = unit * rng.uniform(0.55, 0.85)
        col = white if luminance(c1) < 0.92 else deeper
        _fill_with_mask(bg, col, _soft_mask_shape(w, h, lambda d: d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=150)))

    elif style == "burst_soft":  # 부드러운 집중선 (연하게)
        cx, cy = w * rng.uniform(0.4, 0.6), h * rng.uniform(0.6, 0.9)
        n = rng.randint(14, 22)
        def fn(d):
            for i in range(n):
                a = 2 * math.pi * i / n + rng.uniform(-0.05, 0.05)
                sp = rng.uniform(0.04, 0.07)
                r2 = unit * 2
                d.polygon([(cx, cy), (cx + r2 * math.cos(a - sp), cy + r2 * math.sin(a - sp)),
                           (cx + r2 * math.cos(a + sp), cy + r2 * math.sin(a + sp))], fill=110)
        _fill_with_mask(bg, white, _soft_mask_shape(w, h, fn))

    elif style == "candy_stripes":  # 사선 캔디 스트라이프
        sw = int(unit * rng.uniform(0.07, 0.11))
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for x in range(-h, w + h, sw * 2):
            d.polygon([(x, 0), (x + sw, 0), (x + sw + h, h), (x + h, h)], fill=(*white, 90))
        bg.alpha_composite(ov)

    elif style == "gingham":
        cs = int(unit * rng.uniform(0.07, 0.10))
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for x in range(0, w, cs * 2):
            d.rectangle([x, 0, x + cs, h], fill=(*white, 70))
        for y in range(0, h, cs * 2):
            d.rectangle([0, y, w, y + cs], fill=(*white, 70))
        bg.alpha_composite(ov)

    elif style == "polka":
        step = int(unit * rng.uniform(0.10, 0.15)); r = step * 0.18
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for yy in range(0, h + step, step):
            for xx in range(0, w + step, step):
                sx = xx + (step // 2 if (yy // step) % 2 else 0)
                d.ellipse([sx - r, yy - r, sx + r, yy + r], fill=(*white, 120))
        bg.alpha_composite(ov)

    elif style == "confetti":  # 제대로 된 색종이 (둥근 사각형 3색)
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        cols = [_accent_vivid(theme, 0), _accent_vivid(theme, 1), _accent_vivid(theme, 2), white]
        for _ in range(int(unit * unit / 14000)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            s = unit * rng.uniform(0.012, 0.024)
            piece = Image.new("RGBA", (int(s * 2.2), int(s * 1.2)), (0, 0, 0, 0))
            ImageDraw.Draw(piece).rounded_rectangle([0, 0, piece.width - 1, piece.height - 1], radius=s * 0.4,
                                                    fill=(*rng.choice(cols), 200))
            piece = piece.rotate(rng.uniform(0, 180), expand=True, resample=Image.BICUBIC)
            ov.alpha_composite(piece, (int(x), int(y)))
        bg.alpha_composite(ov)

    elif style == "rainbow_arc":  # 코너 무지개 아치
        cx, cy = (0 if rng.random() < 0.5 else w), h * rng.uniform(0.9, 1.1)
        R = unit * rng.uniform(0.9, 1.3)
        band = unit * 0.06
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for i in range(4):
            col = [_accent_light(theme, 0), _accent_light(theme, 1), _accent_light(theme, 2), white][i]
            rr = R - i * band
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(*col, 190), width=int(band * 0.85))
        bg.alpha_composite(ov)

    elif style == "blobs":
        for _ in range(rng.randint(2, 3)):
            hh = (theme["hue"] + rng.uniform(-0.10, 0.10)) % 1.0
            col = hls(hh, 0.9, 0.8) if rng.random() < 0.6 else white
            rx, ry = w * rng.uniform(0.25, 0.5), h * rng.uniform(0.3, 0.6)
            draw_halo(bg, rng.uniform(0, w), rng.uniform(0, h), rx, ry, col, alpha=rng.randint(100, 170))

    return bg


def draw_halo(img, cx, cy, rx, ry, color, alpha=110):
    """부드러운 원형 글로우 (알파 마스크만 블러 → 어두운 테두리 없음)"""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(min(rx, ry) * 0.18))
    ov = Image.new("RGBA", (w, h), (*color[:3], 0))
    ov.putalpha(mask)
    img.alpha_composite(ov)


def _boxes_overlap(a, b, pad=0):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


def _decor_sprite(kind, r, color, rot, rng, outline=True):
    """스티커처럼 흰 테두리 두른 장식 스프라이트"""
    pad = int(r * 0.35)
    S = int(r * 2 + pad * 2)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = S / 2
    col = (*color[:3], 255)
    if kind == "star":
        draw_star(d, cx, cy, r, col, rot=rot)
    elif kind == "sparkle":
        draw_sparkle(d, cx, cy, r, col, rot=rot)
    elif kind == "heart":
        draw_heart(d, cx, cy, r * 0.95, col, rot=rng.uniform(-0.4, 0.4))
    elif kind == "circle":
        d.ellipse([cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy + r * 0.8], fill=col)
    elif kind == "ring":
        d.ellipse([cx - r * 0.85, cy - r * 0.85, cx + r * 0.85, cy + r * 0.85], outline=col, width=max(3, int(r * 0.3)))
    elif kind == "flower":
        for i in range(5):
            a = rot + 2 * math.pi * i / 5
            px, py = cx + r * 0.5 * math.cos(a), cy + r * 0.5 * math.sin(a)
            d.ellipse([px - r * 0.42, py - r * 0.42, px + r * 0.42, py + r * 0.42], fill=col)
        d.ellipse([cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3], fill=(255, 245, 200, 255))
    elif kind == "music":
        # 음표 ♪
        d.ellipse([cx - r * 0.45, cy + r * 0.2, cx + r * 0.15, cy + r * 0.7], fill=col)
        d.rectangle([cx + r * 0.02, cy - r * 0.8, cx + r * 0.16, cy + r * 0.45], fill=col)
        d.polygon([(cx + r * 0.02, cy - r * 0.8), (cx + r * 0.6, cy - r * 0.55), (cx + r * 0.6, cy - r * 0.2), (cx + r * 0.16, cy - r * 0.45)], fill=col)
    if outline:
        a = im.split()[3]
        grown = a.filter(ImageFilter.MaxFilter(max(3, int(r * 0.16)) * 2 + 1))
        stroke = Image.new("RGBA", im.size, (255, 255, 255, 0))
        stroke.paste(Image.new("RGBA", im.size, (255, 255, 255, 255)), (0, 0), grown)
        stroke.alpha_composite(im)
        im = stroke
    return im


def add_decor_sparse(img, theme, rng, occupied, n=None, zone=None):
    """빈 공간에만 장식 — 스티커풍(흰 테두리) 도형, 크고 또렷하게, 개수 적게"""
    w, h = img.size
    unit = min(w, h)
    kinds = theme["decor"]
    if not kinds:
        return
    n = n if n is not None else rng.randint(3, 6)
    x0, y0, x1, y1 = zone or (w * 0.03, h * 0.05, w * 0.97, h * 0.95)
    placed = []
    tries = 0
    while len(placed) < n and tries < 250:
        tries += 1
        r = unit * rng.uniform(0.045, 0.085)
        cx, cy = rng.uniform(x0 + r, x1 - r), rng.uniform(y0 + r, y1 - r)
        box = (cx - r * 1.3, cy - r * 1.3, cx + r * 1.3, cy + r * 1.3)
        if any(_boxes_overlap(box, o, pad=r * 0.5) for o in occupied):
            continue
        if any(_boxes_overlap(box, p, pad=r * 1.2) for p in placed):
            continue
        placed.append(box)
        kind = rng.choice(kinds)
        color = rng.choice(theme["decor_cols"])
        sp = _decor_sprite(kind, r, color, rng.uniform(0, math.pi * 2), rng, outline=True)
        sp = sp.rotate(rng.uniform(-20, 20), expand=True, resample=Image.BICUBIC)
        img.alpha_composite(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)))


# ---- 스티커 배치 계획 -----------------------------------------------------------
class Placed:
    __slots__ = ("im", "x", "y")

    def __init__(self, im, x, y):
        self.im, self.x, self.y = im, int(x), int(y)

    @property
    def box(self):
        return (self.x, self.y, self.x + self.im.width, self.y + self.im.height)


def fit_top(st, y, top_limit):
    """스티커 상단이 top_limit 위로 올라가면 줄여서 맞춤. (im, y) 반환"""
    if y >= top_limit:
        return st, y
    need_h = st.height - (top_limit - y)
    if need_h < st.height * 0.55:
        need_h = st.height * 0.55
    sc = need_h / st.height
    st = st.resize((max(1, int(st.width * sc)), max(1, int(st.height * sc))), Image.LANCZOS)
    return st, max(top_limit, y + (1 - sc) * st.height / sc)


# ---- 배치 원칙: 스티커끼리 절대 겹치지 않고, 캔버스 밖으로 절대 나가지 않는다 ----------
def _scale_to(im, target_h, max_w):
    sc = min(target_h / im.height, max_w / im.width, 1.0)
    if sc >= 1.0:
        return im
    return im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)


def plan_lineup(w, h, stickers, rng, x_lo=0.0, x_hi=1.0, top=0.0, n=None,
                size=(0.78, 0.92), hero_boost=None, bottom_margin=0.03, align="bottom"):
    """
    2~4개를 같은 높이로 균등 간격 나열. 겹침 없음, 잘림 없음.
    hero_boost: 첫 번째(또는 가운데) 스티커를 이 배율만큼 더 크게 (예: 1.2)
    """
    XL, XH, TOP = w * x_lo, w * x_hi, h * top
    zone_w = XH - XL
    avail_h = h - TOP
    n = n or rng.choice([2, 3, 3])
    chosen = pick_stickers(stickers, rng, n, prefer_square=True)
    n = len(chosen)
    if n == 0:
        return []
    H = avail_h * rng.uniform(*size)
    side_pad = zone_w * 0.03
    gap_min = avail_h * 0.06
    boost_idx = (n // 2) if hero_boost else -1
    for _ in range(12):  # 폭이 넘치면 높이를 줄여가며 맞춤
        preps = []
        for i, s in enumerate(chosen):
            hh = H * (hero_boost if i == boost_idx else 1.0)
            preps.append(prep_sticker(s, hh, max_w=zone_w, rot=tilt(rng, 0.5)))
        total = sum(p.width for p in preps)
        if total + gap_min * (n - 1) + side_pad * 2 <= zone_w:
            break
        H *= 0.92
    gap = (zone_w - side_pad * 2 - total) / max(1, n - 1) if n > 1 else 0
    gap = min(gap, avail_h * 0.35)  # 너무 벌어지지 않게 → 가운데로 모음
    total_w = total + gap * (n - 1)
    x = XL + (zone_w - total_w) / 2
    out = []
    base_y = h - h * bottom_margin
    for p in preps:
        if align == "bottom":
            y = base_y - p.height
        else:  # center
            y = TOP + (avail_h - p.height) / 2
        y = max(TOP, y)
        out.append(Placed(p, x, y))
        x += p.width + gap
    return out


def plan_hero_sub(w, h, stickers, rng, x_lo=0.0, x_hi=1.0, top=0.0, side=None,
                  hero_h=(0.86, 0.96), sub_h=(0.52, 0.66), n_sub=None):
    """대형 히어로 1 + 서브 1~2 (히어로 옆에, 겹치지 않게)"""
    XL, XH, TOP = w * x_lo, w * x_hi, h * top
    zone_w = XH - XL
    avail_h = h - TOP
    side = side or rng.choice(["left", "right"])
    hero_src = pick_hero(stickers, rng)
    hero = prep_sticker(hero_src, avail_h * rng.uniform(*hero_h), max_w=zone_w * 0.58, rot=tilt(rng, 0.4))
    n_sub = n_sub if n_sub is not None else rng.choice([1, 1, 2])
    pool = [s for s in stickers if s is not hero_src] or stickers
    subs = [prep_sticker(s, avail_h * rng.uniform(*sub_h), max_w=zone_w * 0.32, rot=tilt(rng, 0.8))
            for s in pick_stickers(pool, rng, n_sub, prefer_square=True)]
    gap = avail_h * rng.uniform(0.04, 0.08)
    total = hero.width + sum(s.width for s in subs) + gap * len(subs)
    if total > zone_w * 0.94:  # 넘치면 히어로·서브를 같은 비율로 줄임 (서브만 작아지지 않게)
        sc = (zone_w * 0.94 - gap * len(subs)) / max(1, hero.width + sum(s.width for s in subs))
        sc = max(0.55, min(1.0, sc))
        hero = _scale_to(hero, hero.height * sc, hero.width * sc)
        subs = [_scale_to(s, s.height * sc, s.width * sc) for s in subs]
        total = hero.width + sum(s.width for s in subs) + gap * len(subs)
    x = XL + max(zone_w * 0.03, (zone_w - total) / 2)
    base_y = h - h * 0.03
    out = []
    order = ([hero] + subs) if side == "left" else (subs + [hero])
    for p in order:
        y = max(TOP, base_y - p.height)
        out.append(Placed(p, x, y))
        x += p.width + gap
    return out


def plan_solo(w, h, stickers, rng, x_lo=0.0, x_hi=1.0, top=0.0, size=(0.82, 0.94), pos=None):
    """스티커 하나만 크게 (좌/중/우)"""
    XL, XH, TOP = w * x_lo, w * x_hi, h * top
    zone_w = XH - XL
    avail_h = h - TOP
    hero = prep_sticker(pick_hero(stickers, rng), avail_h * rng.uniform(*size), max_w=zone_w * 0.9,
                        rot=tilt(rng, 0.4))
    pos = pos or rng.choice(["center", "center", "left", "right"])
    if pos == "left":
        x = XL + zone_w * 0.05
    elif pos == "right":
        x = XH - hero.width - zone_w * 0.05
    else:
        x = XL + (zone_w - hero.width) / 2
    y = max(TOP, h - h * 0.03 - hero.height)
    return [Placed(hero, x, y)]


def plan_corners(w, h, stickers, rng, top=0.0, left_h=(0.36, 0.46), right_h=(0.46, 0.58)):
    """좌하단 소형 + 우하단 중형, 가운데 비움 — 스튜디오 랜딩용 (겹침 없음)"""
    a_src = pick_hero(stickers, rng)
    A = prep_sticker(a_src, h * rng.uniform(*right_h), max_w=w * 0.30, rot=tilt(rng, 0.6))
    pool = [s for s in stickers if s is not a_src] or stickers
    B = prep_sticker(rng.choice(pool), h * rng.uniform(*left_h), max_w=w * 0.24, rot=tilt(rng, 0.8))
    m = w * 0.035
    ay = max(h * top, h - h * 0.03 - A.height)
    by = max(h * top, h - h * 0.03 - B.height)
    out = [Placed(B, m, by), Placed(A, w - A.width - m, ay)]
    return out


def draw_plan(img, plan):
    """스티커 합성 + 은은한 그림자 (배경 색 계열, 아주 연하게)"""
    w, h = img.size
    sh_col = hls(CURRENT_THEME.get("hue", 0.6), 0.35, 0.5)
    for p in plan:
        a = p.im.split()[3]
        sh = Image.new("RGBA", p.im.size, (*sh_col, 0))
        sh.putalpha(a.point(lambda v: int(v * 0.22)))
        sh = sh.filter(ImageFilter.GaussianBlur(max(2, p.im.height * 0.02)))
        img.alpha_composite(sh, (p.x + int(p.im.height * 0.015), p.y + int(p.im.height * 0.03)))
        img.alpha_composite(p.im, (p.x, p.y))
    return [p.box for p in plan]


def compose(img, theme, stickers, rng, plan, decor_zone=None, decor_n=None, allow_bg_fx=True):
    """(선택) 히어로 뒤 부드러운 할로 → 스티커 → 빈 곳 장식"""
    w, h = img.size
    if not plan:
        return img
    if allow_bg_fx and theme.get("bg_fx") == "halo":
        big = max(plan, key=lambda p: p.im.height)
        cx = big.x + big.im.width / 2
        cy = big.y + big.im.height / 2
        col = (255, 255, 255) if not theme["is_dark"] else hls(theme["hue"], 0.5, 0.6)
        draw_halo(img, cx, cy, big.im.width * 0.75, big.im.height * 0.7, col, alpha=120)
    boxes = draw_plan(img, plan)
    add_decor_sparse(img, theme, rng, boxes, n=decor_n, zone=decor_zone)
    return img


# ---- 배너별 렌더러 ----------------------------------------------------------
def free_compose(img, theme, stickers, rng, x_lo=0.0, x_hi=1.0, top=0.0, styles=None,
                 decor_zone=None, decor_n=None):
    w, h = img.size
    zw = w * (x_hi - x_lo)
    wide = zw > (h - h * top) * 2.4
    if styles is None:
        styles = (["lineup", "lineup", "hero_sub", "hero_sub", "lineup_hero"] if wide
                  else ["lineup", "lineup", "hero_sub", "hero_sub", "solo", "lineup_hero"])
    style = rng.choice(styles)
    if style == "lineup":
        plan = plan_lineup(w, h, stickers, rng, x_lo, x_hi, top, n=rng.choice([2, 2, 3]))
    elif style == "lineup_hero":
        plan = plan_lineup(w, h, stickers, rng, x_lo, x_hi, top, n=3, hero_boost=1.22, size=(0.66, 0.78))
    elif style == "hero_sub":
        plan = plan_hero_sub(w, h, stickers, rng, x_lo, x_hi, top)
    else:
        plan = plan_solo(w, h, stickers, rng, x_lo, x_hi, top)
    compose(img, theme, stickers, rng, plan, decor_zone=decor_zone, decor_n=decor_n)
    return style


def render_nom_main(w, h, theme, data, stickers, rng):
    """NOM 상단배너 (824x464 / 640x360)"""
    img = render_base(w, h, theme, rng)
    free_compose(img, theme, stickers, rng)
    return img


def render_com_main(w, h, theme, data, stickers, rng):
    """채팅+ 메인 984x552"""
    img = render_base(w, h, theme, rng)
    if not TEXT_ENABLED:
        free_compose(img, theme, stickers, rng)
        return img
    plan = plan_lineup(w, h, stickers, rng, n=3, size=(0.5, 0.58), bottom_margin=0.24)
    compose(img, theme, stickers, rng, plan)
    title = data["title"]
    tag = rng.choice(["신규 스티커 출시!", "OGQ마켓에서 만나보세요!", "지금 만나보세요!"])
    d = ImageDraw.Draw(img)
    tcol = theme["text"] if not theme["is_dark"] else (255, 255, 255)
    tf, ts = fit_text(d, title, FONT_BOLD, w * 0.8, int(h * 0.085))
    tw = d.textlength(title, font=tf)
    d.text(((w - tw) / 2, h * 0.845), title, font=tf, fill=tcol)
    sf, _ = fit_text(d, tag, FONT_REG, w * 0.6, int(ts * 0.45))
    sw = d.textlength(tag, font=sf)
    d.text(((w - sw) / 2, h * 0.845 + ts * 1.3), tag, font=sf, fill=tcol)
    return img


def render_strip(w, h, theme, data, stickers, rng):
    """스튜디오 대시보드 PC 1440x180: 왼쪽 ~58% 텍스트 영역(비움), 오른쪽에 2~3개"""
    img = render_base(w, h, theme, rng)
    x_lo = 0.58
    style = rng.choice(["lineup", "lineup", "hero_sub"])
    if style == "hero_sub":
        plan = plan_hero_sub(w, h, stickers, rng, x_lo=x_lo, x_hi=0.985, hero_h=(0.84, 0.94),
                             sub_h=(0.55, 0.66), n_sub=1)
    else:
        plan = plan_lineup(w, h, stickers, rng, x_lo=x_lo, x_hi=0.985, n=rng.choice([2, 3, 3]),
                           size=(0.80, 0.92))
    compose(img, theme, stickers, rng, plan, decor_zone=(w * x_lo, h * 0.05, w * 0.99, h * 0.95),
            decor_n=rng.randint(2, 4), allow_bg_fx=False)
    if TEXT_ENABLED:
        draw_text_block(img, theme, data["title"], f"{data['creator']} 작가" if data["creator"] else "",
                        rng, x_ratio=0.025, y_ratio=0.30, max_w_ratio=0.5, title_size_ratio=0.24,
                        badge=rng.choice(["NEW", "PICK", None]))
    return img


def render_card_sm(w, h, theme, data, stickers, rng):
    """스튜디오 대시보드 MO 350x200: 왼쪽 절반 텍스트 영역(비움), 오른쪽에 1~2개"""
    img = render_base(w, h, theme, rng)
    x_lo = 0.50
    if rng.random() < 0.6:
        plan = plan_solo(w, h, stickers, rng, x_lo=x_lo, x_hi=0.97, size=(0.80, 0.92), pos="center")
    else:
        plan = plan_lineup(w, h, stickers, rng, x_lo=x_lo, x_hi=0.98, n=2, size=(0.62, 0.72))
    compose(img, theme, stickers, rng, plan, decor_zone=(w * x_lo, h * 0.05, w * 0.98, h * 0.95),
            decor_n=rng.randint(1, 3), allow_bg_fx=False)
    if TEXT_ENABLED:
        draw_text_block(img, theme, data["title"], f"{data['creator']} 작가" if data["creator"] else "",
                        rng, x_ratio=0.055, y_ratio=0.14, max_w_ratio=0.45, title_size_ratio=0.115)
    return img


def render_landing(w, h, theme, data, stickers, rng):
    """스튜디오 랜딩 1020x680 / 660x440: 가운데 텍스트 영역 비우고 좌·우 하단 모서리에 스티커"""
    img = render_base(w, h, theme, rng)
    plan = plan_corners(w, h, stickers, rng)
    compose(img, theme, stickers, rng, plan, decor_n=rng.randint(3, 5), allow_bg_fx=False)
    if TEXT_ENABLED:
        sub = data["description"][:34] + ("…" if len(data["description"]) > 34 else "")
        draw_text_block(img, theme, data["title"], sub, rng, x_ratio=0.06, y_ratio=0.16,
                        max_w_ratio=0.5, title_size_ratio=0.10, badge=rng.choice(["NEW", None]))
    return img


def render_som_pc(w, h, theme, data, stickers, rng):
    """SOM PC 1344x260: 오브제는 중앙 960px 이내 & 좌측 400px(텍스트 영역) 비움."""
    img = render_base(w, h, theme, rng)
    zone_x0 = (w - 960) / 2          # 192
    text_zone_end = zone_x0 + 410    # 텍스트 영역 + 여유
    zone_x1 = zone_x0 + 960
    x_lo, x_hi = text_zone_end / w, zone_x1 / w
    style = rng.choice(["lineup", "lineup", "hero_sub", "lineup_hero"])
    if style == "hero_sub":
        plan = plan_hero_sub(w, h, stickers, rng, x_lo=x_lo, x_hi=x_hi, hero_h=(0.86, 0.94),
                             sub_h=(0.56, 0.68), n_sub=rng.choice([1, 2]))
    elif style == "lineup_hero":
        plan = plan_lineup(w, h, stickers, rng, x_lo, x_hi, n=3, hero_boost=1.2, size=(0.72, 0.8))
    else:
        plan = plan_lineup(w, h, stickers, rng, x_lo, x_hi, n=rng.choice([2, 3, 3]), size=(0.80, 0.92))
    compose(img, theme, stickers, rng, plan,
            decor_zone=(text_zone_end, h * 0.06, zone_x1, h * 0.94), decor_n=rng.randint(2, 5))
    return img


def render_som_mo(w, h, theme, data, stickers, rng):
    """SOM MO 672x440: 상단 텍스트영역(~30%) 비움, 좌우 10px 단색+그라데이션."""
    img = render_base(w, h, theme, rng)
    top = 0.30
    style = rng.choice(["lineup", "lineup", "hero_sub", "lineup_hero"])
    if style == "hero_sub":
        plan = plan_hero_sub(w, h, stickers, rng, top=top, hero_h=(0.86, 0.95), sub_h=(0.55, 0.65))
    elif style == "lineup_hero":
        plan = plan_lineup(w, h, stickers, rng, top=top, n=3, hero_boost=1.2, size=(0.7, 0.8))
    else:
        plan = plan_lineup(w, h, stickers, rng, top=top, n=rng.choice([2, 3, 3]), size=(0.80, 0.92))
    compose(img, theme, stickers, rng, plan, decor_zone=(w * 0.06, h * 0.32, w * 0.94, h * 0.96),
            decor_n=rng.randint(2, 5))
    # 좌우 10px 단색 + 그라데이션 블렌드 (가이드 필수사항)
    edge_col = theme["bg1"]
    fade_w = int(w * 0.09)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(fade_w):
        alpha = int(255 * max(0.0, 1 - i / fade_w) ** 1.6)
        od.line([(i, 0), (i, h)], fill=(*edge_col, alpha))
        od.line([(w - 1 - i, 0), (w - 1 - i, h)], fill=(*edge_col, alpha))
    od.rectangle([0, 0, 10, h], fill=(*edge_col, 255))
    od.rectangle([w - 10, 0, w, h], fill=(*edge_col, 255))
    img.alpha_composite(overlay)
    return img


def draw_text_block(img, theme, title, sub, rng, x_ratio=0.06, y_ratio=0.62,
                    max_w_ratio=0.6, title_size_ratio=0.11, align="left", badge=None):
    w, h = img.size
    d = ImageDraw.Draw(img)
    bright_bg = not theme["is_dark"]
    tcol = theme["text"] if bright_bg else (255, 255, 255)
    scol = tuple(min(255, c + 60) for c in tcol) if bright_bg else (240, 240, 245)
    max_w = w * max_w_ratio
    tf, tsize = fit_text(d, title, FONT_BOLD, max_w, int(h * title_size_ratio))
    x, y = w * x_ratio, h * y_ratio
    if badge:
        bf = load_font(FONT_BOLD, max(14, int(tsize * 0.42)))
        bw = d.textlength(badge, font=bf)
        pad = tsize * 0.28
        bx0, by0 = x, y - tsize * 0.72
        d.rounded_rectangle([bx0, by0, bx0 + bw + pad * 2, by0 + tsize * 0.62],
                            radius=tsize * 0.31, fill=theme["accents"][0])
        bcol = (255, 255, 255) if luminance(theme["accents"][0]) < 0.6 else (40, 35, 50)
        d.text((bx0 + pad, by0 + tsize * 0.08), badge, font=bf, fill=bcol)
        y += tsize * 0.18
    d.text((x, y), title, font=tf, fill=tcol)
    if sub:
        sf, _ = fit_text(d, sub, FONT_REG, max_w, max(15, int(tsize * 0.42)))
        d.text((x, y + tsize * 1.28), sub, font=sf, fill=scol)
    return img


def draw_outlined_text(img, xy, text, font, fill, outline, stroke, anchor="la"):
    d = ImageDraw.Draw(img)
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=outline, anchor=anchor)


def wrap_title(d, text, font, max_w):
    """공백 기준으로 최대 2줄 줄바꿈 (공백 없으면 글자 단위)"""
    if d.textlength(text, font=font) <= max_w:
        return [text]
    words = text.split()
    if len(words) >= 2:
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wa, wb = d.textlength(a, font=font), d.textlength(b, font=font)
            if wa <= max_w and wb <= max_w:
                score = abs(wa - wb)
                if best is None or score < best[0]:
                    best = (score, [a, b])
        if best:
            return best[1]
    # 글자 단위
    mid = len(text) // 2
    for k in range(0, mid):
        for cut in (mid - k, mid + k):
            a, b = text[:cut].strip(), text[cut:].strip()
            if a and b and d.textlength(a, font=font) <= max_w and d.textlength(b, font=font) <= max_w:
                return [a, b]
    return [text]


def render_sns_promo(w, h, theme, data, stickers, rng):
    """SNS 출시 홍보 이미지 (세로 1080x1350): 제목 + 스티커 그리드 + 출시 문구"""
    # 배경: 파스텔 단색(살짝 그라데이션)
    img = render_base(w, h, theme, rng)
    d = ImageDraw.Draw(img)
    dark = theme["is_dark"]
    text_col = (40, 36, 44) if not dark else (255, 255, 255)
    stroke_col = (255, 255, 255) if not dark else (30, 30, 40)

    # --- 제목 ---
    font_path = rng.choice(FONT_HAND_ALT) if FONT_HAND_ALT else FONT_BOLD
    title = data["title"] or "NEW STICKER"
    tsize = int(h * 0.075)
    tf = load_font(font_path, tsize)
    lines = wrap_title(d, title, tf, w * 0.86)
    while len(lines) > 1 and max(d.textlength(l, font=tf) for l in lines) > w * 0.86 and tsize > 40:
        tsize -= 4; tf = load_font(font_path, tsize); lines = wrap_title(d, title, tf, w * 0.86)
    while len(lines) == 1 and d.textlength(lines[0], font=tf) > w * 0.86 and tsize > 40:
        tsize -= 4; tf = load_font(font_path, tsize); lines = wrap_title(d, title, tf, w * 0.86)
    stroke = max(4, tsize // 9)
    y = h * 0.06
    line_gap = tsize * 1.25
    for ln in lines:
        draw_outlined_text(img, (w / 2, y), ln, tf, text_col, stroke_col, stroke, anchor="ma")
        y += line_gap
    title_bottom = y + tsize * 0.2

    # --- 하단 출시 문구 ---
    date = RELEASE_DATE
    bottom_txt = f"{date} 출시!" if date else rng.choice(["NEW 출시!", "출시!", "지금 만나보세요!"])
    bsize = int(h * 0.085)
    bf = load_font(font_path, bsize)
    while d.textlength(bottom_txt, font=bf) > w * 0.86 and bsize > 40:
        bsize -= 4; bf = load_font(font_path, bsize)
    bstroke = max(4, bsize // 9)
    by = h - h * 0.05 - bsize
    draw_outlined_text(img, (w / 2, by), bottom_txt, bf, text_col, stroke_col, bstroke, anchor="ma")
    grid_bottom = by - h * 0.03

    # --- 스티커 그리드 ---
    pool = clean_pool(stickers)
    cols = 4
    max_rows = 4 if h >= w * 1.2 else 3
    n = min(len(pool), cols * max_rows)
    if n >= 12 and n % cols != 0 and n > cols * (n // cols):
        pass  # 마지막 줄 부족해도 가운데 정렬로 처리
    chosen = pool[:n] if len(pool) <= cols * max_rows else rng.sample(pool, n)
    # 원본 순서 유지(번호순)로 보여주는 게 자연스러움
    idx = {id(s): i for i, s in enumerate(stickers)}
    chosen.sort(key=lambda s: idx.get(id(s), 0))
    rows = math.ceil(n / cols)
    grid_top = title_bottom + h * 0.02
    grid_h = grid_bottom - grid_top
    side = w * 0.06
    cell_w = (w - side * 2) / cols
    cell_h = grid_h / rows
    for i, s in enumerate(chosen):
        r, c = i // cols, i % cols
        in_row = min(cols, n - r * cols)
        row_offset = (cols - in_row) * cell_w / 2  # 마지막 줄 가운데 정렬
        st = prep_sticker(s, cell_h * 0.82, outline=True, outline_ratio=0.02, max_w=cell_w * 0.9,
                          max_upscale=2.0)
        x = side + row_offset + c * cell_w + (cell_w - st.width) / 2
        yy = grid_top + r * cell_h + (cell_h - st.height) / 2
        img.alpha_composite(st, (int(x), int(yy)))
    return img


RENDERERS = {
    "nom_main": render_nom_main,
    "com_main": render_com_main,
    "strip": render_strip,
    "card_sm": render_card_sm,
    "landing": render_landing,
    "som_pc": render_som_pc,
    "som_mo": render_som_mo,
    "sns_promo": render_sns_promo,
}


# ----------------------------------------------------------------------------
# 5. 메인
# ----------------------------------------------------------------------------
def ensure_not_white(img):
    """가이드: 순백 배경 금지 → 혹시 모를 경계 확인용 (배경 생성 시 이미 회피됨)"""
    return img


def generate_all(data, imgs, out_dir, seed):
    global CURRENT_THEME
    rng = random.Random(seed)
    theme = make_theme(imgs, rng)
    CURRENT_THEME = theme
    os.makedirs(out_dir, exist_ok=True)
    print(f"  테마: {theme['mode']}/{theme['strategy']} · 배경={theme['bg_style']} · "
          f"효과={theme['bg_fx']} · 장식={'+'.join(theme['decor'])} · 기울임={'O' if theme['tilt'] else 'X'} (seed={seed})")
    results = []
    for name, w, h, kind, _has_text in SPECS:
        sub_rng = random.Random(rng.random())
        img = RENDERERS[kind](w, h, theme, data, imgs, sub_rng)
        img = img.convert("RGB")
        path = os.path.join(out_dir, f"{name}.png")
        img.save(path, "PNG")
        # SOM은 500KB 제한 → 초과 시 JPG 재저장
        if name.startswith("SOM") and os.path.getsize(path) > 500 * 1024:
            img.save(path, "PNG", optimize=True)
            if os.path.getsize(path) > 500 * 1024:
                jpath = path.replace(".png", ".jpg")
                img.save(jpath, "JPEG", quality=90)
                os.remove(path)
                path = jpath
        results.append(path)
        print(f"  ✓ {os.path.basename(path)} ({w}x{h})")
    return results


def main():
    ap = argparse.ArgumentParser(description="OGQ마켓 배너 자동 생성기")
    ap.add_argument("source", nargs="?", default=None,
                    help="OGQ마켓 판매 링크(artworkId) 또는 스티커 원본 zip/폴더/이미지 경로")
    ap.add_argument("--out", default=None, help="출력 폴더 (기본: ./output/<작품명>)")
    ap.add_argument("--seed", type=int, default=None, help="랜덤 시드 고정")
    ap.add_argument("--variants", type=int, default=1, help="디자인 시안 수 (기본 1)")
    ap.add_argument("--no-drive", action="store_true", help="Google Drive 자동 복사 끄기")
    ap.add_argument("--with-text", action="store_true", help="타이틀 텍스트를 포함해서 생성")
    ap.add_argument("--date", default=None, help='SNS 홍보 이미지 출시일 문구 (예: "8월 19일")')
    args = ap.parse_args()

    global TEXT_ENABLED, RELEASE_DATE
    TEXT_ENABLED = args.with_text
    RELEASE_DATE = (args.date or "").strip()

    # 링크 없이 실행(더블클릭)하면 대화형 모드
    interactive = args.source is None
    if interactive:
        print("=" * 52)
        print("   OGQ마켓 배너 자동 생성기")
        print("=" * 52)
        print("둘 중 하나를 입력하고 Enter를 누르세요:")
        print("  ① OGQ마켓 판매 링크 붙여넣기")
        print("  ② 스티커 원본 zip 파일을 이 창에 끌어다 놓기")
        print()
        try:
            args.source = input("링크 또는 파일: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if not args.source:
            sys.exit("입력된 내용이 없습니다.")
        if args.date is None:
            try:
                RELEASE_DATE = input("출시일 (SNS 홍보 이미지용, 예: 8월 19일 / 비우면 날짜 없이): ").strip()
            except (EOFError, KeyboardInterrupt):
                RELEASE_DATE = ""

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 로컬 파일(zip/폴더/이미지) 인지 링크인지 판별
    raw = args.source.strip().strip("'\"")
    local_path = os.path.expanduser(raw.replace("\\ ", " "))
    if os.path.exists(local_path):
        print(f"▶ 원본 파일: {os.path.basename(local_path)}")
        try:
            data, imgs = load_local_source(local_path)
        except Exception as e:
            sys.exit(f"원본을 읽지 못했습니다: {e}")
        print(f"▶ 작품: {data['title']}  /  스티커 {len(imgs)}개 (원본 파일)")
    else:
        artwork_id = parse_artwork_id(raw)
        print(f"▶ artworkId: {artwork_id}")
        data = fetch_artwork(artwork_id)
        print(f"▶ 작품: {data['title']}  /  작가: {data['creator']}  /  스티커 {len(data['stickers'])}개")
        cache = os.path.join(script_dir, ".cache", artwork_id)
        urls = data["stickers"] if data["stickers"] else [data["main_image"]]
        imgs = download_images(urls, cache)
        if not imgs:
            sys.exit("스티커 이미지를 받지 못했습니다.")
        print(f"▶ 이미지 {len(imgs)}개 다운로드 완료")

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", data["title"])[:40] or artwork_id
    base_out = args.out or os.path.join(script_dir, "output", safe_title)

    all_paths = []
    for v in range(args.variants):
        seed = args.seed if args.seed is not None else random.randrange(1 << 30)
        if args.seed is not None and args.variants > 1:
            seed = args.seed + v
        out_dir = base_out if args.variants == 1 else os.path.join(base_out, f"시안_{v + 1}")
        print(f"\n[시안 {v + 1}/{args.variants}] → {out_dir}")
        all_paths += generate_all(data, imgs, out_dir, seed)

    print(f"\n✅ 완료! 배너 {len(all_paths)}개 생성 → {base_out}")

    # Google Drive 동기화 폴더에 자동 복사
    if not args.no_drive:
        drive_dir = find_drive_dir()
        if drive_dir:
            dest = os.path.join(drive_dir, f"{safe_title} 배너")
            shutil.copytree(base_out, dest, dirs_exist_ok=True)
            print(f"☁️  Google Drive 복사 완료 → {dest}")
        else:
            print("(Google Drive 동기화 폴더를 찾지 못해 로컬에만 저장했습니다)")

    # 대화형 모드: 결과 폴더를 Finder로 열고 창 유지
    if interactive:
        try:
            import subprocess
            subprocess.run(["open", base_out], check=False)
        except Exception:
            pass
        print()
        try:
            input("결과 폴더를 열었습니다. Enter를 누르면 종료됩니다.")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    main()
