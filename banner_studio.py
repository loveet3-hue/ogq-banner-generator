# -*- coding: utf-8 -*-
"""
이모티콘 배너 생성 엔진 (banner_tool.html 의 캔버스 디자인을 PIL 로 포팅)

입력: 이모티콘 zip (1~24.png/gif + main/tab)
출력: SOM(1344x260, 672x440) · NOM(824x464, 640x360) · COM(984x552, 문구 포함)
      · 인스타 카드뉴스(1080x1350) — 시안 3개, PNG 500KB 초과 시 JPG
"""
import io
import math
import os
import re
import unicodedata
import zipfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JUA = os.path.join(BASE_DIR, "build", "fonts", "Jua-Regular.ttf")

# ---------------------------------------------------------------- 팔레트/레이아웃 (HTML 도구와 동일)
PALETTES = {
    "pink":     dict(bg="#FFD3E1", sh=(226, 110, 155), accent="#F0457F", ink="#3A2130", deco="#FF8A3D", label="핑크"),
    "mint":     dict(bg="#C6ECE3", sh=(60, 150, 135),  accent="#2E9C88", ink="#24302F", deco="#FFFFFF", label="민트"),
    "lavender": dict(bg="#DCD7F7", sh=(110, 95, 190),  accent="#7A63D6", ink="#3A3550", deco="#FFB86B", label="라벤더"),
    "sky":      dict(bg="#CFE5F8", sh=(70, 120, 190),  accent="#FF7B6E", ink="#2C3550", deco="#FFFFFF", label="하늘"),
    "butter":   dict(bg="#FFF0B8", sh=(200, 160, 40),  accent="#F08A24", ink="#3B3020", deco="#FF8FA8", label="버터"),
    "peach":    dict(bg="#FFDCC8", sh=(220, 120, 80),  accent="#F0643C", ink="#3D2620", deco="#FFFFFF", label="피치"),
    "lime":     dict(bg="#E1F2C4", sh=(110, 160, 60),  accent="#5FA032", ink="#2B3420", deco="#FF9F8A", label="라임"),
}
ALT_ORDER = ["sky", "lavender", "mint", "butter", "peach", "lime", "pink"]
STYLES = {"card": "스티커 카드", "halo": "동그란 배경"}
DEFAULT_STYLES = ["card", "halo", "card"]

L = {
    "soop_pc": dict(w=1344, h=260, mask=[("h", [(0, 0), (470, 0), (640, 1), (1040, 1), (1150, 0)])], glow=[(620, -120, 420)],
        slots=[(478, 118, 170, -12), (690, 22, 212, 5), (975, 118, 146, 11), (922, -34, 150, -9)],
        slotsHalo=[(486, 46, 180, 0), (704, 18, 224, 0), (958, 46, 180, 0)],
        deco=[("spark", 560, 36, 40), ("spark2", 1110, 28, 26), ("squig", 648, 186, 70), ("bubble", 520, 200, 18)]),
    "soop_mo": dict(w=672, h=440, mask=[("v", [(0, 0), (170, 0), (260, 1)]), ("h", [(0, 0), (80, 1), (592, 1), (672, 0)])], glow=[(180, 150, 420)],
        slots=[(84, 270, 158, -12), (338, 214, 186, 6), (530, 300, 116, -10)],
        deco=[("spark", 262, 214, 40), ("spark2", 600, 236, 28), ("squig", 56, 250, 70)]),
    "naver_pc": dict(w=824, h=464, mask=[("v", [(0, 1), (209, 1), (362, 0)])], glow=[(180, -150, 460)],
        slots=[(56, 82, 180, -10), (309, 36, 206, 4), (588, 80, 180, 9)],
        deco=[("spark", 262, 30, 36), ("spark2", 536, 232, 26), ("heart", 740, 40, 30), ("squig", 48, 36, 62), ("bubble", 250, 190, 28), ("bubble", 770, 190, 24)]),
    "naver_mo": dict(w=640, h=360, mask=[("v", [(0, 1), (162, 1), (281, 0)])], glow=[(140, -130, 360)],
        slots=[(46, 62, 140, -10), (240, 26, 160, 4), (456, 60, 140, 9)],
        deco=[("spark", 204, 22, 30), ("spark2", 418, 186, 22), ("heart", 574, 30, 26), ("squig", 38, 26, 52), ("bubble", 196, 160, 22)]),
    "chat": dict(w=984, h=552, mask=[("v", [(0, 1), (248, 1), (430, 0)])], glow=[(230, -170, 540)],
        slots=[(70, 110, 210, -10), (372, 46, 240, 4), (700, 104, 210, 9)],
        deco=[("spark", 330, 40, 40), ("spark2", 640, 300, 30), ("heart", 880, 50, 34), ("squig", 70, 46, 70), ("bubble", 268, 296, 26)]),
}
TARGETS = {
    "som": [("soop_pc", "SOM_soop_main_pc_1344x260"), ("soop_mo", "SOM_soop_main_mo_672x440")],
    "nom": [("naver_pc", "NOM_naver_pc_824x464"), ("naver_mo", "NOM_naver_mo_640x360")],
    "com": [("chat", "COM_chattingplus_984x552")],
    "insta": [("insta", "INSTA_card_1080x1350")],
}
# 벡터 장식 (HTML Path2D 와 동일 좌표)
SPARK = [((20, 2), (22, 14), (26, 18), (38, 20)), ((38, 20), (26, 22), (22, 26), (20, 38)),
         ((20, 38), (18, 26), (14, 22), (2, 20)), ((2, 20), (14, 18), (18, 14), (20, 2))]
