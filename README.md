# PKOS 나만의 지식맵 · Streamlit 배포판

**[설계·구상 보고서](https://legoschool-pkos-knowledge-map.streamlit.app/app/static/PKOS_Design_Report.html)** · 앱을 열면 첫 화면에 구상, 업무 프로세스, 시스템 구성도가 먼저 나옵니다.

**[온라인 지식맵 열기](https://legoschool-pkos-knowledge-map.streamlit.app/)** · 처음에는 **예제 16개로 시작**을 누르세요. 한동안 접속이 없어 앱이 잠들어 있으면 깨우는 버튼이 나오고, 다시 켜질 때까지 잠시 걸립니다. 같은 앱을 [Render 주소](https://pkos-knowledge-map.onrender.com/)에서도 열 수 있습니다.

**[설명서·예제 바로보기](https://legoschool-pkos-knowledge-map.streamlit.app/?view=%EC%84%A4%EB%AA%85%EC%84%9C%C2%B7%EC%98%88%EC%A0%9C)** · 사이트 안에서 72쪽 초보자 설명서를 읽고 HTML·PDF·예제 ZIP을 내려받을 수 있습니다. 예제 문서 16개도 하나씩 미리 볼 수 있습니다. [설명서만 크게 열기](https://legoschool-pkos-knowledge-map.streamlit.app/app/static/PKOS_Beginner_Manual.html) · [프로그램까지 포함한 전체 꾸러미](https://github.com/legoschool/pkos-knowledge-map-streamlit/releases/download/v1.1-manual/PKOS_Beginner_Kit_v1.1.zip)

내 자료를 넣고, 내용을 읽어 문서 사이의 연결을 살펴보고, 분류와 메모를 고쳐 나만의 지식맵을 만드는 파이썬 프로그램입니다. 기존 PKOS 자료 변환 엔진을 Streamlit 화면에 연결했습니다.

처음이라면 [초보자 따라하기](초보자_따라하기.html)를 열거나 앱의 **예제 16개로 시작**을 누르세요. 예제는 모두 실습을 위해 만든 가상 자료입니다. 공개 소스에는 실제 사용자의 자료가 들어 있지 않습니다.

## 먼저 알아두세요

- **온라인 앱에서 파일을 선택하면 파일이 운영 서버로 전송됩니다.** 변환 버튼을 누르기 전에도 업로드가 일어납니다. 민감한 자료는 아래의 내 컴퓨터 실행 방법을 이용하세요.
- 업로드와 수정 내용은 세션별 임시 작업 공간에서 처리됩니다. 영구 보관 서비스가 아닙니다. 탭 종료 즉시 삭제를 보장하지 않으며, 자료 초기화·새 작업 교체·세션 객체 정리·서버 재시작 등으로 작업이 사라질 수 있습니다. 필요한 결과는 내려받으세요.
- 개인정보 가리기는 기본으로 켜져 있습니다. 자동 가림이 모든 이름·정보를 찾아낸다고 보장하지 않습니다. 온라인 업로드 자체를 가려 주는 기능도 아닙니다.
- 외부 생성형 AI API와 OCR은 사용하지 않습니다. 태그와 문서 연결은 추출된 텍스트의 단어를 바탕으로 계산하므로 사람이 확인하고 고칠 수 있습니다.

## 5분 사용 순서

1. **1 · 자료 넣기 → 예제 16개로 시작**을 누릅니다. 자료와 지도 표시가 끝날 때까지 기다립니다.
2. **2 · 살펴보고 정리**에서 분야와 검색어로 문서를 좁혀 봅니다. **자세히 볼 자료 선택** 상자에서 문서를 골라 본문·태그·연결을 확인합니다. 지도는 확대·이동하거나 점 위에 마우스를 올려 살펴봅니다.
3. 제목·분야·태그·메모를 바꾸고 **수정 저장**을 누릅니다. 필요한 문서는 **직접 연결 추가**로 연결합니다.
4. **3 · 내려받기 → 내려받을 파일 준비**를 누른 뒤 **HTML 지도 받기**, **JSON 데이터 받기**, **정리 파일 ZIP 받기**로 저장합니다.
5. 자기 자료로 해 보려면 **자료 지우고 처음으로**를 누릅니다. 업로드 안내를 읽고 확인한 후 파일을 선택하고 **업로드한 자료로 지도 만들기**를 누릅니다.

같은 실습을 다시 하려면 [예제자료 16개 ZIP](examples/예제자료_16개.zip)을 내려받아 업로드하세요. 예제 버튼과 ZIP 업로드는 같은 가상 자료를 사용합니다.

## 업로드 범위와 한계

| 항목 | 이 배포판의 기준 |
|---|---|
| 한 번에 올리는 용량 | 전체 50MiB 이하, 개별 파일 20MiB 이하 |
| 압축 자료 | ZIP 지원, 중첩 최대 2단계 |
| 압축 내부 용량 | 개별 항목 20MiB 이하, 해제 누적 100MiB 이하 |
| 항목 수 | 업로드 및 ZIP·Office 압축 내부 항목을 합쳐 최대 300개; 내부 디렉터리도 포함 |
| 사진·스캔 PDF | OCR 미사용. 이미지 속 글자는 추출하지 않음 |
| 문서 속 그림 | 웹판에서는 그림 추출·복사를 끔 |
| 암호 문서·미지원 형식 | 읽지 못한 이유를 확인하고 원래 프로그램에서 다시 저장 |
| 저장 | 세션 임시 저장과 사용자의 다운로드 |

1MiB는 1,048,576바이트입니다. DOCX·PPTX·XLSX·HWPX 등도 내부적으로 압축 파일이므로, 겉보기 파일 수가 적어도 내부 항목 수 제한에 도달할 수 있습니다. 큰 발표자료나 많은 사진을 한꺼번에 넣을 때는 작은 묶음으로 나누거나 전체 로컬 버전을 이용하세요.

파일명보다 실제 내용을 판별해 변환합니다. 텍스트가 있는 PDF, HWP/HWPX, DOCX, PPTX, XLSX, 텍스트·마크다운 등 여러 문서 형식을 처리하며, 실제 업로드 가능한 확장자는 앱의 업로드 안내를 확인하세요. 파일 선택이 허용되어도 암호·손상·스캔 여부에 따라 본문을 읽지 못할 수 있습니다.

## 내려받은 파일 사용법

| 파일 | 쓰는 방법 |
|---|---|
| HTML 지도 | 브라우저로 열어 오프라인에서 읽습니다. 읽기 전용이며 수정 화면은 없습니다. |
| JSON 데이터 | 문서·분류·연결 정보를 다른 프로그램에서 분석하거나 보관합니다. |
| 정리 파일 ZIP | 가림 처리된 Markdown 변환본, 지도, 편집 기록을 함께 보관합니다. 업로드한 원본은 포함하지 않습니다. |
| 우주 지도·3D 교실 ZIP | 압축을 풀고 `index.html`을 열면 우주 지도, `school.html`을 열면 3D 교실입니다. 아래 ‘우주 지도와 3D 교실’을 보세요. |

현재 웹판에는 내려받은 JSON·ZIP을 다시 불러와 같은 프로젝트를 복원하는 기능이 없습니다. 다음에 새로 작업할 때는 원자료로 지도를 다시 만드세요. 세션을 초기화하기 전에 수정한 결과를 내려받는 것이 좋습니다. 원본 자료는 별도로 보관하세요.

## 우주 지도와 3D 교실

**3 · 내려받기** 아래 **우주 지도와 3D 교실로 보기**에서 지도 이름, 가운데 해에 쓸 이름, 분야마다 올릴 자료 수(5~40)를 정하고 **우주 지도 만들기**를 누르면 앱 안에서 미리 볼 수 있습니다. **우주 지도·3D 교실 ZIP 받기**로 내려받으면 다음 파일이 들어 있습니다.

| 파일 | 내용 |
|---|---|
| `index.html` | 우주 지도. 분야가 행성으로 해 둘레를 돌고, 행성 크기는 자료 수를 따릅니다. 행성을 누르면 자료 카드와 연결된 자료가 열립니다. 찾기와 평면 보기가 있습니다. |
| `school.html` | 3D 교실. 분야마다 교실 한 칸, 자료마다 책상 하나가 놓입니다(교실마다 20개까지). WASD·방향키로 걷고, 바닥을 누르면 그 자리로 가며, 책상 위 브릭을 누르면 자료가 열립니다. |
| `data.js` | 두 화면이 함께 읽는 데이터(`window.DX`). [레고학교.com](https://xn--299a9hx7z0r4a.com/) 지도와 같은 구조(`hub`, `zones`, `areas[].items[]`)라서, 이 틀에 레고학교.com의 `data.js`를 넣어도 열립니다. |

자료는 지식맵의 분야별로 연결이 많은 순서대로 고릅니다. 제목, 요약(메모가 있으면 메모), 태그, 연결된 자료 3개만 담고 원본 경로와 본문은 넣지 않습니다. 3D 교실은 three.js r128을 cdnjs에서 불러오므로 인터넷이 필요하고, 우주 지도는 인터넷 없이 열립니다. 공개 사이트로 올리기 전에 `data.js`의 제목과 설명에 개인정보가 없는지 확인하세요.

## 내 컴퓨터에서 실행하기

Python 3.12 이상이 필요합니다. 배포 권장 버전은 3.12이며 작성 환경은 Python 3.14.7입니다. 이 배포판은 Streamlit 1.67.0을 사용합니다. 처음 설치할 때는 패키지를 내려받기 위한 인터넷 연결이 필요합니다.

### Windows

1. [Python 공식 다운로드](https://www.python.org/downloads/)에서 Python을 설치합니다. 설치 화면에 **Add python.exe to PATH**가 보이면 선택합니다.
2. [프로그램 전체 ZIP](https://github.com/legoschool/pkos-knowledge-map-streamlit/archive/refs/heads/main.zip)을 내려받아 압축을 **모두 풀고**, `streamlit_app.py`와 `requirements.txt`가 있는 폴더를 엽니다.
3. `설치.cmd`를 더블클릭하고 설치 완료 메시지를 기다립니다. 이 폴더 안의 `.venv`에 필요한 패키지를 설치합니다.
4. `실행.cmd`를 더블클릭합니다. 화면이 자동으로 열리지 않으면 [내 컴퓨터 지식맵](http://localhost:8501)을 엽니다.
5. 작업하는 동안 실행 창을 열어 둡니다. 종료하려면 실행 창에서 **Ctrl+C**를 누릅니다.

이렇게 실행하면 선택한 자료는 내 컴퓨터의 프로그램으로 전달됩니다. 공개 온라인 앱에 접속한 화면과 주소가 다르므로 주소창이 `localhost:8501`인지 확인하세요. 이 Streamlit판을 로컬에서 실행해도 업로드 제한과 임시 저장 방식은 동일합니다.

### macOS / Linux 또는 터미널

프로젝트 폴더에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py --server.address=127.0.0.1
```

Windows 터미널에서는 활성화 대신 `.venv\Scripts\python.exe`를 직접 사용할 수 있습니다. 포트가 이미 사용 중이면 `--server.port=8502`를 추가하고 `http://localhost:8502`로 접속합니다.

## 기존 전체 로컬 버전과의 차이

| 비교 | Streamlit 배포판 | 기존 전체 로컬 버전 |
|---|---|---|
| 자료 넣기 | 작은 파일 묶음 또는 ZIP 업로드 | 내 컴퓨터의 폴더 전체 선택 |
| 처리 위치 | 온라인 운영 서버 또는 직접 실행한 내 컴퓨터 | 내 컴퓨터 |
| 처리 규모 | 위의 웹판 제한 적용 | 컴퓨터 자원과 변환 옵션에 따라 처리 |
| 작업 보관 | 세션 임시 공간, 결과 다운로드 | 지정한 결과 폴더와 변환 기록으로 보관 |
| 문서 속 그림·OCR | 그림 추출과 OCR 꺼짐 | 그림 추출, 별도 준비가 필요한 OCR 옵션 사용 가능 |
| 활용 | 가볍게 체험하고 작은 자료 묶음 정리 | 큰 개인 자료실 정리와 지속적인 편집 |

여러 GB의 자료실, 학생 정보, 업무 문서 등은 전체 로컬 버전이 적합합니다. 온라인 서비스를 쓰기 위해 실제 자료를 GitHub 저장소에 넣을 필요는 없습니다.

## Render에서 간편 배포하기

Streamlit Community Cloud 대신 Render에서도 같은 파이썬 프로그램을 실행할 수 있습니다.

**[Render에 배포하기](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Flegoschool%2Fpkos-knowledge-map-streamlit)**

1. 위 링크를 열고 Render에 로그인합니다. 처음이라면 GitHub 계정으로 가입할 수 있습니다.
2. 서비스 목록의 `pkos-knowledge-map`과 **Free** 설정을 확인하고 배포를 진행합니다. 저장소·실행 파일·실행 명령은 `render.yaml`이 지정합니다.
3. 배포가 끝나고 상태가 **Live**가 되면 표시되는 `https://…onrender.com` 주소를 엽니다.
4. **예제 16개로 시작**으로 확인한 뒤 주소를 공유합니다.

이 저장소는 `plan: free`를 명시하며 유료 데이터베이스나 디스크를 만들지 않습니다. 무료 서비스는 15분간 접속이 없으면 쉬었다가 다음 접속 때 다시 시작하므로 처음 열 때 약 1분 걸릴 수 있습니다. 재시작 시 임시 자료가 사라질 수 있어 결과를 내려받아 보관하세요. 큰 개인 자료실은 내 컴퓨터에서 실행하는 전체 로컬판을 이용하세요. [공식 무료 서비스 안내](https://render.com/docs/free)

간편 배포 링크로 만든 서비스는 자동 업데이트를 끕니다. 새 버전을 적용할 때 Render의 **Manual Deploy → Deploy latest commit**을 사용합니다. 이 문서와 링크만으로 배포가 완료되는 것은 아니며, 실제 실행 주소는 배포 성공 후 확인합니다. [공식 간편 배포 안내](https://render.com/docs/deploy-to-render)

## Streamlit Community Cloud에 배포하기

아래는 배포 설정 안내입니다. **이 문서의 저장소 주소는 실행 중인 앱 주소가 아니며, 배포 URL은 Community Cloud에서 배포가 끝난 뒤 확인합니다.**

공개 소스를 GitHub 저장소에 준비한 뒤 [Streamlit Community Cloud](https://share.streamlit.io/)에 로그인하고 GitHub 계정을 연결합니다. **Create app → Yup, I have an app**에서 다음 값을 입력하세요.

| 입력 항목 | 값 |
|---|---|
| Repository | `legoschool/pkos-knowledge-map-streamlit` |
| Branch | `main` |
| Main file path | `streamlit_app.py` |
| Advanced settings → Python version | `3.12` |
| Secrets | 현재 앱은 API 키가 필요하지 않으므로 비워 둠 |

저장소: [GitHub 소스](https://github.com/legoschool/pkos-knowledge-map-streamlit). **Paste GitHub URL**을 사용할 때는 `https://github.com/legoschool/pkos-knowledge-map-streamlit/blob/main/streamlit_app.py`를 붙여 넣습니다. 다른 계정에 포크했다면 Repository를 자기 계정의 저장소로 바꾸세요.

**Deploy**를 눌러 설치 로그가 끝날 때까지 기다린 후, 실제 앱에서 예제 16개 생성·수정·HTML 다운로드를 확인하세요. 그때 표시되는 `https://…streamlit.app` 주소가 공유할 실행 주소입니다. 이후 소스를 수정해 같은 브랜치에 푸시하면 Community Cloud가 업데이트를 반영합니다. [공식 배포 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

공식 CLI 문서에는 Community Cloud 신규 배포 명령이 없습니다. 공식 문서에서 공개 배포 API도 확인하지 못했으므로, 이 프로젝트의 배포 안내는 위의 공식 화면 절차를 사용합니다. `streamlit run`은 프로그램 실행 명령입니다. [공식 CLI 안내](https://docs.streamlit.io/develop/api-reference/cli)

Python 의존성은 `requirements.txt`에 모았습니다. 이 배포판은 OCR 등 별도의 운영체제 프로그램을 사용하지 않아 `packages.txt`를 제공하지 않습니다. [공식 의존성 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)

### 선택 사항: Docker 실행

Dockerfile은 자체 서버나 Docker 환경을 위한 선택 사항입니다. Community Cloud 배포에는 필요하지 않습니다. 다음은 실행 예시이며, 이 문서 자체가 Docker 빌드 성공이나 서버 배포 완료를 의미하지 않습니다.

```bash
docker build -t pkos-knowledge-map .
docker run --rm -p 127.0.0.1:8501:8501 pkos-knowledge-map
```

[Streamlit 공식 Docker 안내](https://docs.streamlit.io/deploy/tutorials/docker)를 바탕으로 Python 3.12 컨테이너에서 실행하도록 구성했습니다.

## 문제가 생겼을 때

- **설치 창이 오류로 끝남:** Python 3.12 이상인지, 인터넷 연결이 되는지 확인하고 `설치.cmd`를 다시 실행합니다. ZIP 안에서 바로 실행했다면 먼저 압축을 모두 풉니다.
- **업로드 제한 오류:** 개별 20MiB·합계 50MiB를 확인합니다. 용량이 작아도 Office 문서 내부 항목이 많으면 거절될 수 있습니다. 자료 묶음을 줄이세요.
- **스캔 PDF나 사진의 본문이 비어 있음:** 웹판은 OCR을 하지 않습니다. 텍스트가 포함된 문서로 다시 저장하거나 전체 로컬 버전의 OCR을 사용하세요.
- **문서의 표나 한글 일부가 어색함:** 원본의 글꼴·문서 구조에 따라 추출 순서나 문자가 달라질 수 있습니다. 변환본을 원문과 대조하세요.
- **새로고침 뒤 작업이 사라짐:** 세션 작업은 영구 저장되지 않습니다. 원자료로 다시 생성하고 결과를 내려받아 보관하세요.
- **다운로드한 ZIP을 올렸는데 원래 편집 화면으로 돌아오지 않음:** 결과 ZIP은 보관용이며 프로젝트 복원 기능은 없습니다.
- **온라인 앱이 잠들어 있음:** Community Cloud 화면의 깨우기 버튼을 누르고 재시작을 기다립니다. [공식 앱 관리 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)

지식맵의 연결은 읽기와 정리를 돕는 제안입니다. 파일에 실제로 어떤 내용이 있는지, 두 문서의 관계가 타당한지는 사용자가 확인하며 완성합니다.
