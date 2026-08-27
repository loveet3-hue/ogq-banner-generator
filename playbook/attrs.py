# -*- coding: utf-8 -*-
"""TOP25 콘텐츠를 속성별로 분류하고 매출 비중을 매긴다 (13·20·27장 표).

두 가지 근거만 쓴다.
  1) 픽셀 — 정지형/애니, 배경 투명도, 색상
  2) 마켓 태그 — 기반 분류, 도메인, 성격, 사용 맥락

글자가 몇 장에 들어갔는지(텍스트 비중), 어떤 말투인지(텍스트 종류), 선이 굵은지는
그림을 눈으로 봐야 알 수 있어 여기서 다루지 않는다. 그 줄은 손대지 않고 남겨 둔다
— 근거 없는 값을 채워 넣는 것보다 이전 판이 남아 있는 편이 낫다.

*** v2 덱과 값이 달라질 수 있다 ***
v2는 사람이 눈으로 보고 분류한 것이라 마켓마다 말이 조금씩 달랐다
(같은 뜻인데 '혼합형'·'애니메이션'·'GIF 포함'). 여기서는 말을 하나로 통일한다.
"""

# ---------------------------------------------------------------- 픽셀 기준
# TOP25 74종을 실측해 분위수를 보고 정한 값이다. 바꾸려면 근거를 같이 남길 것.
ACHROMATIC_MAX = 0.12    # 색이 있는 픽셀이 이보다 적으면 무채색
VIVID_MIN_SAT = 0.42     # 색이 있는 픽셀의 채도가 이보다 높으면 원색
DARK_MAX_VALUE = 0.55    # 이보다 어두우면 '어두운 톤'
TRANSPARENT_MIN = 0.15   # 투명 픽셀이 이보다 많으면 배경 없음으로 본다


def color_style(st):
    if st['value'] < DARK_MAX_VALUE:
        return '어두운 톤'
    if st['chroma_ratio'] < ACHROMATIC_MAX:
        return '무채색'
    if st['chroma_sat'] >= VIVID_MIN_SAT:
        return '원색'
    return '파스텔'


def content_type(st):
    r = st['animated_ratio']
    if r >= 0.95:
        return '애니메이션'
    if r <= 0.05:
        return '정지형'
    return '혼합형'


def background(st):
    return '투명' if st['transparent_ratio'] >= TRANSPARENT_MIN else '배경 있음'


# 태그 기반 분류(기반 분류·도메인·성격·사용 맥락)는 뺐다.
# 마켓 태그로 근사해 봤지만 사람이 눈으로 본 것과 갈리는 일이 잦았다
# (채팅+ 상세 성격: 자동 '공손·정중' vs 사람 '귀여운'). 근거가 약한 값을 채워 넣느니
# 그 줄은 손대지 않는 편이 낫다. 되살리려면 git 이력에 있다.

# ---------------------------------------------------------------- 집계
# 표의 어느 줄을 우리가 채우고, 어느 줄은 손대지 않는지
def text_level(d):
    """24장 중 글자가 든 장의 비율 → 높음/보통/낮음. OCR을 못 쓰면 None."""
    r = d.get('text_ratio')
    if r is None:
        return None
    if r >= 0.8:
        return '높음'
    if r >= 0.4:
        return '보통'
    return '낮음'


# 실제 이미지에서 재는 것만 채운다.
COMPUTED_ROWS = {
    '콘텐츠 유형': lambda d: content_type(d['stats']),
    '텍스트 비중': text_level,
    '색상 스타일': lambda d: color_style(d['stats']),
    '배경 유형': lambda d: background(d['stats']),
}


def classify(analyzed, weight, count_weight=None):
    """→ {속성: [(값, 비중%), ...] 내림차순}

    analyzed:     {콘텐츠ID: {'title','tags','stats'}}
    weight:       매출액 무게 — 색상·배경 등 대부분의 줄이 이걸 쓴다
    count_weight: 판매 수 무게 — '콘텐츠 유형'(정지형/애니) 줄만 이걸 쓴다.
                  유형 비중은 판매 수로, 나머지는 매출액으로 재기로 했다.
    """
    revenue = weight
    total = sum(revenue.get(cid, 0) for cid, d in analyzed.items() if d.get('stats'))
    if total <= 0:
        return {}, 0
    counts = count_weight or revenue
    ctotal = sum(counts.get(cid, 0) for cid, d in analyzed.items() if d.get('stats'))
    out = {}
    for attr, fn in COMPUTED_ROWS.items():
        w, wtot = ((counts, ctotal) if attr == '콘텐츠 유형' else (revenue, total))
        if wtot <= 0:
            continue
        agg = {}
        for cid, d in analyzed.items():
            if not d.get('stats'):
                continue
            try:
                label = fn(d)
            except Exception:
                continue
            if label is None:      # OCR을 못 쓰는 등 잴 수 없는 경우
                continue
            agg[label] = agg.get(label, 0) + w.get(cid, 0)
        ranked = sorted(agg.items(), key=lambda kv: -kv[1])
        out[attr] = [(k, round(v / wtot * 100, 1)) for k, v in ranked]
    return out, total


