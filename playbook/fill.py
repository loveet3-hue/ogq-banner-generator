# -*- coding: utf-8 -*-
"""템플릿 pptx에 새 기간 수치를 채워 넣는다.

디자인은 건드리지 않는다. 바꾸는 것은 (1) 텍스트 안의 숫자, (2) 막대 도형의 높이와
그 위에 붙은 값 라벨의 위치뿐이다. 새로 그리는 도형은 없다.
"""
import re
from pptx import Presentation
from pptx.util import Emu, Inches

NUMRE = re.compile(r'\d+(?:\.\d+)?')
WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
EPS = 0.05          # inch, 같은 행/열로 볼 허용 오차


def _in(v):
    return Emu(v).inches


class Changes(list):
    def log(self, slide, what, before, after):
        self.append({'slide': slide, 'what': what, 'before': str(before), 'after': str(after)})


# ------------------------------------------------------------------ 텍스트
def sub_numbers(shape, pairs, changes=None, slide=None, what=''):
    """도형 텍스트 안의 숫자만 교체. 서식이 걸린 run 단위로 바꿔 굵기·색을 보존한다.

    pairs: [(옛값문자열, 새값문자열)] — 앞에서부터 순서대로 첫 일치 1건씩 교체
    """
    before = shape.text_frame.text
    todo = list(pairs)
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if not todo:
                break
            i = 0
            while i < len(todo):
                old, new = todo[i]
                if old in run.text:
                    run.text = run.text.replace(old, new, 1)
                    todo.pop(i)
                else:
                    i += 1
    if todo:
        raise ValueError(f'교체 실패(slide {slide}, "{before[:40]}"): 찾지 못한 값 {todo}')
    if changes is not None and before != shape.text_frame.text:
        changes.log(slide, what or '텍스트', before, shape.text_frame.text)


def set_text(shape, new, changes=None, slide=None, what=''):
    """도형 텍스트 전체 교체 — 서식은 그대로 두고 글자만 바꾼다.

    여러 줄('\n')이면 원래 도형이 쓰던 문단 구조에 한 줄씩 나눠 담는다.
    문단이 모자라면 마지막 문단 안에서 줄바꿈(<a:br>)으로 잇는다.
    """
    from copy import deepcopy
    from pptx.oxml.ns import qn

    before = shape.text_frame.text
    paras = shape.text_frame.paragraphs
    if not paras or not paras[0].runs:
        shape.text_frame.text = new
        if changes is not None and before != shape.text_frame.text:
            changes.log(slide, what or '텍스트', before, new)
        return

    lines = new.split('\n')
    for i, para in enumerate(paras):
        if not para.runs:
            continue
        text = lines[i] if i < len(paras) - 1 and i < len(lines) else ''
        if i == len(paras) - 1:
            text = lines[i] if i < len(lines) else ''
        para.runs[0].text = text
        for r in para.runs[1:]:
            r.text = ''

    # 문단보다 줄이 많으면 마지막 문단 안에서 이어 붙인다
    extra = lines[len(paras):]
    if extra:
        last = [p for p in paras if p.runs][-1]
        anchor = last.runs[0]._r
        for line in extra:
            br = anchor.makeelement(qn('a:br'), {})
            anchor.addnext(br)
            run = deepcopy(last.runs[0]._r)
            for child in run:
                if child.tag == qn('a:t'):
                    child.text = line
            br.addnext(run)
            anchor = run

    if changes is not None and before != shape.text_frame.text:
        changes.log(slide, what or '텍스트', before, new)


# ------------------------------------------------------------------ 도형 찾기
def text_shapes(slide):
    return [sh for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip()]


def blank_shapes(slide):
    return [sh for sh in slide.shapes
            if not (sh.has_text_frame and sh.text_frame.text.strip())]


def _axis_labels(slide, wanted):
    """가로축 라벨 묶음 찾기 — 같은 y에 wanted 값들이 나란히 있는 행."""
    rows = {}
    for sh in text_shapes(slide):
        t = sh.text_frame.text.strip()
        if t in wanted:
            rows.setdefault(round(_in(sh.top), 2), []).append((t, sh))
    if not rows:
        return []
    y, items = max(rows.items(), key=lambda kv: len(kv[1]))
    if len(items) < len(wanted):
        return []
    items.sort(key=lambda p: _in(p[1].left))
    return items


