# -*- coding: utf-8 -*-
"""
Streamlit Cloud에서 apt(packages.txt)가 고장났을 때를 위한 우회 부트스트랩.
Chromium 실행에 필요한 .so 라이브러리를 데비안 풀에서 .deb로 직접 받아
~/.pwlibs 에 풀고 LD_LIBRARY_PATH 로 잡아준다. (apt 메타데이터 서명과 무관)
"""
import lzma
import os
import re
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

DEBIAN = "http://deb.debian.org/debian"
SUITES = ["trixie", "bookworm"]  # 이미지의 소스 순서대로 시도
LIB_DIR = Path.home() / ".pwlibs"
_PKG_INDEX = {}  # suite -> {pkg: filename}

# 로더 에러의 "libX.so.Y" → 데비안 패키지명
LIB2PKG = {
    "libglib-2.0.so.0": ["libglib2.0-0t64", "libglib2.0-0"],
    "libgobject-2.0.so.0": ["libglib2.0-0t64", "libglib2.0-0"],
    "libgio-2.0.so.0": ["libglib2.0-0t64", "libglib2.0-0"],
    "libgmodule-2.0.so.0": ["libglib2.0-0t64", "libglib2.0-0"],
    "libnss3.so": ["libnss3"], "libnssutil3.so": ["libnss3"], "libsmime3.so": ["libnss3"],
    "libssl3.so": ["libnss3"], "libnspr4.so": ["libnspr4"], "libplc4.so": ["libnspr4"],
    "libplds4.so": ["libnspr4"],
    "libdbus-1.so.3": ["libdbus-1-3"],
    "libatk-1.0.so.0": ["libatk1.0-0t64", "libatk1.0-0"],
    "libatk-bridge-2.0.so.0": ["libatk-bridge2.0-0t64", "libatk-bridge2.0-0"],
    "libatspi.so.0": ["libatspi2.0-0t64", "libatspi2.0-0"],
    "libcups.so.2": ["libcups2t64", "libcups2"],
    "libdrm.so.2": ["libdrm2"],
    "libxkbcommon.so.0": ["libxkbcommon0"],
    "libXcomposite.so.1": ["libxcomposite1"],
    "libXdamage.so.1": ["libxdamage1"],
    "libXfixes.so.3": ["libxfixes3"],
    "libXrandr.so.2": ["libxrandr2"],
    "libgbm.so.1": ["libgbm1"],
    "libasound.so.2": ["libasound2t64", "libasound2"],
    "libexpat.so.1": ["libexpat1"],
    "libX11.so.6": ["libx11-6"],
    "libX11-xcb.so.1": ["libx11-xcb1"],
    "libxcb.so.1": ["libxcb1"],
    "libXext.so.6": ["libxext6"],
    "libXi.so.6": ["libxi6"],
    "libXtst.so.6": ["libxtst6"],
    "libXrender.so.1": ["libxrender1"],
    "libXcursor.so.1": ["libxcursor1"],
    "libpango-1.0.so.0": ["libpango-1.0-0"],
    "libpangocairo-1.0.so.0": ["libpangocairo-1.0-0"],
    "libcairo.so.2": ["libcairo2"],
    "libfontconfig.so.1": ["libfontconfig1"],
    "libfreetype.so.6": ["libfreetype6"],
    "libudev.so.1": ["libudev1"],
    "libpcre2-8.so.0": ["libpcre2-8-0"],
    "libffi.so.8": ["libffi8"],
    "libmount.so.1": ["libmount1"],
    "libblkid.so.1": ["libblkid1"],
    "libselinux.so.1": ["libselinux1"],
    "libsystemd.so.0": ["libsystemd0"],
    "libavahi-common.so.3": ["libavahi-common3"],
    "libavahi-client.so.3": ["libavahi-client3"],
    "libgssapi_krb5.so.2": ["libgssapi-krb5-2"],
    "libkrb5.so.3": ["libkrb5-3"],
    "libk5crypto.so.3": ["libk5crypto3"],
    "libcom_err.so.2": ["libcom-err2"],
    "libkrb5support.so.0": ["libkrb5support0"],
    "libkeyutils.so.1": ["libkeyutils1"],
    "libwayland-server.so.0": ["libwayland-server0"],
    "libwayland-client.so.0": ["libwayland-client0"],
    "libxcb-randr.so.0": ["libxcb-randr0"],
    "libxcb-dri3.so.0": ["libxcb-dri3-0"],
    "libepoxy.so.0": ["libepoxy0"],
    "libharfbuzz.so.0": ["libharfbuzz0b"],
    "libfribidi.so.0": ["libfribidi0"],
    "libthai.so.0": ["libthai0"],
    "libdatrie.so.1": ["libdatrie1"],
    "libpixman-1.so.0": ["libpixman-1-0"],
    "libpng16.so.16": ["libpng16-16t64", "libpng16-16"],
    "libxcb-shm.so.0": ["libxcb-shm0"],
    "libxcb-render.so.0": ["libxcb-render0"],
    "libbrotlidec.so.1": ["libbrotli1"],
    "libbrotlicommon.so.1": ["libbrotli1"],
    "libbz2.so.1.0": ["libbz2-1.0"],
    "libgraphite2.so.3": ["libgraphite2-3"],
    "liblzma.so.5": ["liblzma5"],
    "libzstd.so.1": ["libzstd1"],
    "libcap.so.2": ["libcap2"],
    "libgcrypt.so.20": ["libgcrypt20"],
    "libgpg-error.so.0": ["libgpg-error0"],
}