# ---------------------------------------------------------------- 상단 KPI
def series_share(analyzed, revenue):
    """시리즈(넘버링·후속작) 콘텐츠의 매출 비중."""
    import re
    pat = re.compile(r'(\d+\s*(?:탄|편|기|번째|집))|ver\.?\s*\d|시즌\s*\d|season\s*\d|'
                     r'part\s*\d|\bv\.?\s*\d|(?<![0-9])[2-9](?![0-9])\s*$', re.I)
    total = sum(revenue.get(c, 0) for c in analyzed)
    hit = sum(revenue.get(c, 0) for c, d in analyzed.items()
              if pat.search(str(d.get('title', ''))))
    return round(hit / total * 100, 1) if total else 0.0


def style_share(analyzed, revenue, label):
    """특정 색상 스타일(파스텔 등)의 매출 비중."""
    total = sum(revenue.get(c, 0) for c, d in analyzed.items() if d.get('stats'))
    hit = sum(revenue.get(c, 0) for c, d in analyzed.items()
              if d.get('stats') and color_style(d['stats']) == label)
    return round(hit / total * 100, 1) if total else 0.0


# 카드 설명 문구는 판마다 조금씩 달라진다('애니메이션 스티커 매출 비중' →
# '움직이는 이모티콘 매출 비중'). 통째로 비교하면 그때마다 빗나가므로,
# 반드시 들어가야 할 조각(all)과 들어가면 안 되는 조각(none)으로 가린다.
# 덱 안의 모든 비율은 **매출액 기준**으로 통일한다. 건수·구매자·콘텐츠 수로 재면
# 같은 '애니 비중'인데 슬라이드마다 답이 달라지고, 채팅+처럼 우위가 뒤집히기도 한다
# (매출 애니 58.3% vs 건수 정지형 54.9%).
def text_share(analyzed, weight):
    """글자가 든 콘텐츠의 비중. '글자가 하나라도 있으면' 텍스트 포함으로 본다."""
    got = {c: d for c, d in analyzed.items() if d.get('text_ratio') is not None}
    total = sum(weight.get(c, 0) for c in got)
    if not total:
        return None
    hit = sum(weight.get(c, 0) for c, d in got.items() if d['text_ratio'] > 0)
    return round(hit / total * 100, 1)


def meme_share(analyzed, weight):
    """밈·짤 태그가 달린 콘텐츠의 비중.

    KPI_RULES에서는 빼 두었다. 크리에이터가 직접 단 태그라 근거가 아주 없진 않지만,
    사람이 눈으로 매긴 값과 20%p 넘게 갈렸다(NAVER 자동 38.0% vs 사람 58.8%).
    쓰려면 KPI_RULES에 (['밈'], [], meme_share)를 넣으면 된다.
    """
    words = ('밈', '짤', '유행어', '병맛', 'meme')
    total = sum(weight.get(c, 0) for c in analyzed)
    if not total:
        return None
    hit = 0
    for cid, d in analyzed.items():
        hay = ' '.join(str(t) for t in d.get('tags', [])) + ' ' + str(d.get('title', ''))
        if any(w in hay for w in words):
            hit += weight.get(cid, 0)
    return round(hit / total * 100, 1)


KPI_RULES = [
    # (필수 조각들, 금지 조각들, 값 만드는 함수)
    (['텍스트 포함'], [], text_share),
    (['정지형'], ['텍스트', '밈', '표준어'], lambda a, r: type_share(a, r, '정지형')),
    (['시리즈'], [], lambda a, r: series_share(a, r)),
    (['파스텔'], [], lambda a, r: style_share(a, r, '파스텔')),
    (['애니메이션'], ['텍스트', '밈', '표준어'], lambda a, r: type_share(a, r, '애니메이션')),
    (['움직이는'], ['텍스트', '밈', '표준어'], lambda a, r: type_share(a, r, '애니메이션')),
]


# 유형(정지형/애니) 카드는 판매 수로, 나머지는 매출액으로 잰다
_COUNT_CARDS = ('정지형', '애니메이션', '움직이는')


def kpi_value(label, analyzed, revenue, counts=None):
    """카드 설명 문구 → 값. 짝이 없으면 None (그 카드는 손대지 않는다)."""
    for need, avoid, fn in KPI_RULES:
        if all(w in label for w in need) and not any(w in label for w in avoid):
            use = counts if (counts and any(k in label for k in _COUNT_CARDS)) else revenue
            return fn(analyzed, use)
    return None


def type_share(analyzed, revenue, label):
    """특정 콘텐츠 유형(정지형/애니메이션)의 매출 비중."""
    total = sum(revenue.get(c, 0) for c, d in analyzed.items() if d.get('stats'))
    hit = sum(revenue.get(c, 0) for c, d in analyzed.items()
              if d.get('stats') and content_type(d['stats']) == label)
    return round(hit / total * 100, 1) if total else 0.0
