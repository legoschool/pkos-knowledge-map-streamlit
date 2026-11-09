"""PKOS Streamlit interface. Each browser session owns its workspace and caches."""
from __future__ import annotations

import base64
import math
from pathlib import Path

import streamlit as st

from resource_library import PUBLIC_FILES, public_bytes, render_resources
from view_helpers import MAP_LIMIT, PAGE_SIZE, balanced_sample, category_labels, document_label, filter_nodes, graph_option, parse_tags
from web_workspace import ALLOWED_EXTENSIONS, WebWorkspace

st.set_page_config(page_title="PKOS · 나의 지식맵", page_icon=":material/hub:", layout="wide")

STEPS = ["1 · 자료 넣기", "2 · 살펴보고 정리", "3 · 내려받기"]
APP_DIR = Path(__file__).resolve().parent

# Never put a personal workspace or its document contents in a shared cache.
if "workspace" not in st.session_state:
    st.session_state["workspace"] = WebWorkspace()
for key, value in {"snapshot": None, "step": STEPS[0], "query": "", "category": "", "list_page": 1,
                   "selected_doc": None, "revision": 0, "body_cache": {}, "downloads": None, "space": None,
                   "notice": "", "edit_identity": None}.items():
    st.session_state.setdefault(key, value)

if pending := st.session_state.pop("pending_view", None):
    st.session_state["step"] = pending.get("step", st.session_state["step"])
    if pending.get("clear_filters"):
        st.session_state["query"] = ""
        st.session_state["category"] = ""
        st.session_state["list_page"] = 1
    if "selected" in pending:
        st.session_state["selected_doc"] = pending["selected"]
        if pending["selected"] and pending.get("clear_filters"):
            nodes = st.session_state["snapshot"]["graph"]["nodes"]
            index = next((i for i, node in enumerate(nodes) if node["id"] == pending["selected"]), 0)
            st.session_state["list_page"] = index // PAGE_SIZE + 1

workspace = st.session_state["workspace"]


def commit_result(snapshot: dict, message: str, selected: str | None = None, *, clear_filters: bool = False) -> None:
    st.session_state["snapshot"] = snapshot
    st.session_state["revision"] += 1
    st.session_state["body_cache"] = {}
    st.session_state["downloads"] = None
    st.session_state["space"] = None
    st.session_state["edit_identity"] = None
    st.session_state["notice"] = message
    st.session_state["pending_view"] = {"step": STEPS[1], "selected": selected, "clear_filters": clear_filters}
    st.rerun()


def filter_changed() -> None:
    st.session_state["list_page"] = 1
    st.session_state["selected_doc"] = None


def clear_filters() -> None:
    st.session_state["query"] = ""
    st.session_state["category"] = ""
    filter_changed()


def change_page(direction: int) -> None:
    st.session_state["list_page"] = max(1, st.session_state["list_page"] + direction)
    st.session_state["selected_doc"] = None


def choose_related(doc_id: str) -> None:
    nodes = st.session_state["snapshot"]["graph"]["nodes"]
    index = next((i for i, node in enumerate(nodes) if node["id"] == doc_id), 0)
    st.session_state["query"] = ""
    st.session_state["category"] = ""
    st.session_state["list_page"] = index // PAGE_SIZE + 1
    st.session_state["selected_doc"] = doc_id


def reset_session() -> None:
    st.session_state["workspace"].close()
    # This clears only this user's app session; other sessions are independent.
    for key in list(st.session_state):
        del st.session_state[key]


def report_error(error: Exception) -> None:
    st.error("작업을 완료하지 못했습니다. 입력 내용을 확인한 뒤 다시 시도해 주세요.", title="처리 안내")
    # Error messages can contain user-provided filenames: keep them plain text.
    st.text(str(error))


def open_guides() -> None:
    st.session_state["view"] = "guide"


st.caption("PKOS · 개인 자료를 연결하는 작은 작업실")
st.title("내 자료로 만드는 나만의 지식맵")
st.markdown("**자료 넣기 → 살펴보고 정리 → 내 컴퓨터에 내려받기.** 처음이라면 가상 예제 16개로 시작하세요.")

