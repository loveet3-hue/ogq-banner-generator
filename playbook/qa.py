# -*- coding: utf-8 -*-
"""결과물 검수. 배포 원칙 위반과 레이아웃 사고를 잡는다."""
import re
from pptx import Presentation
from pptx.util import Emu

# 크리에이터 배포용 덱 금지: 절대 매출액·건수·구매자 수
MONEY = re.compile(r'(?<![\d.])\d{1,3}(?:,\d{3})+\s*원|\d+\s*억\s*원|\d+\s*만\s*원')
COUNTISH = re.compile(r'(?<![\d.])\d{1,3}(?:,\d{3})+\s*(건|명|종|개)(?!\s*\))')

# 반려 건수처럼 내부 심사 통계는 허용(크리에이터에게 알려주는 게 목적)
ALLOW_CONTEXT = ('반려', '심사')
# 심사 반려 섹션은 슬라이드 전체가 건수 이야기다 — 여기선 절대 수량을 허용한다.
# (매출·구매자 수와 달리 반려 건수는 크리에이터에게 알려주려고 넣는 값이다)
ALLOW_SLIDES = (36, 37)


def check(path, verbose=True):
    prs = Presentation(path)
    issues = []
    for si, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            t = sh.text_frame.text.strip()
            if not t:
                continue
            if si in ALLOW_SLIDES or any(a in t for a in ALLOW_CONTEXT):
                continue
            for pat, kind in ((MONEY, '절대 금액'), (COUNTISH, '절대 수량')):
                m = pat.search(t)
                if m:
                    issues.append((si, kind, m.group(), t[:60]))

            # 카드 밖으로 나간 텍스트
            if Emu(sh.left).inches < -0.05 or Emu(sh.top).inches < -0.05:
                issues.append((si, '캔버스 이탈', '', t[:40]))
            if Emu(sh.left).inches + Emu(sh.width).inches > 13.4:
                issues.append((si, '오른쪽 넘침', '', t[:40]))
            if Emu(sh.top).inches + Emu(sh.height).inches > 7.6:
                issues.append((si, '아래쪽 넘침', '', t[:40]))

    # 비율 값이 범위를 벗어났는지
    for si, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%', sh.text_frame.text):
                v = float(m.group(1))
                if v > 100.5:
                    issues.append((si, '비율 100% 초과', m.group(), ''))

    if verbose:
        if not issues:
            print('검수 통과 — 배포 원칙 위반/레이아웃 이탈 없음')
        else:
            print(f'검수 지적 {len(issues)}건')
            for si, kind, val, ctx in issues[:40]:
                print(f'  slide {si:2d}  [{kind}] {val}  {ctx}')
    return issues


if __name__ == '__main__':
    import sys
    raise SystemExit(1 if check(sys.argv[1]) else 0)