HEART = [((20, 35), (6, 25), (2, 17), (6, 10)), ((6, 10), (10, 4), (18, 5), (20, 12)),
         ((20, 12), (22, 5), (30, 4), (34, 10)), ((34, 10), (38, 17), (34, 25), (20, 35))]
SQUIG = [((4, 30), (14, 4), (26, 4), (26, 22)), ((26, 22), (26, 36), (12, 30), (20, 16)),
         ((20, 16), (28, 4), (44, 6), (46, 22)), ((46, 22), (48, 34), (60, 26), (66, 14))]

SS = 2  # 슈퍼샘플 배율 (장식·카드 외곽 안티앨리어싱)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- zip 읽기
def _decode_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except Exception:
        return info.filename


def analyze(im):
    """투명 여백 제거 + 배치 점수 + 색상 샘플 (HTML analyze 동일 로직)"""
    im = im.convert("RGBA")
    w, h = im.size
    a = im.split()[3]
    mask = a.point(lambda v: 255 if v > 20 else 0)
    bbox = mask.getbbox() or (0, 0, w, h)
    hist = mask.histogram()
    cnt = sum(hist[128:])
    cov = cnt / (w * h)
    touch = (bbox[0] <= 2) + (bbox[1] <= 2) + (bbox[2] >= w - 2) + (bbox[3] >= h - 2)
    score = 3 - touch * 1.2 - abs(cov - 0.38) * 3
    if cov > 0.85:
        score -= 3
    trim = im.crop(bbox)
    sc = min(1, 120 / max(w, h))
    sample = im.resize((max(1, round(w * sc)), max(1, round(h * sc))))
    return dict(full=im, trim=trim, score=score, sample=sample)


def read_zip(data, filename="", max_side=560):
    """zip bytes → emos 리스트 + 기본 이름 (max_side: 메모리 절약용 축소 상한)"""
    zf = zipfile.ZipFile(io.BytesIO(data))
    entries, tops = [], set()
    for info in zf.infolist():
        name = unicodedata.normalize("NFC", _decode_name(info))
        if info.is_dir() or "__MACOSX" in name:
            continue
        base = name.split("/")[-1]
        if not base or base.startswith("."):
            continue
        if not re.search(r"\.(png|gif|webp|jpe?g)$", base, re.I):
            continue
        if "/" in name:
            tops.add(name.split("/")[0])
        entries.append((name, base, info))
    stem = lambda b: re.sub(r"\.[^.]+$", "", b).lower()
    emo = [e for e in entries if stem(e[1]) not in ("main", "tab")]
    num = lambda b: int(m.group(1)) if (m := re.match(r"^(\d+)", b)) else 9999
    emo.sort(key=lambda e: (num(e[1]), e[1]))
    if not emo:
        raise ValueError("zip 안에서 이모티콘 이미지(png/gif)를 찾지 못했어요.")
    out = []
    for i, (name, base, info) in enumerate(emo):
        raw = zf.read(info)
        gif_bytes = None
        if re.search(r"\.gif$", base, re.I):
            try:
                probe = Image.open(io.BytesIO(raw))
                if getattr(probe, "n_frames", 1) > 1:
                    gif_bytes = raw
            except Exception:
                pass
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        if max_side and max(im.size) > max_side:
            k = max_side / max(im.size)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        d = analyze(im)
        n = num(base)
        d["num"] = i + 1 if n == 9999 else n
        d["gif"] = gif_bytes
        d["frames"] = None
        out.append(d)
    name = re.sub(r"\.zip$", "", filename, flags=re.I)
    name = re.sub(r"^[0-9a-f]{8}-", "", name)
    if len(tops) == 1:
        name = next(iter(tops))
    return out, unicodedata.normalize("NFC", name).replace("_", " ").strip()


# ---------------------------------------------------------------- 자동 선택·색
def ranked(emos):
    return sorted(range(len(emos)), key=lambda i: -emos[i]["score"])


def auto_picks(emos, k):
    r = ranked(emos)
    n = len(r)
    g = lambda j: r[(3 * k + j) % n]
    return [g(1), g(0), g(2), g(3)], [r[(3 * k + 4) % n], r[(3 * k + 5) % n]]


def _rgb2hls(r, g, b):
    r, g, b = r / 255, g / 255, b / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0, l, 0
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h / 6, l, s


def character_hue(emos, idxs):
    bins = [0.0] * 36
    total = 0
    for i in idxs:
        for r, g, b, a in emos[i]["sample"].getdata():
            if a < 200:
                continue
            h, l, s = _rgb2hls(r, g, b)
            if l > 0.92 or l < 0.12 or s < 0.15:
                continue
            bins[int(h * 36) % 36] += s
            total += 1
    if not total:
        return 0, 0
    i = bins.index(max(bins))
    return i * 10 + 5, min(1, total / (len(idxs) * 900))


