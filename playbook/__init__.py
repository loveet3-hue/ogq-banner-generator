# -*- coding: utf-8 -*-
"""OGQ 플레이북 생성기 — 매출 엑셀 → 플레이북 초안 pptx.

웹앱에서:   from playbook import tab;  tab.render()
터미널에서: python3 -m playbook.run <엑셀들> --reject <통계엑셀>

여기서 하위 모듈을 미리 불러오지 않는다. `from .build import build` 처럼 쓰면
`playbook.build`가 모듈이 아니라 함수를 가리키게 되어 `from . import build`가 깨진다.
게다가 pandas·python-pptx는 무거워서, 배너 생성기만 쓰는 사람이 그 비용을 낼 이유가 없다.
"""
__all__ = ['tab', 'build', 'ingest', 'metrics', 'reject', 'fill', 'spec',
           'qa', 'config', 'overrides', 'drive_source']
