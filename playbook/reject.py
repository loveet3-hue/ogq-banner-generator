# -*- coding: utf-8 -*-
"""심사 반려 사유(자유 텍스트) → 12개 카테고리 집계.

원천: ogq_statistics.xlsx > 'OCS_월별_반려사유데이터' 시트 (월 / 반려 사유 / 건수)
심사자가 직접 쓴 문장이라 표현이 매번 조금씩 다르다. 그래서 정확 일치가 아니라
규칙 순서대로 훑는 방식이고, 위에 있는 규칙이 이긴다.
"""
import re
import pandas as pd

SHEET = 'OCS_월별_반려사유데이터'

# (카테고리, 정규식) — 순서가 곧 우선순위
RULES = [
    ('내부 심사 규정', r'내부\s*심사\s*규정'),
    ('AI 사용 의심',   r'\bAI\b|생성형\s*AI|ai\s*로고'),
    ('저작권·권리 침해', r'저작권|지적재산권|상표권|퍼블리시티|초상권|스트리머\s*명|스트리머명|'
                      r'스트리머 협의|스트리머 확인|앨범\s*아트|서명|사인 등은|캐릭터가 연상'),
    ('부적절 표현',    r'욕설|폭력|비방|선정성|정치적|종교적|신체 노출|불쾌감|비속어'),
    ('중복 콘텐츠',    r'중복|마켓 내 동일한 콘텐츠|구도와 연출이 상당|내용이 동일|'
                      r'동일하거나 유사|동일\s*/\s*유사|유사한 것으로 확인|매우 유사한'),
    ('다크모드 대응',  r'다크\s*모드|흰색 테두리|하얀 테두리|테두리 선이|테두리를 매끄럽'),
    ('투명 배경(PNG)', r'투명한\s*png|배경이 투명|배경이 없는 png|배경 잔여물|투명도가 포함'),
    ('사진·화질',      r'노이즈|해상도|초점|밝거나 어둡|화질|뭉개|흐릿|흐린'),
    ('텍스트 가독성',  r'가독성|공정위|포스팅 문구|오타|맞춤법|폰트를 통일|텍스트의 크기'),
    ('완성도(채색·모션)', r'채색|움직임|애니메이션|매끄럽|지워진|지워져|프레임|모션|'
                        r'완성도가 판매 기준|디테일과 구도|사용성에 따른 차이'),
    ('크기·정렬 통일', r'통일|정렬|비율|잘립|잘려|사이즈|크기를 키워|중앙|수직|수평'),
]

# '기타'가 이 비율을 넘으면 심사 문구가 바뀐 것이다 — 규칙을 손봐야 한다는 신호
OTHER_WARN_PCT = 5.0

CATEGORIES = [c for c, _ in RULES] + ['기타']
_COMPILED = [(c, re.compile(p, re.I)) for c, p in RULES]


# 카테고리 안에서 다시 쪼개 보여줄 세부 묶음. 상세 카드 문구에서 쓴다.
SUBGROUPS = {
    '다크모드 대응': {
        '테두리 누락': r'흰색 테두리를 추가|하얀 테두리를 추가|테두리가 지워|테두리 일부가',
        '테두리 얇음·흐림': r'얇거나 흐릿|희미|매끄럽',
        '배경 흰 점·선': r'하얀 점|하얀 선|흰 점|까만 점',
    },
    '중복 콘텐츠': {
        '중복 업로드': r'중복 업로드|중복 등록',
        '마켓 내 동일': r'마켓 내 동일',
        '세트 내 유사': r'구도와 연출이 상당|내용이 동일',
        '세트 내 중복 이미지': r'중복 이미지',
        '기존 등록물과 유사': r'이전에 등록|기존 등록된',
    },
    '투명 배경(PNG)': {
        '메인·탭 미적용': r'메인 이미지와 탭|메인, 탭|메인 이미지의',
        '스티커 미적용': r'스티커는 배경이 투명',
    },
}


def classify(text):
    t = str(text)
    for cat, pat in _COMPILED:
        if pat.search(t):
            return cat
    return '기타'