def auto_palette(h, s):
    if s < 0.18:
        return "mint"
    h %= 360
    if h < 20 or h >= 330:
        return "mint"
    if h < 50:
        return "sky"
    if h < 75:
        return "lavender"
    if h < 160:
        return "peach"
    if h < 260:
        return "butter"
    return "lime"


def custom_palette(hexcol):
    r, g, b = hex_rgb(hexcol)
    h, l, s = _rgb2hls(r, g, b)
    import colorsys
    def hls_hex(hh, ll, ss):
        rr, gg, bb = colorsys.hls_to_rgb(hh % 1, max(0, min(1, ll)), max(0, min(1, ss)))
        return "#%02X%02X%02X" % (round(rr * 255), round(gg * 255), round(bb * 255))
    return dict(bg=hexcol, sh=hex_rgb(hls_hex(h, 0.45, min(1, s + .2))), accent=hls_hex(h, 0.5, 0.75),
                ink="#2B2B33", deco="#FFFFFF", label=hexcol)


# ---------------------------------------------------------------- 움직이는 장면(APNG)
ANIM_T = None            # 그리는 중인 시점(ms). None 이면 정지 이미지
FRAME_SCALE = 0.5
TICK = 100               # 장면 간격(ms)
MAX_LOOP = 2000          # 최대 루프 길이(ms)


ANIM_SET = None   # 움직이게 할 이모티콘 id 집합. None 이면 전부


def view(emo):
    """ANIM_T 시점의 프레임으로 바꾼 emo (정지면 그대로)"""
    if ANIM_T is None or not emo.get("frames"):
        return emo
    if ANIM_SET is not None and id(emo) not in ANIM_SET:
        return emo
    f = emo["frames"]
    t = ANIM_T % f["total"]
    acc = 0
    fr = f["list"][-1]
    for cand in f["list"]:
        acc += cand["delay"]
        if t < acc:
            fr = cand
            break
    e2 = dict(emo)
    e2["full"], e2["trim"] = fr["full"], fr["trim"]
    return e2


def ensure_frames(emo):
    """GIF 전 장면을 풀어 공통 영역으로 잘라 축소 보관 (HTML ensureFrames 동일)"""
    if emo.get("frames") or not emo.get("gif"):
        return
    from PIL import ImageSequence
    src = Image.open(io.BytesIO(emo["gif"]))
    W, H = src.size
    raws = []
    bbox = None
    for frame in ImageSequence.Iterator(src):
        fr = frame.convert("RGBA")
        delay = max(20, int(frame.info.get("duration", 100)))
        a = fr.split()[3].point(lambda v: 255 if v > 20 else 0)
        b = a.getbbox()
        if b:
            bbox = b if bbox is None else (min(bbox[0], b[0]), min(bbox[1], b[1]),
                                           max(bbox[2], b[2]), max(bbox[3], b[3]))
        raws.append((fr, delay))
    if bbox is None:
        bbox = (0, 0, W, H)
    sc = FRAME_SCALE
    fw, fh = max(1, round(W * sc)), max(1, round(H * sc))
    lst, total = [], 0
    for fr, delay in raws:
        crop = fr.crop(bbox)
        crop = crop.resize((max(1, round(crop.width * sc)), max(1, round(crop.height * sc))), Image.LANCZOS)
        full = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
        full.alpha_composite(crop, (round(bbox[0] * sc), round(bbox[1] * sc)))
        lst.append(dict(delay=delay, full=full, trim=crop))
        total += delay
    emo["frames"] = dict(list=lst, total=total)


def release_frames(emos):
    for e in emos:
        e["frames"] = None


def used_indexes(key, style, picks, icons):
    S = L[key]
    n = len(S.get("slotsHalo", S["slots"]) if style == "halo" else S["slots"])
    u = list(picks[:n])
    if key == "chat":
        u += icons[:2]
    seen = []
    for i in u:
        if i not in seen:
            seen.append(i)
    return seen


# ---------------------------------------------------------------- 그리기 도구
def bezier(p0, p1, p2, p3, steps=24):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        pts.append((mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
                    mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]))
    return pts


def path_points(segs):
    pts = []
    for s in segs:
        pts += bezier(*s)
    return pts


def rrect(d, box, r, **kw):
    d.rounded_rectangle(box, radius=r, **kw)


def contain(iw, ih, bx, by, bw, bh, px, py):
    k = min(bw / iw, bh / ih)
    w, h = iw * k, ih * k
    return bx + (bw - w) * px, by + (bh - h) * py, w, h


def draw_pattern(img, style, masks):
    w, h = img.size
    pat = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(pat)
    if style == "card":
        c = (255, 255, 255, 107)
        for x in range(0, w + 1, 22):
            d.rectangle([x, 0, x, h], fill=c)
        for y in range(0, h + 1, 22):
            d.rectangle([0, y, w, y], fill=c)
    else:
        c = (255, 255, 255, 191)
        for x in range(13, w, 26):
            for y in range(13, h, 26):
                d.ellipse([x - 2.2, y - 2.2, x + 2.2, y + 2.2], fill=c)
    for dirn, stops in (masks or []):
        ln = w if dirn == "h" else h
        grad = Image.new("L", (w, 1) if dirn == "h" else (1, h))
        gp = grad.load()
        ss = sorted([(min(1, max(0, p / ln)), a) for p, a in stops])
        for i in range(ln):
            t = i / max(1, ln - 1)
            a = ss[0][1] if t <= ss[0][0] else ss[-1][1]
            for (p0, a0), (p1, a1) in zip(ss, ss[1:]):
                if p0 <= t <= p1:
                    a = a0 if p1 == p0 else a0 + (a1 - a0) * (t - p0) / (p1 - p0)
                    break
            if dirn == "h":
                gp[i, 0] = int(a * 255)
            else:
                gp[0, i] = int(a * 255)
        grad = grad.resize((w, h))
        alpha = pat.split()[3]
        from PIL import ImageChops
        pat.putalpha(ImageChops.multiply(alpha, grad))
    img.alpha_composite(pat)


