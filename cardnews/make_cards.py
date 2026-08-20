# -*- coding: utf-8 -*-
"""
OGQ 월간 크리에이터 인터뷰 카드뉴스 자동 생성기

네이버 폼 설문 응답 엑셀(.xlsx)을 읽어 인스타그램 카드뉴스 PNG(1080x1350)와
게시글 캡션(caption.txt)을 자동 생성한다.

사용법:
    python make_cards.py --excel responses.xlsx --row 0 --config config.yaml
    python make_cards.py --excel responses.xlsx --all
    python make_cards.py --excel responses.xlsx --row 0 --preview
"""

import argparse
import base64
import json
import random
import re
import shutil
import ssl
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

# Windows 콘솔에서 한글 출력 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
import yaml
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent

# ---------- 카드 레이아웃 상수 ----------
CARD_FORMATS = {
    "square": (1080, 1080),    # 인스타 피드 1:1
    "portrait": (1080, 1350),  # 인스타 피드 4:5
}
# 배경 테마 팔레트: bg(배경), blob(구름), shadow(그림자 톤 "r, g, b")
THEMES = {
    "mint":     {"bg": "#C9E7DB", "blob": "#E4F4EC", "shadow": "90, 140, 115"},
    "pink":     {"bg": "#F7D9E3", "blob": "#FBECF2", "shadow": "165, 105, 125"},
    "lavender": {"bg": "#DCD6F2", "blob": "#EEEAFA", "shadow": "110, 100, 155"},
    "sky":      {"bg": "#CDE6F5", "blob": "#E6F4FC", "shadow": "85, 125, 155"},
    "cream":    {"bg": "#F5EBD8", "blob": "#FBF5EA", "shadow": "150, 130, 95"},
    "peach":    {"bg": "#FADFCE", "blob": "#FDF0E7", "shadow": "175, 120, 90"},
}

# 홍보 배너 크기 목록 (w, h)
BANNER_SIZES = [(824, 464), (640, 360), (1440, 180), (350, 200), (984, 552)]

QA_TOP_PAD = 90          # 카드 상단 여백
QA_BOTTOM_RESERVE = 130  # 페이지 인디케이터 영역
BUBBLE_GAP = 34          # 말풍선 사이 세로 간격
SET_GAP = 56             # Q&A 세트 사이 간격
MAX_CHUNK_CHARS = 150    # 답변 말풍선 1개당 최대 글자 수(대략)


# ---------- 유틸 ----------
def die(msg: str):
    print(f"[오류] {msg}")
    sys.exit(1)


def warn(msg: str):
    print(f"[경고] {msg}")


def info(msg: str):
    print(f"[안내] {msg}")


def file_to_data_uri(path: Path) -> str:
    """이미지/폰트 파일을 base64 data URI로 변환 (Playwright set_content에서 경로 문제 회피)"""
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif",
        ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2",
    }.get(path.suffix.lower(), "application/octet-stream")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def safe_folder_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "creator"


