# -*- coding: utf-8 -*-
"""기간 판정이 데이터에 맞게 나오는지 확인한다.

예전에는 무조건 상/하반기로 적어서 3월 한 달치를 넣어도 표지에 '2026년 상반기'가
박혔다. 그 회귀를 막는 시험이다.

  python3 -m playbook.test_periods
"""
import datetime as dt

from . import ingest


def P(*months, year=2026):
    return ingest.Period(sorted((year, m) for m in months))


CASES = [
    # (월들, 기대 표기, 기대 종류, 기대 '다음 기간')
    ([3],                    '2026년 3월',   '월',   '2026년 4월'),
    ([12],                   '2026년 12월',  '월',   '2027년 1월'),
    ([1, 2, 3],              '2026년 1분기',  '분기', '2026년 2분기'),
    ([4, 5, 6],              '2026년 2분기',  '분기', '2026년 3분기'),
    ([10, 11, 12],           '2026년 4분기',  '분기', '2027년 1분기'),
    ([1, 2, 3, 4, 5, 6],     '2026년 상반기',  '반기', '2026년 하반기'),
    ([7, 8, 9, 10, 11, 12],  '2026년 하반기',  '반기', '2027년 상반기'),
    (list(range(1, 13)),     '2026년',       '연간', '2027년'),
    ([3, 4, 5],              '2026년 3~5월',  '구간', None),
    ([2, 5],                 None,           '구간', None),   # 구멍 난 경우
]


def main():
    bad = []
    for months, label, kind, nxt in CASES:
        p = P(*months)
        if label and p.label != label:
            bad.append(f'{months} → 표기 "{p.label}" (기대 "{label}")')
        if p.kind != kind:
            bad.append(f'{months} → 종류 "{p.kind}" (기대 "{kind}")')
        if nxt and p.next_label != nxt:
            bad.append(f'{months} → 다음 "{p.next_label}" (기대 "{nxt}")')
        if ' ' in p.slug():
            bad.append(f'{months} → 파일명 조각에 공백: "{p.slug()}"')
        print(f'  {str(months):26s} {p.label:16s} {p.kind:4s} → {p.next_label}')

    # 해를 넘기는 경우
    p = ingest.Period([(2026, 11), (2026, 12), (2027, 1)])
    print(f'  해 넘김                    {p.label:16s} {p.kind}')
    if p.kind != '구간':
        bad.append(f'해를 넘기는 데이터가 "{p.kind}"로 판정됨')

    if bad:
        print('\n문제:')
        for b in bad:
            print('  -', b)
        raise SystemExit(1)
    print('\n통과')


if __name__ == '__main__':
    main()
