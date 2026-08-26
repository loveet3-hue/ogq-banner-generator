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


# ---------------------------------------------------------------- 태그 기준
# 앞에 있는 항목이 이긴다. 태그가 하나도 안 걸리면 마지막 '기본값'.
TAG_RULES = {
    '기반 분류': [
        ('손글씨·문구', ['손글씨', '캘리', '글씨', '문구', '레터링', '타이포', '폰트']),
        ('동물', ['강아지', '고양이', '햄스터', '토끼', '곰', '동물', '펭귄', '오리',
                 '여우', '병아리', '댕댕', '냥이', '멍멍', '햄스', '너구리', '판다',
                 '다람쥐', '돼지', '코알라', '수달', '알파카']),
        ('사람', ['사람', '인간', '소녀', '소년', '여자', '남자', '아기', '직장인',
                 '학생', '아저씨', '아줌마', '커플']),
        ('사물·음식', ['음식', '빵', '커피', '케이크', '과일', '음료', '떡', '디저트',
                     '사물', '꽃', '식물']),
        ('추상적 캐릭터', []),          # 기본값
    ],
    '콘텐츠 도메인': [
        ('블로그', ['블로그', '블로거', '블꾸', '포스팅', '리뷰', '후기', '맛집',
                  '내돈내산', '일기', '기록', '체험단', '공정위']),
        ('방송·게임', ['방송', '스트리머', '시청자', '채팅', '리액션', '게임', '롤',
                    '배그', '스타', '종겜', '트위치', '아프리카', 'soop', '숲']),
        ('시즌·기념일', ['설날', '명절', '추석', '크리스마스', '새해', '생일',
                     '기념일', '연말', '할로윈', '발렌타인']),
        ('연애', ['연애', '사랑', '커플', '고백', '애정', '썸']),
        ('사회생활', ['사회생활', '존댓말', '직장', '회사', '업무', '비즈니스', '공손']),
        ('일상', []),
    ],
    '상세 성격': [
        ('개그·병맛', ['병맛', '밈', '짤', '유행어', '웃긴', '개그', '하찮', '잔망',
                    '드립', '어이없', '황당']),
        ('공손·정중', ['공손', '존댓말', '상냥', '친절', '착한', '정중', '예의', '바른']),
        ('감성·힐링', ['감성', '힐링', '위로', '따뜻', '잔잔', '차분', '평온']),
        ('활기찬', ['활기', '발랄', '신나', '텐션', '에너지', '파이팅']),
        ('귀여운', ['귀여운', '귀요미', '깜찍', '사랑스러운', '말랑', '몽글', '보들']),
        ('귀여운', []),
    ],
    '사용 맥락': [
        ('방송 리액션', ['리액션', '반응', '방송', '채팅', '시청자', '스트리머']),
        ('리뷰·기록', ['리뷰', '후기', '맛집', '일기', '기록', '포스팅', '내돈내산']),
        ('인사·안부', ['인사', '안부', '감사', '축하', '응원', '덕담', '위로']),
        ('공감', ['공감', '감정', '일상', '하루', '기분']),
        ('공감', []),
    ],
}


def by_tags(attr, tags, title=''):
    """태그(+제목)로 분류.

    가장 먼저 걸린 규칙을 쓰지 않고 **몇 개나 걸렸는지 세어** 가장 많이 걸린 쪽을
    고른다. 콘텐츠 하나에 태그가 대여섯 개씩 붙어 있어서, 첫 매칭만 보면
    '일상·블로거·리뷰·포스팅'이 달린 콘텐츠가 규칙 순서에 따라 엉뚱하게 갈린다.
    동점이면 규칙에 적힌 순서가 이긴다.
    """
    hay = (' '.join(str(t) for t in tags) + ' ' + str(title)).lower()
    rules = TAG_RULES[attr]
    best, best_score = None, 0
    for label, words in rules:
        if not words:
            continue
        score = sum(1 for w in words if w.lower() in hay)
        if score > best_score:
            best, best_score = label, score
    return best or rules[-1][0]


# ---------------------------------------------------------------- 집계
# 표의 어느 줄을 우리가 채우고, 어느 줄은 손대지 않는지
COMPUTED_ROWS = {
    '콘텐츠 유형': lambda d: content_type(d['stats']),
    '기반 분류': lambda d: by_tags('기반 분류', d['tags'], d['title']),
    '콘텐츠 도메인': lambda d: by_tags('콘텐츠 도메인', d['tags'], d['title']),
    '상세 성격': lambda d: by_tags('상세 성격', d['tags'], d['title']),
    '색상 스타일': lambda d: color_style(d['stats']),
    '배경 유형': lambda d: background(d['stats']),
    '사용 맥락': lambda d: by_tags('사용 맥락', d['tags'], d['title']),
}

# 그림을 봐야 알 수 있어 손대지 않는 줄
VISION_ROWS = ['텍스트 비중', '텍스트 종류', '라인 스타일']


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
