# -*- coding: utf-8 -*-
"""파이프라인 본체. CLI(run.py)와 웹앱(app.py)이 같이 쓴다.

build(...)는 아무것도 출력하지 않고 Report를 돌려준다. 화면에 어떻게 보여줄지는
부르는 쪽이 정한다.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ingest, metrics, fill, spec, qa, config, overrides
from . import reject as rj_mod

HERE = Path(__file__).parent
DEFAULT_TEMPLATE = HERE / 'template_v2.pptx'


@dataclass
class Report:
    out: Path                      # 생성된 pptx
    period: str                    # '2026년 상반기'
    year: str
    half: str
    rows: dict = field(default_factory=dict)        # 마켓별 행 수·기간
    changes: list = field(default_factory=list)     # 바꾼 것 전부
    issues: list = field(default_factory=list)      # 검수 지적
    warnings: list = field(default_factory=list)    # 확인 필요
    manual: dict = field(default_factory=dict)      # 사람이 채워야 하는 것
    reject_month: str = ''
    reject_total: int = 0
    reject_other_pct: float = 0.0
    changed_slides: list = field(default_factory=list)
    metric_count: int = 0

    def changelog_md(self):
        lines = [f'# {self.period} 플레이북 생성 변경내역', '',
                 f'- 출력: `{self.out.name}`',
                 f'- 변경 {len(self.changes)}건 / 검수 지적 {len(self.issues)}건', '',
                 '| 슬라이드 | 항목 | 이전 | 이후 |', '| --- | --- | --- | --- |']
        for c in self.changes:
            lines.append(f'| {c["slide"]} | {c["what"]} | '
                         f'{c["before"][:40]} | {c["after"][:40]} |')
        return '\n'.join(lines)


def _resolve(fmt, flat):
    """'{nom.ctype.anim_BASIS_pct:.0f}%' → 실제 값 문자열."""
    fmt = fmt.replace('_BASIS_', f'_{config.CTYPE_BASIS}_')
    out, i = [], 0
    while i < len(fmt):
        if fmt[i] == '{':
            j = fmt.index('}', i)
            key, _, spec_ = fmt[i + 1:j].partition(':')
            if key not in flat:
                raise KeyError(f'지표 키 없음: {key}')
            out.append(format(flat[key], spec_) if spec_ else str(flat[key]))
            i = j + 1
        else:
            out.append(fmt[i])
            i += 1
    return ''.join(out)


def _shape_by_id(slide, sid):
    for sh in slide.shapes:
        if sh.shape_id == sid:
            return sh
    return None


def build(xlsx_paths, reject_path=None, reject_month=None,
          template=None, out=None, progress=None):
    """매출 xlsx 3개(+반려 xlsx) → 채워진 pptx. Report를 돌려준다.

    progress: 진행 상황을 받을 콜백 fn(단계번호, 전체, 메시지). 웹앱에서 쓴다.
    """
    def step(i, msg):
        if progress:
            progress(i, 5, msg)

    template = Path(template or DEFAULT_TEMPLATE)
    warn = []

    # 1) 데이터
    step(1, '엑셀 읽는 중')
    dfs = ingest.load_all([str(p) for p in xlsx_paths])
    year, half, period = ingest.period_label(dfs)
    rows = {m: dict(n=len(d), lo=d['일시'].min().date(), hi=d['일시'].max().date())
            for m, d in dfs.items()}

    # 2) 지표
    step(2, '지표 계산 중')
    flat, _ = metrics.compute(dfs)
    nyear, nhalf = (year, '하반기') if half == '상반기' else (str(int(year) + 1), '상반기')
    flat.update({'period.year': year, 'period.half': half, 'period.label': period,
                 'period.next_year': nyear, 'period.next_half': nhalf})

    rj, month = None, ''
    if reject_path:
        month, m_df = rj_mod.load(str(reject_path), reject_month)
        rj = rj_mod.summarize(m_df)
        flat.update({k: v for k, v in rj.items() if isinstance(v, (int, float, str))})
        if 'reject.warning' in rj:
            warn.append(rj['reject.warning'])

    # 3) 채우기
    step(3, '템플릿 채우는 중')
    prs = fill.open_template(str(template))
    ch = fill.Changes()

    for c in spec.CHARTS:
        mk, sn = c['market'].lower(), c['slide']
        try:
            if c['kind'] == 'hour':
                fill.fill_hour_chart(prs.slides[sn - 1], sn,
                                     {h: flat[f'{mk}.hour.{h}.pct'] for h in range(24)}, ch)
            else:
                fill.fill_weekday_chart(prs.slides[sn - 1], sn,
                                        {d: flat[f'{mk}.weekday.{d}.pct']
                                         for d in fill.WEEKDAYS}, ch)
        except Exception as e:
            warn.append(f'{sn}장 {c["kind"]} 차트: {e}')

    b = config.CTYPE_BASIS
    for c in spec.CTYPE_BARS:
        mk, sn = c['market'].lower(), c['slide']
        try:
            fill.fill_ctype_bar(prs.slides[sn - 1], sn,
                                flat[f'{mk}.ctype.still_{b}_pct'],
                                flat[f'{mk}.ctype.anim_{b}_pct'], ch)
        except Exception as e:
            warn.append(f'{sn}장 유형 비율 막대: {e}')

    for k in spec.KEYWORDS:
        mk, sn = k['market'].lower(), k['slide']
        words = [flat[f'{mk}.keyword.{i}'] for i in range(1, k['count'] + 1)]
        n = fill.fill_keywords(prs.slides[sn - 1], sn, words, ch)
        if n < k['count']:
            warn.append(f'{sn}장 키워드 칩 {n}/{k["count"]}개만 교체됨')

    for sn, sid, fmt in spec.TEXT_BINDINGS:
        sh = _shape_by_id(prs.slides[sn - 1], sid)
        if sh is None:
            warn.append(f'{sn}장 도형 {sid} 없음 — 템플릿이 바뀌었는지 확인하세요')
            continue
        try:
            fill.set_text(sh, _resolve(fmt, flat), ch, sn, '핵심 수치')
        except KeyError as e:
            warn.append(f'{sn}장 도형 {sid}: {e}')

    if rj:
        try:
            sentences = {}
            for name, fmt in overrides.CARD_SENTENCES.items():
                try:
                    sentences[name] = _resolve(fmt, flat)
                except KeyError as e:
                    warn.append(f'반려 카드 문장 "{name}": {e}')
            try:
                headline = _resolve(overrides.HEADLINE[2], flat)
            except KeyError as e:
                headline = None
                warn.append(f'반려 머리말: {e}')
            fill.fill_reject_status(prs.slides[spec.REJECT_STATUS - 1], spec.REJECT_STATUS,
                                    rj, month, ch, sentences, overrides.CARD_TAILS, headline)
            fill.fill_reject_action(prs.slides[spec.REJECT_ACTION - 1], spec.REJECT_ACTION,
                                    rj, ch)
        except Exception as e:
            warn.append(f'반려 슬라이드: {e}')

    # 기간 표기. 시즌 캘린더는 '데이터 기간'이 아니라 '다음 반기'를 가리켜야 한다.
    for si, sl in enumerate(prs.slides, 1):
        for sh in sl.shapes:
            if not sh.has_text_frame:
                continue
            t = sh.text_frame.text
            y, h = (nyear, nhalf) if '시즌 캘린더' in t else (year, half)
            new = re.sub(r'\d{4}년\s*(?:상반기|하반기)', f'{y}년 {h}', t)
            new = re.sub(r'(?<!\d)\d{4}\s+(?:상반기|하반기)', f'{y} {h}', new)
            if new != t:
                fill.set_text(sh, new, ch, si, '기간 표기')

    for (sn, sid), fmt in overrides.OVERRIDES.items():
        sh = _shape_by_id(prs.slides[sn - 1], sid)
        if sh is None:
            warn.append(f'{sn}장 도형 {sid} 없음 (overrides.py)')
            continue
        try:
            fill.set_text(sh, _resolve(fmt, flat), ch, sn, '문장 속 숫자')
        except KeyError as e:
            warn.append(f'{sn}장 도형 {sid} 문장: {e}')

    # 4) 저장
    step(4, '파일 저장 중')
    out = Path(out) if out else HERE / f'OGQ_{year}_{half}_플레이북_초안.pptx'
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)

    # 5) 검수
    step(5, '검수 중')
    issues = qa.check(out, verbose=False)

    return Report(
        out=out, period=period, year=year, half=half, rows=rows,
        changes=list(ch), issues=issues, warnings=warn,
        manual={k: dict(slides=sorted(set(v['slides'])), what=v['what'])
                for k, v in spec.MANUAL.items()},
        reject_month=month,
        reject_total=rj['reject.total'] if rj else 0,
        reject_other_pct=rj['reject.other_pct'] if rj else 0.0,
        changed_slides=sorted({c['slide'] for c in ch if c['slide']}),
        metric_count=len(flat),
    )


def available_reject_months(path):
    """반려 엑셀에 들어 있는 월 목록 (최근 순)."""
    import pandas as pd
    df = pd.read_excel(str(path), sheet_name=rj_mod.SHEET)
    return sorted(df['월'].astype(str).unique(), reverse=True)
