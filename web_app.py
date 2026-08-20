# -*- coding: utf-8 -*-
"""
OGQ 콘텐츠 생성기 — 웹 버전 (Streamlit)
탭1: 배너 생성기 (banner_gen)  /  탭2: 인터뷰 카드뉴스 (cardnews/make_cards)
실행:  streamlit run web_app.py
"""
import contextlib
import io
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

sys.argv = ["web"]  # argparse 영향 방지
import banner_gen as bg  # noqa: E402
import editor  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

CARDNEWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cardnews")
sys.path.insert(0, CARDNEWS_DIR)

st.set_page_config(page_title="OGQ 콘텐츠 생성기", page_icon="🎨", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.stDownloadButton button {width: 100%; height: 3rem; font-size: 1.05rem;}
</style>
""", unsafe_allow_html=True)

st.title("🎨 OGQ 콘텐츠 생성기")
tab_banner, tab_card = st.tabs(["🖼 배너 생성기", "📰 인터뷰 카드뉴스"])


# =========================================================================
# 탭 1: 배너 생성기
# =========================================================================
def _load_banner_source(url, upload):
    if upload is not None:
        tmpdir = tempfile.mkdtemp(prefix="ogq_web_")
        path = os.path.join(tmpdir, unicodedata.normalize("NFC", upload.name))
        with open(path, "wb") as f:
            f.write(upload.getbuffer())
        return bg.load_local_source(path)
    artwork_id = bg.parse_artwork_id(url)
    data = bg.fetch_artwork(artwork_id)
    cache = os.path.join(tempfile.gettempdir(), "ogq_web_cache", artwork_id)
    urls = data["stickers"] if data["stickers"] else [data["main_image"]]
    imgs = bg.download_images(urls, cache)
    if not imgs:
        raise RuntimeError("스티커 이미지를 받지 못했습니다.")
    return data, imgs


with tab_banner:
    st.caption("OGQ마켓 판매 링크 또는 스티커 원본 zip을 넣으면 배너 9종 + SNS 홍보 이미지 2종을 자동으로 만들어 드립니다. "
               "실행할 때마다 디자인이 달라져요.")
    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            src_mode = st.radio("소스 선택", ["OGQ마켓 링크", "스티커 원본 zip 업로드"], horizontal=True)
            url = ""
            upload = None
            if src_mode == "OGQ마켓 링크":
                url = st.text_input("판매 링크 (또는 artworkId)",
                                    placeholder="https://ogqmarket.naver.com/artworks/sticker/detail?artworkId=61bc52a6358f4")
            else:
                upload = st.file_uploader("스티커 원본 zip (main/tab/1~24.png)", type=["zip"])
        with c2:
            date = st.text_input("출시일 (SNS 홍보 이미지용)", placeholder="예: 8월 19일  (비우면 'NEW 출시!')")
            variants = st.select_slider("시안 개수", options=[1, 2, 3], value=1,
                                        help="여러 개면 서로 다른 디자인 시안을 한 번에 만듭니다")
            go = st.button("✨ 배너 만들기", type="primary", use_container_width=True)

    if go:
        if src_mode == "OGQ마켓 링크" and not url.strip():
            st.warning("링크를 입력해 주세요.")
            st.stop()
        if src_mode != "OGQ마켓 링크" and upload is None:
            st.warning("zip 파일을 올려 주세요.")
            st.stop()
        bg.TEXT_ENABLED = False
        bg.RELEASE_DATE = date.strip()
        with st.spinner("스티커를 불러오는 중..."):
            try:
                data, imgs = _load_banner_source(url, upload)
            except Exception as e:
                st.error(f"소스를 읽지 못했습니다: {e}")
                st.stop()
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", data["title"])[:40] or "banner"
        workdir = tempfile.mkdtemp(prefix="ogq_out_")
        results = []  # [(variant_idx, name, path, layers)]
        prog = st.progress(0, text="배너 생성 중...")
        for v in range(variants):
            seed = random.randrange(1 << 30)
            out_dir = os.path.join(workdir, safe_title if variants == 1 else f"{safe_title}/시안_{v + 1}")
            with contextlib.redirect_stdout(io.StringIO()):
                paths = bg.generate_all(data, imgs, out_dir, seed, capture=True)
            layers = dict(bg.LAYERS)
            for p in paths:
                name = os.path.splitext(os.path.basename(p))[0]
                results.append((v, name, p, layers.get(name)))
            prog.progress((v + 1) / variants, text=f"시안 {v + 1}/{variants} 완료")
        prog.empty()
        # 메모리 절약: 이전 결과 폴더 삭제 + 세션에는 축소본 스티커만 보관
        prev = st.session_state.get("gen")
        if prev and prev.get("workdir") and prev["workdir"] != workdir:
            shutil.rmtree(prev["workdir"], ignore_errors=True)
        small = []
        for im in imgs:
            if max(im.size) > 480:
                sc = 480 / max(im.size)
                im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
            small.append(im)
        st.session_state["gen"] = {"data": data, "imgs": small, "results": results, "workdir": workdir,
                                   "safe_title": safe_title, "variants": variants}
        st.session_state.pop("edit_target", None)
        import gc
        del imgs
        bg.LAYERS = {}
        gc.collect()

    gen = st.session_state.get("gen")
    if gen:
        data, imgs, results = gen["data"], gen["imgs"], gen["results"]
        safe_title, variants, workdir = gen["safe_title"], gen["variants"], gen["workdir"]
        st.success(f"**{data['title']}**  ·  스티커 {len(imgs)}개"
                   + (f"  ·  작가 {data['creator']}" if data.get("creator") else ""))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for _, _, p, _ in results:
                if os.path.exists(p):
                    z.write(p, os.path.relpath(p, workdir))
        buf.seek(0)
        st.download_button("⬇️  배너 전체 다운로드 (zip)", data=buf, file_name=f"{safe_title}_배너.zip",
                           mime="application/zip", type="primary")
        st.caption("마음에 안 들면 「배너 만들기」를 다시 누르세요 — 매번 새 디자인이 나옵니다. 개별 배너는 아래에서 ✏️ 편집할 수 있어요.")

        st.divider()
        st.subheader("✏️ 배너 편집")
        options = [f"{'시안 ' + str(v + 1) + ' · ' if variants > 1 else ''}{name}" for v, name, _, _ in results]
        pick = st.selectbox("편집할 배너를 고르세요", options, index=None, placeholder="배너 선택…", key="edit_target")
        if pick:
            idx = options.index(pick)
            _, name, p, layers = results[idx]
            if layers:
                html = editor.build_editor_html(layers, imgs, bg.BUNDLED_FONT_DIR, name)
                w, h = layers["size"]
                zoom = min(1, 1000 / w)
                components.html(html, height=int(h * zoom) + 190, scrolling=True)
            else:
                st.info("이 배너는 편집 레이어가 없습니다.")

        st.divider()
        tabs = st.tabs([f"시안 {i + 1}" for i in range(variants)])
        for v, tab in enumerate(tabs):
            with tab:
                cols = st.columns(2)
                k = 0
                for vv, name, p, _ in results:
                    if vv != v or not os.path.exists(p):
                        continue
                    with cols[k % 2]:
                        im = Image.open(p)
                        st.image(im, caption=f"{name}  ({im.width}x{im.height})", use_container_width=True)
                    k += 1


# =========================================================================
# 탭 2: 인터뷰 카드뉴스
# =========================================================================
@st.cache_resource(show_spinner=False)
def _ensure_chromium():
    """Playwright Chromium 설치 (클라우드 첫 부팅 시 1회, 로컬은 이미 있으면 통과)"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            if os.path.exists(p.chromium.executable_path):
                return True
    except Exception:
        pass
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       capture_output=True, text=True, timeout=600)
    return r.returncode == 0


