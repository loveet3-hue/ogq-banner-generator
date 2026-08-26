#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""터미널에서 쓰는 진입점. 실제 작업은 build.py가 한다.

  python3 run.py ~/Downloads/*_상반기.xlsx --reject ~/Downloads/ogq_statistics.xlsx

웹으로 쓰려면:  streamlit run app.py
"""
import argparse, sys, traceback
from pathlib import Path

from . import build as B
from . import ingest

HERE = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsx', nargs='+', help='매출 xlsx 3개 (NOM/SOM/COM)')
    ap.add_argument('--reject', help='ogq_statistics.xlsx (심사 반려 데이터)')
    ap.add_argument('--reject-month', help='예: 2026-12. 생략하면 가장 최근 월')
    ap.add_argument('--template', default=None)
    ap.add_argument('--out', help='출력 pptx 경로')
    a = ap.parse_args()

    labels = {1: '데이터 읽기', 2: '지표 계산', 3: '템플릿 채우기',
              4: '파일 저장', 5: '검수'}

    def progress(i, n, msg):
        print(f'■ {i}/{n}  {labels.get(i, msg)}')

    r = B.build(a.xlsx, a.reject, a.reject_month, a.template, a.out, progress)

    print()
    for m, v in r.rows.items():
        print(f'    {m}  {v["n"]:,}행  {v["lo"]} ~ {v["hi"]}')
    print(f'    기간 판정: {r.period} ({r.kind}) · 지표 {r.metric_count}개')
    if r.reject_month:
        print(f'    반려 데이터 {r.reject_month} · {r.reject_total:,}건 · '
              f'미분류 {r.reject_other_pct}%')
    print(f'    변경 {len(r.changes)}건 · 값이 갱신된 슬라이드 {len(r.changed_slides)}장')
    print(f'    검수 지적 {len(r.issues)}건')
    for si, kind, val, ctx in r.issues[:10]:
        print(f'      {si}장 [{kind}] {val} {ctx}')

    print()
    print('사람이 채워야 하는 것')
    for name, info in r.manual.items():
        print(f'    · {info["slides"]} {info["what"]}')

    if r.warnings:
        print()
        print('확인 필요')
        for w in r.warnings:
            print(f'    ! {w}')

    log = r.out.parent / '변경내역.md'
    log.write_text(r.changelog_md(), encoding='utf-8')
    print()
    print(f'완료 → {r.out}')
    print(f'      {log}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ingest.IngestError, ValueError) as e:
        print(f'\n실패: {e}', file=sys.stderr)
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(2)