def _bar_for(slide, label_shape, baseline):
    """라벨 바로 위에 바닥을 대고 서 있는 막대 도형."""
    lx, lw = _in(label_shape.left), _in(label_shape.width)
    cx = lx + lw / 2
    best = None
    for sh in blank_shapes(slide):
        x, w, top, h = _in(sh.left), _in(sh.width), _in(sh.top), _in(sh.height)
        if h <= 0 or w > lw + 0.1:
            continue
        if abs(top + h - baseline) > EPS:
            continue
        if abs(x + w / 2 - cx) > lw / 2 + EPS:
            continue
        if best is None or _in(best.height) < h:
            best = sh
    return best


def _rescale(bars, values, baseline_emu, changes, slide, what):
    """가장 큰 막대의 현재 높이를 유지한 채 값에 비례해 전체를 다시 그린다."""
    top_v = max(values)
    if top_v <= 0:
        return
    tallest = max(_in(b.height) for b in bars)
    k = tallest / top_v                       # inch per 1%
    for bar, v in zip(bars, values):
        h = Inches(max(v, 0) * k)
        before = round(_in(bar.height), 3)
        bar.height = h
        bar.top = baseline_emu - h
        changes.log(slide, f'{what} 막대', before, round(_in(bar.height), 3))
    return k


# ------------------------------------------------------------------ 차트
def fill_hour_chart(slide, sn, values, changes):
    """0~23시 막대 24개 + 최저/최고 콜아웃."""
    labels = _axis_labels(slide, {str(h) for h in range(24)})
    if len(labels) != 24:
        raise ValueError(f'slide {sn}: 시간축 라벨 24개를 찾지 못했습니다({len(labels)}개)')
    baseline = _in(labels[0][1].top)
    baseline_emu = labels[0][1].top
    order = [int(t) for t, _ in labels]
    bars = []
    for t, sh in labels:
        b = _bar_for(slide, sh, baseline)
        if b is None:
            raise ValueError(f'slide {sn}: {t}시 막대를 찾지 못했습니다')
        bars.append(b)
    vals = [values[h] for h in order]
    _rescale(bars, vals, baseline_emu, changes, sn, '시간대')

    # 콜아웃(최저·최고 값 라벨) — 새 최저/최고 막대 위로 옮기고 값을 갱신
    chart_x0 = min(_in(s.left) for _, s in labels) - 0.3
    chart_x1 = max(_in(s.left) + _in(s.width) for _, s in labels) + 0.3
    callouts = [sh for sh in text_shapes(slide)
                if re.fullmatch(r'\d+\.\d', sh.text_frame.text.strip())
                and chart_x0 <= _in(sh.left) <= chart_x1
                and _in(sh.top) < baseline]
    if callouts:
        lo_i, hi_i = vals.index(min(vals)), vals.index(max(vals))
        targets = sorted([(min(vals), lo_i), (max(vals), hi_i)])
        for sh, (v, i) in zip(sorted(callouts, key=lambda s: float(s.text_frame.text.strip())),
                              targets):
            bar = bars[i]
            gap = 0.18
            sh.left = Emu(int(bar.left + bar.width / 2 - sh.width / 2))
            sh.top = Emu(int(bar.top - Inches(gap)))
            set_text(sh, f'{v:g}', changes, sn, '시간대 콜아웃')
    return vals


def fill_weekday_chart(slide, sn, values, changes):
    """월~일 막대 7개 + 값 라벨 7개."""
    labels = _axis_labels(slide, set(WEEKDAYS))
    if len(labels) != 7:
        raise ValueError(f'slide {sn}: 요일 라벨 7개를 찾지 못했습니다({len(labels)}개)')
    baseline = _in(labels[0][1].top)
    baseline_emu = labels[0][1].top
    bars, vlabels = [], []
    for t, sh in labels:
        b = _bar_for(slide, sh, baseline)
        if b is None:
            raise ValueError(f'slide {sn}: {t}요일 막대를 찾지 못했습니다')
        bars.append(b)
        # 막대 위 값 라벨 = 같은 x대에 있는 소수 텍스트
        cx = _in(sh.left) + _in(sh.width) / 2
        cand = [v for v in text_shapes(slide)
                if re.fullmatch(r'\d+\.\d', v.text_frame.text.strip())
                and abs(_in(v.left) + _in(v.width) / 2 - cx) < 0.2
                and _in(v.top) < baseline]
        vlabels.append(cand[0] if cand else None)

    vals = [values[t] for t, _ in labels]
    _rescale(bars, vals, baseline_emu, changes, sn, '요일')
    for bar, vl, v in zip(bars, vlabels, vals):
        if vl is None:
            continue
        vl.top = Emu(int(bar.top - Inches(0.18)))
        set_text(vl, f'{v:.1f}', changes, sn, '요일 값')
    return dict(zip([t for t, _ in labels], vals))


