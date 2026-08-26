# -*- coding: utf-8 -*-
"""특정 슬라이드만 뽑아 png로 렌더한다 (이 맥에 LibreOffice가 없어 QuickLook을 쓴다).

  python preview.py 결과물.pptx 16 23 36
  → preview/s16.png ...

주의: QuickLook은 원형·도넛 도형과 차트 객체를 제대로 못 그린다. 이 덱은 모든
차트를 사각형으로 작도해서 문제가 없다.
"""
import copy, shutil, subprocess, sys
from pathlib import Path
from pptx import Presentation


def keep_only(src, idx, dst):
    prs = Presentation(src)
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    for i, s in enumerate(slides):
        if i != idx:
            prs.part.drop_rel(s.rId)
            xml_slides.remove(s)
    prs.save(dst)


def render(pptx, numbers, outdir='preview'):
    src = Path(pptx)
    out = Path(outdir)
    out.mkdir(exist_ok=True)
    tmp = out / '_tmp'
    tmp.mkdir(exist_ok=True)
    made = []
    for n in numbers:
        one = tmp / f's{n}.pptx'
        keep_only(src, n - 1, one)
        subprocess.run(['qlmanage', '-t', '-s', '1600', '-o', str(tmp), str(one)],
                       capture_output=True)
        png = tmp / f's{n}.pptx.png'
        if png.exists():
            shutil.move(str(png), str(out / f's{n}.png'))
            made.append(out / f's{n}.png')
    shutil.rmtree(tmp, ignore_errors=True)
    return made


if __name__ == '__main__':
    made = render(sys.argv[1], [int(x) for x in sys.argv[2:]])
    for m in made:
        print(m)
