# -*- coding: utf-8 -*-
"""웹앱이 실제로 도는지 확인한다.

 1) 배너 생성기 앱을 통째로 실행해 세 탭이 예외 없이 그려지는지 (Streamlit AppTest)
 2) 업로드된 파일을 받아 pptx가 나오기까지의 경로 (tab.py가 쓰는 함수 그대로)

  python3 -m playbook.test_app <NOM.xlsx> <SOM.xlsx> <COM.xlsx> [stats.xlsx]
"""
import sys, tempfile
from pathlib import Path


class FakeUpload:
    """streamlit의 UploadedFile 흉내 — tab._save가 쓰는 것만."""
    def __init__(self, path):
        self.name = Path(path).name
        self._b = Path(path).read_bytes()

    def getbuffer(self):
        return self._b


def test_script_runs():
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parent.parent
    at = AppTest.from_file(str(root / 'web_app.py'), default_timeout=180).run()
    assert not at.exception, f'앱 실행 중 예외: {at.exception}'
    print(f'  탭 {len(at.tabs)}개 · 예외 없음')
    return True


def test_upload_flow(xlsx, stats=None):
    from playbook import tab as T
    from playbook import build as B

    workdir = Path(tempfile.mkdtemp(prefix='ogq_uitest_'))
    paths = T._save([FakeUpload(p) for p in xlsx], workdir)
    guessed = T._guess(paths)
    unknown = [p.name for p, m in guessed.items() if m is None]
    assert not unknown, f'마켓을 못 알아낸 파일: {unknown}'
    print(f'  마켓 인식: {[(p.name, m) for p, m in guessed.items()]}')

    reject_path, month = None, None
    if stats:
        reject_path = workdir / Path(stats).name
        reject_path.write_bytes(Path(stats).read_bytes())
        month = B.available_reject_months(reject_path)[0]
        print(f'  반려 월: {month}')

    r = B.build(list(guessed.keys()), reject_path, month, out=workdir / 'out.pptx')
    size = r.out.stat().st_size
    assert size > 1_000_000, f'결과물이 너무 작습니다: {size}바이트'

    from pptx import Presentation
    n = len(Presentation(str(r.out)).slides)
    assert n == 39, f'슬라이드가 39장이 아닙니다: {n}장'

    md = r.changelog_md()
    assert md.startswith('#'), '변경내역이 비었습니다'

    print(f'  {r.period} · {n}장 · {size/1e6:.1f}MB · 변경 {len(r.changes)}건 · '
          f'검수 지적 {len(r.issues)}건')
    if r.warnings:
        for w in r.warnings:
            print(f'  ! {w}')
    return True


if __name__ == '__main__':
    args = sys.argv[1:]
    xlsx = [a for a in args if 'statistic' not in a.lower()]
    stats = next((a for a in args if 'statistic' in a.lower()), None)

    print('1. 앱 화면 그리기')
    test_script_runs()
    print('2. 파일 올리기 → PPT 생성')
    test_upload_flow(xlsx, stats)
    print('\n통과')
