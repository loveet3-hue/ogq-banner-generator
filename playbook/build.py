# -*- coding: utf-8 -*-
"""파이프라인 본체. CLI(run.py)와 웹앱(app.py)이 같이 쓴다.

build(...)는 아무것도 출력하지 않고 Report를 돌려준다. 화면에 어떻게 보여줄지는
부르는 쪽이 정한다.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ingest, metrics, fill, spec, qa, config, overrides, season
from . import artwork, attrs
from . import reject as rj_mod

HERE = Path(__file__).parent
DEFAULT_TEMPLATE = HERE / 'template_v2.pptx'


@dataclass
class Report:
    out: Path                      # 생성된 pptx
    period: str                    # '2026년 상반기' / '2026년 3분기' / '2026년 9월'
    kind: str                      # 월 / 분기 / 반기 / 연간 / 구간
    slug: str                      # 파일 이름 조각
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
    reference: dict = field(default_factory=dict)   # 사람이 채울 줄의 분류기 추정치

    def changelog_md(self):
        lines = [f'# {self.period} 플레이북 생성 변경내역', '',
                 f'- 출력: `{self.out.name}`',
                 f'- 변경 {len(self.changes)}건 / 검수 지적 {len(self.issues)}건', '',
                 '| 슬라이드 | 항목 | 이전 | 이후 |', '| --- | --- | --- | --- |']
        for c in self.changes:
            lines.append(f'| {c["slide"]} | {c["what"]} | '
                         f'{c["before"][:40]} | {c["after"][:40]} |')
        if self.reference:
            lines += ['', '## 참고값 — TOP25 속성 표 (덱에는 넣지 않았습니다)', '',
                      '이 줄들은 그림을 눈으로 봐야 정해지는 값이라 자동으로 채우지 않습니다.',
                      '아래는 이미지 분류기가 어림한 값이니, 직접 채우실 때 출발점으로만 봐주세요.', '',
                      '| 슬라이드 | 속성 | 1위 (추정) | 2위 (추정) |', '| --- | --- | --- | --- |']
            for sn in sorted(self.reference):
                for attr, vals in self.reference[sn].items():
                    a = f'{vals[0][0]} {vals[0][1]:g}%' if vals else '—'
                    b = f'{vals[1][0]} {vals[1][1]:g}%' if len(vals) > 1 else '—'
                    lines.append(f'| {sn} | {attr} | {a} | {b} |')
        return '\n'.join(lines)


# [[ ... ]] 로 감싼 조각은 안에 든 값이 전부 0이면 통째로 빠진다.
# 심사 문구는 반기마다 표현이 달라져서, 어떤 항목은 그 달에 아예 안 나온다.
# 그때 '동일·유사 0건'처럼 적히면 없느니만 못하다.
_OPTIONAL = re.compile(r'\[\[(.*?)\]\]', re.S)


def _resolve(fmt, flat):
    """'{nom.ctype.anim_BASIS_pct:.0f}%' → 실제 값 문자열."""
    fmt = fmt.replace('_BASIS_', f'_{config.CTYPE_BASIS}_')

    def _opt(m):
        body = m.group(1)
        keys = re.findall(r'\{([^}:]+)', body)
        if keys and all(not flat.get(k.replace('_BASIS_', f'_{config.CTYPE_BASIS}_'), 0)
                        for k in keys):
            return ''
        return body
    fmt = _OPTIONAL.sub(_opt, fmt)
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
          template=None, out=None, progress=None, use_artwork=True):
    """매출 xlsx 3개(+반려 xlsx) → 채워진 pptx. Report를 돌려준다.

    progress: 진행 상황을 받을 콜백 fn(단계번호, 전체, 메시지). 웹앱에서 쓴다.
    """
    def step(i, msg):
        if progress:
            progress(i, 5, msg)

    template = Path(template or DEFAULT_TEMPLATE)
    warn = []
    artwork_note = False
    dropped_rows = {}
    reference = {}

    # 1) 데이터
    step(1, '엑셀 읽는 중')
    dfs = ingest.load_all([str(p) for p in xlsx_paths])
    per = ingest.period_label(dfs)
    rows = {m: dict(n=len(d), lo=d['일시'].min().date(), hi=d['일시'].max().date())
            for m, d in dfs.items()}

    # 2) 지표
    step(2, '지표 계산 중')
    flat, _ = metrics.compute(dfs)
    flat.update({'period.year': per.year, 'period.half': per.sub, 'period.sub': per.sub,
                 'period.label': per.label, 'period.short': per.short,
                 'period.kind': per.kind, 'period.next': per.next_label,
                 'period.months': per.n})

    # 기간이 짧으면 월별 추이·시즌성 수치는 뜻이 없다. 조용히 넘어가면 안 된다.
    if per.n < 3:
        warn.append(
            f'데이터가 {per.n}개월치({per.label})뿐입니다. 월별 추이와 시즌성 수치'
            f'(성수기 배수 등)는 뜻이 없으니 해당 슬라이드는 직접 확인하세요.')
    if per.kind == '구간':
        warn.append(
            f'월·분기·반기 어디에도 딱 맞지 않는 기간입니다({per.label}). '
            f'표지와 각주에 이 문구가 그대로 들어갑니다.')

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

    # 정지형/애니 비율 — 글자만 바꾼다. 막대 길이는 손으로 다듬어져 있어 건드리지 않는다.
    b = config.CTYPE_BASIS
    for c in spec.CTYPE_BARS:
        mk, sn = c['market'].lower(), c['slide']
        still = flat[f'{mk}.ctype.still_{b}_pct']
        anim = flat[f'{mk}.ctype.anim_{b}_pct']
        try:
            fill.fill_ctype_labels(prs.slides[sn - 1], sn, still, anim, ch)
            if not fill.fill_ctype_bar(prs.slides[sn - 1], sn, still, anim, ch):
                warn.append(f'{sn}장 유형 비율 막대를 찾지 못했습니다 — 글자만 바꿨으니 '
                            f'막대 길이는 눈으로 맞춰 주세요.')
        except Exception as e:
            warn.append(f'{sn}장 유형 비율: {e}')

    # TOP25 속성 — 콘텐츠ID로 마켓을 조회해 실제 이미지를 본다
    if use_artwork:
        step(3, 'TOP25 콘텐츠 조회 중 (마켓에서 이미지를 받아옵니다)')
        for c in spec.TOP25:
            mk, sn = c['market'], c['slide']
            try:
                # 상위 25종은 매출로 고른다. 잣대(매출/판매 수/콘텐츠 수)는
                # 카드·표에 적힌 문구를 읽어서 고른다 — attrs.basis_of 참고.
                top = metrics.MarketMetrics(mk, dfs[mk]).content.head(25)
                rev = {str(k): int(v) for k, v in top['매출'].items()}
                cnt = {str(k): int(v) for k, v in top['건수'].items()}
                uni = {str(k): 1 for k in top.index}
                got = artwork.analyze_many(artwork.fetch_many(top.index))
                miss = 25 - len(got)
                if miss:
                    warn.append(f'{sn}장 TOP25 중 {miss}종은 마켓에서 찾지 못했습니다'
                                f'(비공개·삭제된 콘텐츠일 수 있습니다). 나머지로 계산했습니다.')
                classified, _ = attrs.classify(got, rev, cnt)
                ref = {a: v for a, v in classified.items()
                       if a in attrs.KEEP_ROWS and v}
                if ref:
                    reference[sn] = ref
                _, dropped = fill.fill_top25_table(prs.slides[sn - 1], sn, classified, ch,
                                                   attrs.KEEP_ROWS)
                if dropped:
                    dropped_rows[sn] = dropped
                fill.fill_top25_kpi(
                    prs.slides[sn - 1], sn,
                    lambda lab: attrs.kpi_value(lab, got, rev, cnt, uni), ch)
                # OCR이 25종 전부에서 글자를 찾았다면 과검출을 의심한다.
                ts = attrs.text_share(got, rev)
                if ts >= 99.5:
                    warn.append(f'{sn}장 "텍스트 포함 콘텐츠 비중"이 {ts:.1f}%로 나왔습니다. '
                                f'OCR이 배경 무늬까지 글자로 본 것일 수 있으니 눈으로 확인해 주세요.')
                artwork_note = True
            except Exception as e:
                warn.append(f'{sn}장 TOP25 속성: {e}')

    # 설명 문구는 손대지 않기로 했으므로, 그 문구가 데이터와 어긋나면 알려만 준다.
    peak = flat.get('com.month.peak')
    if peak and peak != 2:
        warn.append(f'7장 채팅+ 설명이 "설날 시즌(2월)"으로 적혀 있는데 이번 기간의 성수기는 '
                    f'{peak}월입니다. 숫자만 바꿨으니 문구는 직접 고쳐 주세요.')

    # 기준이 바뀐 설명줄 (예: '콘텐츠 수 기준' → 매출 기준으로 통일)
    for c in spec.BASIS_CAPTIONS:
        sh = fill.find_by_text(prs.slides[c['slide'] - 1], c['anchor'])
        if sh is not None:
            fill.set_text(sh, c['text'], ch, c['slide'], '기준 표기')

    # 시즌 캘린더 — 다음 달들의 명절·기념일. 음력이라 해마다 날짜가 바뀐다.
    end_y, end_m = per.end
    season_span = ''
    for c in spec.SEASON:
        mk, sn = c['market'], c['slide']
        try:
            cards = season.cards(end_y, end_m, mk)
            season_span = season.span_label(cards)
            if not fill.fill_season_calendar(prs.slides[sn - 1], sn, cards, ch):
                warn.append(f'{sn}장 시즌 캘린더 카드를 찾지 못했습니다')
            elif mk == 'SOM':
                unknown = [f"{c['year']}년 {c['month_num']}월" for c in cards
                           if not season.has_confirmed_esports(c['year'], c['month_num'])]
                if unknown:
                    warn.append(
                        f'{sn}장 캘린더에서 {" · ".join(unknown)}은 확정된 e스포츠 일정이 없어 '
                        f'날짜 없이 넣었습니다. 일정이 발표되면 season.py의 ESPORTS_DATES에 '
                        f'넣어 주세요.')
        except Exception as e:
            warn.append(f'{sn}장 시즌 캘린더: {e}')

    for k in spec.KEYWORDS:
        mk, sn = k['market'].lower(), k['slide']
        words = [flat[f'{mk}.keyword.{i}'] for i in range(1, k['count'] + 1)]
        n = fill.fill_keywords(prs.slides[sn - 1], sn, words, ch)
        if n < k['count']:
            warn.append(f'{sn}장 키워드 칩 {n}/{k["count"]}개만 교체됨')

    for card in spec.STAT_CARDS:
        sn = card['slide']
        cap = fill.find_by_text(prs.slides[sn - 1], card['anchor'])
        if cap is None:
            warn.append(f'{sn}장에서 "{card["anchor"]}" 문구를 찾지 못했습니다 — '
                        f'템플릿이 바뀌었는지 확인하세요.')
            continue
        val = fill.value_beside(prs.slides[sn - 1], cap)
        try:
            if val is not None:
                fill.set_text(val, _resolve(card['value'], flat), ch, sn, '핵심 수치')
        except KeyError as e:
            warn.append(f'{sn}장 "{card["anchor"]}": {e}')

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
            # 템플릿(v2)에는 '2026년 상반기'로 적혀 있다. 항상 원본 템플릿에서
            # 시작하므로, 그 자리를 이번 기간 표기로 갈아 끼우면 된다.
            # 캘린더 제목은 '다음 기간'이 아니라 카드가 실제로 덮는 달을 가리켜야 한다
            nxt = '캘린더' in t
            full = (season_span or per.next_label) if nxt else per.label
            short = (season_span or per.next_short) if nxt else per.short
            new = re.sub(r'\d{4}년\s*(?:상반기|하반기)', full, t)
            new = re.sub(r'(?<!\d)\d{4}\s+(?:상반기|하반기)', short, new)
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
    out = Path(out) if out else HERE / f'OGQ_{per.slug()}_플레이북_초안.pptx'
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)

    # 5) 검수
    step(5, '검수 중')
    issues = qa.check(out, verbose=False)
    if dropped_rows:
        names = sorted({r for v in dropped_rows.values() for r in v})
        slides = ' · '.join(f'{n}장' for n in sorted(dropped_rows))
        warn.append(f'{slides} TOP25 표에서 {" · ".join(names)} 줄을 뺐습니다. '
                    f'그림을 눈으로 봐야 아는 값이라 데이터로 확인할 수 없어, 지난 판 값을 '
                    f'그대로 두는 대신 지웠습니다.')

    return Report(
        out=out, period=per.label, kind=per.kind, slug=per.slug(), rows=rows,
        changes=list(ch), issues=issues, warnings=warn,
        manual={k: dict(slides=sorted(set(v['slides'])), what=v['what'])
                for k, v in spec.MANUAL.items()},
        reject_month=month,
        reject_total=rj['reject.total'] if rj else 0,
        reject_other_pct=rj['reject.other_pct'] if rj else 0.0,
        changed_slides=sorted({c['slide'] for c in ch if c['slide']}),
        metric_count=len(flat),
        reference=reference,
    )


def available_reject_months(path):
    """반려 엑셀에 들어 있는 월 목록 (최근 순)."""
    import pandas as pd
    df = pd.read_excel(str(path), sheet_name=rj_mod.SHEET)
    return sorted(df['월'].astype(str).unique(), reverse=True)
