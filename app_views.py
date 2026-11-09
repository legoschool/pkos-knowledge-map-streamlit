"""Navigation: home hub, sidebar menu and design pages. Every part sits behind one button."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import streamlit as st

STATIC = Path(__file__).resolve().parent / "static"
REPORT_FILE = "PKOS_Design_Report.html"
SITE_URL = "https://xn--299a9hx7z0r4a.com/"
SOURCE_URL = "https://github.com/legoschool/pkos-knowledge-map-streamlit"

DESIGN_PARTS = {
    "concept": "구상",
    "workflow": "업무 프로세스",
    "system": "시스템 구성도",
    "pipeline": "데이터 처리 단계",
    "result": "결과 사이트",
    "report": "전체 보고서",
}

# group title -> markdown color used for its icons and card titles
GROUP_COLORS = {"설계 보기": "blue", "직접 해 보기": "red", "자료": "green"}

# (card id, icon, title, one line, target)
HOME_GROUPS = [
    ("설계 보기", "어떻게 구상하고 설계했는지 하나씩 열어 보세요.", [
        ("concept", ":material/lightbulb:", "구상", "왜 만들었고 어떤 원칙으로 설계했는지", {"view": "design", "design_part": "concept"}),
        ("workflow", ":material/account_tree:", "업무 프로세스", "선생님과 프로그램이 나눠 맡는 7단계", {"view": "design", "design_part": "workflow"}),
        ("system", ":material/lan:", "시스템 구성도", "자료 출처에서 화면까지 프로그램 구성", {"view": "design", "design_part": "system"}),
        ("pipeline", ":material/conversion_path:", "데이터 처리 단계", "원본에서 지도까지 6단계와 숫자", {"view": "design", "design_part": "pipeline"}),
        ("result", ":material/public:", "결과 사이트", "이렇게 만든 지식 지도 레고학교.com", {"view": "design", "design_part": "result"}),
        ("report", ":material/description:", "전체 보고서", "설계 보고서를 처음부터 끝까지", {"view": "design", "design_part": "report"}),
    ]),
    ("직접 해 보기", "가상 예제로 먼저 해 보고, 내 자료로 넘어가세요.", [
        ("demo", ":material/play_circle:", "예제로 지식맵 만들기", "가상 문서 16개로 지도를 그려 봐요", {"view": "map", "step": "1 · 자료 넣기", "input_mode": "예제로 연습"}),
        ("upload", ":material/upload_file:", "내 파일로 만들기", "내 자료를 올려 나만의 지도를 만들어요", {"view": "map", "step": "1 · 자료 넣기", "input_mode": "내 파일 업로드"}),
        ("space", ":material/rocket_launch:", "우주 지도·3D 교실", "만든 지도를 행성과 레고 교실로 바꿔요", {"view": "map", "step": "3 · 내려받기"}),
    ]),
    ("자료", "설명서와 연습 자료, 소스 코드예요.", [
        ("manual", ":material/menu_book:", "초보자 설명서", "설치부터 배포까지 72쪽", {"view": "guide", "guide_section": "manual"}),
        ("examples", ":material/folder_open:", "예제 16개 보기", "연습용 가상 문서를 미리 읽어요", {"view": "guide", "guide_section": "examples"}),
        ("source", ":material/code:", "소스 코드", "GitHub 저장소", SOURCE_URL),
    ]),
]

PRINCIPLES = [
    ("원본은 읽기만", "결과는 별도 폴더에 만들고 원본 파일은 바꾸지 않아요."),
    ("내용으로 형식 판별", "확장자 대신 파일 앞부분과 내부 목록을 보고 형식을 알아내요."),
    ("마크다운 한 형식", "모든 자료를 사람도 AI도 읽는 글로 바꾸고 출처를 남겨요."),
    ("개인정보 가림", "주민번호, 전화번호, 계좌번호, 사람 이름을 변환할 때 가려요."),
    ("컴퓨터가 제안, 사람이 수정", "태그와 연결은 보통 단어로 만들고 이유를 보여 줘요."),
    ("내 컴퓨터에서 처리", "외부 생성형 AI API를 쓰지 않아요. 웹 버전은 체험용이에요."),
]

PIPELINE = [
    ("원본", "3곳", "블로그·유튜브·드라이브. 옮기거나 지우지 않아요.", False),
    ("사본", "7,203개", "드라이브 자료를 35묶음으로 모아요.", False),
    ("마크다운 변환", "6,063건", "블로그 910편, 영상 목차 153편, 문서 본문 5,000장", True),
    ("연결", "6,149장", "카드로 넣고 공통어·태그로 서로 연결해요.", True),
    ("공개", "14곳", "공개할 묶음만 골라 기록 사이트로 올려요.", False),
    ("지도", "312건", "분야 18개의 지식 지도와 3D 교실. 같은 구조의 지도를 자동으로 만들어요.", True),
]


def go(target: dict) -> None:
    """Button callback: move to a view (and sub-section) before the next run."""
    for key, value in target.items():
        st.session_state[key] = value


def _cards(cards: list, color: str, columns: int = 3) -> None:
    for start in range(0, len(cards), columns):
        row = st.columns(columns)
        for column, (card_id, icon, title, line, target) in zip(row, cards[start:start + columns]):
            with column.container(border=True, height="stretch"):
                st.markdown(f"#### :{color}[{icon}] {title}")
                st.caption(line)
                if isinstance(target, str):
                    st.link_button("열기 ↗", target, key=f"home_{card_id}", width="stretch")
                else:
                    st.button("열기", key=f"home_{card_id}", on_click=go, args=(target,), type="primary", width="stretch")


def render_home() -> None:
    st.markdown("흩어진 블로그·유튜브·드라이브 자료를 모아 **연결된 지식맵**으로 만들고, **우주 지도와 3D 교실**로 보여 주는 파이썬 프로그램이에요. 아래 버튼에서 보고 싶은 것을 고르세요.")
    for title, line, cards in HOME_GROUPS:
        color = GROUP_COLORS[title]
        st.subheader(f":{color}[{title}]", divider=color)
        st.caption(line)
        _cards(cards, color)


def _back() -> None:
    st.button("처음 화면", icon=":material/arrow_back:", key="design_home", on_click=go, args=({"view": "home"},))


def render_design() -> None:
    _back()
    part = st.segmented_control("설계 보기", list(DESIGN_PARTS), default="concept", required=True,
                                format_func=DESIGN_PARTS.get, key="design_part", width="stretch",
                                label_visibility="collapsed")
    if part == "concept":
        st.header("구상")
        with st.container(border=True):
            st.markdown("**문제** · 13년 동안 쌓인 블로그 글 910편, 유튜브 영상 183개, 드라이브 교사 폴더 파일 3,082개가 서로 다른 곳에 있었어요. 형식도 한글·PPT·PDF·사진으로 제각각이라 다시 찾고 쓰기 어려웠어요.")
            st.markdown("**목표** · 흩어진 자료를 한 형식으로 모으고, 자료 사이의 관계를 눈에 보이게 하고, 내 기록을 다시 쓸 수 있게 해요.")
        st.subheader("설계 원칙")
        for start in range(0, len(PRINCIPLES), 3):
            row = st.columns(3)
            for column, (name, line) in zip(row, PRINCIPLES[start:start + 3]):
                with column.container(border=True, height="stretch"):
                    st.markdown(f"**{name}**")
                    st.caption(line)
    elif part == "workflow":
        st.header("업무 프로세스")
        st.caption("선생님은 정리할 곳을 고르고, 결과를 고치고, 다시 써요. 형식 판별·변환·연결 같은 반복 작업은 프로그램이 맡아요.")
        st.image(STATIC / "design_workflow.png", alt="업무 프로세스: 선생님과 프로그램이 나눠 맡는 7단계")
    elif part == "system":
        st.header("시스템 구성도")
        st.caption("자료 출처 → 변환 엔진(engine/) → 지식 구조(graph.py) → 화면과 배포. 초록 점선 안은 내 컴퓨터에서 처리하고, 주황 점선은 인터넷에 공개한 웹 버전이에요.")
        st.image(STATIC / "design_system.png", alt="시스템 구성도: 자료 출처, 변환 엔진, 지식 구조, 화면과 배포")
    elif part == "pipeline":
        st.header("데이터 처리 단계")
        st.caption("레고학교.com은 아래 여섯 단계를 거쳐 만들었어요. 초록 표시가 이 프로그램이 맡는 단계예요.")
        for start in range(0, len(PIPELINE), 3):
            row = st.columns(3)
            for offset, (column, (name, value, line, mine)) in enumerate(zip(row, PIPELINE[start:start + 3])):
                with column.container(border=True, height="stretch"):
                    st.markdown(f"**{start + offset + 1}. {name}**")
                    st.metric(name, value, label_visibility="collapsed")
                    st.caption(line)
                    if mine:
                        st.badge("이 프로그램", icon=":material/check:", color="green")
    elif part == "result":
        st.header("결과 사이트: 레고학교.com")
        st.link_button("레고학교.com 열기 ↗", SITE_URL, icon=":material/public:", type="primary")
        st.image(STATIC / "result_map.jpg", caption="첫 화면. 분야가 행성처럼 궤도를 돌고, 구슬 크기가 자료 수예요.", alt="레고학교.com 지식 지도 첫 화면")
        left, right = st.columns(2)
        left.image(STATIC / "result_school.jpg", caption="같은 자료를 3D 레고 교실에서 걸어 다니며 열어요.", alt="레고학교.com 3D 교실")
        right.image(STATIC / "example_space.jpg", caption="이 프로그램으로 예제 16개를 넣어 만든 우주 지도", alt="예제로 만든 우주 지도")
        st.button("내 지도로 우주 지도 만들기", icon=":material/rocket_launch:", key="result_to_space", on_click=go,
                  args=({"view": "map", "step": "3 · 내려받기"},))
    else:
        st.header("전체 보고서")
        st.link_button("보고서 크게 보기 · 새 탭", "/app/static/" + REPORT_FILE, icon=":material/open_in_new:")
        st.iframe(STATIC / REPORT_FILE, height=900, alt="PKOS 개인 지식맵 설계 보고서")


def _active(target: dict) -> bool:
    state = st.session_state
    if target.get("view") != state.get("view", "home"):
        return False
    if "design_part" in target:
        return state.get("design_part", "concept") == target["design_part"]
    if "guide_section" in target:
        return state.get("guide_section", "manual") == target["guide_section"]
    if "step" in target and target["view"] == "map":
        same_step = state.get("step") == target["step"]
        if "input_mode" in target:
            return same_step and state.get("input_mode", "예제로 연습") == target["input_mode"]
        return same_step
    return True


def render_sidebar(on_reset, has_map: bool) -> None:
    """Whole menu as buttons; the current page is the highlighted (primary) one."""
    with st.sidebar:
        st.markdown("## PKOS 나의 지식맵")
        st.button("처음 화면", icon=":material/home:", key="nav_home", on_click=go, args=({"view": "home"},),
                  type="primary" if st.session_state.get("view", "home") == "home" else "secondary", width="stretch")
        for title, _, cards in HOME_GROUPS:
            st.markdown(f"**{title}**")
            for card_id, icon, label, _, target in cards:
                if isinstance(target, str):
                    st.link_button(label, target, icon=icon, key=f"nav_{card_id}", width="stretch")
                else:
                    st.button(label, icon=icon, key=f"nav_{card_id}", on_click=go, args=(target,),
                              type="primary" if _active(target) else "secondary", width="stretch")
        if has_map:
            st.divider()
            st.button("자료 지우고 처음으로", icon=":material/restart_alt:", key="reset_workspace", on_click=on_reset, width="stretch")
        st.caption("이 웹앱의 자료는 지금 브라우저 세션에만 있어요. 탭을 닫거나 서버가 다시 시작되면 사라지니 결과를 내려받으세요.")
