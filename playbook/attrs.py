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
# 실제 이미지에서 재는 것만 채운다.
COMPUTED_ROWS = {
    '콘텐츠 유형': lambda d: content_type(d['stats']),
    '색상 스타일': lambda d: color_style(d['stats']),
    '배경 유형': lambda d: background(d['stats']),
}


def classify(analyzed, revenue):
    """→ {속성: [(값, 매출비중%), ...] 내림차순}

    analyzed: {콘텐츠ID: {'title','tags','stats'}}
    revenue:  {콘텐츠ID: 매출}
    """
    total = sum(revenue.get(cid, 0) for cid, d in analyzed.items() if d.get('stats'))
    if total <= 0:
        return {}, 0
    out = {}
    for attr, fn in COMPUTED_ROWS.items():
        agg = {}
        for cid, d in analyzed.items():
            if not d.get('stats'):
                continue
            try:
                label = fn(d)
            except Exception:
                continue
            agg[label] = agg.get(label, 0) + revenue.get(cid, 0)
        ranked = sorted(agg.items(), key=lambda kv: -kv[1])
        out[attr] = [(k, round(v / total * 100, 1)) for k, v in ranked]
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


def type_count_share(analyzed, label):
    """콘텐츠 '수' 기준 유형 비중 (27장 카드가 이 기준이다)."""
    got = [d for d in analyzed.values() if d.get('stats')]
    if not got:
        return 0.0
    hit = sum(1 for d in got if content_type(d['stats']) == label)
    return round(hit / len(got) * 100, 1)


def kpi_labels(analyzed, revenue):
    """카드 설명 문구 → 값. 문구에 이 조각이 들어 있으면 그 값을 쓴다."""
    return {
        '정지형 스티커(이모티콘) 매출 비중': type_share(analyzed, revenue, '정지형'),
        '애니메이션 스티커 매출 비중': type_share(analyzed, revenue, '애니메이션'),
        '움직이는(GIF) 이모티콘 비중': type_count_share(analyzed, '애니메이션'),
        '시리즈(넘버링) 콘텐츠 매출': series_share(analyzed, revenue),
        '파스텔 톤 매출 비중': style_share(analyzed, revenue, '파스텔'),
    }


def type_share(analyzed, revenue, label):
    """특정 콘텐츠 유형(정지형/애니메이션)의 매출 비중."""
    total = sum(revenue.get(c, 0) for c, d in analyzed.items() if d.get('stats'))
    hit = sum(revenue.get(c, 0) for c, d in analyzed.items()
              if d.get('stats') and content_type(d['stats']) == label)
    return round(hit / total * 100, 1) if total else 0.0