with st.sidebar:
    st.subheader("사용 안내")
    st.markdown("1. 예제 또는 내 파일 선택\n2. 검색·분야로 찾고 메모 추가\n3. HTML·JSON·ZIP 저장")
    st.markdown("[내 컴퓨터에서 실행하기](/app/static/PKOS_Beginner_Manual.html#install-python)")
    st.button("설명서·예제 바로보기", icon=":material/menu_book:", on_click=open_guides, key="open_guides", width="stretch")
    st.download_button("초보자 사용설명서 받기", data=public_bytes("html"), file_name=PUBLIC_FILES["html"], mime="text/html", on_click="ignore", key="manual_download")
    st.caption("이 웹앱의 자료는 현재 브라우저 세션용입니다. 탭을 닫거나 서버가 재시작되면 잃을 수 있으므로 결과를 내려받으세요.")
    if st.session_state["snapshot"]:
        st.button("자료 지우고 처음으로", icon=":material/restart_alt:", key="reset_workspace", on_click=reset_session, width="stretch")

view = st.segmented_control("작업 화면", ["map", "guide"], default="map", required=True,
                            format_func=lambda value: {"map": "지식맵 만들기", "guide": "설명서·예제"}[value],
                            key="view", bind="query-params", width="stretch")
if view == "guide":
    render_resources()
    st.stop()

step = st.segmented_control("진행 단계", STEPS, key="step", selection_mode="single", persist_state="session", width="stretch") or STEPS[0]
if notice := st.session_state.pop("notice", ""):
    st.success(notice)

if step == STEPS[0]:
    st.header("1. 자료를 준비해요")
    mode = st.segmented_control("시작 방법", ["예제로 연습", "내 파일 업로드"], default="예제로 연습", key="input_mode") or "예제로 연습"
    if mode == "예제로 연습":
        with st.container(border=True):
            st.subheader("처음에는 버튼 하나면 됩니다", icon=":material/school:")
            st.markdown("수업·연구·독서·프로젝트를 담은 **가상 문서 16개**를 준비했습니다. 개인 자료나 API 키 없이 지식맵의 흐름을 익힐 수 있습니다.")
            if st.button("예제 16개로 시작", type="primary", icon=":material/play_arrow:", key="build_demo"):
                try:
                    with st.spinner("예제 자료를 읽고 연결하고 있어요…"):
                        result = workspace.build_demo(title="나의 지식맵 예제", privacy=True)
                    commit_result(result, "예제 지도를 만들었습니다. 검색하거나 아래에서 자료를 골라 보세요.", clear_filters=True)
                except Exception as error:
                    report_error(error)
    else:
        st.info("공개 웹주소에서 파일을 선택하면 그 파일이 이 앱을 운영하는 서버로 전송됩니다. 개인정보 가리기는 전송 후에 실행됩니다. 민감한 자료는 아래 안내에 따라 내 컴퓨터에서 실행해 주세요.", title="파일을 고르기 전에", icon=":material/cloud_upload:")
        st.markdown("[내 컴퓨터에서 실행하는 방법 보기](#local-guide)")
        consent = st.checkbox("업로드 안내를 확인했습니다", key="upload_acknowledged")
        uploads = st.file_uploader("자료 파일 또는 ZIP을 선택하세요", type=ALLOWED_EXTENSIONS, accept_multiple_files=True,
                                   max_upload_size=20, disabled=not consent, key="source_uploads")
        st.caption("파일 하나 20MiB · 전체 50MiB까지. ZIP·Office 내부 항목은 합계 300개, 해제 용량 100MiB, ZIP 중첩 2단계까지 검사합니다. OCR과 음성 전사는 사용하지 않습니다.")
        with st.form("build_upload_form"):
            project_title = st.text_input("지도 제목", value="나의 자료 지식맵", max_chars=120, key="project_title")
            privacy = st.checkbox("전화번호·이메일 등 개인정보 가리기", value=True, key="privacy_enabled")
            submitted = st.form_submit_button("업로드한 자료로 지도 만들기", type="primary", disabled=not consent or not uploads)
        if submitted:
            try:
                if not consent or not uploads:
                    raise ValueError("업로드 안내 확인 후 자료를 선택해 주세요.")
                if not project_title.strip():
                    raise ValueError("지도 제목을 입력해 주세요.")
                with st.spinner("파일을 읽고 지식맵을 만들고 있어요…"):
                    result = workspace.build_uploads([(file.name, file.getvalue()) for file in uploads], title=project_title.strip(), privacy=bool(privacy))
                commit_result(result, "자료를 정리했습니다. 변환 결과와 읽지 못한 파일도 확인해 주세요.", clear_filters=True)
            except Exception as error:
                report_error(error)

