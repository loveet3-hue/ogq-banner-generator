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
# 9장(SOOP 유형 선호도)은 은택님 요청으로 그대로 둔다.
CTYPE_SKIP = {INSIGHT_DETAIL['SOM']}
CTYPE_BARS = [dict(market=m, slide=INSIGHT_DETAIL[m]) for m in ('NOM', 'SOM', 'COM')
              if INSIGHT_DETAIL[m] not in CTYPE_SKIP]

# ---------------------------------------------------------------- TOP25 속성
# 콘텐츠ID로 OGQ마켓을 조회해 실제 콘텐츠를 보고 채운다
TOP25 = [dict(market=m, slide=slide_of(m, 'top25')) for m in ('NOM', 'SOM', 'COM')]

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
    'top25_vision': dict(
        slides=[slide_of(m, 'top25') for m in ('NOM', 'SOM', 'COM')],
        what='TOP25 속성 표에서 콘텐츠 유형 줄만 자동입니다. 나머지 아홉 줄(텍스트 비중·텍스트 '
             '종류·기반 분류·콘텐츠 도메인·상세 성격·색상 스타일·라인 스타일·배경 유형·사용 맥락)과 '
             '왼쪽 유형별 매출 비중 막대는 25종을 눈으로 보고 직접 채워 주세요. '
             '분류기 추정치는 변경내역 맨 아래 "참고값"에 적어 두었습니다.'),
    'guides': dict(
        slides=[33, 34, 35],
        what='제작·등록 가이드. 규격 문서라 데이터와 무관 — 규격이 바뀔 때만 수정.'),
    'company': dict(
        slides=[4, 5],
        what='OGQ 소개·마켓 소개. 마켓이 추가/변경될 때만 수정.'),
}


# ---------------------------------------------------------------- 낱개 수치
# 도형ID가 아니라 '설명줄에 적힌 글자'로 자리를 찾는다. 템플릿을 다시 내보내면
# 도형ID가 전부 바뀌어(2~14 → 2302~2306) ID로 잡아 둔 건 통째로 깨진다.
#   anchor  : 템플릿에 적혀 있는 설명줄의 한 조각 (이걸로 카드를 찾는다)
#   value   : 그 카드의 큰 수치에 넣을 서식
#   caption : 설명줄 자체를 바꿀 때만. 없으면 그대로 둔다.
STAT_CARDS = [
    dict(slide=INSIGHT_SUMMARY, anchor='블로그·포스팅 실용 테마',
         value='{nom.theme.by_name.블로그/포스팅 실용.pct:g}%'),
    dict(slide=INSIGHT_SUMMARY, anchor='움직이는 이모티콘 선호',
         value='{som.ctype.anim_BASIS_pct:.0f}%'),
    dict(slide=INSIGHT_SUMMARY, anchor='설날 시즌',
         value='{com.month.peak_vs_low_x:.1f}배'),
]

# 덱 전체에서 기간 표기를 갈아 끼운다
PERIOD_PATTERNS = [
    (r'(\d{4})년\s*(상반기|하반기)', '{year}년 {half}'),
    (r'(\d{4})\s*(상반기|하반기)', '{year} {half}'),
]


# ---------------------------------------------------------------- 기준이 바뀐 설명줄
# 문구는 원본을 지키는 게 원칙이지만, '콘텐츠 수 기준'이라고 적힌 카드에 매출 기준
# 값을 넣으면 글자가 거짓말이 된다. 기준을 바꾼 자리만 문구도 함께 고친다.
BASIS_CAPTIONS = [
    # 유형 비중(정지형/애니)은 판매 수로 재기로 했으므로, '매출 비중'이라고 적힌
    # 설명은 그대로 두면 글자가 거짓말이 된다. 기준을 바꾼 자리만 문구도 고친다.
    dict(slide=slide_of('NOM', 'top25'), anchor='정지형 스티커(이모티콘) 매출 비중',
         text='정지형 스티커(이모티콘) 판매 수 비중'),
    dict(slide=slide_of('SOM', 'top25'), anchor='움직이는 이모티콘 매출 비중',
         text='움직이는 이모티콘 판매 수 비중'),
    dict(slide=slide_of('COM', 'top25'), anchor='콘텐츠 수 기준',
         text='움직이는(GIF) 이모티콘 판매 수 비중'),
    # 설명에 '신조어는 10%뿐'처럼 지난 판 숫자가 박혀 있으면 값과 어긋난다
    dict(slide=slide_of('COM', 'top25'), anchor='신조어는', text='표준어 비중'),
    # 표에서 '콘텐츠 유형' 줄만 판매 수, 나머지는 매출액이라 열 이름을 중립으로
    dict(slide=slide_of('NOM', 'top25'), anchor='상위 콘텐츠 속성별 데이터',
         text='상위 콘텐츠 속성별 데이터 (유형=판매 수 · 그 외=매출액)'),
    dict(slide=slide_of('SOM', 'top25'), anchor='상위 콘텐츠 속성별 데이터',
         text='상위 콘텐츠 속성별 데이터 (유형=판매 수 · 그 외=매출액)'),
    dict(slide=slide_of('COM', 'top25'), anchor='상위 콘텐츠 속성별 데이터',
         text='상위 콘텐츠 속성별 데이터 (유형=판매 수 · 그 외=매출액)'),
]