# ---------- 설정/입력 로드 ----------
def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        die(f"설정 파일을 찾을 수 없습니다: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for key in ("month", "year", "creator_name", "questions"):
        if key not in cfg:
            die(f"config.yaml에 '{key}' 항목이 없습니다.")
    return cfg


def load_fonts_css(cfg: dict) -> str:
    """fonts/ 폴더의 폰트를 @font-face로 임베드. 없으면 시스템 폰트 fallback."""
    fonts_dir = BASE_DIR / "fonts"
    roles = {  # 역할명 → (CSS family 이름, config 키)
        "title": "TitleFont",
        "hand": "HandFont",
        "body": "BodyFont",
        "body_bold": "BodyBoldFont",
    }
    css_parts = []
    font_cfg = cfg.get("fonts") or {}
    for role, family in roles.items():
        fname = font_cfg.get(role)
        fpath = fonts_dir / fname if fname else None
        if fpath and fpath.exists():
            css_parts.append(
                f"@font-face {{ font-family: '{family}'; "
                f"src: url('{file_to_data_uri(fpath)}'); }}"
            )
        else:
            hint = f"fonts/{fname}" if fname else f"config의 fonts.{role}"
            warn(f"폰트 없음: {hint} → 시스템 기본 한글 폰트(Malgun Gothic)로 대체합니다.")
    return "\n".join(css_parts)


def load_image(path_str: str, what: str) -> str:
    path = BASE_DIR / path_str
    if not path.exists():
        die(f"{what} 이미지를 찾을 수 없습니다: {path}\n"
            f"assets/ 폴더에 파일을 넣거나 config.yaml의 경로를 수정해주세요.")
    return file_to_data_uri(path)


def load_responses(excel_path: Path, cfg: dict) -> pd.DataFrame:
    if not excel_path.exists():
        die(f"엑셀 파일을 찾을 수 없습니다: {excel_path}")
    df = pd.read_excel(excel_path, engine="openpyxl")
    if df.empty:
        die("엑셀에 응답 데이터가 없습니다 (2행부터 응답이 있어야 합니다).")

    df.columns = [str(c).strip() for c in df.columns]
    return df


def _norm(s) -> str:
    return re.sub(r"[\s?!.,'\"]+", "", str(s)).lower()


# 인터뷰 내용이 아닌 메타 정보 컬럼 (자동 분류 시 제외)
META_COL_PAT = re.compile(
    r"타임스탬프|timestamp|이메일|e-?mail|아이디|^id$|계정|닉네임|활동명|이름|성함"
    r"|연락처|전화|링크|url|주소|동의|개인정보", re.I)


def resolve_questions(df: pd.DataFrame, cfg: dict) -> list[dict]:
    """config 질문과 엑셀 컬럼을 매칭. 제목이 조금 달라도 자동 매칭하고,
    하나도 안 맞으면 메타 컬럼(아이디/이메일/링크 등)을 뺀 나머지를 질문으로 사용."""
    cols = list(df.columns)

    def looks_like_url_col(c):  # 값에 OGQ 링크가 들어있는 컬럼
        return df[c].astype(str).str.contains("ogqmarket", na=False).any()

    resolved, used = [], set()
    for q in cfg["questions"]:
        key, display = q["column"], q["display"]
        found = key if key in cols else None
        if not found:  # 부분 일치 매칭 (공백/문장부호 무시)
            nk, nd = _norm(key), _norm(display)
            for c in cols:
                if c in used:
                    continue
                nc = _norm(c)
                if (nk and (nk in nc or nc in nk)) or (nd and (nd in nc or nc in nd)):
                    found = c
                    info(f"질문 자동 매칭: 엑셀 '{c}' → '{display[:20]}...'")
                    break
        if found and found not in used:
            resolved.append({"column": found, "display": display})
            used.add(found)
        else:
            warn(f"엑셀에서 찾지 못한 질문(건너뜀): {key}")

    if not resolved:
        info("config 질문과 일치하는 컬럼이 없어 엑셀 컬럼을 자동 분류합니다.")
        for c in cols:
            if META_COL_PAT.search(c) or looks_like_url_col(c):
                info(f"  메타 정보로 판단해 제외: {c}")
                continue
            resolved.append({"column": c, "display": c})
    return resolved


# ---------- OGQ 마켓 연동 ----------
OGQ_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 맥의 python.org 파이썬은 인증서 설정이 안 돼 있는 경우가 많아 certifi를 우선 사용
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


def http_get(url: str, timeout: int = 20):
    global _SSL_CTX
    req = urllib.request.Request(url, headers=OGQ_UA)
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            raise
        warn("SSL 인증서 검증에 실패해 검증 없이 다시 시도합니다 (pip install certifi 권장).")
        _SSL_CTX = ssl._create_unverified_context()
        return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)


def fetch_ogq_artwork(url: str) -> dict:
    """OGQ 마켓 스티커 상세 링크에서 크리에이터명/대표 이미지를 추출한다."""
    m = re.search(r"artworkId=([0-9a-f]+)", url)
    if not m:
        die(f"OGQ 마켓 링크에서 artworkId를 찾을 수 없습니다: {url}")
    artwork_id = m.group(1)

    info(f"OGQ 마켓에서 정보 가져오는 중: {artwork_id}")
    try:
        html = http_get(url).read().decode("utf-8", "ignore")
    except Exception as e:
        die(f"OGQ 마켓 페이지를 불러오지 못했습니다: {e}")

    payload = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not payload:
        die("OGQ 마켓 페이지 구조가 변경된 것 같습니다 (__NUXT_DATA__ 없음).")
    arr = json.loads(payload.group(1))

    def resolve(idx):
        return arr[idx] if isinstance(idx, int) and 0 <= idx < len(arr) else None

    image_url, artwork_name, nickname = None, None, None
    for el in arr:  # 메인 아트워크 객체 (mainImageUrl 보유)
        if isinstance(el, dict) and "mainImageUrl" in el and "creatorId" in el:
            image_url = resolve(el["mainImageUrl"])
            artwork_name = resolve(el.get("defaultName"))
            break
    for el in arr:  # 크리에이터 객체 (username+nickname 보유)
        if isinstance(el, dict) and "nickname" in el and "username" in el:
            nickname = resolve(el["nickname"])
            break

    if not image_url:
        die("스티커 대표 이미지를 찾지 못했습니다. 링크를 확인해주세요.")
    return {"artwork_id": artwork_id, "artwork_name": artwork_name,
            "nickname": nickname, "image_url": image_url}


