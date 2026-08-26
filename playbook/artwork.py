# -*- coding: utf-8 -*-
"""콘텐츠ID로 OGQ마켓에서 실제 콘텐츠를 가져와 속성을 뽑는다 (13·20·27장).

매출 데이터에는 '무엇이 팔렸는지'만 있고 '그게 어떻게 생겼는지'는 없다.
그래서 콘텐츠ID로 마켓을 조회해 제목·태그·스티커 이미지를 받아 온다.
  https://ogqmarket.naver.com/artworks/sticker/detail?artworkId=<콘텐츠ID>

여기서 뽑는 것은 **계산으로 알 수 있는 것과 태그로 알 수 있는 것**뿐이다.
글자가 몇 장에 들어갔는지, 선이 굵은지 같은 건 이미지를 눈으로 봐야 알 수 있어
여기서 다루지 않는다(build.py가 그 항목은 손대지 않고 경고를 띄운다).
"""
import concurrent.futures as cf
import io
import json
import sys
import tempfile
from pathlib import Path

CACHE_DIR = Path(tempfile.gettempdir()) / 'ogq_playbook_artwork'
SAMPLE_STICKERS = 8      # 24장 다 받으면 느리고 무겁다. 표본으로 충분하다.
TIMEOUT = 15


# ---------------------------------------------------------------- 마켓 조회
def _bg():
    """배너 생성기의 OGQ 조회 코드를 그대로 쓴다."""
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    argv, sys.argv = sys.argv, ['playbook']   # banner_gen이 argparse를 건드린다
    try:
        import banner_gen
        return banner_gen
    finally:
        sys.argv = argv


def fetch(content_id):
    """→ {'title','tags','stickers',...} / 못 찾으면 None"""
    cid = str(content_id)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta = CACHE_DIR / f'{cid}.json'
    if meta.exists():
        d = json.loads(meta.read_text(encoding='utf-8'))
        return None if d.get('error') else d
    try:
        a = _bg().fetch_artwork(cid)
        d = {'id': cid, 'title': a['title'], 'tags': a['tags'],
             'stickers': a['stickers'][:SAMPLE_STICKERS],
             'description': a['description'][:300]}
    except Exception as e:
        d = {'id': cid, 'error': f'{type(e).__name__}: {e}'[:120]}
    meta.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    return None if d.get('error') else d


def fetch_many(content_ids, workers=6, progress=None):
    """여러 콘텐츠를 한꺼번에. → {콘텐츠ID: 정보}"""
    ids = [str(c) for c in content_ids]
    out, done = {}, 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for cid, d in zip(ids, ex.map(fetch, ids)):
            done += 1
            if progress:
                progress(done, len(ids))
            if d:
                out[cid] = d
    return out


# ---------------------------------------------------------------- 이미지 분석
def _load_image(url):
    import hashlib
    import requests
    from PIL import Image
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # 파일명으로 캐시하면 안 된다. 모든 콘텐츠의 스티커가 original_1.gif 처럼
    # 같은 이름을 쓰고 콘텐츠ID는 경로에만 있어서, 전부 같은 파일로 덮인다.
    f = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + '.bin')
    if not f.exists():
        r = requests.get(url, headers=_bg().UA, timeout=TIMEOUT)
        r.raise_for_status()
        f.write_bytes(r.content)
    return Image.open(io.BytesIO(f.read_bytes()))


def image_stats(urls):
    """스티커 표본에서 계산으로 알 수 있는 것만 뽑는다.

    → {'animated_ratio': 0~1, 'transparent_ratio': 0~1,
       'saturation': 0~1, 'value': 0~1, 'n': 표본 수}
    """
    import numpy as np
    anim, trans, sat, val, chroma, csat = [], [], [], [], [], []
    for u in urls:
        try:
            im = _load_image(u)
        except Exception:
            continue
        anim.append(1.0 if getattr(im, 'is_animated', False) else 0.0)
        arr = np.asarray(im.convert('RGBA'), dtype=np.float32) / 255.0
        a = arr[..., 3]
        trans.append(float((a < 0.05).mean()))
        solid = a > 0.5
        if solid.sum() < 16:
            continue
        rgb = arr[..., :3][solid]
        mx, mn = rgb.max(1), rgb.min(1)
        s_pix = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        sat.append(float(s_pix.mean()))
        val.append(float(mx.mean()))
        # 평균 채도만 보면 흰 여백이 많은 그림이 전부 '무채색'이 된다.
        # 사람은 '연한 분홍 캐릭터'를 파스텔이라 부르므로, 색이 있는 픽셀만 따로 잰다.
        colored = s_pix > 0.15
        chroma.append(float(colored.mean()))
        csat.append(float(s_pix[colored].mean()) if colored.any() else 0.0)
    if not anim:
        return None
    mean = lambda xs: float(sum(xs) / len(xs)) if xs else 0.0
    return {'animated_ratio': mean(anim), 'transparent_ratio': mean(trans),
            'saturation': mean(sat), 'value': mean(val),
            'chroma_ratio': mean(chroma), 'chroma_sat': mean(csat), 'n': len(anim)}


def analyze(info):
    """조회 결과 + 이미지 → 속성 계산에 필요한 원자료."""
    stats = image_stats(info.get('stickers', []))
    return {**info, 'stats': stats}


def analyze_many(infos, workers=4, progress=None):
    out, done = {}, 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(analyze, v): k for k, v in infos.items()}
        for fu in cf.as_completed(futs):
            done += 1
            if progress:
                progress(done, len(futs))
            try:
                out[futs[fu]] = fu.result()
            except Exception:
                out[futs[fu]] = {**infos[futs[fu]], 'stats': None}
    return out
