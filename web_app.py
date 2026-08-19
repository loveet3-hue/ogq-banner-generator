# -*- coding: utf-8 -*-
"""
OGQ 배너 생성기 — 웹 버전 (Streamlit)
실행:  streamlit run web_app.py
"""
import io
import os
import random
import re
import shutil
import sys
import tempfile
import zipfile

import streamlit as st
from PIL import Image

sys.argv = ["web"]  # banner_gen 의 argparse 영향 방지
import banner_gen as bg  # noqa: E402
import editor  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

st.set_page_config(page_title="OGQ 배너 생성기", page_icon="🎨", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.stDownloadButton button {width: 100%; height: 3rem; font-size: 1.05rem;}
</style>
""", unsafe_allow_html=True)

st.title("🎨 OGQ 배너 생성기")
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


def _load(url, upload):
    """소스에서 (data, imgs, title) 로드"""
    if upload is not None:
        tmpdir = tempfile.mkdtemp(prefix="ogq_web_")
        import unicodedata
        path = os.path.join(tmpdir, unicodedata.normalize("NFC", upload.name))
        with open(path, "wb") as f:
            f.write(upload.getbuffer())
        data, imgs = bg.load_local_source(path)
        return data, imgs
    artwork_id = bg.parse_artwork_id(url)
    data = bg.fetch_artwork(artwork_id)
    cache = os.path.join(tempfile.gettempdir(), "ogq_web_cache", artwork_id)
    urls = data["stickers"] if data["stickers"] else [data["main_image"]]
    imgs = bg.download_images(urls, cache)
    if not imgs:
        raise RuntimeError("스티커 이미지를 받지 못했습니다.")
    return data, imgs


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
            data, imgs = _load(url, upload)
        except Exception as e:
            st.error(f"소스를 읽지 못했습니다: {e}")
            st.stop()

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", data["title"])[:40] or "banner"
    workdir = tempfile.mkdtemp(prefix="ogq_out_")
    results = []  # [(variant_idx, name, path, layers)]
    import contextlib
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
    st.session_state["gen"] = {"data": data, "imgs": imgs, "results": results, "workdir": workdir,
                               "safe_title": safe_title, "variants": variants}
    st.session_state.pop("edit_target", None)

gen = st.session_state.get("gen")
if gen:
    data, imgs, results = gen["data"], gen["imgs"], gen["results"]
    safe_title, variants, workdir = gen["safe_title"], gen["variants"], gen["workdir"]
    st.success(f"**{data['title']}**  ·  스티커 {len(imgs)}개" + (f"  ·  작가 {data['creator']}" if data.get("creator") else ""))

    # 전체 다운로드
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for _, _, p, _ in results:
            if os.path.exists(p):
                z.write(p, os.path.relpath(p, workdir))
    buf.seek(0)
    st.download_button("⬇️  배너 전체 다운로드 (zip)", data=buf, file_name=f"{safe_title}_배너.zip",
                       mime="application/zip", type="primary")
    st.caption("마음에 안 들면 「배너 만들기」를 다시 누르세요 — 매번 새 디자인이 나옵니다. 개별 배너는 아래에서 ✏️ 편집할 수 있어요.")

    # 편집기
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
            zoom = min(1, min(1000, 1100) / w)
            components.html(html, height=int(h * zoom) + 190, scrolling=True)
        else:
            st.info("이 배너는 편집 레이어가 없습니다.")

    # 미리보기
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