def remove_white_bg(path: Path):
    """이미지 가장자리와 이어진 흰 배경을 투명하게 가공 (내부 흰색은 유지)"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        warn("Pillow가 없어 흰 배경 제거를 건너뜁니다 (pip install pillow).")
        return
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        r, g, b, a = img.getpixel(corner)
        if a > 0 and r > 235 and g > 235 and b > 235:  # 모서리가 흰색일 때만
            ImageDraw.floodfill(img, corner, (0, 0, 0, 0), thresh=32)
    img.save(path)


def download_ogq_image(art: dict) -> Path:
    """대표 이미지를 고해상도로 다운로드해 흰 배경을 제거하고 assets/ogq/에 캐시한다."""
    out_dir = BASE_DIR / "assets" / "ogq"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{art['artwork_id']}.png"
    if out_path.exists():
        info(f"캐시된 이미지 사용: {out_path.relative_to(BASE_DIR)}")
        return out_path

    base = art["image_url"].split("?")[0]
    for q in ("?type=m480_480", "?type=m240_240", ""):  # 큰 해상도부터 시도
        try:
            data = http_get(base + q).read()
            out_path.write_bytes(data)
            info(f"이미지 다운로드 완료: {out_path.relative_to(BASE_DIR)} ({len(data):,} bytes)")
            remove_white_bg(out_path)
            return out_path
        except Exception:
            continue
    die(f"스티커 이미지 다운로드에 실패했습니다: {art['image_url']}")


def apply_ogq_links(cfg: dict, creator_url: str | None) -> dict:
    """config/CLI의 OGQ 링크를 처리해 이미지 경로와 크리에이터명을 자동 반영한다."""
    cfg = dict(cfg)

    # 인터뷰어 캐릭터 (고정 링크, config)
    if cfg.get("interviewer_url"):
        art = fetch_ogq_artwork(cfg["interviewer_url"])
        path = download_ogq_image(art)
        cfg["interviewer_avatar"] = str(path.relative_to(BASE_DIR))

    # 인터뷰 대상 크리에이터 (CLI --creator-url이 config보다 우선)
    url = creator_url or cfg.get("creator_url")
    if url:
        art = fetch_ogq_artwork(url)
        path = download_ogq_image(art)
        rel = str(path.relative_to(BASE_DIR))
        cfg["creator_avatar"] = rel
        cfg["creator_main_image"] = rel
        if art["nickname"]:
            cfg["creator_name"] = art["nickname"]
            info(f"크리에이터명 자동 반영: {art['nickname']} (작품: {art['artwork_name']})")
        else:
            warn("크리에이터명을 찾지 못해 config의 creator_name을 사용합니다.")
    return cfg


# ---------- 텍스트 처리 ----------
def split_sentences(text: str) -> list[str]:
    """문장 단위로 대략 분리"""
    text = re.sub(r"\s+", " ", str(text)).strip()
    parts = re.split(r"(?<=[.!?…])\s+|(?<=요\.)\s*|(?<=다\.)\s*", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_answer(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """긴 답변을 문장 경계 기준으로 여러 말풍선으로 분할"""
    sentences = split_sentences(text)
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks or [str(text).strip()]


def build_qa_items(row: pd.Series, cfg: dict) -> list[dict]:
    """응답 1건 → 말풍선 아이템 리스트. type: 'q'(질문) / 'a'(답변)"""
    items = []
    for q in cfg["questions"]:
        col = q["column"]
        if col not in row.index:
            continue
        answer = row[col]
        if pd.isna(answer) or not str(answer).strip():
            info(f"답변이 비어 있어 건너뜁니다: {col}")
            continue
        items.append({"type": "q", "text": q["display"], "set_start": True})
        for chunk in chunk_answer(str(answer)):
            items.append({"type": "a", "text": chunk, "set_start": False})
    return items


# ---------- 배경 테마 ----------
def creator_seed(name: str) -> int:
    """크리에이터 이름 → 고정 시드 (같은 이름이면 항상 같은 스타일)"""
    return zlib.crc32(name.encode("utf-8"))


def resolve_theme(choice, creator_name: str) -> dict:
    """테마 결정: CLI --theme > config theme > 기본 auto.
    auto = 크리에이터마다 다른 테마 자동 배정 / random = 실행마다 무작위 / dict = 커스텀 색상"""
    choice = choice or "auto"
    if isinstance(choice, dict):  # 커스텀: {bg: "#...", blob: "#...", shadow: "r, g, b"}
        theme = {**THEMES["mint"], **choice}
        info(f"커스텀 테마 사용: {theme['bg']}")
        return theme
    choice = str(choice).lower()
    if choice == "auto":
        names = sorted(THEMES)
        choice = names[creator_seed(creator_name) % len(names)]
        info(f"'{creator_name}'님 전용 테마 자동 배정: {choice}")
    elif choice == "random":
        choice = random.choice(list(THEMES))
        info(f"랜덤 테마 선택: {choice}")
    if choice not in THEMES:
        die(f"알 수 없는 테마: {choice}\n사용 가능: {', '.join(THEMES)}, auto, random")
    info(f"배경 테마: {choice}")
    return THEMES[choice]


# ---------- 배경 구름 블롭 ----------
def make_sparks(card_w: int, card_h: int, seed: int, n: int = 6) -> list[dict]:
    """표지 반짝이(✦) 장식 — 크리에이터마다 위치/크기/색이 달라진다"""
    rng = random.Random(seed + 7)
    colors = ["#6DBE94", "#F5A94F", "#7ED0EA"]
    rng.shuffle(colors)
    sparks = []
    for i in range(n):
        left_side = i % 2 == 0
        x = rng.randint(70, 210) if left_side else rng.randint(card_w - 230, card_w - 90)
        y = rng.randint(390, card_h - 210)
        sparks.append({"x": x, "y": y, "size": rng.choice([28, 36, 46]),
                       "color": colors[i % 3], "rot": rng.randint(-20, 20)})
    return sparks


def make_blobs(card_w: int, card_h: int, seed: int = 42, n: int = 7) -> list[dict]:
    rng = random.Random(seed)
    blobs = []
    for _ in range(n):
        blobs.append({
            "x": rng.randint(-150, card_w - 100),
            "y": rng.randint(-100, card_h - 100),
            "w": rng.randint(260, 520),
            "h": rng.randint(150, 260),
            "op": round(rng.uniform(0.25, 0.5), 2),
        })
    return blobs


# ---------- 렌더링 ----------
class CardRenderer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.theme = THEMES["mint"]
        fmt = cfg.get("card_format", "portrait")
        if fmt not in CARD_FORMATS:
            die(f"card_format은 {list(CARD_FORMATS)} 중 하나여야 합니다: {fmt}")
        self.card_w, self.card_h = CARD_FORMATS[fmt]
        self.qa_usable = self.card_h - QA_TOP_PAD - QA_BOTTOM_RESERVE
        info(f"카드 규격: {fmt} ({self.card_w}x{self.card_h})")
        self.env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
        tpl_dir = BASE_DIR / "templates"
        for t in ("cover.html", "qa.html"):
            if not (tpl_dir / t).exists():
                die(f"템플릿이 없습니다: templates/{t}")
        self.fonts_css = load_fonts_css(cfg)
        self.interviewer_avatar = load_image(cfg["interviewer_avatar"], "인터뷰어 아바타")
        self.creator_avatar = None   # set_creator()로 응답자마다 설정
        self.creator_main = None
        self.blobs = make_blobs(self.card_w, self.card_h)
        self.sparks = make_sparks(self.card_w, self.card_h, 42)
        self._pw = None
        self._browser = None
        self._page = None

    def set_creator(self, cfg: dict):
        """응답자(크리에이터)별 이미지를 로드한다. 렌더 전에 반드시 호출."""
        self.creator_avatar = load_image(cfg["creator_avatar"], "크리에이터 아바타")
        self.creator_main = load_image(cfg["creator_main_image"], "크리에이터 대표")

    def set_style(self, theme: dict, seed: int):
        """응답자(크리에이터)별 테마/장식 스타일 설정 — 구름·반짝이 배치도 달라진다."""
        self.theme = theme
        self.blobs = make_blobs(self.card_w, self.card_h, seed=seed)
        self.sparks = make_sparks(self.card_w, self.card_h, seed)

    # --- Playwright 수명 관리 ---
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": self.card_w, "height": self.card_h})
        return self

    def __exit__(self, *a):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def _screenshot(self, html: str, out_path: Path):
        self._page.set_content(html, wait_until="load")
        self._page.evaluate("() => document.fonts.ready")
        self._page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": self.card_w, "height": self.card_h})

    # --- 말풍선 높이 실측 → 카드 분배 ---
    def measure_items(self, items: list[dict]) -> list[int]:
        """qa.html을 measure 모드로 렌더해 각 말풍선의 실제 픽셀 높이를 잰다."""
        html = self.env.get_template("qa.html").render(
            mode="measure", items=items, fonts_css=self.fonts_css,
            interviewer_avatar=self.interviewer_avatar, creator_avatar=self.creator_avatar,
            blobs=[], page_num=0, total_pages=0, card_w=self.card_w, card_h=self.card_h,
            theme=self.theme,
        )
        self._page.set_content(html, wait_until="load")
        self._page.evaluate("() => document.fonts.ready")
        heights = self._page.evaluate(
            "() => Array.from(document.querySelectorAll('.m-item')).map(e => e.offsetHeight)"
        )
        return heights

    def paginate(self, items: list[dict]) -> list[list[dict]]:
        """실측 높이 기준으로 말풍선들을 카드에 분배.
        규칙: 질문 말풍선은 반드시 첫 답변 말풍선과 같은 카드에 있어야 한다."""
        heights = self.measure_items(items)
        usable = self.qa_usable
        pages, cur, used = [], [], 0

        def flush():
            nonlocal cur, used
            if cur:
                pages.append(cur)
            cur, used = [], 0

        i = 0
        while i < len(items):
            it, h = dict(items[i]), heights[i]
            # 질문이면 다음 답변 1개와 묶어서 들어갈 수 있는지 확인
            if it["type"] == "q":
                pair_h = h + BUBBLE_GAP + (heights[i + 1] if i + 1 < len(items) else 0)
                gap = SET_GAP if cur else 0
                if cur and used + gap + pair_h > usable:
                    flush()
                it["continued"] = False
            else:
                gap = BUBBLE_GAP if cur else 0
                if cur and used + gap + h > usable:
                    # 직전 아이템이 질문이면 질문도 함께 다음 카드로 옮겨 고아 질문 방지
                    if cur and cur[-1]["type"] == "q":
                        moved_q = cur.pop()
                        moved_h = heights[i - 1]
                        flush()
                        cur.append(moved_q)
                        used = moved_h
                    else:
                        flush()
                    it["continued"] = True  # 답변이 이어지는 카드
                else:
                    it["continued"] = False
            gap = 0 if not cur else (SET_GAP if it["type"] == "q" else BUBBLE_GAP)
            cur.append(it)
            used += gap + h
            i += 1
        flush()
        return pages

    # --- 카드 생성 ---
    def render_all(self, out_dir: Path, items: list[dict]) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        pages = self.paginate(items)
        self._last_pages = pages  # render_layers()에서 재사용
        total = 1 + len(pages)  # 표지 + QA 카드들
        outputs = []

        # 표지
        cover_html = self.env.get_template("cover.html").render(
            cfg=self.cfg, fonts_css=self.fonts_css, blobs=self.blobs,
            interviewer_avatar=self.interviewer_avatar, creator_main=self.creator_main,
            page_num=1, total_pages=total, card_w=self.card_w, card_h=self.card_h,
            compact=self.card_h <= 1080, theme=self.theme, sparks=self.sparks,
        )
        cover_path = out_dir / "01_cover.png"
        self._screenshot(cover_html, cover_path)
        outputs.append(cover_path)
        info(f"생성: {cover_path.name}")

        # QA 카드들
        for pi, page_items in enumerate(pages, start=2):
            html = self.env.get_template("qa.html").render(
                mode="card", items=page_items, fonts_css=self.fonts_css,
                interviewer_avatar=self.interviewer_avatar, creator_avatar=self.creator_avatar,
                blobs=self.blobs, page_num=pi, total_pages=total,
                card_w=self.card_w, card_h=self.card_h, theme=self.theme,
            )
            p = out_dir / f"{pi:02d}_qa.png"
            self._screenshot(html, p)
            outputs.append(p)
            info(f"생성: {p.name}")
        return outputs

    # --- 요소별 PNG 분리 저장 (layers/) ---
    def _element_shot(self, selector: str, out_path: Path, pad: int = 24) -> bool:
        """현재 페이지에서 요소 하나를 여백(pad) 포함 투명 PNG로 저장.
        말풍선 꼬리·그림자처럼 요소 박스 밖으로 나가는 부분까지 담기 위해 clip을 넓힌다."""
        el = self._page.query_selector(selector)
        if not el:
            return False
        box = el.bounding_box()
        if not box:
            return False
        x = max(box["x"] - pad, 0)
        y = max(box["y"] - pad, 0)
        w = min(box["width"] + pad * 2, self.card_w - x)
        h = box["height"] + pad * 2
        self._page.screenshot(path=str(out_path), omit_background=True,
                              clip={"x": x, "y": y, "width": w, "height": h})
        return True

    def render_layers(self, out_dir: Path, cfg: dict):
        """배경/말풍선/표지 요소를 개별 PNG로 분리 저장 → 나중에 포토샵 등에서 수정하기 좋게."""
        ldir = out_dir / "layers"
        ldir.mkdir(parents=True, exist_ok=True)
        pages = getattr(self, "_last_pages", [])
        total = 1 + len(pages)
        TRANSPARENT = ("body{background:transparent !important}"
                       ".blob,.dots{display:none !important}")

        # 1) 배경 (내지: 테마색 + 구름)
        html = self.env.get_template("qa.html").render(
            mode="card", items=[], fonts_css=self.fonts_css,
            interviewer_avatar=self.interviewer_avatar, creator_avatar=self.creator_avatar,
            blobs=self.blobs, page_num=0, total_pages=0,
            card_w=self.card_w, card_h=self.card_h, theme=self.theme,
        )
        self._page.set_content(html, wait_until="load")
        self._page.add_style_tag(content=".dots{display:none !important}")
        self._page.screenshot(path=str(ldir / "배경_내지.png"),
                              clip={"x": 0, "y": 0, "width": self.card_w, "height": self.card_h})

        # 2) 표지: 배경 + 요소들
        cover_html = self.env.get_template("cover.html").render(
            cfg=self.cfg, fonts_css=self.fonts_css, blobs=self.blobs,
            interviewer_avatar=self.interviewer_avatar, creator_main=self.creator_main,
            page_num=1, total_pages=total, card_w=self.card_w, card_h=self.card_h,
            compact=self.card_h <= 1080, theme=self.theme, sparks=self.sparks,
        )
        self._page.set_content(cover_html, wait_until="load")
        self._page.evaluate("() => document.fonts.ready")
        self._page.add_style_tag(
            content=".content,.main-image,.dots{display:none !important}")
        self._page.screenshot(path=str(ldir / "배경_표지.png"),
                              clip={"x": 0, "y": 0, "width": self.card_w, "height": self.card_h})

        self._page.set_content(cover_html, wait_until="load")
        self._page.evaluate("() => document.fonts.ready")
        self._page.add_style_tag(content=TRANSPARENT)
        for sel, fname in [
            (".pill", "표지_타이틀_크리에이터.png"),
            (".line-interview", "표지_타이틀_인터뷰.png"),
            (".subtitle", "표지_부제목.png"),
            (".cta", "표지_버튼.png"),
            (".deco-bubble.left", "표지_장식말풍선_Q.png"),
            (".deco-bubble.right", "표지_장식말풍선_A.png"),
        ]:
            self._element_shot(sel, ldir / fname)

        # 3) 카드별 말풍선 (투명 배경, 꼬리·그림자 포함)
        for pi, page_items in enumerate(pages, start=2):
            html = self.env.get_template("qa.html").render(
                mode="card", items=page_items, fonts_css=self.fonts_css,
                interviewer_avatar=self.interviewer_avatar, creator_avatar=self.creator_avatar,
                blobs=self.blobs, page_num=pi, total_pages=total,
                card_w=self.card_w, card_h=self.card_h, theme=self.theme,
            )
            self._page.set_content(html, wait_until="load")
            self._page.evaluate("() => document.fonts.ready")
            self._page.add_style_tag(content=TRANSPARENT)
            bubbles = self._page.query_selector_all(".bubble")
            for bi, el in enumerate(bubbles, start=1):
                kind = "질문" if "q" in (el.get_attribute("class") or "") else "답변"
                box = el.bounding_box()
                if not box:
                    continue
                pad = 24
                x = max(box["x"] - pad, 0)
                y = max(box["y"] - pad, 0)
                w = min(box["width"] + pad * 2, self.card_w - x)
                h = box["height"] + pad * 2
                self._page.screenshot(
                    path=str(ldir / f"카드{pi:02d}_말풍선{bi}_{kind}.png"),
                    omit_background=True,
                    clip={"x": x, "y": y, "width": w, "height": h})

        # 4) 프로필/대표 이미지 원본 복사
        for key, fname in [("interviewer_avatar", "프로필_인터뷰어.png"),
                           ("creator_avatar", "프로필_크리에이터.png"),
                           ("creator_main_image", "대표이미지.png")]:
            src = BASE_DIR / cfg.get(key, "")
            if src.is_file():
                shutil.copy(src, ldir / fname)

        info(f"요소별 PNG 저장 완료: {ldir.relative_to(BASE_DIR)}/ ({len(list(ldir.iterdir()))}개)")

    # --- 홍보 배너 생성 ---
    def render_banners(self, out_dir: Path, cfg: dict, seed: int) -> list[Path]:
        bdir = out_dir / "banners"
        bdir.mkdir(parents=True, exist_ok=True)
        tpl = self.env.get_template("banner.html")
        colors = ["#6DBE94", "#F5A94F", "#7ED0EA"]
        outputs = []
        for w, h in BANNER_SIZES:
            strip = w / h > 3.5          # 1440x180 같은 가로 스트립
            k = min(w / 824, h / 464)    # 박스형은 824x464 디자인을 비율 축소
            rng = random.Random(seed + w * 7 + h)
            sparks = []
            for i in range(2 if min(w, h) < 220 else 4):  # 상하단 가장자리에만 배치
                sparks.append({
                    "x": rng.randint(24, max(40, w - 70)),
                    "y": rng.choice([rng.randint(10, max(16, h // 5)),
                                     rng.randint(h * 3 // 4, h - 42)]),
                    "size": rng.choice([16, 22, 28]) if min(w, h) < 300 else rng.choice([22, 30, 38]),
                    "color": colors[i % 3], "rot": rng.randint(-20, 20),
                })
            html = tpl.render(
                fonts_css=self.fonts_css, theme=self.theme,
                blobs=make_blobs(w, h, seed=seed, n=5), sparks=sparks,
                card_w=w, card_h=h, strip=strip,
                k=round(k, 4), tx=round((w - 824 * k) / 2, 1), ty=round((h - 464 * k) / 2, 1),
                name=cfg["creator_name"], creator_main=self.creator_main,
            )
            self._page.set_viewport_size({"width": w, "height": h})
            self._page.set_content(html, wait_until="load")
            self._page.evaluate("() => document.fonts.ready")
            p = bdir / f"banner_{w}x{h}.png"
            self._page.screenshot(path=str(p), clip={"x": 0, "y": 0, "width": w, "height": h})
            outputs.append(p)
            info(f"생성: banners/{p.name}")
        self._page.set_viewport_size({"width": self.card_w, "height": self.card_h})
        return outputs


# ---------- 캡션 ----------
def make_caption(row: pd.Series, cfg: dict) -> str:
    cap = cfg.get("caption") or {}
    name = cfg["creator_name"]
    lines = [
        cap.get("intro", "크리에이터 인터뷰 🎨"),
        "",
        f"OGQ 크리에이터 {name}님을 소개합니다 ✨",
        "",
    ]
    # 답변에서 핵심 문장 1~2개 추출 (20~80자 사이의 문장 우선)
    highlights = []
    for q in cfg["questions"][1:] + cfg["questions"][:1]:  # 자기소개보다 뒷 질문 우선
        col = q["column"]
        if col not in row.index or pd.isna(row[col]):
            continue
        for s in split_sentences(str(row[col])):
            if 20 <= len(s) <= 80:
                highlights.append(s)
                break
        if len(highlights) >= 2:
            break
    for h in highlights:
        lines.append(f"💬 \"{h}\"")
    if highlights:
        lines.append("")
    lines += [
        f"{name}님의 자세한 인터뷰는 카드뉴스에서 확인하세요! 👉",
        "",
        cap.get("hashtags", "#OGQ"),
    ]
    return "\n".join(lines)


# ---------- 블로그 글 ----------
def make_blog(row: pd.Series, cfg: dict) -> str:
    """인터뷰 전문을 담은 블로그 포스트 (네이버 블로그 등에 붙여넣기 좋은 형식)"""
    blog = cfg.get("blog") or {}
    name = cfg["creator_name"]
    fmt = {"year": cfg["year"], "month": cfg["month"], "name": name}

    title = blog.get(
        "title", "크리에이터 인터뷰 ! OGQ 크리에이터, {name}님을 만났습니다 🎨"
    ).format(**fmt)
    intro = blog.get("intro", "안녕하세요, OGQ입니다!").format(**fmt).strip()
    outro = blog.get(
        "outro", "인터뷰에 응해주신 {name}님께 감사드립니다!"
    ).format(**fmt).strip()

    lines = [title, "", intro, "",
             f"이번 인터뷰의 주인공은 바로 {name}님! 지금 바로 만나보세요 👇", ""]

    qa_num = 0
    for q in cfg["questions"]:
        col = q["column"]
        if col not in row.index or pd.isna(row[col]) or not str(row[col]).strip():
            continue
        qa_num += 1
        answer = re.sub(r"\s+", " ", str(row[col])).strip()
        lines += [
            f"Q{qa_num}. {q['display']}",
            "",
            f"{name}: {answer}",
            "",
            "─" * 30,
            "",
        ]

    lines += [outro, "", (cfg.get("caption") or {}).get("hashtags", "#OGQ")]
    return "\n".join(lines)


# ---------- 프리뷰 ----------
def make_preview(out_dir: Path, images: list[Path]):
    imgs_html = "\n".join(
        f'<div class="card"><img src="{p.name}" alt="{p.name}"><p>{p.name}</p></div>'
        for p in images
    )
    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>카드뉴스 미리보기</title>
<style>
body {{ background:#f0f0f0; font-family:sans-serif; margin:24px; }}
.grid {{ display:flex; flex-wrap:wrap; gap:20px; }}
.card img {{ width:320px; border-radius:12px; box-shadow:0 4px 14px rgba(0,0,0,.15); }}
.card p {{ text-align:center; color:#555; font-size:13px; }}
</style></head><body>
<h1>카드뉴스 미리보기</h1><div class="grid">{imgs_html}</div></body></html>"""
    preview_path = out_dir / "preview.html"
    preview_path.write_text(html, encoding="utf-8")
    info(f"미리보기 생성: {preview_path}")
    return preview_path


