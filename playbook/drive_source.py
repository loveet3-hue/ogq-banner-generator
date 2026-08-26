# -*- coding: utf-8 -*-
"""구글 드라이브 폴더에서 매출 파일을 가져오는 모드.

드라이브 폴더에 파일을 넣어두면 앱이 알아서 찾아 읽고, 만든 PPT를 같은 폴더에
다시 올려 준다.

**한 번만 해두면 되는 준비** (설정이 없으면 화면에 안내가 뜬다):
 1. Google Cloud Console에서 서비스 계정을 만들고 JSON 키를 받는다
 2. Drive API를 켠다
 3. 드라이브 폴더를 그 서비스 계정 이메일에 '편집자'로 공유한다
 4. JSON을 `.streamlit/secrets.toml`의 [gcp_service_account]에 넣고,
    폴더 ID를 drive_folder_id 에 적는다

서비스 계정 키는 비밀번호와 같다. 앱에는 secrets로만 넣고 깃에 올리지 않는다
(.gitignore에 이미 넣어 두었다).
"""
import io
import re
from pathlib import Path

import streamlit as st

SCOPES = ['https://www.googleapis.com/auth/drive']
XLSX_MIME = ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             'application/vnd.google-apps.spreadsheet')
PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'

SETUP_GUIDE = """
### 준비가 아직 안 되어 있습니다

드라이브에서 바로 읽으려면 **서비스 계정**을 한 번 만들어야 합니다. 이건 구글 계정
비밀번호를 다루는 일이라 제가 대신 해드릴 수 없고, 아래대로 5분이면 됩니다.

1. [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 만들기
2. **API 및 서비스 → 라이브러리** → `Google Drive API` 사용 설정
3. **사용자 인증 정보 → 서비스 계정 만들기** → 만든 계정의 **키 → 키 추가 → JSON**
4. 매출 파일을 넣어 둘 드라이브 폴더를 그 서비스 계정 이메일
   (`...@....iam.gserviceaccount.com`)에 **편집자**로 공유
5. 받은 JSON을 이 폴더의 `.streamlit/secrets.toml`에 아래 형태로 붙여넣기

```toml
drive_folder_id = "드라이브 폴더 URL의 folders/ 뒤 문자열"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

Streamlit Cloud에 올릴 때는 앱 설정의 **Secrets** 칸에 같은 내용을 넣으면 됩니다.

설정하기 전까지는 왼쪽 **파일 올리기** 탭을 쓰시면 똑같이 동작합니다.
"""


def _secret(key, default=None):
    """secrets.toml이 아예 없으면 st.secrets는 예외를 던진다 — 없는 것도 정상이다."""
    try:
        return st.secrets[key]
    except Exception:
        return default


def _service():
    """서비스 계정으로 Drive API 클라이언트를 만든다. 설정이 없으면 None."""
    info = _secret('gcp_service_account')
    if not info:
        return None
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build as gbuild
    creds = Credentials.from_service_account_info(dict(info), scopes=SCOPES)
    return gbuild('drive', 'v3', credentials=creds, cache_discovery=False)


def list_xlsx(svc, folder_id):
    """폴더 안의 엑셀 파일 목록 (최근 수정 순)."""
    q = (f"'{folder_id}' in parents and trashed = false and ("
         + ' or '.join(f"mimeType = '{m}'" for m in XLSX_MIME) + ')')
    res = svc.files().list(q=q, orderBy='modifiedTime desc', pageSize=100,
                           fields='files(id,name,modifiedTime,size,mimeType)').execute()
    return res.get('files', [])