elif not st.session_state["snapshot"] or not st.session_state["snapshot"].get("graph"):
    st.info("먼저 ‘1 · 자료 넣기’에서 예제 또는 내 파일로 지도를 만들어 주세요.", title="아직 지도가 없습니다")

elif step == STEPS[1]:
    snapshot = st.session_state["snapshot"]
    graph = snapshot["graph"]
    labels = category_labels(graph)
    st.header("2. 찾고, 연결하고, 내 말로 정리해요")
    st.text(graph.get("title", "나의 지식맵"))
    for column, label, value in zip(st.columns(3), ["전체 자료", "분야", "연결"], [len(graph.get("nodes", [])), len(labels), len(graph.get("edges", []))]):
        column.metric(label, f"{value:,}", border=True)
    if snapshot.get("errors"):
        with st.expander(f'읽지 못한 파일 {len(snapshot["errors"])}개 확인'):
            st.caption("암호·스캔·지원하지 않는 형식 등이 있을 수 있습니다. 아래 기록을 확인해 주세요.")
            st.code("\n".join(str(item) for item in snapshot["errors"][:100]), language=None, wrap_lines=True, height=220)
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.text_input("자료 검색", key="query", type="search", placeholder="예: 인공지능, 수업, 독서", on_change=filter_changed, persist_state="session")
        st.selectbox("분야", [""] + list(labels), format_func=lambda value: labels.get(value, "모든 분야"), key="category", on_change=filter_changed, persist_state="session")
        st.button("검색 초기화", on_click=clear_filters, key="clear_filters")
    matched = filter_nodes(graph, st.session_state["query"], st.session_state["category"])
    st.caption(f'전체 {len(graph["nodes"]):,}개 중 {len(matched):,}개 일치 · 제목·미리보기·태그·메모·분야명을 검색합니다.')
    view = st.segmented_control("보기 방식", ["지도", "목록"], default="지도", key="view_mode", persist_state="session") or "지도"
    if not matched:
        st.info("검색어를 줄이거나 다른 분야를 선택해 보세요.", title="일치하는 자료가 없습니다")
    else:
        page_count = math.ceil(len(matched) / PAGE_SIZE)
        st.session_state["list_page"] = min(max(1, st.session_state["list_page"]), page_count)
        page = st.session_state["list_page"]
        with st.container(horizontal=True, vertical_alignment="center"):
            st.button("이전 100개", key="page_previous", disabled=page <= 1, on_click=change_page, args=(-1,))
            st.caption(f"{page} / {page_count} 페이지")
            st.button("다음 100개", key="page_next", disabled=page >= page_count, on_click=change_page, args=(1,))
        shown = matched[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
        options = [node["id"] for node in shown]
        if st.session_state["selected_doc"] not in options:
            st.session_state["selected_doc"] = options[0]
        lookup = {node["id"]: node for node in graph["nodes"]}
        selected = st.selectbox("자세히 볼 자료 선택", options, format_func=lambda value: document_label(lookup[value]), key="selected_doc", persist_state="session")
        if view == "지도":
            sample = balanced_sample(matched, selected=selected)
            st.caption(f'지도에는 분야별 대표 {len(sample):,}개를 표시합니다(최대 {MAP_LIMIT}개). 분야 이름 옆 숫자는 전체 일치 건수입니다. 확대·이동은 지도에서, 자료 선택은 위의 선택 상자에서 합니다.')
            st.echarts_chart(graph_option(graph, matched, selected), height=500, key="knowledge_graph",
                             alt=f'검색에 일치하는 {len(matched)}개 자료 중 분야별 대표 {len(sample)}개와 연결 관계')
        else:
            st.caption(f'{(page - 1) * PAGE_SIZE + 1:,}–{min(page * PAGE_SIZE, len(matched)):,}번째 자료 · 한 페이지 최대 {PAGE_SIZE}개')
            with st.container(height=380, border=True, key="document_table"):
                for offset, item in enumerate(shown, start=(page - 1) * PAGE_SIZE + 1):
                    with st.container(border=False, gap="xsmall", key=f'document_row_{item["id"]}'):
                        st.caption(f"자료 {offset:,}")
                        st.text(item.get("title", "제목 없는 자료"))
                        st.text(f'분야: {labels.get(item.get("category"), item.get("category", "미분류"))} · 형식: {item.get("format", "문서")}')
                        st.text("태그: " + (", ".join(item.get("tags", [])) or "없음"))
        node = lookup[selected]
        with st.container(border=True):
            st.subheader("선택한 자료", icon=":material/description:")
            st.text(node.get("title", "제목 없는 자료"))
            st.text(f'{labels.get(node.get("category"), node.get("category", "미분류"))} · {node.get("format", "문서")}')
            st.text(node.get("summary") or "미리보기가 없습니다.")
            st.text("태그: " + ", ".join(node.get("tags", [])))
            if node.get("notes"):
                st.text("내 메모: " + node["notes"])
            if st.toggle("변환한 본문 보기", key="show_body"):
                try:
                    if selected not in st.session_state["body_cache"]:
                        body = workspace.document(selected).get("body", "")
                        if len(st.session_state["body_cache"]) >= 8:
                            st.session_state["body_cache"].pop(next(iter(st.session_state["body_cache"])))
                        st.session_state["body_cache"][selected] = {"body": body[:100_000], "truncated": len(body) > 100_000}
                    body = st.session_state["body_cache"][selected]
                    st.code(body["body"] or "읽을 수 있는 본문이 없습니다.", language=None, wrap_lines=True, height=320)
                    if body["truncated"]:
                        st.caption("화면에는 앞 100,000자만 표시합니다. 전체 변환본은 정리 파일 ZIP에서 확인하세요.")
                except Exception as error:
                    report_error(error)
        identity = (selected, st.session_state["revision"])
        if st.session_state["edit_identity"] != identity or any(key not in st.session_state for key in ("edit_title", "edit_category", "edit_tags", "edit_notes")):
            for key, value in {"edit_title": node.get("title", ""), "edit_category": labels.get(node.get("category"), node.get("category", "")),
                               "edit_tags": ", ".join(node.get("tags", [])), "edit_notes": node.get("notes", "")}.items():
                st.session_state[key] = value
            st.session_state["edit_identity"] = identity
        with st.form("edit_document"):
            st.subheader("내 기준으로 고치기", icon=":material/edit:")
            title = st.text_input("제목", max_chars=200, key="edit_title")
            category = st.text_input("분야 이름", max_chars=120, key="edit_category")
            tags = st.text_input("태그 · 쉼표로 구분", max_chars=1000, key="edit_tags")
            notes = st.text_area("내 메모", max_chars=5000, key="edit_notes")
            edited = st.form_submit_button("수정 저장", type="primary", key="save_edit")
        if edited:
            try:
                if not title.strip() or not category.strip():
                    raise ValueError("제목과 분야 이름을 입력해 주세요.")
                result = workspace.edit(selected, {"title": title.strip(), "category": category.strip(), "tags": parse_tags(tags), "notes": notes})
                commit_result(result, "분야·태그·메모를 저장했습니다. 내려받을 파일에도 반영됩니다.", selected, clear_filters=True)
            except Exception as error:
                report_error(error)
        st.subheader("관련 자료와 연결 이유", icon=":material/link:")
        related = [edge for edge in graph.get("edges", []) if selected in (edge.get("source"), edge.get("target"))]
        if not related:
            st.caption("아직 관련 자료가 없습니다. 공통 태그를 붙이거나 아래에서 직접 연결해 보세요.")
        for index, edge in enumerate(related[:20]):
            target_id = edge["target"] if edge["source"] == selected else edge["source"]
            target = lookup.get(target_id)
            if not target:
                continue
            with st.container(border=True):
                st.text(target.get("title", "제목 없는 자료"))
                st.text(("직접 연결 · " if edge.get("kind") == "manual" else "자동 연결 · ") + str(edge.get("label", "공통 태그")))
                with st.container(horizontal=True):
                    st.button("이 자료 보기", key=f"related_{index}", on_click=choose_related, args=(target_id,))
                    if edge.get("kind") == "manual" and st.button("직접 연결 해제", key=f"unlink_{index}"):
                        try:
                            commit_result(workspace.unlink(selected, target_id), "직접 만든 연결을 해제했습니다.", selected)
                        except Exception as error:
                            report_error(error)
        if len(related) > 20:
            st.caption(f'연결 {len(related)}개 중 앞 20개를 표시합니다. 전체 관계는 JSON에서 확인할 수 있습니다.')
        target_query = st.text_input("연결할 자료 찾기", key="link_search", placeholder="자료가 많으면 제목이나 태그로 검색하세요")
        targets = [item for item in filter_nodes(graph, target_query) if item["id"] != selected][:100]
        if targets:
            if st.session_state.get("link_target") not in [item["id"] for item in targets]:
                st.session_state["link_target"] = targets[0]["id"]
            with st.form("manual_link"):
                target_id = st.selectbox("연결할 자료", [item["id"] for item in targets], format_func=lambda value: document_label(lookup[value]), key="link_target")
                reason = st.text_input("연결 이유", max_chars=300, key="link_reason", placeholder="예: 같은 수업에서 함께 활용할 자료")
                linked = st.form_submit_button("직접 연결 추가", key="save_link")
            st.caption("연결 대상은 검색에 일치하는 앞 100개까지 표시합니다. 필요한 자료가 없으면 검색어를 좁혀 주세요.")
            if linked:
                try:
                    if not reason.strip():
                        raise ValueError("연결 이유를 입력해 주세요.")
                    commit_result(workspace.link(selected, target_id, reason.strip()), "자료를 직접 연결했습니다.", selected)
                except Exception as error:
                    report_error(error)
        else:
            st.caption("연결할 다른 자료가 없습니다. 검색어를 바꿔 보세요.")

elif step == STEPS[2]:
    st.header("3. 내 컴퓨터에 보관해요")
    st.markdown("수정한 내용을 저장한 뒤 파일을 준비하세요. 브라우저 탭을 닫기 전에 **정리 파일 ZIP**까지 받아 두면 변환한 문서와 편집 기록을 함께 보관할 수 있습니다.")
    st.caption("HTML: 읽기 전용 지도 · JSON: 구조화한 지도 데이터 · ZIP: 변환 문서와 편집 기록. 업로드한 원본 자체는 별도로 보관하세요.")
    if st.button("내려받을 파일 준비", type="primary", icon=":material/download:", key="prepare_downloads"):
        try:
            with st.spinner("현재 지도와 정리한 문서를 묶고 있어요…"):
                st.session_state["downloads"] = {"html": workspace.export_html(), "json": workspace.export_json(), "zip": workspace.export_markdown_zip()}
        except Exception as error:
            report_error(error)
    if downloads := st.session_state["downloads"]:
        with st.container(horizontal=True):
            st.download_button("HTML 지도 받기", data=downloads["html"], file_name="나의_지식맵.html", mime="text/html", key="download_html", on_click="ignore")
            st.download_button("JSON 데이터 받기", data=downloads["json"], file_name="나의_지식맵.json", mime="application/json", key="download_json", on_click="ignore")
            st.download_button("정리 파일 ZIP 받기", data=downloads["zip"], file_name="나의_정리자료.zip", mime="application/zip", key="download_zip", on_click="ignore")
        st.success("파일을 준비했습니다. 위 버튼을 눌러 컴퓨터에 저장하세요.")

    st.subheader("우주 지도와 3D 교실로 보기", anchor="space-map")
    st.markdown("지식맵을 레고학교.com과 같은 구조의 **우주 지도**와 **3D 교실**로 바꿔요. 분야는 행성과 교실이 되고, 자료는 위성과 책상이 돼요.")
    graph_title = (st.session_state["snapshot"] or {}).get("graph", {}).get("title", "나의 지식맵")
    with st.form("space_form", border=False):
        name_col, hub_col = st.columns(2)
        space_title = name_col.text_input("지도 이름", value=graph_title, max_chars=60, key="space_title")
        space_hub = hub_col.text_input("가운데 해에 쓸 이름", max_chars=20, key="space_hub", placeholder="예: 김선생님 (비우면 지도 이름)")
        per_area = st.slider("분야마다 올릴 자료 수", min_value=5, max_value=40, value=18, key="space_per_area",
                             help="연결이 많은 자료부터 고릅니다. 3D 교실에는 분야마다 책상을 20개까지 놓아요.")
        made = st.form_submit_button("우주 지도 만들기", type="primary", icon=":material/public:")
    if made:
        try:
            with st.spinner("행성과 교실을 배치하고 있어요…"):
                st.session_state["space"] = workspace.export_space(title=space_title, byline=space_hub, per_area=per_area)
        except Exception as error:
            report_error(error)
    if space := st.session_state["space"]:
        st.download_button("우주 지도·3D 교실 ZIP 받기", data=space["zip"], file_name="나의_우주지도.zip", mime="application/zip",
                           key="download_space", on_click="ignore", icon=":material/download:")
        st.caption(f"분야 {space['areas']}개, 자료 {space['items']}건을 올렸어요. ZIP을 풀고 index.html을 열면 우주 지도, school.html을 열면 3D 교실이에요. 3D 교실은 인터넷 연결이 필요해요.")
        map_tab, school_tab = st.tabs(["우주 지도 미리 보기", "3D 교실 미리 보기"])
        # data: URLs give the preview its own origin, separate from the app.
        with map_tab:
            st.iframe("data:text/html;base64," + base64.b64encode(space["map"].encode("utf-8")).decode("ascii"), height=620, alt="우주 지도 미리 보기")
        with school_tab:
            st.caption("교실 화면을 한 번 누른 뒤 WASD 또는 방향키로 걸어요. 책상 위 브릭을 누르면 자료가 열려요.")
            st.iframe("data:text/html;base64," + base64.b64encode(space["school"].encode("utf-8")).decode("ascii"), height=620, alt="3D 교실 미리 보기")

st.header("내 컴퓨터에서 실행하기", anchor="local-guide")
with st.expander("개인 자료를 서버에 보내지 않고 사용하는 방법"):
    st.markdown("1. 배포받은 ‘스트림릿_배포판’ 폴더 전체를 압축 해제합니다.\n2. Python 3.12 이상을 설치합니다(3.12 권장).\n3. 폴더 안의 설치 명령 파일을 실행합니다.\n4. 실행 명령 파일로 앱을 열고 내 자료를 넣습니다.")
    st.caption("명령창으로 실행한다면 아래 명령을 사용하세요. 내 컴퓨터에서 실행한 앱의 업로드는 그 컴퓨터 안에서 처리됩니다.")
    st.code("python -m pip install -r requirements.txt\npython -m streamlit run streamlit_app.py --server.address 127.0.0.1", language="bash")
    st.caption("자동 분류와 연결은 폴더·태그·단어 규칙에 따른 제안입니다. AI 의미 분석이나 사실 검증 결과가 아닙니다.")