# ------------------------------------------------------------------ 키워드
def fill_keywords(slide, sn, words, changes):
    """'인기 키워드' 제목 아래 한 줄로 놓인 칩 텍스트들을 교체."""
    heads = [sh for sh in text_shapes(slide) if '인기 키워드' in sh.text_frame.text]
    if not heads:
        return 0
    head = heads[0]
    hy = _in(head.top)
    chips = [sh for sh in text_shapes(slide)
             if _in(sh.top) > hy and _in(sh.left) >= _in(head.left) - 0.2
             and len(sh.text_frame.text.strip()) <= 8
             and _in(sh.top) - hy < 1.2]
    chips.sort(key=lambda s: (round(_in(s.top), 1), _in(s.left)))
    n = 0
    for sh, w in zip(chips, words):
        set_text(sh, w, changes, sn, '인기 키워드')
        n += 1
    return n


# ------------------------------------------------------------------ 진입점
def open_template(path):
    return Presentation(path)


# ------------------------------------------------------------------ 반려 현황(36장)
def _hbar_axis(slide):
    """가로 막대들이 공통으로 시작하는 x. 좌표를 박아 두면 템플릿을 조금만
    옮겨도(2.45 → 2.40) 통째로 못 찾는다."""
    groups = {}
    for sh in blank_shapes(slide):
        if 0 < _in(sh.height) < 0.3 and _in(sh.width) > 0:
            groups.setdefault(round(_in(sh.left), 2), []).append(sh)
    if not groups:
        return None
    x, items = max(groups.items(), key=lambda kv: len(kv[1]))
    return x if len(items) >= 3 else None


def _hbar_rows(slide, x_axis=None, name_x=0.9):
    """가로 막대 행 묶음: [(이름도형, 막대도형, 값도형)] — 위에서 아래 순."""
    if x_axis is None:
        x_axis = _hbar_axis(slide)
    if x_axis is None:
        return []
    rows = []
    bars = [sh for sh in blank_shapes(slide)
            if abs(_in(sh.left) - x_axis) < EPS and 0 < _in(sh.height) < 0.3]
    for bar in sorted(bars, key=lambda s: _in(s.top)):
        y = _in(bar.top)
        names = [sh for sh in text_shapes(slide)
                 if abs(_in(sh.top) - y) < EPS and _in(sh.left) < x_axis - 0.05]
        vals = [sh for sh in text_shapes(slide)
                if abs(_in(sh.top) - y) < EPS and _in(sh.left) > x_axis
                and re.fullmatch(r'\d+(?:\.\d+)?', sh.text_frame.text.strip())]
        if names and vals:
            rows.append((names[0], bar, vals[0]))
    return rows


