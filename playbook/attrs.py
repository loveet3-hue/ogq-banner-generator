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

import re

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
# 크리에이터가 마켓에 단 태그로 가른다. 사람이 눈으로 보고 매긴 것과는 다를 수
# 있는 근사치다 — 정확한 값이 아니라 '대략 이 정도'로 읽어야 한다.
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
# 선 굵기: 어두운 윤곽을 한 겹 깎았을 때 남는 비율. TOP25 74종 실측 중앙값이
# 0.59~0.70이라 0.5를 경계로 둔다.
THICK_LINE_MIN = 0.50


def line_style(st):
    v = st.get('stroke')
    if v is None:
        return None
    return '굵은 선' if v >= THICK_LINE_MIN else '가는 선'


# 초성만 쓰거나(ㅋㅋ, ㅇㅈ) 자모만 남은 말은 신조어·초성체로 본다
_JAMO = re.compile(r'^[ㄱ-ㅎㅏ-ㅣ]+$')
_INTERJECTION = ('헐', '헉', '와', '우와', '오', '앗', '악', '음', '흠', '아', '어',
                 '히히', '헤헤', '하하', '후후', '엥', '웅', '응', '넹', '뿅', '쨘',
                 '대박', '와우', '어머', '아이고', '에휴', '쳇', '흥')
_SLANG = ('ㅋ', 'ㅎ', 'ㅇㅈ', 'ㄱㅅ', 'ㅅㄱ', 'ㅈㅅ', '갑분', '억까', '존버', '낫닝겐',
          '개꿀', '핵', '띵', '어쩔', '킹받', '지린', '알잘딱', '스불재', '오히려좋아')


def text_kind(d):
    """읽힌 글자를 보고 말투를 가른다. OCR을 못 썼으면 None."""
    words = d.get('texts')
    if not words:
        return None
    kinds = {'표준어': 0, '감탄사·의성어': 0, '신조어·초성체': 0}
    for w in words:
        t = str(w).strip()
        if not t:
            continue
        if _JAMO.match(t) or any(k in t for k in _SLANG):
            kinds['신조어·초성체'] += 1
        elif len(t) <= 4 and any(t.startswith(k) for k in _INTERJECTION):
            kinds['감탄사·의성어'] += 1
        else:
            kinds['표준어'] += 1
    return max(kinds.items(), key=lambda kv: kv[1])[0] if any(kinds.values()) else None


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
    '텍스트 종류': lambda d: text_kind(d),
    '기반 분류': lambda d: by_tags('기반 분류', d['tags'], d['title']),
    '콘텐츠 도메인': lambda d: by_tags('콘텐츠 도메인', d['tags'], d['title']),
    '상세 성격': lambda d: by_tags('상세 성격', d['tags'], d['title']),
    '색상 스타일': lambda d: color_style(d['stats']),
    '라인 스타일': lambda d: line_style(d['stats']),
    '사용 맥락': lambda d: by_tags('사용 맥락', d['tags'], d['title']),
}

# 자동으로 채우지도, 지우지도 않고 손대지 않는 줄.
#
# '배경 유형': OGQ가 투명 PNG를 필수로 요구해서 재면 거의 언제나 '투명 100%'가
# 나온다. 재는 것 자체는 되지만 갈라 주는 게 없어 쓸모가 없고, 사람이 눈으로
# 골라 넣은 값(97.5% / 2.5%)을 덮어쓰기만 한다. 그래서 템플릿 값을 그대로 둔다.
# 표에서 자동으로 채우지 않는 줄.
#
# 이미지 분류기가 내놓는 값이 v2 최종본(사람이 25종을 눈으로 보고 정리한 표)과
# 분류 체계부터 다르다. 예를 들어 최종본은 '감탄사·의성어 / 짧은 대사·문장',
# '동물 의인화', '캐릭터 리액션'처럼 나누는데 분류기는 '표준어 / 동물 / 방송·게임'
# 으로 뭉갠다. 값도 크게 어긋난다(NOM 기반 분류: 최종본 추상적 캐릭터 52.6%,
# 분류기 동물 36.2%). 덮어쓰면 잘 만들어 둔 표가 나빠지므로 손대지 않는다.
#
# 분류기 추정치는 버리지 않고 변경내역에 '참고값'으로 남긴다. 사람이 새 판을
# 채울 때 출발점으로 쓰라는 뜻이다.
#
# AUTO_ROWS 를 늘리면 그만큼 자동으로 채운다. 근거가 생기면 옮길 것.
AUTO_ROWS = {'콘텐츠 유형'}
CURATED_ROWS = {'텍스트 비중', '텍스트 종류', '기반 분류', '콘텐츠 도메인',
                '상세 성격', '색상 스타일', '라인 스타일', '배경 유형', '사용 맥락'}
