"""Read and display bundled public instructions and fictional practice documents.

Only these reviewed, application-owned files enter the shared cache or iframe.
Personal uploads and generated maps remain in WebWorkspace's session storage.
"""
from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import zipfile

import streamlit as st

RESOURCE_DIR = Path(__file__).resolve().parent / "static"
PUBLIC_FILES = {
    "html": "PKOS_Beginner_Manual.html",
    "pdf": "PKOS_Beginner_Manual.pdf",
    "examples": "PKOS_Example_16.zip",
    "report": "PKOS_Design_Report.html",
}
KIT_URL = "https://github.com/legoschool/pkos-knowledge-map-streamlit/releases/download/v1.1-manual/PKOS_Beginner_Kit_v1.1.zip"


@st.cache_data(show_spinner=False, max_entries=3)
def public_bytes(kind: str) -> bytes:
    return (RESOURCE_DIR / PUBLIC_FILES[kind]).read_bytes()


@st.cache_data(show_spinner=False, max_entries=1)
def example_documents() -> dict[str, str]:
    """Preview the same immutable fictional documents offered in the download."""
    with zipfile.ZipFile(io.BytesIO(public_bytes("examples"))) as archive:
        return {
            name: archive.read(name).decode("utf-8-sig")
            for name in sorted(archive.namelist())
            if not name.endswith("/") and PurePosixPath(name).suffix.lower() in {".md", ".txt"}
        }


def render_resources() -> None:
    st.header("설명서와 연습 자료")
    st.markdown("**처음 사용하는 분도 한 단계씩 따라오세요.** 자료 준비부터 설치·지도 편집·저장·온라인 배포까지 담았습니다.")
    st.caption("초보자 설명서 · 15장 · 103단계 · PDF 72쪽 · 실제 화면과 공식 참고 그림 16개")
    with st.container(horizontal=True):
        st.download_button("HTML 설명서 받기", public_bytes("html"), file_name=PUBLIC_FILES["html"],
                           mime="text/html", icon=":material/download:", on_click="ignore", key="guide_html_download")
        st.download_button("PDF 설명서 받기", public_bytes("pdf"), file_name=PUBLIC_FILES["pdf"],
                           mime="application/pdf", icon=":material/picture_as_pdf:", on_click="ignore", key="guide_pdf_download")
        st.download_button("예제 16개 ZIP 받기", public_bytes("examples"), file_name=PUBLIC_FILES["examples"],
                           mime="application/zip", icon=":material/folder_zip:", on_click="ignore", key="example_zip_download")
        st.link_button("프로그램까지 한꺼번에 받기", KIT_URL, icon=":material/inventory_2:")

    section = st.segmented_control(
        "살펴볼 자료", ["manual", "examples"], default="manual", required=True,
        format_func=lambda value: {"manual": "설명서 바로 읽기", "examples": "예제 자료 살펴보기"}[value],
        key="guide_section", persist_state="session", width="stretch",
    )
    if section == "examples":
        st.subheader("가상 문서 16개를 먼저 살펴보세요")
        st.markdown("수업·연구·생활·코딩을 주제로 만든 연습 자료입니다. 실제 학생이나 교사의 개인 자료는 들어 있지 않습니다.")
        documents = example_documents()
        selected = st.selectbox("읽어 볼 예제", list(documents), key="example_document", persist_state="session")
        if selected:
            st.caption(selected)
            st.code(documents[selected], language=None, wrap_lines=True, height=400)
        st.info("위의 ‘예제 16개 ZIP 받기’를 누른 다음, ‘지식맵 만들기 → 1 · 자료 넣기 → 내 파일 업로드’에서 받은 ZIP을 선택하세요.", title="내 자료를 넣기 전에 연습하기")
        st.caption("파일 선택 연습 없이 시작하려면 ‘지식맵 만들기’ 화면에서 ‘예제 16개로 시작’을 누르세요.")
    else:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.link_button("설명서 크게 보기 · 새 탭", "/app/static/PKOS_Beginner_Manual.html", icon=":material/open_in_new:")
            st.caption("아래 설명서 안에서 검색하거나 그림을 눌러 확대할 수 있습니다.")
        st.iframe(RESOURCE_DIR / PUBLIC_FILES["html"], height=850, alt="PKOS 초보자 설명서: 자료 준비부터 설치와 배포까지 103단계")


def render_report() -> None:
    st.header("설계와 구상")
    st.markdown("**이 프로그램을 어떻게 구상하고 설계했는지** 먼저 보여 드려요. 설계 원칙, 업무 프로세스, 시스템 구성도 다음에 결과 사이트 레고학교.com과 데이터 처리 단계가 나와요.")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.link_button("보고서 크게 보기 · 새 탭", "/app/static/" + PUBLIC_FILES["report"], icon=":material/open_in_new:")
        st.caption("지식맵을 직접 만들어 보려면 위의 ‘지식맵 만들기’를 누르세요.")
    st.iframe(RESOURCE_DIR / PUBLIC_FILES["report"], height=900, alt="PKOS 개인 지식맵 설계 보고서: 구상, 업무 프로세스, 시스템 구성도")
