# -*- coding: utf-8 -*-
"""배너 생성기 앱에 얹는 '플레이북 만들기' 탭.

  from playbook import tab
  with tab_playbook:
      tab.render()
"""
import gc
import tempfile
import traceback
from pathlib import Path

import streamlit as st

from . import build as B
from . import config, ingest

MARKET_LABEL = {'NOM': 'NAVER OGQ마켓', 'SOM': 'SOOP OGQ이모티콘', 'COM': '채팅+ OGQ마켓'}
PPTX_MIME = ('application/vnd.openxmlformats-officedocument'
             '.presentationml.presentation')


def _workdir():
    """이 세션이 쓸 임시 폴더. 다시 그릴 때마다 새로 만들면 올린 파일이 사라진다."""
    if 'pb_workdir' not in st.session_state:
        st.session_state.pb_workdir = tempfile.mkdtemp(prefix='ogq_playbook_')
    return Path(st.session_state.pb_workdir)


def _save(files, workdir):
    out = []
    for f in files:
        p = workdir / f.name
        p.write_bytes(f.getbuffer())
        out.append(p)
    return out


def _guess(paths):
    got = {}
    for p in paths:
        try:
            got[p] = ingest.detect_market(str(p))
        except ingest.IngestError:
            got[p] = None
    return got


def _run(xlsx_paths, reject_path, reject_month, workdir):
    bar = st.progress(0.0, text='시작하는 중')
    labels = {1: '엑셀 읽는 중 (파일이 크면 30초쯤 걸립니다)', 2: '지표 계산 중',
              3: '슬라이드 채우는 중', 4: '파일 저장 중', 5: '검수 중'}

    def progress(i, n, msg):
        bar.progress(i / n, text=labels.get(i, msg))

    try:
        r = B.build(xlsx_paths, reject_path, reject_month,
                    out=workdir / 'playbook.pptx', progress=progress)
    except ingest.IngestError as e:
        bar.empty()
        st.error(f'데이터를 읽지 못했습니다.\n\n{e}')
        return None
    except MemoryError:
        bar.empty()
        st.error('메모리가 모자랍니다. 파일이 너무 크면 웹 대신 내 컴퓨터에서 '
                 '`python3 -m playbook.run` 으로 돌려 주세요.')
        return None
    except Exception as e:
        bar.empty()
        st.error(f'만드는 중 문제가 생겼습니다: {e}')
        with st.expander('자세한 내용'):
            st.code(traceback.format_exc())
        return None
    finally:
        gc.collect()          # 큰 표를 붙들고 있지 않도록

    bar.empty()
    named = workdir / f'OGQ_{r.year}_{r.half}_플레이북_초안.pptx'
    if named.exists():
        named.unlink()
    r.out.rename(named)
    r.out = named
    return r


def _report(r):
    st.success(f'**{r.period}** 플레이북 초안이 나왔습니다. (39장)')

    c1, c2, c3 = st.columns(3)
    c1.metric('바뀐 값', f'{len(r.changes)}건')
    c2.metric('갱신된 슬라이드', f'{len(r.changed_slides)}장')
    c3.metric('검수 지적', f'{len(r.issues)}건')

    st.download_button('📥 플레이북 PPT 내려받기', r.out.read_bytes(),
                       file_name=r.out.name, mime=PPTX_MIME,
                       type='primary', use_container_width=True)
    st.download_button('변경내역 내려받기 (.md)', r.changelog_md().encode('utf-8'),
                       file_name=f'변경내역_{r.year}_{r.half}.md',
                       mime='text/markdown', use_container_width=True)

    if r.changed_slides:
        st.caption('값이 갱신된 슬라이드: '
                   + ', '.join(str(s) for s in r.changed_slides) + '장')

    with st.expander('읽어 들인 데이터'):
        for m, v in r.rows.items():
            st.write(f'**{MARKET_LABEL.get(m, m)}** — {v["n"]:,}행 · {v["lo"]} ~ {v["hi"]}')
        if r.reject_month:
            st.write(f'**심사 반려** — {r.reject_month} · {r.reject_total:,}건 · '
                     f'미분류 {r.reject_other_pct}%')

    if r.issues:
        st.warning('검수에서 걸린 것')
        for si, kind, val, ctx in r.issues[:20]:
            st.write(f'- {si}장 **[{kind}]** {val} {ctx}')

    if r.warnings:
        st.warning('확인이 필요합니다')
        for w in r.warnings:
            st.write(f'- {w}')

    with st.expander('사람이 직접 채워야 하는 슬라이드', expanded=True):
        st.caption('매출 데이터에 없는 정보라 자동으로 못 채웁니다. '
                   '이 슬라이드들은 이전 판 내용이 그대로 넘어와 있습니다.')
        for info in r.manual.values():
            slides = ', '.join(f'{s}장' for s in info['slides'])
            st.write(f'- **{slides}** — {info["what"]}')