with tab_card:
    st.caption("네이버 폼 인터뷰 응답 엑셀(.xlsx)을 올리면 인스타그램 카드뉴스(표지+Q&A)와 "
               "게시 캡션·블로그 글을 자동으로 만들어 드립니다.")
    import make_cards as mc  # cardnews/

    with st.container(border=True):
        xlsx = st.file_uploader("인터뷰 응답 엑셀 (.xlsx)", type=["xlsx"],
                                help="네이버 폼 → 응답 → 엑셀 다운로드 파일 그대로")
        use_sample = st.toggle("샘플 데이터로 먼저 테스트해보기", value=False,
                               help="엑셀이 없어도 내장 샘플 응답으로 작동을 확인할 수 있습니다")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            month = st.text_input("월", value=mc.load_config(Path(CARDNEWS_DIR) / "config.yaml").get("month", "8월"))
        with c2:
            card_format = st.selectbox("카드 규격", ["square", "portrait"],
                                       format_func=lambda x: "1080x1080 (1:1)" if x == "square" else "1080x1350 (4:5)")
        with c3:
            theme_choice = st.selectbox("배경 테마", ["auto", "mint", "pink", "lavender", "sky", "cream", "peach", "random"],
                                        help="auto = 크리에이터마다 자동 배정")
        with c4:
            creator_url = st.text_input("크리에이터 마켓 링크(선택)",
                                        placeholder="엑셀에 링크가 있으면 비워두세요")

        # 응답자 선택
        row_pick = "전체"
        df = None
        tmp_xlsx = None
        if xlsx is not None:
            tmp_xlsx = os.path.join(tempfile.mkdtemp(prefix="ogq_cn_"), unicodedata.normalize("NFC", xlsx.name))
            with open(tmp_xlsx, "wb") as f:
                f.write(xlsx.getbuffer())
        elif use_sample:
            tmp_xlsx = os.path.join(CARDNEWS_DIR, "responses_multi_sample.xlsx")
        if tmp_xlsx:
            try:
                base_cfg_probe = mc.load_config(Path(CARDNEWS_DIR) / "config.yaml")
                df = mc.load_responses(Path(tmp_xlsx), base_cfg_probe)
                name_col = base_cfg_probe.get("name_column")
                labels = []
                for i in range(len(df)):
                    nm = ""
                    if name_col and name_col in df.columns and str(df.iloc[i].get(name_col, "")).strip() not in ("", "nan"):
                        nm = str(df.iloc[i][name_col]).strip()
                    labels.append(f"{i + 1}번 응답자" + (f" · {nm}" if nm else ""))
                row_pick = st.selectbox("응답자 선택", ["전체"] + labels)
            except Exception as e:
                st.error(f"엑셀을 읽지 못했습니다: {e}")
                df = None
        go_card = st.button("📰 카드뉴스 만들기", type="primary", use_container_width=True,
                            disabled=(df is None))

    if go_card and df is not None:
        with st.spinner("렌더링 엔진 준비 중... (첫 실행은 1~2분)"):
            if not _ensure_chromium():
                st.error("Chromium 설치에 실패했습니다. 잠시 후 다시 시도해 주세요.")
                st.stop()
        cfg = mc.load_config(Path(CARDNEWS_DIR) / "config.yaml")
        cfg["month"] = month.strip() or cfg.get("month", "")
        cfg["card_format"] = card_format
        cfg["export_layers"] = False  # 웹에서는 레이어 PNG 생략 (속도)
        try:
            cfg = mc.apply_ogq_links(cfg, creator_url.strip() or None)
        except SystemExit:
            st.error("크리에이터 링크를 읽지 못했습니다. 링크를 확인해 주세요.")
            st.stop()
        cfg["questions"] = mc.resolve_questions(df, cfg)
        if not cfg["questions"]:
            st.error("인터뷰 질문으로 쓸 컬럼을 찾지 못했습니다. 엑셀 양식을 확인해 주세요.")
            st.stop()

        out_root = Path(mc.BASE_DIR) / "output"
        shutil.rmtree(out_root, ignore_errors=True)
        rows = range(len(df)) if row_pick == "전체" else [int(row_pick.split("번")[0]) - 1]
        log = io.StringIO()
        try:
            with st.spinner(f"카드뉴스 생성 중... ({len(list(rows))}명, 30초~2분)"):
                rows = list(rows)
                with contextlib.redirect_stdout(log):
                    with mc.CardRenderer(cfg) as renderer:
                        for i in rows:
                            mc.process_row(renderer, df, i, cfg, False, theme_choice)
        except SystemExit:
            st.error("생성 중 문제가 발생했습니다:\n```\n" + log.getvalue()[-800:] + "\n```")
            st.stop()
        except Exception as e:
            st.error(f"생성 실패: {e}\n```\n{log.getvalue()[-800:]}\n```")
            st.stop()
        st.session_state["cardnews_done"] = str(out_root)
        import gc
        gc.collect()

    cn_root = st.session_state.get("cardnews_done")
    if cn_root and os.path.isdir(cn_root):
        creators = sorted(d for d in os.listdir(cn_root) if os.path.isdir(os.path.join(cn_root, d)))
        if creators:
            # 전체 zip
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for root, _, files in os.walk(cn_root):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        z.write(fp, os.path.relpath(fp, cn_root))
            buf.seek(0)
            st.download_button("⬇️  카드뉴스 전체 다운로드 (zip)", data=buf, file_name="카드뉴스.zip",
                               mime="application/zip", type="primary", key="cn_zip")
            for name in creators:
                cdir = os.path.join(cn_root, name)
                with st.expander(f"📁 {name}", expanded=(len(creators) == 1)):
                    pngs = sorted(f for f in os.listdir(cdir) if f.endswith(".png"))
                    cols = st.columns(3)
                    for i, fn in enumerate(pngs):
                        with cols[i % 3]:
                            st.image(Image.open(os.path.join(cdir, fn)), caption=fn, use_container_width=True)
                    for txt, label in [("caption.txt", "📋 인스타 캡션"), ("blog.txt", "📝 블로그 글")]:
                        tp = os.path.join(cdir, txt)
                        if os.path.exists(tp):
                            st.text_area(label, open(tp, encoding="utf-8").read(), height=160,
                                         key=f"{name}_{txt}")