def draw_glow(img, gx, gy, gs):
    r = gs // 2
    m = Image.new("L", (gs, gs), 0)
    dm = ImageDraw.Draw(m)
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps          # 1 → 0
        if t > 0.7:
            a = 0
        else:
            a = 0.65 * (1 - t / 0.7)
        dm.ellipse([r - r * t, r - r * t, r + r * t, r + r * t], fill=int(a * 255))
    ov = Image.new("RGBA", (gs, gs), (255, 255, 255, 0))
    ov.putalpha(m)
    img.alpha_composite(ov, (int(gx), int(gy)))


def _poly_sprite(segs, size, box, fill, stroke, lw):
    S = int(size * SS)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = S / box
    pts = [(x * k, y * k) for x, y in path_points(segs)]
    if fill:
        d.polygon(pts, fill=fill)
    if stroke:
        d.line(pts + [pts[0]], fill=stroke, width=max(1, int(lw * k)), joint="curve")
    return im.resize((size, size), Image.LANCZOS)


def draw_deco(img, kind, X, Y, s, P):
    ink = hex_rgb(P["ink"]) + (255,)
    if kind in ("spark", "spark2", "heart"):
        fill = {"spark": (255, 224, 122, 255), "spark2": (255, 255, 255, 255), "heart": (255, 140, 140, 255)}[kind]
        lw = 2.4 if kind == "spark" else 2.6
        sp = _poly_sprite(HEART if kind == "heart" else SPARK, s, 40, fill, ink, lw)
        img.alpha_composite(sp, (int(X), int(Y)))
    elif kind == "squig":
        S = int(s * SS)
        im2 = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im2)
        k = S / 70
        pts = [(x * k, y * k) for x, y in path_points(SQUIG)]
        d.line(pts, fill=hex_rgb(P["deco"]) + (255,), width=max(1, int(5 * k)), joint="curve")
        img.alpha_composite(im2.resize((s, s), Image.LANCZOS), (int(X), int(Y)))
    elif kind == "bubble":
        S = int(s * SS)
        im2 = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im2)
        r = S / 2
        d.ellipse([2 * SS, 2 * SS, S - 2 * SS, S - 2 * SS], fill=(255, 255, 255, 140), outline=(255, 255, 255, 255), width=int(2.5 * SS))
        rr = max(2 * SS, r * .22)
        d.ellipse([r * .7 - rr, r * .7 - rr, r * .7 + rr, r * .7 + rr], fill=(255, 255, 255, 255))
        img.alpha_composite(im2.resize((s, s), Image.LANCZOS), (int(X), int(Y)))


def _shadow_of(sprite, color, alpha, blur, dy):
    a = sprite.split()[3]
    sh = Image.new("RGBA", sprite.size, tuple(color) + (0,))
    sh.putalpha(a.point(lambda v: int(v * alpha)))
    if blur:
        sh = sh.filter(ImageFilter.GaussianBlur(blur))
    return sh, dy


def paste_sprite(img, sprite, x, y, sh_color, sh_alpha=0.22, blur=13, dy=12):
    sh, dy = _shadow_of(sprite, sh_color, sh_alpha, blur, dy)
    img.alpha_composite(sh, (int(x), int(y + dy)))
    img.alpha_composite(sprite, (int(x), int(y)))


def make_card(s, rot, emo, P):
    """흰 스티커 카드 + 이모티콘 (회전 포함 스프라이트)"""
    S = int(s * SS)
    card = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    R = S * 0.26
    rrect(d, [0, 0, S - 1, S - 1], R, fill=(255, 253, 248, 255))
    # 내용
    clip = Image.new("L", (S, S), 0)
    rrect(ImageDraw.Draw(clip), [0, 0, S - 1, S - 1], R, fill=255)
    from PIL import ImageChops
    inner = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    b, o = S * 1.04, -S * 0.02
    ix, iy, iw, ih = contain(emo["full"].width, emo["full"].height, o, o, b, b, .5, .6)
    inner.alpha_composite(emo["full"].resize((max(1, int(iw)), max(1, int(ih))), Image.LANCZOS), (int(ix), max(0, int(iy))))
    inner.putalpha(ImageChops.multiply(inner.split()[3], clip))
    card.alpha_composite(inner)
    # 안쪽 테두리
    line = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rrect(ImageDraw.Draw(line), [3 * SS, -3 * SS, S - 3 * SS, S - 3 * SS], R, outline=tuple(P["sh"]) + (31,), width=6 * SS)
    line.putalpha(ImageChops.multiply(line.split()[3], clip))
    card.alpha_composite(line)
    card = card.resize((int(s), int(s)), Image.LANCZOS)
    if rot:
        card = card.rotate(-rot, resample=Image.BICUBIC, expand=True)
    return card


