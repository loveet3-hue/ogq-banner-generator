# -*- coding: utf-8 -*-
"""정규화된 거래 데이터 → 플레이북에 들어가는 모든 파생 수치(flat dict).

키 규칙:  <market>.<metric>[.<sub>]      예) nom.ctype.sticker_cnt_pct
공통 키:  all.<metric>

*** 배포 원칙 ***
여기서 나오는 값은 전부 비율(%)·배수·지수·순위다. 절대 매출액·건수·구매자 수는
크리에이터 배포용 덱에 넣지 않는다(qa.py가 검사). 절대 수치가 필요한 내부용
데이터시트는 raw_* 키로 따로 뽑는다.
"""
import re
from collections import Counter
import numpy as np
import pandas as pd

ANIM = '애니메이션 스티커'
STILL = '스티커'
WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']

# 콘텐츠명 기반 테마 분류 — 반기마다 유행이 바뀌면 여기만 손보면 된다
THEMES = {
    '블로그/포스팅 실용': r'블로그|블꾸|포스팅|공정위|구분선|리뷰|맛집|여행|템플릿|타이틀|말풍선|카테고리|꾸미기',
    '동물 캐릭터': r'고양이|강아지|냥|댕|토끼|곰|햄|펭귄|오리|여우|동물|쥐|병아리',
    '움직임/리액션': r'움직이|움티|움짤|리액션|반응|춤|댄스|표정|확대',
    '일상/인사': r'일상|인사|안부|하루|출근|직장|기록',
    '감정/공감': r'공감|감정|사랑|행복|위로|감사',
    '설날/명절/새해': r'설날|명절|새해|연말|한가위|추석|세뱃',
    '손글씨/캘리': r'손글씨|캘리|글씨|글귀|메시지|말말|자막|폰트',
    '밈/유머': r'밈|유행어|병맛|잔망|하찮|짤',
}

# 키워드 추출에서 걸러낼 말들.
# (1) 어디에나 붙는 일반어  (2) 상품 자체를 가리키는 말 — '스티커'가 1위로 뽑히면 의미가 없다
# (3) 버전·시리즈 표기.  조사는 떼지 않는다 — '움직이는'을 '움직이'로 자르면 말이 안 된다.
_STOP = set("""
그리고 그런 하는 있는 해요 해서 하고 위한 대한 너무 정말 완전 그냥 오늘 이제 우리 당신
스티커 이모티콘 움티 콘텐츠 세트 이미지 파일 버전 시즌 에디션 시리즈 모음
ver version vol no the and for with new
""".split())

# 크리에이터 배포용 — 한 크리에이터에게 쏠린 단어는 키워드로 쓰지 않는다
KEYWORD_MIN_CREATORS = 5


def _pct(part, whole, nd=1):
    return round(float(part) / float(whole) * 100, nd) if whole else 0.0


