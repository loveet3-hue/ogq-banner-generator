# OGQ 크리에이터 인터뷰 카드뉴스 생성기

네이버 폼 설문 응답 엑셀(.xlsx)을 넣으면 인스타그램 카드뉴스 PNG와
게시글 캡션(caption.txt), 블로그 글(blog.txt)을 자동으로 만들어주는 도구입니다.

## 빠른 시작 (개발 지식 없어도 OK)

### Windows
1. **파이썬 설치** — https://www.python.org/downloads/
   (설치 화면에서 **"Add Python to PATH"** 체크 필수!)
2. **`1_설치.bat` 더블클릭** — 최초 1회만
3. **`2_카드뉴스만들기.bat` 더블클릭** — 엑셀 드래그 → Enter 몇 번이면 끝

### Mac
1. **파이썬 설치** — https://www.python.org/downloads/
2. **터미널을 열고** 이 폴더로 이동한 뒤 아래 실행 (최초 1회):
   ```
   chmod +x *.command
   ```
3. 이후 **`1_설치_맥용.command` 더블클릭** (최초 1회) →
   **`2_카드뉴스만들기_맥용.command` 더블클릭**
   - "확인되지 않은 개발자" 경고가 뜨면: 파일 우클릭 → 열기

### 생성되는 것 (응답자마다)
- 카드뉴스 PNG (표지 + Q&A 카드)
- `banners/` 홍보 배너 5종 (824x464, 640x360, 1440x180, 350x200, 984x552)
- caption.txt (인스타 캡션) / blog.txt (블로그 글)

### 핵심 사용법
- 네이버 폼 응답 엑셀만 있으면 됩니다. **응답에 OGQ 마켓 링크가 포함되어 있으면
  어느 컬럼이든 자동으로 찾아서** 크리에이터명 + 캐릭터 이미지를 반영합니다.
- 여러 명 응답이면 **전원 일괄 생성** (각자 폴더로 분리)
- 배경 테마는 기본값(auto)일 때 **크리에이터마다 다르게 자동 배정**됩니다

## 다른 사람에게 공유하는 법

이 폴더 전체를 압축(zip)해서 전달하면 됩니다.
받은 사람은 위 "빠른 시작" 1~3번만 따라 하면 바로 쓸 수 있습니다.
(`output/` 폴더와 `assets/ogq/` 캐시는 지우고 압축하면 용량이 줄어요)

## 1. 설치 (터미널 사용 시)

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 2. 폰트 준비

`fonts/` 폴더에 폰트 파일을 넣으세요. 추천 무료 폰트:

| 용도 | 폰트 | 다운로드 |
|---|---|---|
| 표지 제목 (통통한 느낌) | 카페24 써라운드 | https://fonts.cafe24.com/ |
| 부제 손글씨 | 온글잎 계열 손글씨체 | https://ownglyph.com/ |
| 본문 (말풍선) | 프리텐다드 Regular/Bold | https://github.com/orioncactus/pretendard/releases |

파일명은 `config.yaml`의 `fonts:` 항목과 일치시키면 됩니다.
폰트가 없으면 시스템 기본 한글 폰트(Malgun Gothic)로 자동 대체됩니다(경고만 출력).

## 3. 이미지 준비

`assets/` 폴더에 아래 PNG를 넣으세요 (배경 투명 권장):

- `interviewer.png` — 인터뷰어 캐릭터 (표지 + 질문 말풍선 아바타)
- `creator_avatar.png` — 크리에이터 말풍선용 아바타
- `creator_main.png` — 표지 하단 대표 이미지

테스트용 플레이스홀더 이미지와 샘플 엑셀은 아래 명령으로 생성할 수 있습니다:

```bash
python make_sample.py
```

## 4. 설정 (config.yaml)

- `month`, `year`, `creator_name` — 표지에 들어갈 정보
- `questions` — **엑셀 컬럼명 → 카드에 표시할 질문 문구** 매핑. 순서대로 카드에 들어갑니다.
  네이버 폼의 질문 제목을 `column` 값과 정확히 일치시키면 자동 매핑됩니다.
- `name_column` — (선택) 크리에이터 이름이 담긴 엑셀 컬럼. `--all` 일괄 생성 시 폴더 구분에 사용
- `caption` — 캡션 인사말과 해시태그

