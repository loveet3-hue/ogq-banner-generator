# -*- coding: utf-8 -*-
"""원천 xlsx → 정규화된 DataFrame. 컬럼 스키마 검증 포함.

입력 파일이 반기마다 달라져도 여기서만 잡으면 되도록, 컬럼 검증을 강하게 건다.
"""
import re, sys, hashlib
from pathlib import Path
import pandas as pd

REQUIRED = ['일시', '콘텐츠명', '콘텐츠ID', '콘텐츠타입', '크리에이터ID',
            '닉네임', '출신마켓', '판매자유형', '구매자', '판매금액']

MARKETS = ['NOM', 'SOM', 'COM']

# 파일명으로 마켓 추정 (2026_NOM_상반기.xlsx / SOM_상반기.xlsx 등 모두 커버)
_MARKET_PAT = {
    'NOM': re.compile(r'NOM|네이버|naver', re.I),
    'SOM': re.compile(r'SOM|SOOP|숲|아프리카', re.I),
    'COM': re.compile(r'COM|채팅', re.I),
}


class IngestError(Exception):
    pass


def detect_market(path):
    name = Path(path).name
    hits = [m for m, p in _MARKET_PAT.items() if p.search(name)]
    # SOM 파일명에 'OGQ마켓'이 들어가면 COM 패턴('마켓')과 안 겹치도록 우선순위 고정
    for m in MARKETS:
        if m in hits:
            return m
    raise IngestError(
        f'파일명에서 마켓을 알 수 없습니다: {name}\n'
        f'  파일명에 NOM/SOM/COM 중 하나를 포함시키거나 run.py에 --market 으로 지정하세요.')


# 되풀이되는 값이 많은 열은 category로 담는다. 29만 행짜리 파일에서 메모리가 크게 줄고,
# 웹앱은 배너 생성기와 메모리를 나눠 쓰므로 이게 곧 안 죽는 조건이 된다.
CATEGORICAL = ['콘텐츠명', '콘텐츠ID', '콘텐츠타입', '크리에이터ID', '닉네임',
               '출신마켓', '판매자유형']


def load_market(path, market=None):
    path = str(path)
    market = market or detect_market(path)

    # 먼저 머리글만 읽어 검증한다. 통째로 읽고 나서 버리면 메모리를 두 배로 쓴다.
    head = pd.read_excel(path, nrows=0)
    missing = [c for c in REQUIRED if c not in head.columns]
    if missing:
        raise IngestError(
            f'[{market}] {Path(path).name} 컬럼 누락: {missing}\n'
            f'  실제 컬럼: {list(head.columns)}\n'
            f'  → 원천 데이터 양식이 바뀌었습니다. ingest.py의 REQUIRED를 확인하세요.')
    del head

    df = _read_columns(path, REQUIRED)
    df['일시'] = pd.to_datetime(df['일시'], errors='coerce')
    bad = df['일시'].isna().sum()
    if bad:
        raise IngestError(f'[{market}] 일시 파싱 실패 {bad}건 — 날짜 형식을 확인하세요.')

    df['판매금액'] = pd.to_numeric(df['판매금액'], errors='coerce').fillna(0).astype('int32')
    df['콘텐츠명'] = df['콘텐츠명'].fillna('').astype(str).str.strip()
    df['월'] = df['일시'].dt.month.astype('int8')
    df['시'] = df['일시'].dt.hour.astype('int8')
    df['요일'] = df['일시'].dt.dayofweek.astype('int8')     # 0=월
    for c in CATEGORICAL:
        df[c] = df[c].astype('category')
    df['마켓'] = market
    return market, df


def _read_columns(path, columns):
    """필요한 열만 한 줄씩 흘려 읽는다.

    pd.read_excel은 시트를 통째로 메모리에 올린다. 29만 행짜리 파일에서 그 순간이
    가장 위험한 지점이라(배너 생성기와 메모리를 나눠 쓴다) openpyxl의 read_only로
    흘려 읽는다. 실측으로 더 빠르기도 하다(23초 → 15초, 346MB → 301MB).
    문제가 생기면 원래 방식으로 물러난다.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb[wb.sheetnames[0]]
            rows = ws.iter_rows(values_only=True)
            header = list(next(rows))
            idx = [header.index(c) for c in columns]
            data = [[r[i] for i in idx] for r in rows]
        finally:
            wb.close()
        df = pd.DataFrame(data, columns=columns)
        del data
        return df
    except Exception:
        return pd.read_excel(path, usecols=columns)


def load_all(paths):
    """paths: xlsx 경로 리스트 → {'NOM': df, 'SOM': df, 'COM': df}"""
    out = {}
    for p in paths:
        m, df = load_market(p)
        if m in out:
            raise IngestError(f'{m} 마켓 파일이 2개 이상입니다: {p}')
        out[m] = df
    missing = [m for m in MARKETS if m not in out]
    if missing:
        raise IngestError(f'마켓 파일 누락: {missing} — 3개 마켓 xlsx를 모두 넣어야 합니다.')
    return out


def period_label(dfs):
    """데이터에서 기간을 자동 추론 → ('2026', '상반기', '2026년 상반기')"""
    lo = min(d['일시'].min() for d in dfs.values())
    hi = max(d['일시'].max() for d in dfs.values())
    if lo.year != hi.year:
        raise IngestError(f'데이터가 두 해에 걸쳐 있습니다: {lo.date()} ~ {hi.date()}')
    half = '상반기' if hi.month <= 6 else '하반기'
    if lo.month <= 6 <= hi.month and hi.month > 6:
        raise IngestError(f'데이터가 상·하반기에 걸쳐 있습니다: {lo.date()} ~ {hi.date()}')
    return str(lo.year), half, f'{lo.year}년 {half}'


if __name__ == '__main__':
    dfs = load_all(sys.argv[1:])
    for m, d in dfs.items():
        print(f'{m}: {len(d):,}행  {d["일시"].min().date()} ~ {d["일시"].max().date()}  '
              f'매출 {d["판매금액"].sum():,}원')
    print('기간:', period_label(dfs)[2])
