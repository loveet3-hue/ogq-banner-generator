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


# ------------------------------------------------------------------ 정지형/애니 비율 막대
# 브랜드 색으로 어느 칸이 무엇인지 가린다 (Vol.1 디자인 토큰)
STILL_COLOR = '38761D'   # 진한 초록 = 정지형
ANIM_COLOR = 'E69138'    # 주황 = 애니메이션


def _fill_hex(shape):
    try:
        return str(shape.fill.fore_color.rgb).upper()
    except Exception:
        return None


def _ctype_band(slide, min_y=4.5):
    """'정지형 nn%' 글자가 놓인 높이. 띠는 그 글자와 같은 줄에 있다.

    판마다 띠가 위아래로 조금씩 움직여서 높이를 못 박아 두면 못 찾는다
    (v2_에서 5.30~5.60 → 5.16~5.19로 옮겨졌다).
    """
    for sh in text_shapes(slide):
        t = sh.text_frame.text
        if _in(sh.top) >= min_y and CTYPE_LABEL.search(t):
            y = _in(sh.top)
            return (y - 0.25, y + 0.25)
    return None


def fill_ctype_bar(slide, sn, still_pct, anim_pct, changes, band=None):
    """가로 띠를 값에 맞춰 다시 그린다.

    템플릿의 띠는 손으로 그려져 같은 색 사각형이 여러 장 겹쳐 있다(슬라이드마다 2~3장).
    그대로 두면 글자만 42%로 바뀌고 띠는 58% 길이라 그림이 값과 어긋난다.
    그래서 색으로 정지형/애니를 가려낸 뒤, 각 색 하나만 남기고 길이를 다시 잡는다.
    겹쳐 있던 나머지는 지운다 — 의도된 디자인이 아니라 편집하다 남은 사본이다.
    """
    band = band or _ctype_band(slide)
    if band is None:
        return False
    lo, hi = band
    bars = [sh for sh in slide.shapes
            if lo <= _in(sh.top) <= hi and _in(sh.width) > 0.05
            and not (sh.has_text_frame and sh.text_frame.text.strip())
            and _fill_hex(sh) in (STILL_COLOR, ANIM_COLOR)]
    if not bars:
        return False
    still = [b for b in bars if _fill_hex(b) == STILL_COLOR]
    anim = [b for b in bars if _fill_hex(b) == ANIM_COLOR]
    if not still or not anim:
        return False

    x0 = min(_in(b.left) for b in bars)
    x1 = max(_in(b.left) + _in(b.width) for b in bars)
    track = x1 - x0
    if track <= 0:
        return False

    keep_s, keep_a = still[0], anim[0]
    w_s = track * max(still_pct, 0) / 100
    before = f'정지형 {round(_in(keep_s.width), 2)}″ / 애니 {round(_in(keep_a.width), 2)}″'
    keep_s.left, keep_s.width = Emu(int(Inches(x0))), Inches(w_s)
    keep_a.left = Emu(int(Inches(x0 + w_s)))
    keep_a.width = Inches(max(track - w_s, 0))
    for extra in still[1:] + anim[1:]:
        extra._element.getparent().remove(extra._element)
    changes.log(sn, '유형 비율 막대', before,
                f'정지형 {round(w_s, 2)}″ / 애니 {round(track - w_s, 2)}″'
                f' (겹친 사본 {len(still) + len(anim) - 2}장 정리)')
    return True


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
def fill_top25_table(slide, sn, classified, changes, keep_rows=()):
    """속성 표에서 '근거가 있는 줄'만 채운다.

    표는 [속성 | 1위 값 | 매출 비중 | 2위 값 | 매출 비중] 다섯 칸이다.
    그림을 봐야 아는 줄(텍스트 비중·텍스트 종류·라인 스타일)은 손대지 않는다 —
    빈 값을 넣거나 짐작해 채우는 것보다 이전 판이 남아 있는 편이 낫다.
    """
    frames = [sh for sh in slide.shapes if sh.has_table]
    if not frames:
        return 0, []
    frame = frames[0]
    tbl = frame.table
    row_h = [r.height for r in tbl.rows]        # 지우기 전 행 높이

    # 줄마다 잣대가 다르다(유형=판매 수 / 그 외=매출액). 열 이름을 '매출 비중'으로
    # 두면 유형 줄이 거짓말이 되므로 중립으로 바꾼다.
    for cell in tbl.rows[0].cells:
        if cell.text.strip() == '매출 비중':
            _set_cell(cell, '비중', changes, sn, 'TOP25 열 이름')
    filled, skipped = 0, []
    for row in list(tbl.rows)[1:]:
        cells = row.cells
        attr = cells[0].text.strip()
        if attr in keep_rows:          # 손대지 않기로 한 줄
            continue
        vals = classified.get(attr)
        if not vals:
            # 근거가 없는 줄은 지운다. 옛 값을 그대로 두면 다른 줄은 새 데이터인데
            # 이 줄만 지난 판 값이라, 한 표 안에서 기준이 섞인다.
            if attr:
                skipped.append(attr)
                row._tr.getparent().remove(row._tr)
            continue
        top1 = vals[0]
        # 값이 한 종류뿐이면 2위 칸에 '0%'를 쓰지 않는다 — 없는 것과 0인 것은 다르다
        top2 = (vals[1][0], f'{vals[1][1]:g}%') if len(vals) > 1 else ('—', '—')
        for cell, new in ((cells[1], top1[0]), (cells[2], f'{top1[1]:g}%'),
                          (cells[3], top2[0]), (cells[4], top2[1])):
            _set_cell(cell, new, changes, sn, f'TOP25 {attr}')
        filled += 1

    # 행을 지우면 남은 행이 원래 표 높이를 채우려고 늘어난다. 높이를 다시 잡아 준다.
    if skipped:
        keep = list(tbl.rows)
        unit = row_h[1] if len(row_h) > 1 else row_h[0]
        for i, r in enumerate(keep):
            r.height = row_h[0] if i == 0 else unit
        frame.height = sum(r.height for r in keep)
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
def fill_top25_kpi(slide, sn, value_of, changes):
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
        value = value_of(subs[0].text_frame.text)
        if value is not None:
            set_text(sh, f'{value:g}%', changes, sn, 'TOP25 KPI')
            n += 1
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