# ---------- 메인 ----------
def process_row(renderer: CardRenderer, df: pd.DataFrame, row_idx: int,
                cfg: dict, preview: bool, theme_choice=None):
    if row_idx < 0 or row_idx >= len(df):
        die(f"--row {row_idx} 는 범위를 벗어났습니다 (응답자 수: {len(df)}, 0부터 시작).")
    row = df.iloc[row_idx]
    cfg = dict(cfg)

    # 1순위: 엑셀에서 OGQ 마켓 링크 자동 탐지 — 어느 컬럼에 있든 알아서 찾는다
    row_url = None
    url_col = cfg.get("url_column")  # (선택) 컬럼을 못박고 싶을 때만 사용
    candidates = [url_col] if url_col and url_col in row.index else list(row.index)
    for col in candidates:
        if pd.isna(row[col]):
            continue
        m = re.search(r"https?://\S*ogqmarket\.naver\.com/\S*artworkId=[0-9a-f]+", str(row[col]))
        if m:
            row_url = m.group(0)
            info(f"OGQ 링크 자동 탐지: '{col}' 컬럼에서 발견")
            break
    if not row_url:  # naver.me 단축링크면 리다이렉트를 따라가 OGQ 링크인지 확인
        for col in candidates:
            if pd.isna(row[col]):
                continue
            m = re.search(r"https?://naver\.me/\S+", str(row[col]))
            if not m:
                continue
            try:
                final_url = http_get(m.group(0)).geturl()
            except Exception:
                continue
            m2 = re.search(r"https?://\S*ogqmarket\.naver\.com/\S*artworkId=[0-9a-f]+", final_url)
            if m2:
                row_url = m2.group(0)
                info(f"단축링크(naver.me) 해석 → OGQ 링크 확인: '{col}' 컬럼")
                break
    if row_url:
        art = fetch_ogq_artwork(row_url)
        path = download_ogq_image(art)
        rel = str(path.relative_to(BASE_DIR))
        cfg["creator_avatar"] = rel
        cfg["creator_main_image"] = rel
        if art["nickname"]:
            cfg["creator_name"] = art["nickname"]
            info(f"크리에이터명 자동 반영: {art['nickname']} (작품: {art['artwork_name']})")

    # 2순위: name_column, 3순위: config의 creator_name
    name_col = cfg.get("name_column")
    if not row_url:
        if name_col and name_col in row.index and pd.notna(row[name_col]) and str(row[name_col]).strip():
            cfg["creator_name"] = str(row[name_col]).strip()
        elif len(df) > 1 and row_idx > 0:
            cfg["creator_name"] = f"{cfg['creator_name']}_{row_idx}"
    name = safe_folder_name(cfg["creator_name"])
    out_dir = BASE_DIR / "output" / name
    print(f"\n=== 응답자 #{row_idx} → output/{name}/ ===")

    items = build_qa_items(row, cfg)
    if not items:
        die("생성할 Q&A가 없습니다. config의 questions와 엑셀 컬럼명을 확인해주세요.")

    renderer.set_creator(cfg)
    renderer.cfg = cfg  # 표지의 크리에이터명 등 반영
    theme = resolve_theme(theme_choice, cfg["creator_name"])
    renderer.set_style(theme, creator_seed(cfg["creator_name"]))
    images = renderer.render_all(out_dir, items)
    renderer.render_banners(out_dir, cfg, creator_seed(cfg["creator_name"]))
    if cfg.get("export_layers", True):
        renderer.render_layers(out_dir, cfg)

    caption = make_caption(row, cfg)
    cap_path = out_dir / "caption.txt"
    cap_path.write_text(caption, encoding="utf-8")
    info(f"생성: {cap_path.name}")

    blog = make_blog(row, cfg)
    blog_path = out_dir / "blog.txt"
    blog_path.write_text(blog, encoding="utf-8")
    info(f"생성: {blog_path.name}")

    if preview:
        make_preview(out_dir, images)