def outlined_char(emo, max_w, max_h, o=3):
    im = emo["trim"]
    k = min(max_w / im.width, max_h / im.height)
    w, h = max(1, int(im.width * k)), max(1, int(im.height * k))
    im = im.resize((w, h), Image.LANCZOS)
    pad = o + 1
    cv = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    cv.alpha_composite(im, (pad, pad))
    grown = cv.split()[3].filter(ImageFilter.MaxFilter(o * 2 + 1))
    out = Image.new("RGBA", cv.size, (255, 255, 255, 0))
    out.paste(Image.new("RGBA", cv.size, (255, 255, 255, 255)), (0, 0), grown)
    out.alpha_composite(cv)
    return out


def draw_char(img, emo, cx, bottom, max_w, max_h, rot, P, o=3):
    c = outlined_char(emo, max_w, max_h, o)
    if rot:
        c = c.rotate(-rot, resample=Image.BICUBIC, expand=True)
    x, y = cx - c.width / 2, bottom - c.height + o + 1
    paste_sprite(img, c, x, y, P["sh"], 0.25, 4, 8)


def make_halo(X, Y, s, emo, P, img):
    S = int(s * SS)
    circ = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(circ)
    d.ellipse([0, 0, S - 1, S - 1], fill=(255, 255, 255, 255))
    # 점선 안쪽 원
    r2 = S / 2 - S * 0.07
    cx = cy = S / 2
    acc = hex_rgb(P["accent"]) + (85,)
    n = int(2 * math.pi * r2 / ((8 + 6) * SS))
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = a0 + (8 / (8 + 6)) * 2 * math.pi / n
        d.arc([cx - r2, cy - r2, cx + r2, cy + r2], math.degrees(a0), math.degrees(a1), fill=acc, width=3 * SS)
    circ = circ.resize((int(s), int(s)), Image.LANCZOS)
    paste_sprite(img, circ, X, Y, P["sh"], 0.18, 15, 13)
    draw_char(img, emo, X + s / 2, Y + s - s * 0.04, s * 1.12, s * 1.18, 0, P)


# ---------------------------------------------------------------- 텍스트 (Jua, *강조*)
def segments(text):
    out = []
    text = unicodedata.normalize("NFC", text or "")
    last = 0
    for m in re.finditer(r"\*(.+?)\*", text):
        if m.start() > last:
            out.append((text[last:m.start()], False))
        out.append((m.group(1), True))
        last = m.end()
    if last < len(text):
        out.append((text[last:], False))
    return out


def _font(fs):
    return ImageFont.truetype(JUA, int(fs))


def rich_width(segs, fs, ls=0.0):
    f = _font(fs)
    return sum(f.getlength(t) + ls * len(t) for t, _ in segs)


def fit_size(segs, fs, maxw, ls_pct=0.0):
    while fs > 14 and rich_width(segs, fs, ls_pct * fs / 100) > maxw:
        fs -= 1
    return fs


def draw_rich(img, segs, cx, cy, fs, sw, P, ls=0.0):
    """가운데 정렬, 흰 테두리 + 아래 그림자 (JS drawRich 동일)"""
    f = _font(fs)
    total = rich_width(segs, fs, ls)
    stroke = max(1, round(sw / 2))
    asc, desc = f.getmetrics()
    top = cy - (asc + desc) / 2
    d = ImageDraw.Draw(img)
    accent_col = hex_rgb(P["accent"])
    ink_col = hex_rgb(P["ink"])
    sh_col = tuple(P["sh"]) + (150,)

    def pass_draw(dy, fill_fn, stroke_fill):
        x = cx - total / 2
        for t, acc in segs:
            if ls > 0:
                for ch in t:
                    d.text((x, top + dy), ch, font=f, fill=fill_fn(acc),
                           stroke_width=(stroke if stroke_fill else 0), stroke_fill=stroke_fill)
                    x += f.getlength(ch) + ls
            else:
                d.text((x, top + dy), t, font=f, fill=fill_fn(acc),
                       stroke_width=(stroke if stroke_fill else 0), stroke_fill=stroke_fill)
                x += f.getlength(t)

    pass_draw(5, lambda a: sh_col, sh_col)                       # 그림자
    pass_draw(0, lambda a: (255, 255, 255), (255, 255, 255))     # 흰 테두리
    pass_draw(0, lambda a: accent_col if a else ink_col, None)   # 본문
    return total


def draw_pill(img, text, cx, top, fs, pad_y, pad_x, bg, fg, P, pipe_color=None):
    text = unicodedata.normalize("NFC", text)
    f = _font(fs)
    tw = f.getlength(text) + len(text)
    h, w = fs * 1.2 + pad_y * 2, tw + pad_x * 2
    pill = Image.new("RGBA", (int(w) + 8, int(h) + 8), (0, 0, 0, 0))
    rrect(ImageDraw.Draw(pill), [0, 0, int(w) - 1, int(h) - 1], h / 2, fill=hex_rgb(bg) + (255,) if isinstance(bg, str) else bg)
    paste_sprite(img, pill, cx - w / 2, top, P["sh"], 0.25, 2, 4)
    d = ImageDraw.Draw(img)
    asc, desc = f.getmetrics()
    x = cx - tw / 2
    ty = top + h / 2 + 1 - (asc + desc) / 2
    for ch in text:
        col = pipe_color if (pipe_color and ch == "|") else fg
        col = hex_rgb(col) if isinstance(col, str) else col
        d.text((x, ty), ch, font=f, fill=col)
        x += f.getlength(ch) + 1