def fill_reject_status(slide, sn, rj, month, changes, sentences=None, tails=None,
                       headline=None):
    """반려 사유 비중 가로 막대 + 상단 KPI 카드 + 머리말/각주."""
    cats = rj['reject.categories']
    total = rj['reject.total']

    # 1) 가로 막대
    rows = _hbar_rows(slide)
    if not rows:
        raise ValueError(f'slide {sn}: 반려 막대 행을 찾지 못했습니다')
    k = max(_in(b.width) for _, b, _ in rows) / max(c['pct'] for c in cats[:len(rows)])
    for (name_sh, bar, val_sh), c in zip(rows, cats):
        set_text(name_sh, c['name'], changes, sn, '반려 사유명')
        before = round(_in(bar.width), 3)
        bar.width = Inches(c['pct'] * k)
        changes.log(sn, '반려 막대', before, round(_in(bar.width), 3))
        val_sh.left = Emu(int(bar.left + bar.width + Inches(0.04)))
        set_text(val_sh, f'{c["pct"]:.1f}', changes, sn, '반려 비중')

    # 2) 상단 KPI 카드 4장 (같은 y에 나란한 '..%' 텍스트)
    cards = [sh for sh in text_shapes(slide)
             if re.fullmatch(r'\d+(?:\.\d+)?%', sh.text_frame.text.strip())]
    cards.sort(key=lambda s: _in(s.left))
    for sh, c in zip(cards, cats):
        set_text(sh, f'{c["pct"]:g}%', changes, sn, '반려 KPI')
        # 카드 설명줄 = 바로 아래 텍스트
        y = _in(sh.top) + _in(sh.height)
        subs = [t for t in text_shapes(slide)
                if abs(_in(t.left) - _in(sh.left)) < EPS and 0 <= _in(t.top) - y < 0.1]
        if subs:
            tail = (tails or {}).get(c['name'])
            if tail:
                set_text(subs[0], f'{c["name"]} — {tail}', changes, sn, '반려 카드 설명')
            else:
                # 설명 문구가 없으면 이름만 갈고 옛 설명은 지운다 —
                # 다른 사유의 설명이 남아 있는 것보다 없는 게 낫다
                set_text(subs[0], c['name'], changes, sn, '반려 카드 설명(문구 없음)')

    # 3) 머리말 · 각주
    for sh in text_shapes(slide):
        t = sh.text_frame.text
        if t.startswith('반려의') and '%' in t:
            if headline:
                set_text(sh, headline, changes, sn, '반려 머리말')
            else:
                old = NUMRE.search(t).group()
                sub_numbers(sh, [(old, f'{cats[0]["pct"]:g}')], changes, sn, '반려 머리말')
        elif '규격성' in t and '%' in t:
            # 하단 띠: '규격성 사유만 챙겨도 반려의 약 N%' — 여기 N은 1위 사유가 아니라
            # 규격성 사유 합계다. 머리말과 헷갈리면 62.5%가 잘못 들어간다.
            old = re.search(r'약\s*([\d.]+)\s*%', t)
            if old:
                sub_numbers(sh, [(old.group(1), f'{rj["reject.spec_pct"]:g}')],
                            changes, sn, '반려 하단 띠')
        if '기준' in t and '건' in t:
            y, mm = month.split('-')
            new = re.sub(r'\d{4}년\s*\d{1,2}월', f'{y}년 {int(mm)}월', t)
            new = re.sub(r'[\d,]+건', f'{total:,}건', new, count=1)
            new = re.sub(r'\d+개 항목', f'{len(cats)}개 항목', new)
            if new != t:
                set_text(sh, new, changes, sn, '반려 각주')

    # 4) TOP3 상세 카드 — 제목과 본문을 위에서부터 순서대로
    titles = sorted([sh for sh in text_shapes(slide)
                     if re.fullmatch(r'.+\s\([\d,]+건\)', sh.text_frame.text.strip())],
                    key=lambda s: _in(s.top))
    for i, title in enumerate(titles, 1):
        name = rj.get(f'reject.top{i}.name')
        cnt = rj.get(f'reject.top{i}.count')
        if not name:
            continue
        set_text(title, f'{name} ({cnt:,}건)', changes, sn, f'반려 TOP{i} 제목')
        body = _card_body(slide, title)
        text = (sentences or {}).get(name)
        if body is not None and text:
            set_text(body, text, changes, sn, f'반려 TOP{i} 본문')
        elif body is not None:
            changes.log(sn, f'반려 TOP{i} 본문 미작성',
                        body.text_frame.text[:40],
                        f'(overrides.CARD_SENTENCES에 "{name}" 문장이 없습니다)')
    return len(rows)


def _card_body(slide, title):
    """카드 제목 바로 아래, 같은 x에서 시작하는 설명 텍스트."""
    tx, ty = _in(title.left), _in(title.top) + _in(title.height)
    cands = [sh for sh in text_shapes(slide)
             if sh is not title and abs(_in(sh.left) - tx) < 0.1
             and 0 <= _in(sh.top) - ty < 0.4]
    return min(cands, key=lambda s: _in(s.top)) if cands else None


def fill_reject_action(slide, sn, rj, changes):
    """'반려 10.5%' 형태의 배지를 새 비중으로 갱신.

    배지는 카드 오른쪽 끝에 있고, 그 카드의 제목은 같은 높이의 바로 왼쪽 텍스트다.
    제목이 '권리 · AI 표기'처럼 두 사유를 묶고 있으면 두 비중을 더한다.
    """
    n = 0
    for sh in list(text_shapes(slide)):
        if not re.fullmatch(r'반려\s*[\d.]+%', sh.text_frame.text.strip()):
            continue
        cats = _card_categories(slide, sh, rj)
        if not cats:
            continue
        pct = round(sum(c['pct'] for c in cats), 1)
        set_text(sh, f'반려 {pct:g}%', changes, sn, '반려 대응 배지')
        n += 1
    return n


