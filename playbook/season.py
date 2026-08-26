# -*- coding: utf-8 -*-
"""다음 기간의 시즌 캘린더를 만든다 (16·23·30장).

설날·추석은 음력이라 해마다 날짜가 바뀐다. 손으로 적으면 반기마다 틀리므로
음력 계산으로 뽑고, 수능은 '11월 셋째 목요일' 규칙으로 구한다.
월별 이벤트와 마켓별 추천 주제는 아래 표를 고치면 된다 — 데이터에서 나오는 값이 아니라
'그 달에 무슨 일이 있는가'라는 달력 지식이다.
"""
import calendar as _cal
import datetime as dt

# 캘린더에 넣을 달: 데이터가 끝난 달 + 이만큼 뒤부터 4개월.
# 자료를 만들어 배포하고, 크리에이터가 제작·심사까지 마치려면 두세 달이 필요하다.
# (v2 덱도 상반기 데이터로 9~12월을 안내했다)
LEAD_MONTHS = 3
CARD_COUNT = 4

# 월마다 늘 있는 일. {날짜}는 그 해 실제 날짜로 채워진다.
MONTH_EVENTS = {
    1:  ['새해 인사', '신정', '겨울방학'],
    2:  ['{설날}', '발렌타인데이', '졸업 시즌'],
    3:  ['새 학기', '화이트데이', '봄 시작'],
    4:  ['벚꽃 · 봄 나들이', '만우절', '중간고사'],
    5:  ['어린이날', '어버이날', '스승의 날', '가정의 달'],
    6:  ['여름 시작', '현충일', '장마 준비'],
    7:  ['여름휴가', '방학 시작', '장마'],
    8:  ['휴가 절정', '광복절', '늦더위'],
    9:  ['{추석}', '개학', '가을 시작'],
    10: ['개천절 · 한글날', '단풍 나들이', '할로윈'],
    11: ['{수능}', '빼빼로데이', '블랙 프라이데이'],
    12: ['크리스마스', '연말 결산', '송년 인사'],
}

# SOOP은 e스포츠 일정이 곧 시즌이다. 다만 LCK 결승·롤드컵 날짜는 해마다 달라지고
# 미리 알 수 없으므로, 날짜 없이 '언제쯤 무엇이 있다'만 적는다.
# 확정 일정이 나오면 여기 손으로 날짜를 넣으면 된다.
MARKET_EVENTS = {
    'SOM': {
        1:  ['새해 방송', 'LCK 스프링 개막', '겨울 이벤트'],
        2:  ['{설날}', 'LCK 스프링 정규시즌', '발렌타인 방송'],
        3:  ['새 학기', 'LCK 스프링 플레이오프', '봄 이벤트'],
        4:  ['LCK 스프링 결승', 'MSI 예선', '봄 나들이 방송'],
        5:  ['MSI', '어린이날·가정의 달', 'LCK 서머 개막'],
        6:  ['LCK 서머 정규시즌', '여름 이벤트', '시험 응원'],
        7:  ['여름휴가 방송', 'LCK 서머 정규시즌', '방학 시청 증가'],
        8:  ['LCK 서머 플레이오프', '휴가 절정', '롤드컵 선발전'],
        9:  ['{추석}', 'LCK 서머 결승', '롤드컵 시즌'],
        10: ['롤드컵 본선', '할로윈 방송', '가을 신규 방송'],
        11: ['롤드컵 결승', '{수능}', '빼빼로데이'],
        12: ['스트리머 대상 시상식', '크리스마스 방송', '연말 결산'],
    },
}