KEEP_ROWS = CURATED_ROWS


def classify(analyzed, weight, count_weight=None):
    """→ {속성: [(값, 비중%), ...] 내림차순}

    analyzed:     {콘텐츠ID: {'title','tags','stats'}}
    weight:       매출액 무게 — 표 머리글이 '매출 비중'이므로 모든 줄이 이걸 쓴다
    count_weight: (더 이상 쓰지 않음) 예전에는 '콘텐츠 유형' 줄만 판매 수로 쟀는데,
                  그러면 머리글 '매출 비중'과 그 줄만 기준이 달라져 표 안에서
                  잣대가 섞였다. v2 최종본도 매출 기준이라 매출로 통일한다.
    """
    revenue = weight
    total = sum(revenue.get(cid, 0) for cid, d in analyzed.items() if d.get('stats'))
    if total <= 0:
        return {}, 0
    counts = count_weight or revenue
    ctotal = sum(counts.get(cid, 0) for cid, d in analyzed.items() if d.get('stats'))
    out = {}
    for attr, fn in COMPUTED_ROWS.items():
        w, wtot = revenue, total
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


def standard_share(analyzed, weight):
    """말투가 '표준어'로 읽힌 콘텐츠의 비중."""
    got = {c: d for c, d in analyzed.items() if d.get('texts')}
    total = sum(weight.get(c, 0) for c in got)
    if not total:
        return None
    hit = sum(weight.get(c, 0) for c, d in got.items() if text_kind(d) == '표준어')
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
    (['밈'], [], meme_share),
    (['표준어'], [], standard_share),
    (['정지형'], ['텍스트', '밈', '표준어'], lambda a, r: type_share(a, r, '정지형')),
    (['시리즈'], [], lambda a, r: series_share(a, r)),
    (['파스텔'], [], lambda a, r: style_share(a, r, '파스텔')),
    (['애니메이션'], ['텍스트', '밈', '표준어'], lambda a, r: type_share(a, r, '애니메이션')),
    (['움직이는'], ['텍스트', '밈', '표준어'], lambda a, r: type_share(a, r, '애니메이션')),
]


def basis_of(label, revenue, counts=None, uniform=None):
    """카드 설명 문구가 스스로 밝힌 잣대를 따른다.

    덱은 카드마다 기준을 글로 적어 둔다 — '매출 비중', '(이모티콘 수 기준)',
    '판매 수 비중'. 코드가 기준을 따로 정해 두면 문구와 숫자가 어긋나므로
    (v2 최종본에서 실제로 어긋났다) 문구를 읽어서 무게를 고른다.

    반환: (무게 dict, 기준 이름)
    """
    if re.search(r'(이모티콘|콘텐츠|스티커)\s*수\s*기준', label) or '종수' in label:
        return (uniform if uniform else revenue), '콘텐츠 수'
    if '판매 수' in label:
        return (counts if counts else revenue), '판매 수'
    return revenue, '매출액'


def kpi_value(label, analyzed, revenue, counts=None, uniform=None):
    """카드 설명 문구 → 값. 짝이 없으면 None (그 카드는 손대지 않는다)."""
    for need, avoid, fn in KPI_RULES:
        if all(w in label for w in need) and not any(w in label for w in avoid):
            use, _ = basis_of(label, revenue, counts, uniform)
            return fn(analyzed, use)
    return None


def type_share(analyzed, revenue, label):
    """특정 콘텐츠 유형(정지형/애니메이션)의 매출 비중."""
    total = sum(revenue.get(c, 0) for c, d in analyzed.items() if d.get('stats'))
    hit = sum(revenue.get(c, 0) for c, d in analyzed.items()
              if d.get('stats') and content_type(d['stats']) == label)
    return round(hit / total * 100, 1) if total else 0.0
