"""First screen: the design report (concept, workflow, system architecture)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

REPORT_FILE = "PKOS_Design_Report.html"
REPORT_PATH = Path(__file__).resolve().parent / "static" / REPORT_FILE


def render_report() -> None:
    st.header("설계와 구상")
    st.markdown("**이 프로그램을 어떻게 구상하고 설계했는지** 먼저 보여 드려요. 설계 원칙, 업무 프로세스, 시스템 구성도 다음에 결과 사이트 레고학교.com과 데이터 처리 단계가 나와요.")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.link_button("보고서 크게 보기 · 새 탭", "/app/static/" + REPORT_FILE, icon=":material/open_in_new:")
        st.caption("지식맵을 직접 만들어 보려면 위의 ‘지식맵 만들기’를 누르세요.")
    st.iframe(REPORT_PATH, height=900, alt="PKOS 개인 지식맵 설계 보고서: 구상, 업무 프로세스, 시스템 구성도")
