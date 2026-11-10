# -*- coding: utf-8 -*-
"""
OGQ 콘텐츠 생성기 — 웹 버전 (Streamlit)
탭1: 배너 생성기 (banner_tool.html — 브라우저에서 전부 처리)  /  탭2: 인터뷰 카드뉴스 (cardnews/make_cards)
탭3: 플레이북 만들기 (playbook)
실행:  streamlit run web_app.py
"""
import contextlib
import io
import os
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
tab_banner, tab_card, tab_playbook = st.tabs(
    ["🖼 배너 생성기", "📰 인터뷰 카드뉴스", "📊 플레이북 만들기"])


# =========================================================================
# 탭 1: 배너 생성기 — banner_studio (zip → SOM·NOM·COM·인스타, 시안 3개)
# =========================================================================
import banner_studio as bst  # noqa: E402

with tab_banner:
    st.caption("OGQ 제출용 zip(1~24.png/gif · main · tab)을 올리면 지면별 규격에 맞춘 출시 배너를 "
               "시안 3개로 만들어 드립니다.")

    up = st.file_uploader("이모티콘 zip", type=["zip"], key="studio_zip")
    sd = st.session_state.get("studio")
    if up is not None and (sd is None or sd.get("file") != (up.name, up.size)):
        try:
            with st.spinner("이모티콘 불러오는 중..."):
                emos, name = bst.read_zip(up.getvalue(), unicodedata.normalize("NFC", up.name))
            st.session_state["studio"] = sd = {"file": (up.name, up.size), "emos": emos, "name": name}
            st.session_state.pop("studio_res", None)
        except Exception as e:
            st.error(f"zip을 읽지 못했습니다: {e}")
            sd = None
    if up is None and sd is not None:
        sd = None
        st.session_state.pop("studio", None)
        st.session_state.pop("studio_res", None)

    if sd:
        emos, default_name = sd["emos"], sd["name"]
        n_gif = sum(1 for e in emos if e.get("gif"))
        st.success(f"**{default_name}** · 이모티콘 {len(emos)}개"
                   + (f" · 움직이는 GIF {n_gif}개" if n_gif else ""))
        with st.expander("🔢 이모티콘 번호 보기 (시안에서 번호로 지정할 때 참고)"):
            cols = st.columns(8)
            for i, e in enumerate(emos):
                with cols[i % 8]:
                    st.image(e["sample"], caption=str(e["num"]), use_container_width=True)

        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                name_in = st.text_input("이모티콘 이름 (인스타 제목 · *별표*는 강조색)", value=default_name)
                chat_in = st.text_input("채팅플러스(COM) 출시 문구",
                                        placeholder=f"비우면: {default_name} 이모티콘 *출시*")
            with c2:
                cc1, cc2 = st.columns(2)
                with cc1:
                    tag_in = st.text_input("COM 문구 위 라벨", value="NEW 이모티콘")
                with cc2:
                    creator_in = st.text_input("크리에이터명 (인스타)", placeholder="예) 아지그림")
                footer_in = st.text_input("인스타 하단 문구", value="OGQ마켓 *출시!*")

            if n_gif:
                anim_on = st.checkbox("GIF 이모티콘은 움직이는 PNG(APNG)로", value=True,
                                      help=f"움직이는 GIF {n_gif}개를 찾았어요. SOM·NOM·COM에 적용되고, "
                                           "용량은 500KB 아래로 자동으로 맞춰요.")
            else:
                anim_on = False
                st.caption("이 zip에는 움직이는 GIF가 없어서 일반 PNG로 만들어요.")

            st.markdown("**만들 지면**")
            t1, t2, t3, t4 = st.columns(4)
            targets = []
            if t1.checkbox("SOM · SOOP 메인", value=True, help="PC 1344×260 / MO 672×440"):
                targets.append("som")
            if t2.checkbox("NOM · 네이버", value=True, help="PC 824×464 / MO 640×360"):
                targets.append("nom")
            if t3.checkbox("COM · 채팅플러스", value=True, help="984×552, 문구 포함"):
                targets.append("com")
            if t4.checkbox("인스타 카드뉴스", value=False, help="1080×1350"):
                targets.append("insta")

            st.markdown("**시안** — 비워두면 시안마다 디자인·배경색·이모티콘이 다르게 자동으로 정해져요.")
            parse_nums = lambda t: [int(x) for x in re.split(r"[,\s]+", t.strip()) if x.isdigit()]
            variants = []
            vc = st.columns(3)
            for k in range(3):
                with vc[k], st.container(border=True):
                    on = st.checkbox(f"시안 {k + 1} 사용", value=True, key=f"sv{k}_on")
                    style = st.selectbox("디자인", list(bst.STYLES), key=f"sv{k}_style",
                                         index=list(bst.STYLES).index(bst.DEFAULT_STYLES[k]),
                                         format_func=lambda v: bst.STYLES[v])
                    color = st.selectbox("배경색", ["auto"] + list(bst.PALETTES) + ["custom"], key=f"sv{k}_color",
                                         format_func=lambda v: {"auto": "자동", "custom": "직접 고르기"}.get(v, bst.PALETTES.get(v, {}).get("label", v)))
                    hexv = "#CFE5F8"
                    if color == "custom":
                        hexv = st.color_picker("배경색 직접 선택", "#CFE5F8", key=f"sv{k}_hex")
                    pick = st.text_input("이모티콘 번호 (왼·중·오·추가)", key=f"sv{k}_pick",
                                         placeholder="비우면 자동  예) 1, 9, 13")
                    icons = st.text_input("COM 문구 양옆 아이콘 2개", key=f"sv{k}_icons",
                                          placeholder="비우면 자동  예) 2, 22")
                    variants.append(dict(on=on, style=style, color=color, hex=hexv.upper(),
                                         pick=parse_nums(pick), icons=parse_nums(icons)))

            go_banner = st.button("✨ 배너 만들기", type="primary", use_container_width=True,
                                  disabled=not targets)

        if go_banner:
            opts = dict(
                name=(name_in.strip() or default_name),
                chat=(chat_in.strip() or f"{name_in.strip() or default_name} 이모티콘 *출시*"),
                tagline=tag_in.strip(), creator=creator_in.strip(), footer=footer_in.strip())
            prog = st.progress(0, text="배너 그리는 중...")

            def _prog(k, n, msg):
                label = f"시안 {k + 1}/{n} · {msg}..." if msg else f"시안 {k + 1}/{n} 그리는 중..."
                prog.progress(min(0.99, k / n), text=label)

            try:
                res = bst.generate(emos, opts, variants, targets, progress=_prog, anim=anim_on)
            except Exception:
                import traceback
                prog.empty()
                st.error("배너 생성 중 오류가 났습니다. 아래 내용을 그대로 담당자에게 보내주세요.\n```\n"
                         + traceback.format_exc()[-1500:] + "\n```")
                st.stop()
            prog.empty()
            safe = re.sub(r"[^0-9A-Za-z가-힣]+", "_", opts["name"].replace("*", "")).strip("_") or "emoticon"
            st.session_state["studio_res"] = {"res": res, "base": safe}

    sres = st.session_state.get("studio_res")
    if sres:
        res, base = sres["res"], sres["base"]
        # 전체 zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for r in res:
                for f in r["files"]:
                    z.writestr(f"{r['label'].replace(' ', '')}/{f['name']}", f["data"])
        buf.seek(0)
        st.download_button("⬇️  전체 시안 zip 받기", data=buf, file_name=f"{base}_배너_전체시안.zip",
                           mime="application/zip", type="primary", key="studio_all")
        vtabs = st.tabs([f"{r['label']} · {bst.STYLES[r['style']]} · {r['pal_label']}" for r in res])
        for r, vt in zip(res, vtabs):
            with vt:
                st.caption(f"사용한 이모티콘 {', '.join(map(str, r['pick']))} · COM 아이콘 {', '.join(map(str, r['icons']))}")
                vbuf = io.BytesIO()
                with zipfile.ZipFile(vbuf, "w", zipfile.ZIP_DEFLATED) as z:
                    for f in r["files"]:
                        z.writestr(f["name"], f["data"])
                vbuf.seek(0)
                st.download_button(f"⬇️ {r['label']} zip 받기", data=vbuf,
                                   file_name=f"{base}_{r['label'].replace(' ', '')}.zip",
                                   mime="application/zip", key=f"studio_{r['label']}")
                for f in r["files"]:
                    kb = len(f["data"]) // 1024
                    badge = f" · 🎞 움직임 {f['anim']['sec']}초" if f.get("anim") else ""
                    st.image(f["data"], caption=f"{f['name']} · {f['w']}×{f['h']} · {kb}KB{badge}",
                             use_container_width=(f["w"] > 700))


# =========================================================================
# 탭 2: 인터뷰 카드뉴스
# =========================================================================
@st.cache_resource(show_spinner=False)
def _ensure_chromium():
    """Chromium 설치 + 실행 가능 상태 보장 (apt 불가 환경에서는 라이브러리 직접 부트스트랩)"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            need_install = not os.path.exists(p.chromium.executable_path)
    except Exception:
        need_install = True
    if need_install:
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            return False
    import chromium_boot
    ok, msg = chromium_boot.ensure_chromium_runs()
    if not ok:
        st.session_state["_chromium_err"] = msg
    return ok


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
                st.error("렌더링 엔진 준비에 실패했습니다: "
                         + str(st.session_state.get("_chromium_err", ""))
                         + "\n잠시 후 다시 시도하시거나, Drive의 Mac용 카드뉴스 생성기를 이용해 주세요.")
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


# =========================================================================
# 탭 3: 플레이북 만들기
# =========================================================================
with tab_playbook:
    # playbook은 pandas/python-pptx를 끌어오므로 탭을 열 때만 불러온다
    from playbook import tab as playbook_tab  # noqa: E402
    playbook_tab.render()