# 카드 제목에 쓰인 말 → 반려 카테고리
_ACTION_ALIAS = {
    '다크모드': '다크모드 대응',
    '가독성': '텍스트 가독성',
    '투명화': '투명 배경(PNG)',
    '투명 배경': '투명 배경(PNG)',
    '중복': '중복 콘텐츠',
    '권리': '저작권·권리 침해',
    'AI': 'AI 사용 의심',
    '화질': '사진·화질',
    '크기': '크기·정렬 통일',
    '정렬': '크기·정렬 통일',
}


def _card_title(slide, badge):
    """배지와 같은 높이에서 바로 왼쪽에 있는 텍스트 = 그 카드의 제목."""
    by, bx = _in(badge.top), _in(badge.left)
    cands = [sh for sh in text_shapes(slide)
             if sh is not badge and abs(_in(sh.top) - by) < 0.12
             and _in(sh.left) < bx]
    if not cands:
        return None
    return max(cands, key=lambda s: _in(s.left))


def _card_categories(slide, badge, rj):
    title = _card_title(slide, badge)
    if title is None:
        return []
    t = title.text_frame.text
    lookup = {c['name']: c for c in rj['reject.categories']}
    found, seen = [], set()
    for word, cat in _ACTION_ALIAS.items():
        if word in t and cat in lookup and cat not in seen:
            seen.add(cat)
            found.append(lookup[cat])
    return found


# ------------------------------------------------------------------ 정지형/애니 비율 막대 (8·9·10장)
def fill_ctype_bar(slide, sn, still_pct, anim_pct, changes, row_y=5.40, row_h=0.38):
    """가로로 둘로 나뉜 띠. 폭이 곧 비중이라 글자만 바꾸면 그림이 거짓말을 한다.

    한 칸은 막대 도형과 그 위에 겹쳐 놓은 글자 도형이 같은 자리에 포개져 있고,
    두 번째 칸은 글자가 없을 수도 있다(작아서 안 넣은 경우).
    """
    row = [sh for sh in slide.shapes
           if abs(_in(sh.top) - row_y) < EPS and abs(_in(sh.height) - row_h) < EPS]
    if len(row) < 2:
        raise ValueError(f'slide {sn}: 유형 비율 막대를 찾지 못했습니다')

    lefts = sorted({round(_in(sh.left), 2) for sh in row})
    if len(lefts) != 2:
        raise ValueError(f'slide {sn}: 막대 칸이 2개가 아닙니다({len(lefts)}개)')
    x0 = lefts[0]
    g1 = [sh for sh in row if abs(_in(sh.left) - lefts[0]) < EPS]
    g2 = [sh for sh in row if abs(_in(sh.left) - lefts[1]) < EPS]
    total = max(_in(sh.left) + _in(sh.width) for sh in row) - x0

    def label_of(group):
        for sh in group:
            if sh.has_text_frame and sh.text_frame.text.strip():
                return sh.text_frame.text.strip()
        return ''

    first = label_of(g1)
    lead_anim = '애니' in first
    p1, p2 = (anim_pct, still_pct) if lead_anim else (still_pct, anim_pct)
    n1, n2 = ('애니메이션', '정지형') if lead_anim else ('정지형', '애니메이션')

    w1 = Inches(total * p1 / 100)
    w2 = Inches(total * p2 / 100)
    x2 = Emu(int(Inches(x0) + w1))
    for sh in g1:
        sh.width = w1
    for sh in g2:
        sh.left, sh.width = x2, w2
    changes.log(sn, f'{n1} 비율 막대', round(_in(g1[0].width) if g1 else 0, 3),
                round(total * p1 / 100, 3))

    # 글자: 원래 '정지형 94%'처럼 유형명이 붙어 있으면 유지, 아니면 숫자만
    for group, name, pct in ((g1, n1, p1), (g2, n2, p2)):
        for sh in group:
            if not (sh.has_text_frame and sh.text_frame.text.strip()):
                continue
            old = sh.text_frame.text.strip()
            new = f'{name} {pct:.0f}%' if re.search(r'정지형|애니', old) else f'{pct:.0f}%'
            set_text(sh, new, changes, sn, '유형 비율')
    return {n1: p1, n2: p2}