def download(svc, file_id, name, mime, dest_dir):
    """드라이브 파일을 내려받는다. 구글 시트면 xlsx로 변환해서 받는다."""
    from googleapiclient.http import MediaIoBaseDownload
    dest = Path(dest_dir) / (name if name.endswith('.xlsx') else f'{name}.xlsx')
    if mime == 'application/vnd.google-apps.spreadsheet':
        req = svc.files().export_media(
            fileId=file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        req = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest.write_bytes(buf.getvalue())
    return dest


def upload(svc, path, folder_id):
    """만든 PPT를 같은 폴더에 올린다. 같은 이름이 있으면 새 버전으로 덮어쓴다."""
    from googleapiclient.http import MediaFileUpload
    path = Path(path)
    media = MediaFileUpload(str(path), mimetype=PPTX_MIME, resumable=True)
    q = (f"'{folder_id}' in parents and trashed = false and "
         f"name = '{path.name}'")
    found = svc.files().list(q=q, fields='files(id)').execute().get('files', [])
    if found:
        f = svc.files().update(fileId=found[0]['id'], media_body=media,
                               fields='id,webViewLink').execute()
    else:
        f = svc.files().create(body={'name': path.name, 'parents': [folder_id]},
                               media_body=media, fields='id,webViewLink').execute()
    return f.get('webViewLink')


# 파일명에서 마켓 알아내기 — ingest와 같은 규칙
_MARKET_PAT = {'NOM': r'NOM|네이버|naver', 'SOM': r'SOM|SOOP|숲|아프리카', 'COM': r'COM|채팅'}


def classify(files):
    """드라이브 파일 목록 → {마켓: 파일} + 반려 통계 파일. 같은 마켓이면 최신 것."""
    sales, stats = {}, None
    for f in files:
        n = f['name']
        if re.search(r'statistic|통계', n, re.I):
            stats = stats or f
            continue
        for m, pat in _MARKET_PAT.items():
            if re.search(pat, n, re.I):
                sales.setdefault(m, f)      # 목록이 최신순이라 먼저 걸린 게 최신
                break
    return sales, stats


def render(workdir, run_build, render_report):
    svc = _service()
    if svc is None:
        st.markdown(SETUP_GUIDE)
        return

    folder_id = _secret('drive_folder_id', '') or ''
    folder_id = st.text_input('드라이브 폴더 ID', value=folder_id,
                              help='폴더 URL의 folders/ 뒤에 붙은 문자열')
    if not folder_id:
        st.info('매출 파일을 넣어 둔 드라이브 폴더 ID를 넣어 주세요.')
        return

    try:
        files = list_xlsx(svc, folder_id)
    except Exception as e:
        st.error(f'폴더를 읽지 못했습니다. 서비스 계정에 공유가 되어 있는지 확인해 주세요.\n\n{e}')
        return

    if not files:
        st.warning('폴더에 엑셀 파일이 없습니다.')
        return

    sales, stats = classify(files)
    st.write('**폴더에서 찾은 파일**')
    for m in ('NOM', 'SOM', 'COM'):
        if m in sales:
            f = sales[m]
            st.write(f'✅ {m} — `{f["name"]}` · {f["modifiedTime"][:10]}')
        else:
            st.write(f'❌ {m} — 못 찾았습니다')
    if stats:
        st.write(f'✅ 심사 반려 — `{stats["name"]}` · {stats["modifiedTime"][:10]}')
    else:
        st.write('➖ 심사 반려 통계 파일 없음 (36·37장은 이전 판 그대로)')

    ready = len(sales) == 3
    if not ready:
        st.warning('파일명에 NOM / SOM / COM(또는 네이버 / SOOP / 채팅)이 들어가야 '
                   '어느 마켓인지 알 수 있습니다.')

    back = st.checkbox('만든 PPT를 같은 폴더에 다시 올리기', value=True)

    if st.button('PPT 만들기', type='primary', disabled=not ready,
                 use_container_width=True, key='go_drive'):
        with st.spinner('드라이브에서 내려받는 중'):
            paths = [download(svc, f['id'], f['name'], f['mimeType'], workdir)
                     for f in sales.values()]
            reject_path = (download(svc, stats['id'], stats['name'], stats['mimeType'], workdir)
                           if stats else None)
        month = None
        if reject_path:
            from . import build as B
            try:
                month = B.available_reject_months(reject_path)[0]
            except Exception:
                month = None
        r = run_build(paths, reject_path, month, workdir)
        if r:
            if back:
                try:
                    link = upload(svc, r.out, folder_id)
                    st.success(f'드라이브에도 올렸습니다 — [열어보기]({link})')
                except Exception as e:
                    st.warning(f'드라이브 업로드는 실패했습니다(파일은 아래에서 받으실 수 있습니다): {e}')
            render_report(r, workdir)