def render():
    st.caption('마켓별 매출 엑셀을 넣으면 플레이북 초안 PPT(39장)를 만들어 드립니다. '
               '디자인은 그대로 두고 숫자·그래프·키워드만 새 데이터로 바꿉니다.')

    workdir = _workdir()

    with st.container(border=True):
        st.markdown('**1. 매출 엑셀 3개** — NAVER · SOOP · 채팅+. 순서는 상관없습니다.')
        sales = st.file_uploader('매출 엑셀', type=['xlsx'], accept_multiple_files=True,
                                 label_visibility='collapsed', key='pb_sales')

        assigned = {}
        if sales:
            paths = _save(sales, workdir)
            guessed = _guess(paths)
            cols = st.columns(min(3, len(paths)) or 1)
            for i, p in enumerate(paths):
                g = guessed[p]
                with cols[i % len(cols)]:
                    if g:
                        assigned[p] = g
                        st.success(f'{MARKET_LABEL[g]}\n\n`{p.name}`')
                    else:
                        pick = st.selectbox(f'`{p.name}` 은 어느 마켓?',
                                            ['고르세요'] + list(MARKET_LABEL.values()),
                                            key=f'pb_pick_{p.name}')
                        if pick != '고르세요':
                            assigned[p] = next(k for k, v in MARKET_LABEL.items()
                                               if v == pick)

    with st.container(border=True):
        st.markdown('**2. 심사 반려 데이터** (선택) — `ogq_statistics.xlsx`')
        st.caption('올리면 36·37장 심사 반려 슬라이드까지 갱신됩니다. '
                   '없으면 그 두 장은 이전 판 그대로 넘어갑니다.')
        stats = st.file_uploader('심사 통계 엑셀', type=['xlsx'],
                                 label_visibility='collapsed', key='pb_stats')

        reject_path, reject_month = None, None
        if stats:
            reject_path = workdir / stats.name
            reject_path.write_bytes(stats.getbuffer())
            try:
                months = B.available_reject_months(reject_path)
                reject_month = st.selectbox('어느 달 기준으로 만들까요?', months,
                                            index=0, key='pb_month')
            except Exception as e:
                st.error(f'반려 데이터를 읽지 못했습니다: {e}')
                reject_path = None

    markets = set(assigned.values())
    ready = len(assigned) == 3 and markets == {'NOM', 'SOM', 'COM'}
    if sales and not ready:
        missing = [MARKET_LABEL[m] for m in ('NOM', 'SOM', 'COM') if m not in markets]
        if missing:
            st.warning(f'아직 부족합니다 — {", ".join(missing)} 파일이 필요합니다.')

    if st.button('플레이북 만들기', type='primary', disabled=not ready,
                 use_container_width=True, key='pb_go'):
        st.session_state.pb_result = _run(list(assigned.keys()),
                                          reject_path, reject_month, workdir)

    r = st.session_state.get('pb_result')
    if r is not None:
        _report(r)

    st.caption(f'정지형/애니메이션 비중 기준: '
               f'{"매출액" if config.CTYPE_BASIS == "rev" else config.CTYPE_BASIS}')