# ------------------------------------------------------------------ 시즌 캘린더 (16·23·30장)
def fill_season_calendar(slide, sn, cards, changes):
    """월 카드 4장을 새 기간으로 갈아 끼운다.

    한 카드는 [월] [등록 시점] / [이벤트] / [추천 주제] 네 줄이고, 월 표시를 기준으로
    같은 줄 오른쪽(등록 시점)과 아래 두 줄(이벤트·주제)을 찾아 채운다.
    """
    # 캘린더 제목 아래에서만 찾는다. 같은 슬라이드의 월별 매출 차트도 가로축이
    # '1월 2월 ...'이라, 그냥 찾으면 차트 축을 카드로 착각해 덮어쓴다.
    titles = [sh for sh in text_shapes(slide) if '캘린더' in sh.text_frame.text]
    if not titles:
        return 0
    floor = max(_in(t.top) for t in titles)

    heads = [sh for sh in text_shapes(slide)
             if _in(sh.top) > floor
             and re.fullmatch(r'\d{1,2}월', sh.text_frame.text.strip())]
    if not heads:
        return 0
    # 같은 y에 여러 개 늘어선 줄이 카드 머리다
    rows = {}
    for sh in heads:
        rows.setdefault(round(_in(sh.top), 2), []).append(sh)
    y, months = max(rows.items(), key=lambda kv: len(kv[1]))
    months.sort(key=lambda s: _in(s.left))
    if len(months) < 2:
        return 0

    n = 0
    for sh, card in zip(months, cards):
        set_text(sh, card['month'], changes, sn, '캘린더 월')
        x = _in(sh.left)
        same_row = [t for t in text_shapes(slide)
                    if abs(_in(t.top) - y) < EPS and _in(t.left) > x and t is not sh]
        if same_row:
            reg = min(same_row, key=lambda t: _in(t.left))
            set_text(reg, card['register'], changes, sn, '캘린더 등록시점')
        # 아래로 이어지는 줄들 (같은 x에서 시작)
        below = sorted([t for t in text_shapes(slide)
                        if abs(_in(t.left) - x) < EPS and 0 < _in(t.top) - y < 0.8],
                       key=lambda t: _in(t.top))
        if len(below) >= 1:
            set_text(below[0], card['events'], changes, sn, '캘린더 이벤트')
        if len(below) >= 2:
            set_text(below[1], card['topics'], changes, sn, '캘린더 주제')
        n += 1

    # 카드가 남으면 비운다 (안 그러면 지난 기간 내용이 남는다)
    for sh in months[len(cards):]:
        x, = (_in(sh.left),)
        for t in text_shapes(slide):
            if abs(_in(t.left) - x) < EPS and 0 <= _in(t.top) - y < 0.8:
                set_text(t, '', changes, sn, '캘린더 빈 칸')
        set_text(sh, '', changes, sn, '캘린더 빈 칸')
    return n


# ------------------------------------------------------------------ TOP25 속성 표 (13·20·27장)
def fill_top25_table(slide, sn, classified, changes):
    """속성 표에서 '근거가 있는 줄'만 채운다.

    표는 [속성 | 1위 값 | 매출 비중 | 2위 값 | 매출 비중] 다섯 칸이다.
    그림을 봐야 아는 줄(텍스트 비중·텍스트 종류·라인 스타일)은 손대지 않는다 —
    빈 값을 넣거나 짐작해 채우는 것보다 이전 판이 남아 있는 편이 낫다.
    """
    tables = [sh.table for sh in slide.shapes if sh.has_table]
    if not tables:
        return 0, []
    tbl = tables[0]
    filled, skipped = 0, []
    for row in list(tbl.rows)[1:]:
        cells = row.cells
        attr = cells[0].text.strip()
        vals = classified.get(attr)
        if not vals:
            if attr:
                skipped.append(attr)
            continue
        top1 = vals[0]
        # 값이 한 종류뿐이면 2위 칸에 '0%'를 쓰지 않는다 — 없는 것과 0인 것은 다르다
        top2 = (vals[1][0], f'{vals[1][1]:g}%') if len(vals) > 1 else ('—', '—')
        for cell, new in ((cells[1], top1[0]), (cells[2], f'{top1[1]:g}%'),
                          (cells[3], top2[0]), (cells[4], top2[1])):
            _set_cell(cell, new, changes, sn, f'TOP25 {attr}')
        filled += 1
    return filled, skipped