# 마켓마다 같은 달을 다른 각도로 쓴다.
# NOM=블로그에 쓰는 도구 / SOM=방송 리액션 / COM=문자로 보내는 인사
MARKET_TOPICS = {
    'NOM': {
        1:  ['새해 계획 기록', '겨울 일상', '신년 목표'],
        2:  ['명절 인사', '졸업·입학 기록', '발렌타인 리뷰'],
        3:  ['새 학기 준비', '봄 감성', '벚꽃 예고'],
        4:  ['나들이 후기', '벚꽃 리뷰', '봄 맛집'],
        5:  ['가정의 달 기록', '선물 리뷰', '나들이 일상'],
        6:  ['여름 준비', '장마 일상', '카페 리뷰'],
        7:  ['휴가 계획', '여행 리뷰', '여름 맛집'],
        8:  ['휴가 후기', '늦더위 일상', '가을 예고'],
        9:  ['명절 인사', '여행 리뷰', '가을 감성'],
        10: ['나들이 상황', '축제 후기', '할로윈 리액션'],
        11: ['응원 문구', '쇼핑 리뷰', '내돈내산'],
        12: ['감사·송년 인사', '회고 문구', '새해 계획'],
    },
    'SOM': {
        1:  ['새해 인사 리액션', '겨울 드립', '목표 선언'],
        2:  ['명절 리액션', '고백 드립', '졸업 축하'],
        3:  ['새 학기 드립', '봄 리액션', '화이트데이'],
        4:  ['나들이 리액션', '만우절 드립', '시험 응원'],
        5:  ['가정의 달 인사', '선물 리액션', '나들이'],
        6:  ['더위 리액션', '장마 드립', '시험 응원'],
        7:  ['휴가 리액션', '더위 드립', '방학 텐션'],
        8:  ['휴가 자랑', '늦더위 드립', '복귀 인사'],
        9:  ['명절 리액션', '가을 인사', '개학 드립'],
        10: ['할로윈 리액션', '단풍 드립', '축제 텐션'],
        11: ['수능 응원', '빼빼로 드립', '첫눈 리액션'],
        12: ['크리스마스 텐션', '연말 결산', '송년 인사'],
    },
    'COM': {
        1:  ['새해 인사', '건강 안부', '덕담'],
        2:  ['명절 인사', '감사 인사', '고백·응원'],
        3:  ['새 학기 응원', '봄 안부', '감사'],
        4:  ['안부 인사', '나들이 인사', '응원'],
        5:  ['어버이날 감사', '스승의 날 인사', '가정의 달 안부'],
        6:  ['건강 안부', '더위 인사', '응원'],
        7:  ['휴가 인사', '건강 안부', '더위 인사'],
        8:  ['휴가 안부', '광복절 인사', '가을 안부'],
        9:  ['명절 인사', '건강 안부', '감사'],
        10: ['가을 안부', '나들이 인사', '할로윈 인사'],
        11: ['수능 응원', '고백·선물', '날씨 안부'],
        12: ['크리스마스 인사', '연말 감사', '새해 인사'],
    },
}


def _lunar_to_solar(year, lmonth, lday):
    """음력 → 양력. 라이브러리가 없으면 None (호출한 쪽이 이벤트를 건너뛴다)."""
    try:
        from korean_lunar_calendar import KoreanLunarCalendar
    except ImportError:
        return None
    c = KoreanLunarCalendar()
    if not c.setLunarDate(year, lmonth, lday, False):
        return None
    iso = c.SolarIsoFormat()
    return dt.date.fromisoformat(iso) if iso else None


def seollal(year):
    return _lunar_to_solar(year, 1, 1)


def chuseok(year):
    return _lunar_to_solar(year, 8, 15)


def suneung(year):
    """수능 = 11월 셋째 목요일."""
    thursdays = [d for d in range(1, 31)
                 if dt.date(year, 11, d).weekday() == 3]
    return dt.date(year, 11, thursdays[2])


def _holiday_span(day):
    """명절 연휴 = 당일 앞뒤 하루."""
    a, b = day - dt.timedelta(days=1), day + dt.timedelta(days=1)
    if a.month == b.month:
        return f'{a.month}/{a.day}~{b.day}'
    return f'{a.month}/{a.day}~{b.month}/{b.day}'


def events_for(year, month, market=None):
    """그 달의 이벤트 문구 목록. 날짜가 필요한 것은 실제 날짜를 넣는다."""
    table = MARKET_EVENTS.get(market, MONTH_EVENTS)
    out = []
    for e in table[month]:
        if e == '{설날}':
            d = seollal(year)
            out.append(f'설날 연휴({_holiday_span(d)})' if d else '설날 연휴')
        elif e == '{추석}':
            d = chuseok(year)
            out.append(f'추석 연휴({_holiday_span(d)})' if d else '추석 연휴')
        elif e == '{수능}':
            d = suneung(year)
            out.append(f'수능({d.month}/{d.day})')
        else:
            out.append(e)
    return out


def register_hint(year, month):
    """등록 권장 시점. 슬라이드에 적힌 '6~8주 전'을 달 표기로 옮긴 것."""
    y, m = (year - 1, 12) if month == 1 else (year, month - 1)
    return f'{m}월 초 등록'


def cards(end_year, end_month, market, count=CARD_COUNT, lead=LEAD_MONTHS):
    """데이터가 끝난 달을 기준으로 앞으로 안내할 달 카드를 만든다.

    → [{'month': '9월', 'register': '8월 초 등록',
        'events': '추석 연휴(9/24~26) · 개학 · 가을 시작',
        'topics': '→ 명절 인사 · 여행 리뷰 · 가을 감성'}, ...]
    """
    topics = MARKET_TOPICS.get(market, MARKET_TOPICS['NOM'])
    out = []
    for i in range(count):
        idx = (end_month - 1) + lead + i
        y, m = end_year + idx // 12, idx % 12 + 1
        out.append({
            'year': y,
            'month_num': m,
            'month': f'{m}월',
            'register': register_hint(y, m),
            'events': ' · '.join(events_for(y, m, market)),
            'topics': '→ ' + ' · '.join(topics[m]),
        })
    return out


def span_label(cards_):
    """'2026 9~12월' 처럼 캘린더가 덮는 구간 표기."""
    if not cards_:
        return ''
    a, b = cards_[0], cards_[-1]
    if a['year'] == b['year']:
        return f'{a["year"]} {a["month_num"]}~{b["month_num"]}월'
    return f'{a["year"]}년 {a["month_num"]}월~{b["year"]}년 {b["month_num"]}월'
