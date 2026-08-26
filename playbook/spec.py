# -*- coding: utf-8 -*-
"""템플릿 슬라이드 ↔ 지표 연결 규칙.

덱 구조가 규칙적이라(마켓별 6장 세트가 3번 반복) 슬라이드 번호를 하드코딩하지 않고
섹션 표지 위치에서 상대 번호로 잡는다. 표지 슬라이드가 밀려도 SECTION만 고치면 된다.
"""

# 마켓별 섹션 표지 슬라이드 번호(1-base). 본문은 표지 +1 ~ +6
SECTION = {'NOM': 11, 'SOM': 18, 'COM': 25}
SUB = {'explore': 1, 'top25': 2, 'topic': 3, 'compose': 4, 'launch': 5, 'summary': 6}

# 마켓별 구매자 세부 분석 슬라이드
INSIGHT_DETAIL = {'NOM': 8, 'SOM': 9, 'COM': 10}
INSIGHT_SUMMARY = 7          # 3열 인사이트 요약
REJECT_STATUS = 36           # 반려 현황
REJECT_ACTION = 37           # 반려 대응


def slide_of(market, role):
    return SECTION[market] + SUB[role]


# ---------------------------------------------------------------- 차트
# kind='hour'  : 0~23시 막대 24개 + 최저/최고 콜아웃 + 집중구간 문구
# kind='weekday': 월~일 막대 7개 + 값 라벨 7개 + 평일/주말 문구
CHARTS = [
    dict(kind='hour',    market=m, slide=slide_of(m, 'launch')) for m in ('NOM', 'SOM')
] + [
    dict(kind='weekday', market=m, slide=slide_of(m, 'launch')) for m in ('NOM', 'SOM')
]
# COM 출시·홍보(30장)는 '시간보다 시즌' 레이아웃이라 시간/요일 차트가 없다.

# ---------------------------------------------------------------- 정지형/애니 비율 막대
# 폭이 곧 비중인 가로 띠. 글자와 폭을 함께 갱신해야 한다.
CTYPE_BARS = [dict(market=m, slide=INSIGHT_DETAIL[m]) for m in ('NOM', 'SOM', 'COM')]

# ---------------------------------------------------------------- 시즌 캘린더
# 마켓별 '출시 및 홍보 전략' 슬라이드 하단의 월 카드 4장
SEASON = [dict(market=m, slide=slide_of(m, 'launch')) for m in ('NOM', 'SOM', 'COM')]

# ---------------------------------------------------------------- 키워드
KEYWORDS = [dict(market=m, slide=INSIGHT_DETAIL[m], count=8) for m in ('NOM', 'SOM', 'COM')]

# ---------------------------------------------------------------- 반려
REJECT_BARS = dict(slide=REJECT_STATUS)   # 사유별 가로 막대 + %

# ---------------------------------------------------------------- 사람이 정해야 하는 것
# 매출 데이터에서 나오지 않는 값들. run.py가 실행 때마다 목록으로 알려준다.
MANUAL = {
    'top25_tagging': dict(
        slides=[slide_of(m, 'top25') for m in ('NOM', 'SOM', 'COM')],
        what='TOP25 콘텐츠 속성 태깅(텍스트 비중·텍스트 종류·기반 분류·상세 성격·색상 스타일)과 '
             '유형별 매출 비중 라벨. 콘텐츠를 눈으로 보고 분류하는 값이라 거래 데이터에 없음.'),
    'guides': dict(
        slides=[33, 34, 35],
        what='제작·등록 가이드. 규격 문서라 데이터와 무관 — 규격이 바뀔 때만 수정.'),
    'company': dict(
        slides=[4, 5],
        what='OGQ 소개·마켓 소개. 마켓이 추가/변경될 때만 수정.'),
}


# ---------------------------------------------------------------- 낱개 수치
# (슬라이드, 도형ID, 새 텍스트 서식) — 도형ID는 템플릿에서 고정이다.
# 서식 안의 {키}는 metrics.py가 만든 지표 키.
TEXT_BINDINGS = [
    (7,  19, '{nom.theme.by_name.블로그/포스팅 실용.pct:g}%'),
    (7,  31, '{som.ctype.anim_BASIS_pct:.0f}%'),
    # 8·9·10장의 '정지형 94%' 같은 글자는 CTYPE_BARS가 막대 폭과 함께 처리한다.
    # (여기서 글자만 바꾸면 폭이 안 따라가서 그림이 값과 어긋난다)
    # 상반기엔 설날(2월)이 성수기라 옛 '2월/1월' 값과 같은 3.2배가 나온다.
    # 하반기엔 2월이 아예 없으므로 성수기/비수기로 일반화해 둔다.
    (7,  43, '{com.month.peak_vs_low_x:.1f}배'),
]

# 덱 전체에서 기간 표기를 갈아 끼운다
PERIOD_PATTERNS = [
    (r'(\d{4})년\s*(상반기|하반기)', '{year}년 {half}'),
    (r'(\d{4})\s*(상반기|하반기)', '{year} {half}'),
]