def _set_cell(cell, new, changes, sn, what):
    """표 칸의 글자만 바꾼다 (칸 서식·정렬은 그대로)."""
    tf = cell.text_frame
    before = tf.text
    paras = tf.paragraphs
    if paras and paras[0].runs:
        paras[0].runs[0].text = new
        for r in paras[0].runs[1:]:
            r.text = ''
        for p in paras[1:]:
            for r in p.runs:
                r.text = ''
    else:
        tf.text = new
    if before != new:
        changes.log(sn, what, before, new)


# ------------------------------------------------------------------ TOP25 상단 KPI (13·20·27장)
def fill_top25_kpi(slide, sn, kpi_by_label, changes):
    """카드 설명줄의 문구를 보고 그 카드에 맞는 값을 넣는다.

    카드 구성이 마켓마다 달라서(정지형/애니메이션/GIF/파스텔) 위치가 아니라
    설명 문구로 짝을 짓는다. 짝이 없는 카드(텍스트 포함·밈 등)는 건드리지 않는다.
    """
    cards = [sh for sh in text_shapes(slide)
             if re.fullmatch(r'\d+(?:\.\d+)?%', sh.text_frame.text.strip())
             and 2.2 < _in(sh.top) < 3.2]
    n = 0
    for sh in cards:
        y = _in(sh.top) + _in(sh.height)
        subs = [t for t in text_shapes(slide)
                if abs(_in(t.left) - _in(sh.left)) < EPS and 0 <= _in(t.top) - y < 0.15]
        if not subs:
            continue
        label = subs[0].text_frame.text
        for key, value in kpi_by_label.items():
            if key in label:
                set_text(sh, f'{value:g}%', changes, sn, 'TOP25 KPI')
                n += 1
                break
    return n


# ------------------------------------------------------------------ 글자로 자리 찾기
def find_by_text(slide, needle):
    """그 글자를 담고 있는 도형. 템플릿을 다시 내보내면 도형ID가 전부 바뀌므로
    ID 대신 글자로 찾는다."""
    for sh in text_shapes(slide):
        if needle in sh.text_frame.text:
            return sh
    return None


def value_beside(slide, caption_shape, max_gap=1.6):
    """설명줄 왼쪽에 붙어 있는 큰 수치 도형."""
    y, x = _in(caption_shape.top), _in(caption_shape.left)
    cands = [sh for sh in text_shapes(slide)
             if sh is not caption_shape and abs(_in(sh.top) - y) < 0.25
             and 0 < x - _in(sh.left) < max_gap]
    return max(cands, key=lambda s: _in(s.left)) if cands else None


CTYPE_LABEL = re.compile(r'(정지형|애니메이션)(\s*)(\d+(?:\.\d+)?)%')


def fill_ctype_labels(slide, sn, still_pct, anim_pct, changes, min_y=4.5):
    """'정지형 91%' · '애니메이션 70%' 같은 글자를 새 값으로.

    막대 길이는 건드리지 않는다. 이 슬라이드의 막대는 손으로 다듬어져 슬라이드마다
    구조가 달라서(어떤 장은 글자만 바뀌고 막대는 그대로다) 자동으로 늘였다 줄였다 하면
    디자인을 망가뜨린다. 대신 build.py가 '막대 길이는 확인해 달라'고 알린다.
    """
    n = 0
    for sh in list(text_shapes(slide)):
        if _in(sh.top) < min_y:
            continue
        t = sh.text_frame.text
        if not CTYPE_LABEL.search(t):
            continue
        # 한 상자에 '정지형 58% ... 애니메이션 42%'가 같이 있을 때, 두 값을 차례로
        # 갈아 끼우면 방금 써 넣은 숫자를 다음 차례가 다시 집어서 제자리로 돌아온다.
        # 그래서 한 번에 훑으며 바꾼다.
        def swap(m):
            new = still_pct if m.group(1) == '정지형' else anim_pct
            return f'{m.group(1)}{m.group(2)}{new:.0f}%'

        before = sh.text_frame.text
        changed_any = False
        for para in sh.text_frame.paragraphs:
            for run in para.runs:
                new_run = CTYPE_LABEL.sub(swap, run.text)
                if new_run != run.text:
                    run.text = new_run
                    changed_any = True
        if changed_any:
            changes.log(sn, '유형 비율', before, sh.text_frame.text)
            n += 1
    return n