def main():
    ap = argparse.ArgumentParser(description="OGQ 크리에이터 인터뷰 카드뉴스 생성기")
    ap.add_argument("--excel", required=True, help="네이버 폼 응답 엑셀 파일(.xlsx)")
    ap.add_argument("--row", type=int, default=0, help="몇 번째 응답자를 사용할지 (0부터)")
    ap.add_argument("--all", action="store_true", help="모든 응답자를 각각 폴더로 일괄 생성")
    ap.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    ap.add_argument("--preview", action="store_true", help="preview.html 생성")
    ap.add_argument("--creator-url", default=None,
                    help="OGQ 마켓 스티커 링크 — 크리에이터명과 이미지를 자동 반영")
    ap.add_argument("--theme", default=None,
                    help=f"배경 테마: {', '.join(THEMES)}, random")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    cfg = apply_ogq_links(cfg, args.creator_url)
    theme_choice = args.theme or cfg.get("theme")  # 미지정 시 auto(크리에이터별 자동)

    df = load_responses(Path(args.excel), cfg)
    cfg["questions"] = resolve_questions(df, cfg)
    if not cfg["questions"]:
        die("인터뷰 질문으로 쓸 컬럼을 찾지 못했습니다. 엑셀을 확인해주세요.")

    with CardRenderer(cfg) as renderer:
        if args.all:
            for i in range(len(df)):
                process_row(renderer, df, i, cfg, args.preview, theme_choice)
        else:
            process_row(renderer, df, args.row, cfg, args.preview, theme_choice)

    print("\n완료! output/ 폴더를 확인하세요.")


if __name__ == "__main__":
    main()