def _load_index(suite):
    if suite in _PKG_INDEX:
        return _PKG_INDEX[suite]
    url = f"{DEBIAN}/dists/{suite}/main/binary-amd64/Packages.xz"
    raw = urllib.request.urlopen(url, timeout=120).read()
    text = lzma.decompress(raw).decode("utf-8", "replace")
    idx = {}
    pkg = None
    for line in text.splitlines():
        if line.startswith("Package: "):
            pkg = line[9:].strip()
        elif line.startswith("Filename: ") and pkg and pkg not in idx:
            idx[pkg] = line[10:].strip()
    _PKG_INDEX[suite] = idx
    return idx


def _extract_deb(deb_path: Path, dest: Path):
    """deb = ar 아카이브. dpkg-deb 있으면 그걸로, 없으면 순수 파이썬 ar+tar."""
    try:
        subprocess.run(["dpkg-deb", "-x", str(deb_path), str(dest)], check=True,
                       capture_output=True, timeout=120)
        return
    except Exception:
        pass
    data = deb_path.read_bytes()
    assert data[:8] == b"!<arch>\n", "not an ar archive"
    off = 8
    while off < len(data):
        name = data[off:off + 16].decode().strip()
        size = int(data[off + 48:off + 58].decode().strip())
        body = data[off + 60:off + 60 + size]
        if name.startswith("data.tar"):
            import io
            if name.endswith(".xz"):
                buf = io.BytesIO(lzma.decompress(body))
            elif name.endswith(".gz"):
                import gzip
                buf = io.BytesIO(gzip.decompress(body))
            elif name.endswith(".zst"):
                try:
                    from compression import zstd  # py3.14+
                    buf = io.BytesIO(zstd.decompress(body))
                except Exception:
                    import zstandard  # 있으면 사용
                    buf = io.BytesIO(zstandard.ZstdDecompressor().decompress(body))
            else:
                raise RuntimeError(f"unknown data member {name}")
            with tarfile.open(fileobj=buf) as t:
                t.extractall(dest)
            return
        off += 60 + size + (size % 2)
    raise RuntimeError("data.tar not found in deb")


def _install_pkg(pkg_names) -> bool:
    LIB_DIR.mkdir(exist_ok=True)
    for suite in SUITES:
        try:
            idx = _load_index(suite)
        except Exception:
            continue
        for pkg in pkg_names:
            fn = idx.get(pkg)
            if not fn:
                continue
            try:
                deb = LIB_DIR / os.path.basename(fn)
                if not deb.exists():
                    urllib.request.urlretrieve(f"{DEBIAN}/{fn}", deb)
                _extract_deb(deb, LIB_DIR)
                deb.unlink(missing_ok=True)
                return True
            except Exception:
                continue
    return False


def _lib_paths():
    cands = [LIB_DIR / "usr/lib/x86_64-linux-gnu", LIB_DIR / "lib/x86_64-linux-gnu",
             LIB_DIR / "usr/lib", LIB_DIR / "lib"]
    return [str(p) for p in cands if p.is_dir()]


def _apply_env():
    paths = _lib_paths()
    if not paths:
        return
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [p for p in paths if p not in cur]
    if parts:
        os.environ["LD_LIBRARY_PATH"] = ":".join(parts + ([cur] if cur else []))


def _try_launch():
    """크로뮴 실행 시도. 성공→None, 실패→빠진 lib 이름 또는 'unknown: ...'"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            b.close()
        return None
    except Exception as e:
        m = re.search(r"error while loading shared libraries: (\S+?):", str(e))
        if m:
            return m.group(1)
        return f"unknown: {str(e)[:300]}"


def ensure_chromium_runs(progress=lambda msg: None, max_iter=40):
    """
    설치된 Chromium이 실제로 뜰 때까지 빠진 라이브러리를 하나씩 채운다.
    반환: (성공여부, 마지막 메시지)
    """
    if sys.platform == "darwin":
        return True, "mac"
    _apply_env()
    seen = set()
    for i in range(max_iter):
        missing = _try_launch()
        if missing is None:
            return True, "ok"
        if missing.startswith("unknown"):
            return False, missing
        if missing in seen:
            return False, f"{missing} 설치 실패(반복)"
        seen.add(missing)
        progress(f"라이브러리 준비 중… ({missing})")
        pkgs = LIB2PKG.get(missing)
        if not pkgs:
            base = re.sub(r"\.so[.\d]*$", "", missing).lower().replace("_", "-")
            m = re.search(r"\.so\.(\d+)", missing)
            maj = m.group(1) if m else ""
            pkgs = [f"{base}{maj}t64", f"{base}{maj}", f"{base}-{maj}", base]
        if not _install_pkg(pkgs):
            return False, f"{missing} 를 제공하는 패키지를 찾지 못함({pkgs})"
        _apply_env()
    return False, "반복 한도 초과"