TEXT_DEFAULT = dict(cX=0, cY=0, cS=100, itX=0, itY=0, itS=100, ifX=0, ifY=0, ifS=100)


def _text(opts):
    t = dict(TEXT_DEFAULT)
    t.update(opts.get("text") or {})
    return t


# ---------------------------------------------------------------- 지면 그리기
def render_stage(key, P, style, emos, picks, opts):
    S = L[key]
    w, h = S["w"], S["h"]
    img = Image.new("RGBA", (w, h), hex_rgb(P["bg"]) + (255,))
    draw_pattern(img, style, S.get("mask"))
    for g in S["glow"]:
        draw_glow(img, *g)
    for dk in S["deco"]:
        draw_deco(img, dk[0], dk[1], dk[2], dk[3], P)
    slots = S.get("slotsHalo", S["slots"]) if style == "halo" else S["slots"]
    for i, (X, Y, s, r) in enumerate(slots):
        if i >= len(picks):
            break
        emo = view(emos[picks[i]])
        if style == "halo":
            s = min(s, h - 16)
            Y = max(8, min(Y, h - s - 8))
            make_halo(X, Y, s, emo, P, img)
        else:
            card = make_card(s, r, emo, P)
            paste_sprite(img, card, X - (card.width - s) / 2, Y - (card.height - s) / 2, P["sh"])
    if key == "chat":
        T = _text(opts)
        sc = T["cS"] / 100
        dx, dy = T["cX"], T["cY"]
        pill_top = 358 + dy - (sc - 1) * 30
        if opts.get("tagline"):
            draw_pill(img, opts["tagline"], w / 2 + dx, pill_top, round(24 * max(.8, sc)), 6, 20,
                      P["accent"], (255, 255, 255), P)
        segs = segments(opts["chat"])
        fs = fit_size(segs, round(56 * sc), 690 + max(0, sc - 1) * 300)
        tw = rich_width(segs, fs)
        ic_h, gap = round(84 * sc), 12
        ic = [view(emos[i]) for i in opts.get("icons", []) if i < len(emos)]
        icw = [min(110 * sc, e["trim"].width * ic_h / e["trim"].height) for e in ic]
        total = tw + sum(icw) + gap * len(icw)
        left = w / 2 + dx - total / 2
        cy = 450 + dy
        if ic:
            draw_char(img, ic[0], left + icw[0] / 2, cy + ic_h / 2, icw[0], ic_h, 0, P, 2)
            left += icw[0] + gap
        draw_rich(img, segs, left + tw / 2, cy, fs, 10, P)
        left += tw + gap
        if len(ic) > 1:
            draw_char(img, ic[1], left + icw[1] / 2, cy + ic_h / 2, icw[1], ic_h, 0, P, 2)
    return img


def render_insta(P, style, emos, picks, opts):
    W, H, head, foot = 1080, 1350, 322, 124
    img = Image.new("RGBA", (W, H), (255, 253, 246, 255))
    hd = Image.new("RGBA", (W, head), hex_rgb(P["bg"]) + (255,))
    draw_pattern(hd, style, None)
    draw_glow(hd, 240, -200, 600)
    for dk in [("spark", 196, 36, 40), ("spark2", 770, 226, 30), ("bubble", 790, 30, 30), ("bubble", 250, 240, 22)]:
        draw_deco(hd, *dk, P)
    img.paste(hd, (0, 0))
    if picks:
        draw_char(img, emos[picks[0]], 130, head, 270, 250, -4, P)
    if len(picks) > 2:
        draw_char(img, emos[picks[2]], 950, head, 260, 240, 4, P)
    # 머리 영역 밖으로 번진 캐릭터는 그대로 (JS 도 clip 안에서 그려 살짝 잘림) → head 아래 잘라줌
    T = _text(opts)
    segs = segments(opts["name"])
    fs = fit_size(segs, round(128 * T["itS"] / 100), 560 + max(0, T["itS"] - 100) * 3, 3)
    pill_h = (28 * 1.2 + 20) if opts.get("creator") else 0
    gap_p = 22 if opts.get("creator") else 0
    block_h = fs * 1.0 + gap_p + pill_h
    top = (head - block_h) / 2 - 6 + T["itY"]
    tcx = W / 2 + T["itX"]
    draw_rich(img, segs, tcx, top + fs * 0.5, fs, max(10, 16 * fs / 128), P, fs * 0.03)
    if opts.get("creator"):
        draw_pill(img, f"크리에이터 | {opts['creator']}", tcx, top + fs + gap_p, 28, 10, 28,
                  P["ink"], (255, 255, 255), P, P["bg"])
    # 그리드
    n = len(emos)
    cols = 4
    rows = math.ceil(n / cols)
    gx, gy, gw = 70, head + 20, 940
    gh = (H - foot - 18) - gy
    cg, rg = 22, 10
    cw, ch = (gw - cg * (cols - 1)) / cols, (gh - rg * (rows - 1)) / rows
    for i, e0 in enumerate(emos):
        e = view(e0)
        X = gx + (i % cols) * (cw + cg)
        Y = gy + (i // cols) * (ch + rg)
        cell = Image.new("RGBA", (int(cw), int(ch)), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cell)
        rrect(cd, [0, 0, int(cw) - 1, int(ch) - 1], 18, fill=(255, 255, 255, 255), outline=tuple(P["sh"]) + (20,), width=2)
        ix, iy, iw, ih = contain(e["full"].width, e["full"].height, 0, 0, cw, ch, .5, 1)
        cell.alpha_composite(e["full"].resize((max(1, int(iw)), max(1, int(ih))), Image.LANCZOS), (int(ix), int(iy)))
        mask = Image.new("L", cell.size, 0)
        rrect(ImageDraw.Draw(mask), [0, 0, int(cw) - 1, int(ch) - 1], 18, fill=255)
        cell.putalpha(Image.composite(cell.split()[3], Image.new("L", cell.size, 0), mask))
        paste_sprite(img, cell, X, Y, P["sh"], 0.12, 2, 4)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - foot, W, H], fill=hex_rgb(P["bg"]) + (255,))
    fsegs = segments(opts.get("footer") or "")
    if fsegs:
        ffs = fit_size(fsegs, round(80 * T["ifS"] / 100), 900, 3)
        draw_rich(img, fsegs, W / 2 + T["ifX"], H - foot / 2 + T["ifY"], ffs,
                  max(8, 14 * ffs / 80), P, ffs * 0.03)
    return img


