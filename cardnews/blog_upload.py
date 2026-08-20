# -*- coding: utf-8 -*-
"""
네이버 블로그 임시저장 자동화 (베타)

생성된 인터뷰(blog.txt + 카드뉴스 이미지)를 네이버 블로그 글쓰기 화면에 자동 입력하고
'저장'(임시저장) 버튼까지 눌러준다. ※ 발행은 절대 하지 않음 — 발행은 직접 확인 후 수동으로!

사용법:
    python blog_upload.py --folder "output/호록" --blog-id 네이버아이디

- 최초 1회는 자동으로 열리는 브라우저 창에서 직접 네이버에 로그인해주세요.
  로그인 세션은 browser_profile/ 폴더에 저장되어 다음부터는 자동입니다.
- 네이버 에디터 구조가 바뀌면 동작하지 않을 수 있습니다 (그 경우 blog.txt 수동 복붙).
"""

import argparse
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "browser_profile"


def die(msg):
    print(f"[오류] {msg}", flush=True)
    sys.exit(1)


def info(msg):
    print(f"[안내] {msg}", flush=True)


def try_click(page, selector, timeout=3000, desc=""):
    """있으면 누르고 없으면 조용히 넘어가는 클릭"""
    try:
        page.locator(selector).first.click(timeout=timeout)
        if desc:
            info(f"{desc} 닫음")
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="네이버 블로그 임시저장 자동화 (베타)")
    ap.add_argument("--folder", required=True, help="output/크리에이터명 폴더 경로")
    ap.add_argument("--blog-id", required=True, help="네이버 블로그 아이디")
    ap.add_argument("--no-images", action="store_true", help="이미지 첨부 생략")
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = BASE_DIR / folder
    blog_txt = folder / "blog.txt"
    if not blog_txt.exists():
        die(f"blog.txt가 없습니다: {blog_txt}\n먼저 make_cards.py로 카드뉴스를 생성하세요.")

    lines = blog_txt.read_text(encoding="utf-8").splitlines()
    title = lines[0].strip()
    body_lines = [l for l in lines[1:]]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    images = sorted(folder.glob("*.png")) if not args.no_images else []

    info(f"제목: {title}")
    info(f"본문 {len(body_lines)}줄, 이미지 {len(images)}장")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, slow_mo=80,
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # JS 대화상자(alert/confirm)는 조용히 닫는다 — 자동 처리 충돌 방지
        def on_dialog(dialog):
            try:
                dialog.dismiss()
            except Exception:
                pass
        page.on("dialog", on_dialog)

        write_url = f"https://blog.naver.com/{args.blog_id}/postwrite"
        info("블로그 글쓰기 페이지로 이동 중...")
        try:
            page.goto(write_url, wait_until="domcontentloaded")
        except Exception:
            pass
        time.sleep(3)

        # 로그인 안 되어 있으면 로그인 페이지로 튕김 → 사용자가 직접 로그인할 때까지 대기
        if "postwrite" not in page.url:
            print("\n" + "=" * 50)
            print("  브라우저 창에서 네이버에 직접 로그인해주세요!")
            print("  (로그인하면 자동으로 계속 진행됩니다. 최대 5분 대기)")
            print("=" * 50 + "\n", flush=True)
            deadline = time.time() + 300
            while time.time() < deadline:
                time.sleep(5)
                if "postwrite" in page.url:
                    break
                # 로그인 페이지가 아니게 됐으면(=로그인 완료) 글쓰기 페이지로 재이동
                if "nid.naver.com" not in page.url:
                    try:
                        page.goto(write_url, wait_until="domcontentloaded")
                        time.sleep(3)
                    except Exception:
                        time.sleep(2)
            if "postwrite" not in page.url:
                die("로그인이 확인되지 않았습니다. 다시 실행해주세요.")
        info("에디터 로드 대기 중...")
        page.wait_for_timeout(5000)

        # 팝업 정리: 이어쓰기 취소, 도움말 닫기
        try_click(page, ".se-popup-button-cancel", desc="이어쓰기 팝업")
        try_click(page, ".se-help-panel-close-button", desc="도움말 패널")

        # 제목 입력
        info("제목 입력 중...")
        try:
            page.locator(".se-documentTitle .se-text-paragraph").first.click(timeout=8000)
        except Exception:
            die("에디터 제목 영역을 찾지 못했습니다. 네이버 에디터가 변경된 것 같습니다.\n"
            "blog.txt 내용을 직접 복사해 붙여넣어 주세요.")
        page.keyboard.type(title, delay=10)

        # 본문 입력
        info("본문 입력 중...")
        page.locator(".se-component.se-text .se-text-paragraph").last.click(timeout=8000)
        for line in body_lines:
            if line.strip():
                page.keyboard.type(line, delay=5)
            page.keyboard.press("Enter")

        # 이미지 첨부
        if images:
            info(f"카드뉴스 이미지 {len(images)}장 첨부 중...")
            try:
                with page.expect_file_chooser(timeout=10000) as fc:
                    page.locator("button[data-name='image'], .se-image-toolbar-button").first.click()
                fc.value.set_files([str(p) for p in images])
                page.wait_for_timeout(1000 + 1500 * len(images))  # 업로드 대기
            except Exception as e:
                print(f"[경고] 이미지 자동 첨부 실패 — 직접 첨부해주세요. ({e})")

        # 임시저장 (발행 아님!)
        info("임시저장 버튼 클릭...")
        saved = False
        for sel in ["button:has-text('저장'):not(:has-text('발행'))",
                    "[class*='save_btn']"]:
            if try_click(page, sel, timeout=5000):
                saved = True
                break
        page.wait_for_timeout(3000)

        if saved:
            print("\n✅ 임시저장 완료! 블로그 관리 > 임시저장 글에서 확인 후 직접 발행하세요.")
        else:
            print("\n⚠ 저장 버튼을 찾지 못했습니다. 브라우저에서 '저장'을 직접 눌러주세요.")
            print("  (30초 후 브라우저가 닫힙니다 — 그 안에 눌러주세요)")
            page.wait_for_timeout(30000)

        ctx.close()


if __name__ == "__main__":
    main()