class MarketMetrics:
    """마켓 1개에 대한 모든 파생 수치."""

    def __init__(self, key, df):
        self.key = key
        self.df = df
        self.pos = df[df['판매금액'] > 0]
        self._content = None

    # ---------- 기초 집계 ----------
    @property
    def content(self):
        if self._content is None:
            self._content = self.df.groupby('콘텐츠ID', observed=True).agg(
                콘텐츠명=('콘텐츠명', 'first'), 타입=('콘텐츠타입', 'first'),
                크리에이터ID=('크리에이터ID', 'first'), 닉네임=('닉네임', 'first'),
                출신마켓=('출신마켓', 'first'), 판매자유형=('판매자유형', 'first'),
                매출=('판매금액', 'sum'), 건수=('판매금액', 'size'),
                구매자=('구매자', 'nunique'), 판매월수=('월', 'nunique'),
            ).sort_values('매출', ascending=False)
        return self._content

    # ---------- 콘텐츠 타입 ----------
    def ctype(self):
        rev = self.df.groupby('콘텐츠타입', observed=True)['판매금액'].sum()
        cnt = self.pos.groupby('콘텐츠타입', observed=True).size()
        buy = self.df.groupby('콘텐츠타입', observed=True)['구매자'].nunique()
        n = self.df.groupby('콘텐츠타입', observed=True)['콘텐츠ID'].nunique()
        out = {}
        for label, series in [('rev', rev), ('cnt', cnt), ('buyer', buy), ('title', n)]:
            tot = series.sum()
            out[f'ctype.anim_{label}_pct'] = _pct(series.get(ANIM, 0), tot)
            out[f'ctype.still_{label}_pct'] = _pct(series.get(STILL, 0), tot)
        return out

    # ---------- 월별 ----------
    def monthly(self):
        mo = self.df.groupby('월')['판매금액'].sum()
        base = mo.mean()
        out = {}
        for m, v in mo.items():
            out[f'month.{m}.index'] = round(v / base * 100, 1)   # 반기평균=100 지수
            out[f'month.{m}.share_pct'] = _pct(v, mo.sum())
        out['month.peak'] = int(mo.idxmax())
        out['month.low'] = int(mo.idxmin())
        out['month.peak_vs_low_x'] = round(mo.max() / mo.min(), 2) if mo.min() else 0.0
        first = mo.index.min()
        out['month.peak_vs_first_x'] = round(mo.max() / mo.loc[first], 2) if mo.loc[first] else 0.0
        # 설날이 있는 달 대비 직전 달 (COM 시즌성 지표)
        if 2 in mo.index and 1 in mo.index and mo.loc[1]:
            out['month.feb_vs_jan_x'] = round(mo.loc[2] / mo.loc[1], 2)
        return out

    # ---------- 시간대 / 요일 ----------
    def timing(self):
        out = {}
        hr = self.df.groupby('시')['판매금액'].sum().reindex(range(24), fill_value=0)
        hp = (hr / hr.sum() * 100).round(1)
        for h, v in hp.items():
            out[f'hour.{h}.pct'] = float(v)
        out['hour.peak'] = int(hp.idxmax())
        out['hour.peak_pct'] = float(hp.max())
        out['hour.low'] = int(hp.idxmin())
        out['hour.low_pct'] = float(hp.min())
        # 집중 구간: 누적 2/3를 담는 연속 시간대
        lo, hi = self._peak_window(hp, 65.0)
        out['hour.window_start'], out['hour.window_end'] = lo, hi
        out['hour.window_pct'] = round(float(hp.loc[lo:hi].sum()), 1)

        wd = self.df.groupby('요일')['판매금액'].sum().reindex(range(7), fill_value=0)
        wp = (wd / wd.sum() * 100).round(1)
        for i, name in enumerate(WEEKDAYS):
            out[f'weekday.{name}.pct'] = float(wp.iloc[i])
        out['weekday.weekday_pct'] = round(float(wp.iloc[:5].sum()), 1)
        out['weekday.weekend_pct'] = round(float(wp.iloc[5:].sum()), 1)
        out['weekday.peak'] = WEEKDAYS[int(wp.idxmax())]
        return out

    @staticmethod
    def _peak_window(hp, target):
        """target% 이상을 담는 가장 짧은 연속 시간 구간(동률이면 늦은 쪽)."""
        best = None
        for a in range(24):
            s = 0.0
            for b in range(a, 24):
                s += float(hp.iloc[b])
                if s >= target:
                    if best is None or (b - a) <= (best[1] - best[0]):
                        best = (a, b)
                    break
        return best if best else (0, 23)

    # ---------- 테마 ----------
    def themes(self):
        g = self.content
        tot = g['매출'].sum()
        rows = []
        for name, pat in THEMES.items():
            m = g['콘텐츠명'].str.contains(pat, regex=True, na=False)
            if not m.any():
                continue
            rows.append((name, int(m.sum()), _pct(g.loc[m, '매출'].sum(), tot)))
        rows.sort(key=lambda r: -r[2])
        out = {}
        for i, (name, n, pct) in enumerate(rows, 1):
            out[f'theme.{i}.name'] = name
            out[f'theme.{i}.pct'] = pct
        for name, n, pct in rows:
            out[f'theme.by_name.{name}.pct'] = pct
        return out

    # ---------- 집중도 ----------
    def concentration(self):
        g = self.content['매출']
        c = self.df.groupby('크리에이터ID', observed=True)['판매금액'].sum().sort_values(ascending=False)
        b = self.df.groupby('구매자')['판매금액'].sum().sort_values(ascending=False)
        out = {}
        for x in (10, 25, 50, 100):
            out[f'conc.content_top{x}_pct'] = _pct(g.head(x).sum(), g.sum())
        for x in (10, 50, 100):
            out[f'conc.creator_top{x}_pct'] = _pct(c.head(x).sum(), c.sum())
        out['conc.content_top10p_pct'] = _pct(g.head(max(1, int(len(g) * .1))).sum(), g.sum())
        out['conc.buyer_top10p_pct'] = _pct(b.head(max(1, int(len(b) * .1))).sum(), b.sum())
        return out

    # ---------- 구매 행태 ----------
    def behavior(self):
        b = self.df.groupby('구매자')['판매금액'].agg(['size', 'sum'])
        out = {
            'behavior.single_purchase_pct': round(float((b['size'] == 1).mean() * 100), 1),
            'behavior.avg_purchases': round(float(b['size'].mean()), 2),
            'behavior.refund_pct': _pct((self.df['판매금액'] < 0).sum(), len(self.pos), 2),
        }
        # 1회 결제로 여러 개를 사는 거래 = 결제액이 해당 타입 단가(최빈값)를 넘는 건.
        # 마켓이 낱개 판매만 지원하면 구조적으로 0%가 나온다(=정상). SOM에만 크게 잡힌다.
        unit = self.pos.groupby('콘텐츠타입', observed=True)['판매금액'].agg(lambda x: x.mode().iat[0])
        # map 결과가 카테고리형으로 나오면 대소 비교가 안 된다 → 숫자로 되돌린다
        base = self.pos['콘텐츠타입'].map(unit).astype('int64')
        multi = self.pos['판매금액'] > base
        out['behavior.unit_price'] = {k: int(v) for k, v in unit.items()}
        out['behavior.multi_item_order_pct'] = round(float(multi.mean() * 100), 1)
        out['behavior.multi_item_rev_pct'] = _pct(self.pos.loc[multi, '판매금액'].sum(),
                                                  self.pos['판매금액'].sum())
        return out

    # ---------- 수명 ----------
    def lifespan(self):
        g = self.content
        n_months = self.df['월'].nunique()
        out = {'life.avg_months': round(float(g['판매월수'].mean()), 1)}
        for m in range(1, n_months + 1):
            out[f'life.months_{m}_pct'] = _pct((g['판매월수'] == m).sum(), len(g))
        top = g.head(25)
        out['life.top25_avg_months'] = round(float(top['판매월수'].mean()), 1)
        out['life.full_run_pct'] = _pct((g['판매월수'] == n_months).sum(), len(g))
        return out

    # ---------- 키워드 ----------
    def keywords(self, n=8):
        g = self.df.groupby('콘텐츠ID', observed=True).agg(
            명=('콘텐츠명', 'first'), 매출=('판매금액', 'sum'), 크리에이터=('크리에이터ID', 'first'))
        rev, crt = Counter(), {}
        for _, r in g.iterrows():
            for tok in set(re.findall(r'[가-힣A-Za-z]{2,}', str(r['명']))):
                if len(tok) < 2 or tok in _STOP:
                    continue
                rev[tok] += int(r['매출'])
                crt.setdefault(tok, set()).add(r['크리에이터'])
        # 크리에이터 5명 미만 단어는 특정 콘텐츠 지목이 되므로 제외 (배포 원칙)
        safe = [(t, v) for t, v in rev.most_common(400)
                if len(crt[t]) >= KEYWORD_MIN_CREATORS]
        out = {}
        for i, (t, v) in enumerate(safe[:n], 1):
            out[f'keyword.{i}'] = t
        out['keyword.count'] = len(safe[:n])
        return out

    # ---------- TOP25 (매출 기준) ----------
    def top25(self):
        t = self.content.head(25)
        tot = t['매출'].sum()
        out = {
            'top25.anim_rev_pct': _pct(t.loc[t['타입'] == ANIM, '매출'].sum(), tot),
            'top25.still_rev_pct': _pct(t.loc[t['타입'] == STILL, '매출'].sum(), tot),
            'top25.share_of_market_pct': _pct(tot, self.content['매출'].sum()),
            'top25.creator_count': int(t['크리에이터ID'].nunique()),
            'top25.avg_months': round(float(t['판매월수'].mean()), 1),
        }
        # 시리즈(넘버링/후속작) 비중 — 제목 패턴으로 판정
        ser = t['콘텐츠명'].str.contains(r'\d\s*(?:탄|편|기|번째)|ver\.?\s*\d|시즌\s*\d|part\s*\d',
                                     case=False, regex=True, na=False)
        out['top25.series_rev_pct'] = _pct(t.loc[ser, '매출'].sum(), tot)
        return out

    # ---------- 내부용 절대 수치 ----------
    def raw(self):
        return {
            'raw.revenue': int(self.df['판매금액'].sum()),
            'raw.orders': int(len(self.pos)),
            'raw.buyers': int(self.df['구매자'].nunique()),
            'raw.contents': int(self.df['콘텐츠ID'].nunique()),
            'raw.creators': int(self.df['크리에이터ID'].nunique()),
        }

    def all(self):
        out = {}
        for fn in (self.ctype, self.monthly, self.timing, self.themes, self.concentration,
                   self.behavior, self.lifespan, self.keywords, self.top25, self.raw):
            out.update(fn())
        return out


def compute(dfs):
    """{'NOM': df, ...} → flat dict  {'nom.ctype.anim_rev_pct': 9.2, ...}"""
    flat = {}
    per = {}
    for k, df in dfs.items():
        mm = MarketMetrics(k, df)
        per[k] = mm
        for mk, v in mm.all().items():
            flat[f'{k.lower()}.{mk}'] = v
    # 전체 합산
    total_rev = sum(d['판매금액'].sum() for d in dfs.values())
    for k, df in dfs.items():
        flat[f'all.share.{k.lower()}_pct'] = _pct(df['판매금액'].sum(), total_rev)
    flat['all.raw.revenue'] = int(total_rev)
    return flat, per