def _encode_apng(frames_rgb, durations, colors, step):
    """프레임(RGB)들을 공통 팔레트로 양자화해 APNG 인코딩.
    step>1 이면 프레임을 솎되 지속시간을 합쳐 재생 속도를 유지한다."""
    fs, ds = [], []
    for i, f in enumerate(frames_rgb):
        if i % step == 0:
            fs.append(f)
            ds.append(durations[i])
        else:
            ds[-1] += durations[i]
    MEDIANCUT = getattr(getattr(Image, "Quantize", Image), "MEDIANCUT", 0)
    FS_DITHER = getattr(getattr(Image, "Dither", Image), "FLOYDSTEINBERG", 3)
    pal = fs[0].quantize(colors, method=MEDIANCUT)
    qs = [pal] + [f.quantize(colors, palette=pal, dither=FS_DITHER) for f in fs[1:]]
    buf = io.BytesIO()
    qs[0].save(buf, "PNG", save_all=True, append_images=qs[1:], duration=ds, loop=0,
               optimize=True)
    return buf.getvalue(), len(fs)


def _anim_timeline(emos, subset, loop, merge=45):
    """subset(emo 인덱스)의 실제 프레임 전환 시각 → (times, durations).
    merge: 이보다 짧은 간격은 병합(값이 클수록 장면 수가 줄어 용량이 작아짐)"""
    events = {0}
    for i in subset:
        f = emos[i]["frames"]
        acc = 0
        while acc < loop:
            for fr in f["list"]:
                acc += fr["delay"]
                if acc >= loop:
                    break
                events.add(acc)
    times = [0]
    for t in sorted(events):
        if t - times[-1] >= merge:
            times.append(t)
    durations = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    durations.append(max(20, loop - times[-1]))
    return times, durations


def _render_timeline(key, P, style, emos, picks, opts, subset, times):
    global ANIM_T, ANIM_SET
    ANIM_SET = {id(emos[i]) for i in subset}
    frames = []
    for t in times:
        ANIM_T = t
        frames.append(render_stage(key, P, style, emos, picks, opts).convert("RGB"))
    ANIM_T = None
    ANIM_SET = None
    return frames


def export_animated(key, base, P, style, emos, picks, opts, used):
    """부드러움(원본 타이밍)을 지키고, 용량이 넘치면 '움직이는 이모티콘 수'를 먼저 줄인다.
    그래도 넘치면 정지 PNG 로 (500KB 를 절대 넘기지 않음)."""
    for i in used:
        ensure_frames(emos[i])
    S = L[key]
    n_slots = len(S.get("slotsHalo", S["slots"]) if style == "halo" else S["slots"])
    main = [i for i in used if i in picks[:min(3, n_slots)]]
    hero = [i for i in used if len(picks) > 1 and i == picks[1]]
    full = min(MAX_LOOP, max(emos[i]["frames"]["total"] for i in used))
    # 줄이는 순서: 색 → 반복 길이 1초 → 메인 이모티콘만 1초 → 가운데만
    plans = [
        dict(subset=used, cap=MAX_LOOP, label="", colors=(256, 160, 112, 96, 72, 56, 48)),
        dict(subset=used, cap=1000, label="1초 반복", colors=(160, 112, 96, 72, 56, 48)),
        dict(subset=main, cap=1000, label="배너 이모티콘만 움직임 · 1초 반복",
             colors=(112, 96, 72, 56, 48)),
        dict(subset=hero, cap=MAX_LOOP, label="가운데 이모티콘만 움직임", colors=(160, 112, 96, 72)),
    ]
    plans = [p for i, p in enumerate(plans) if p["subset"]
             and not (i == 1 and full <= 1000)
             and not (i == 2 and len(p["subset"]) == len(used))]
    for plan in plans:
        loop = min(plan["cap"], max(emos[i]["frames"]["total"] for i in plan["subset"]))
        times, durations = _anim_timeline(emos, plan["subset"], loop, 45)
        frames = _render_timeline(key, P, style, emos, picks, opts, plan["subset"], times)
        for colors in plan["colors"]:
            data, n = _encode_apng(frames, durations, colors, 1)
            if len(data) <= 500 * 1024:
                return dict(name=f"{base}.png", data=data, w=S["w"], h=S["h"],
                            anim=dict(sec=round(loop / 1000, 1), colors=colors, frames=n),
                            note=plan["label"])
    # 전부 넘치면 정지 이미지로
    img = render_stage(key, P, style, emos, picks, opts)
    return dict(export(img, base), note="용량 제한 때문에 정지 이미지로 저장")