def load(path, month=None, sheet=SHEET):
    """반려 데이터 로드. month='2026-06' 형태, 생략 시 가장 최근 월."""
    df = pd.read_excel(path, sheet_name=sheet)
    need = ['월', '반려 사유', '건수']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f'{sheet} 컬럼 누락: {missing} / 실제: {list(df.columns)}')
    df['월'] = df['월'].astype(str)
    month = month or sorted(df['월'].unique())[-1]
    m = df[df['월'] == month].copy()
    if m.empty:
        raise ValueError(f'{month} 데이터가 없습니다. 가능한 월: {sorted(df["월"].unique())}')
    m['카테고리'] = m['반려 사유'].map(classify)
    return month, m


def summarize(m, top_detail=3):
    """→ dict(month 제외): 카테고리별 건수·비중 + 상위 카테고리 상세 문구"""
    tot = int(m['건수'].sum())
    g = m.groupby('카테고리')['건수'].sum().sort_values(ascending=False)
    out = {'reject.total': tot, 'reject.categories': []}
    for i, (cat, cnt) in enumerate(g.items(), 1):
        pct = round(cnt / tot * 100, 1)
        out['reject.categories'].append({'name': cat, 'count': int(cnt), 'pct': pct})
        out[f'reject.{i}.name'] = cat
        out[f'reject.{i}.pct'] = pct
        out[f'reject.{i}.count'] = int(cnt)
        out[f'reject.by_name.{cat}.pct'] = pct
        out[f'reject.by_name.{cat}.count'] = int(cnt)

    # TOP N 카테고리의 대표 문구 (건수 큰 순)
    for i, cat in enumerate(list(g.index)[:top_detail], 1):
        sub = m[m['카테고리'] == cat].sort_values('건수', ascending=False)
        out[f'reject.top{i}.name'] = cat
        out[f'reject.top{i}.count'] = int(sub['건수'].sum())
        out[f'reject.top{i}.reasons'] = [
            (str(r['반려 사유']).strip().replace('\n', ' ')[:60], int(r['건수']))
            for _, r in sub.head(4).iterrows()]

    # 카테고리 안 세부 묶음
    for cat, subs in SUBGROUPS.items():
        sub_df = m[m['카테고리'] == cat]
        if sub_df.empty:
            continue
        for label, pat in subs.items():
            hit = sub_df[sub_df['반려 사유'].str.contains(pat, regex=True, na=False)]
            out[f'reject.sub.{cat}.{label}'] = int(hit['건수'].sum())

    # 규격만 지켜도 막을 수 있는 반려 = 주관 판단(내부 심사 규정) 외 규격성 사유
    spec = ['다크모드 대응', '중복 콘텐츠', '투명 배경(PNG)', '사진·화질', '텍스트 가독성', '크기·정렬 통일']
    out['reject.spec_pct'] = round(sum(int(g.get(c, 0)) for c in spec) / tot * 100, 1)

    # 분류 못 한 게 많으면 심사 문구가 바뀐 것 — 조용히 '기타'로 묻으면 안 된다
    other = round(int(g.get('기타', 0)) / tot * 100, 1)
    out['reject.other_pct'] = other
    if other > OTHER_WARN_PCT:
        top = (m[m['카테고리'] == '기타'].sort_values('건수', ascending=False)
               .head(5)[['반려 사유', '건수']].values.tolist())
        out['reject.warning'] = (
            f"분류 못 한 반려 사유가 {other}%입니다(기준 {OTHER_WARN_PCT}%). "
            f"심사 문구가 바뀐 것으로 보이니 reject.py의 RULES를 보완하세요. 미분류 상위: "
            + ' / '.join(f'{int(c):,}건 "{str(t)[:40]}"' for t, c in top))
    return out


if __name__ == '__main__':
    import sys
    month, m = load(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    s = summarize(m)
    print(f'{month}  총 {s["reject.total"]:,}건')
    for c in s['reject.categories']:
        print(f'  {c["pct"]:5.1f}%  {c["count"]:5,}건  {c["name"]}')
    print(f'  규격성 사유 합계: {s["reject.spec_pct"]}%')