questions에 없는 엑셀 컬럼(타임스탬프, 이메일 등)은 무시되고,
답변이 비어 있는 질문은 카드에서 자동 제외됩니다.

## 5. 실행

```bash
# 첫 번째 응답자(0번)로 생성
python make_cards.py --excel responses.xlsx --row 0 --config config.yaml

# 모든 응답자를 각각 폴더로 일괄 생성
python make_cards.py --excel responses.xlsx --all

# preview.html도 함께 생성 (브라우저에서 전체 카드 한눈에 보기)
python make_cards.py --excel responses.xlsx --row 0 --preview

# OGQ 마켓 링크로 크리에이터명 + 캐릭터 이미지 자동 반영
python make_cards.py --excel responses.xlsx --creator-url "https://ogqmarket.naver.com/artworks/sticker/detail?artworkId=..."

# 배경 테마 지정 (mint / pink / lavender / sky / cream / peach / random)
python make_cards.py --excel responses.xlsx --theme pink
```

## 배경 테마

`--theme` 옵션 또는 config.yaml의 `theme:` 항목으로 배경색을 바꿀 수 있습니다.

| 테마 | 색감 |
|---|---|
| `mint` | 연한 민트그린 (기본) |
| `pink` | 연핑크 |
| `lavender` | 연보라 |
| `sky` | 하늘색 |
| `cream` | 크림 베이지 |
| `peach` | 피치 |
| `random` | 실행할 때마다 무작위 선택 |
| `auto` | **크리에이터마다 다른 테마 + 장식 배치 자동 배정 (기본)** |

커스텀 색상: `theme: { bg: "#C9E7DB", blob: "#E4F4EC", shadow: "90, 140, 115" }`

## 6. 출력

```
output/{크리에이터명}/
├── 01_cover.png      # 표지
├── 02_qa.png         # Q&A 카드 (채팅 UI 스타일)
├── 03_qa.png
├── ...
├── caption.txt       # 인스타 게시글 캡션 (해시태그 포함)
└── preview.html      # --preview 옵션 시
```

## 네이버 블로그 임시저장 자동화

생성된 인터뷰(제목+본문+카드뉴스 이미지)를 블로그 글쓰기 화면에 자동 입력하고
**임시저장**까지 해줍니다. (발행은 절대 자동으로 하지 않음 — 확인 후 직접 발행하세요)

- **Windows**: `3_블로그올리기.bat` 더블클릭 → 폴더명(예: 호록)과 블로그 아이디 입력
- **Mac**: `3_블로그올리기_맥용.command` 더블클릭
- 터미널: `python blog_upload.py --folder "output/호록" --blog-id 네이버아이디`

주의사항:
- **최초 1회는 열리는 브라우저 창에서 직접 네이버 로그인** (세션이 `browser_profile/`에
  저장되어 그 다음부터는 자동)
- 저장 후 블로그 관리 > 임시저장 글에서 내용 확인 후 발행
- 네이버 에디터 구조가 바뀌면 동작하지 않을 수 있습니다 → blog.txt 수동 복붙으로 대체

## 동작 방식

- HTML/CSS 템플릿(Jinja2)을 Playwright headless Chromium에서 1080×1350으로 렌더 후 PNG 캡처
- 답변이 길면 문장 경계로 말풍선을 나누고, **브라우저에서 실제 픽셀 높이를 측정**해
  카드가 넘치지 않게 자동 분배 (질문 말풍선은 반드시 첫 답변과 같은 카드에 배치)
- 말풍선 텍스트는 한글 단어 단위 줄바꿈 (`word-break: keep-all`)

## 문제 해결

- **컬럼 매칭 실패** — 실행 시 어떤 컬럼이 엑셀에서 발견되지 않았는지, 엑셀에 실제로 어떤
  컬럼이 있는지 출력됩니다. 네이버 폼 질문 제목과 config의 `column` 값을 맞춰주세요.
- **이미지 없음** — 어떤 파일이 없는지 명확한 에러가 출력됩니다.
- **디자인 수정** — `templates/cover.html`, `templates/qa.html`의 CSS를 수정하면 됩니다.