def export_insta_gif(base, P, style, emos, picks, opts, progress=lambda m: None):
    """카드뉴스(1080x1350) 움직이는 GIF — 모든 GIF 이모티콘이 움직임, 용량 제한 없음"""
    global ANIM_T
    gifs = [i for i, e in enumerate(emos) if e.get("gif")]
    for i in gifs:
        ensure_frames(emos[i])
    loop = min(MAX_LOOP, max(emos[i]["frames"]["total"] for i in gifs))
    times, durations = _anim_timeline(emos, gifs, loop)
    frames = []
    for k, t in enumerate(times):
        ANIM_T = t
        frames.append(render_insta(P, style, emos, picks, opts).convert("RGB"))
        progress(f"{round((k + 1) / len(times) * 100)}%")
    ANIM_T = None
    MEDIANCUT = getattr(getattr(Image, "Quantize", Image), "MEDIANCUT", 0)
    pal = frames[0].quantize(255, method=MEDIANCUT)
    qs = [pal] + [f.quantize(255, palette=pal) for f in frames[1:]]
    buf = io.BytesIO()
    qs[0].save(buf, "GIF", save_all=True, append_images=qs[1:], duration=durations, loop=0,
               optimize=True, disposal=1)
    return dict(name=f"{base}.gif", data=buf.getvalue(), w=1080, h=1350, gif=True,
                anim=dict(sec=round(loop / 1000, 1)), note="인스타에선 첫 장면으로 보여요")


# ---------------------------------------------------------------- 내보내기·생성
def export(img, base):
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    ext = "png"
    if buf.tell() > 500 * 1024:
        for q in (92, 85):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=q)
            ext = "jpg"
            if buf.tell() <= 500 * 1024:
                break
    return dict(name=f"{base}.{ext}", data=buf.getvalue(), w=img.width, h=img.height)


def generate(emos, opts, variants, targets, progress=lambda *a: None, anim=True, vid=False):
    """variants: [{on, style, color, hex, pick(번호), icons(번호)}] → 결과 리스트
    anim=True 면 GIF 가 쓰인 SOM·NOM·COM 배너를 움직이는 PNG(APNG)로,
    vid=True 면 인스타 카드뉴스의 움직이는 GIF 도 함께 만든다."""
    num2idx = {e["num"]: i for i, e in enumerate(emos)}
    results = []
    base_pal = None
    vs = [v for v in variants if v.get("on", True)] or [dict(style="card", color="auto", pick=[], icons=[])]
    for k, v in enumerate(vs):
        progress(k, len(vs), None)
        ap, ai = auto_picks(emos, k)
        picks = [num2idx[n] for n in v.get("pick", []) if n in num2idx]
        for i in ap:
            if len(picks) >= 4:
                break
            if i not in picks:
                picks.append(i)
        icons = [num2idx[n] for n in v.get("icons", []) if n in num2idx] or ai
        if base_pal is None:
            h, s = character_hue(emos, picks[:3])
            base_pal = auto_palette(h, s)
        pname = v.get("color", "auto")
        if pname == "auto":
            pname = base_pal if k == 0 else [c for c in ALT_ORDER if c != base_pal][(k - 1) % 6]
        P = custom_palette(v["hex"]) if pname == "custom" else PALETTES[pname]
        o = dict(opts, icons=icons)
        files = []
        for t in targets:
            for key, fname in TARGETS[t]:
                used = [] if key == "insta" else [i for i in used_indexes(key, v["style"], picks, icons)
                                                  if emos[i].get("gif")]
                if anim and used:
                    progress(k, len(vs), f"{fname.split('_')[0]} 움직이는 PNG 만드는 중")
                    files.append(dict(export_animated(key, fname, P, v["style"], emos, picks, o, used), target=t))
                else:
                    img = render_insta(P, v["style"], emos, picks, o) if key == "insta" \
                        else render_stage(key, P, v["style"], emos, picks, o)
                    files.append(dict(export(img, fname), target=t))
                if key == "insta" and vid and any(e.get("gif") for e in emos):
                    progress(k, len(vs), "카드뉴스 움직이는 GIF 만드는 중")
                    files.append(dict(export_insta_gif(fname, P, v["style"], emos, picks, o), target=t))
        release_frames(emos)
        results.append(dict(label=f"시안 {k + 1}", style=v["style"], pname=pname,
                            pal_label=P["label"], bg=P["bg"],
                            pick=[emos[i]["num"] for i in picks], icons=[emos[i]["num"] for i in icons],
                            files=files))
    return results
