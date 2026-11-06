"""Headless application checks: python -m unittest discover -s tests -p test_streamlit_app.py -v"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
from view_helpers import balanced_sample, filter_nodes, graph_option, parse_tags
from web_workspace import WebWorkspace

STEPS = ["1 · 자료 넣기", "2 · 살펴보고 정리", "3 · 내려받기"]


def large_graph() -> dict:
    categories = [{"id": f"c{i}", "label": f"분야 {i}", "count": 200} for i in range(14)]
    nodes = [{"id": f"n{i}", "title": f"unique{i} 자료", "category": f"c{i // 200}", "format": "md",
              "summary": "가상 규모 시험", "tags": ["가상"], "notes": ""} for i in range(2800)]
    return {"title": "대용량 가상 지도", "categories": categories, "nodes": nodes, "edges": [],
            "stats": {"documents": 2800, "categories": 14, "links": 0}}


def displayed_rows(app: AppTest):
    return [block for block in app.container if block.key and block.key.startswith("document_row_")]


class PresentationLogicTests(unittest.TestCase):
    def test_balanced_sample_retains_minority_and_selected(self):
        nodes = [{"id": f"major{i}", "category": "major"} for i in range(2000)]
        nodes += [{"id": f"minor{i}", "category": "minor"} for i in range(10)]
        nodes += [{"id": "only", "category": "single"}]
        sample = balanced_sample(nodes, selected="major1999")
        self.assertEqual(len(sample), 220)
        self.assertEqual(len({node["id"] for node in sample}), 220)
        self.assertEqual(sum(node["category"] == "minor" for node in sample), 10)
        self.assertIn("only", [node["id"] for node in sample])
        self.assertIn("major1999", [node["id"] for node in sample])
        self.assertEqual(sample, balanced_sample(nodes, selected="major1999"))

    def test_graph_counts_are_full_matches_and_tooltips_are_text(self):
        graph = large_graph()
        option = graph_option(graph, graph["nodes"], "n2799")
        chart_nodes = option["series"][0]["data"]
        self.assertEqual(sum(node["id"].startswith("doc:") for node in chart_nodes), 220)
        hubs = [node for node in chart_nodes if node["id"].startswith("category:")]
        self.assertEqual(len(hubs), 14)
        self.assertTrue(all(node["name"].endswith("200개") for node in hubs))
        self.assertEqual(option["tooltip"]["renderMode"], "richText")
        self.assertIn("doc:n2799", [node["id"] for node in chart_nodes])

    def test_search_includes_notes_and_all_fields(self):
        graph = large_graph()
        graph["nodes"][-1]["notes"] = "나중에 수업에서 활용"
        self.assertEqual([node["id"] for node in filter_nodes(graph, "나중에 활용", "c13")], ["n2799"])
        self.assertEqual(len(filter_nodes(graph, category="c13")), 200)
        self.assertEqual(parse_tags("#수업, 독서，수업\n연구"), ["수업", "독서", "연구"])


class StreamlitWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=45)

    def tearDown(self):
        try:
            self.app.session_state["workspace"].close()
        except KeyError:
            pass

    def run_ok(self):
        self.app.run()
        self.assertFalse(self.app.exception, [entry.message for entry in self.app.exception])
        return self.app

    def demo(self):
        self.run_ok()
        self.app.button(key="build_demo").click()
        self.run_ok()
        self.assertEqual(len(self.app.session_state["snapshot"]["graph"]["nodes"]), 16)
        return self.app

    def test_first_screen_and_upload_notice_before_picker(self):
        app = self.run_ok()
        self.assertEqual(app.get_by_key("step").value, STEPS[0])
        self.assertEqual(app.button(key="build_demo").label, "예제 16개로 시작")
        app.get_by_key("input_mode").set_value("내 파일 업로드")
        self.run_ok()
        self.assertTrue(any("서버로 전송" in item.value for item in app.info))
        self.assertTrue(app.get_by_key("source_uploads").proto.disabled)
        app.checkbox(key="upload_acknowledged").check()
        self.run_ok()
        self.assertFalse(app.get_by_key("source_uploads").proto.disabled)

    def test_resource_visit_preserves_saved_map_and_prepared_downloads(self):
        app = self.demo()
        saved_note = "설명서를 읽고 돌아와도 유지할 메모"
        app.text_area(key="edit_notes").set_value(saved_note)
        app.button(key="save_edit").click()
        self.run_ok()
        app.get_by_key("step").set_value(STEPS[2])
        self.run_ok()
        app.button(key="prepare_downloads").click()
        self.run_ok()
        before = json.loads(json.dumps(app.session_state["snapshot"]))
        downloads = dict(app.session_state["downloads"])
        workspace = app.session_state["workspace"]

        app.get_by_key("view").set_value("guide")
        self.run_ok()
        self.assertEqual(app.session_state["snapshot"], before)
        self.assertIs(app.session_state["workspace"], workspace)
        self.assertTrue(app.get("iframe"))

        app.get_by_key("view").set_value("map")
        self.run_ok()
        self.assertEqual(app.get_by_key("step").value, STEPS[2])
        self.assertEqual(app.session_state["downloads"], downloads)
        self.assertEqual(app.session_state["snapshot"], before)
        self.assertFalse(app.get("iframe"))
        app.get_by_key("step").set_value(STEPS[1])
        self.run_ok()
        self.assertEqual(app.text_area(key="edit_notes").value, saved_note)

    def test_resource_link_opens_manual_and_previews_the_downloaded_examples(self):
        # URL-bound choices use the displayed label, not the internal option.
        self.app.query_params["view"] = "설명서·예제"
        with patch.object(WebWorkspace, "build_demo", side_effect=AssertionError("unexpected conversion")), patch.object(WebWorkspace, "build_uploads", side_effect=AssertionError("unexpected conversion")):
            app = self.run_ok()
            self.assertEqual(app.get_by_key("view").value, "guide")
            self.assertIsNone(app.session_state["snapshot"])
            self.assertEqual(len(app.get("iframe")), 1)
            for key in ("guide_html_download", "guide_pdf_download", "example_zip_download"):
                self.assertTrue(app.get_by_key(key).proto.url)
            self.assertTrue(any("/app/static/PKOS_Beginner_Manual.html" in item.proto.url for item in app.link_button))

            app.get_by_key("guide_section").set_value("examples")
            self.run_ok()
            self.assertFalse(app.get("iframe"))
            choices = app.selectbox(key="example_document").options
            self.assertEqual(len(choices), 16)
            with zipfile.ZipFile(ROOT / "static" / "PKOS_Example_16.zip") as archive:
                for name in (choices[0], choices[-1]):
                    app.selectbox(key="example_document").select(name)
                    self.run_ok()
                    text = archive.read(name).decode("utf-8-sig")
                    self.assertTrue(any(item.value == text.strip() for item in app.code))
            self.assertIsNone(app.session_state["snapshot"])

    def test_demo_search_and_category_do_not_reconvert(self):
        app = self.demo()
        self.assertEqual([metric.value for metric in app.metric], ["16", "4", "24"])
        workspace = app.session_state["workspace"]
        with patch.object(workspace, "build_demo", side_effect=AssertionError("unexpected conversion")), patch.object(workspace, "build_uploads", side_effect=AssertionError("unexpected conversion")):
            app.get_by_key("view_mode").set_value("목록")
            self.run_ok()
            app.text_input(key="query").set_value("독서")
            self.run_ok()
            expected = filter_nodes(app.session_state["snapshot"]["graph"], "독서")
            self.assertEqual(len(displayed_rows(app)), len(expected))
            self.assertEqual([row.text[0].value for row in displayed_rows(app)], [node["title"] for node in expected])
            app.button(key="clear_filters").click()
            self.run_ok()
            category = app.session_state["snapshot"]["graph"]["categories"][0]["id"]
            app.selectbox(key="category").select(category)
            self.run_ok()
            self.assertEqual(len(displayed_rows(app)), len(filter_nodes(app.session_state["snapshot"]["graph"], category=category)))

    def test_edit_notes_and_tags_persist_through_download_step(self):
        app = self.demo()
        selected = app.session_state["selected_doc"]
        app.text_input(key="edit_tags").set_value("#나의태그, 테스트, 나의태그")
        app.text_area(key="edit_notes").set_value("수업에서 활용할 나만의 메모")
        app.button(key="save_edit").click()
        self.run_ok()
        node = next(node for node in app.session_state["snapshot"]["graph"]["nodes"] if node["id"] == selected)
        self.assertEqual(node["tags"], ["나의태그", "테스트"])
        self.assertEqual(node["notes"], "수업에서 활용할 나만의 메모")
        app.get_by_key("view_mode").set_value("목록")
        self.run_ok()
        app.text_input(key="query").set_value("수업에서 활용할 나만의 메모")
        self.run_ok()
        self.assertEqual(len(displayed_rows(app)), 1)
        self.assertEqual(displayed_rows(app)[0].text[0].value, node["title"])
        self.assertIn("나의태그, 테스트", displayed_rows(app)[0].text[2].value)
        app.get_by_key("step").set_value(STEPS[2])
        self.run_ok()
        app.get_by_key("step").set_value(STEPS[1])
        self.run_ok()
        self.assertEqual(app.text_area(key="edit_notes").value, node["notes"])

    def test_manual_link_and_unlink(self):
        app = self.demo()
        selected = app.session_state["selected_doc"]
        target = app.selectbox(key="link_target").value
        app.text_input(key="link_reason").set_value("함께 읽고 비교할 자료")
        app.button(key="save_link").click()
        self.run_ok()
        edges = app.session_state["snapshot"]["graph"]["edges"]
        self.assertTrue(any(edge.get("kind") == "manual" and {edge["source"], edge["target"]} == {selected, target} and edge["label"] == "함께 읽고 비교할 자료" for edge in edges))
        unlink = next(button for button in app.button if button.key and button.key.startswith("unlink_"))
        unlink.click()
        self.run_ok()
        self.assertFalse(any(edge.get("kind") == "manual" and {edge["source"], edge["target"]} == {selected, target} for edge in app.session_state["snapshot"]["graph"]["edges"]))

    def test_exports_are_downloadable_and_reset_cleans_session(self):
        app = self.demo()
        app.get_by_key("step").set_value(STEPS[2])
        self.run_ok()
        app.button(key="prepare_downloads").click()
        self.run_ok()
        data = app.session_state["downloads"]
        self.assertEqual(len(json.loads(data["json"])["nodes"]), 16)
        self.assertIn(b"PKOS_EXPORT", data["html"])
        with zipfile.ZipFile(io.BytesIO(data["zip"])) as archive:
            self.assertIn("지식맵.json", archive.namelist())
            self.assertEqual(len([name for name in archive.namelist() if name.startswith("문서/") and name.endswith(".md")]), 16)
        for key in ("download_html", "download_json", "download_zip"):
            self.assertIsNotNone(app.get_by_key(key))
        old_workspace = app.session_state["workspace"]
        with patch.object(old_workspace, "close", wraps=old_workspace.close) as close:
            app.button(key="reset_workspace").click()
            self.run_ok()
            close.assert_called_once()
        self.assertIsNone(app.session_state["snapshot"])
        self.assertIsNone(app.session_state["downloads"])
        self.assertIsNot(app.session_state["workspace"], old_workspace)
        self.assertEqual(app.get_by_key("step").value, STEPS[0])

    def test_failed_replacement_keeps_previous_result(self):
        app = self.demo()
        before = app.session_state["snapshot"]
        app.get_by_key("step").set_value(STEPS[0])
        self.run_ok()
        with patch.object(app.session_state["workspace"], "build_demo", side_effect=ValueError("허용 용량을 넘었습니다")):
            app.button(key="build_demo").click()
            self.run_ok()
        self.assertTrue(app.error)
        self.assertEqual(app.session_state["snapshot"], before)

    def test_large_map_pagination_and_last_document_search(self):
        self.app.session_state["snapshot"] = {"graph": large_graph(), "stats": {}, "errors": []}
        self.app.session_state["step"] = STEPS[1]
        app = self.run_ok()
        app.get_by_key("view_mode").set_value("목록")
        self.run_ok()
        self.assertEqual(len(displayed_rows(app)), 100)
        self.assertEqual(len(app.selectbox(key="selected_doc").options), 100)
        app.button(key="page_next").click()
        self.run_ok()
        self.assertEqual(len(displayed_rows(app)), 100)
        self.assertEqual(displayed_rows(app)[0].text[0].value, "unique100 자료")
        app.text_input(key="query").set_value("unique2799")
        self.run_ok()
        self.assertEqual(len(displayed_rows(app)), 1)
        self.assertEqual(displayed_rows(app)[0].text[0].value, "unique2799 자료")
        self.assertEqual(app.session_state["selected_doc"], "n2799")
        self.assertEqual(app.session_state["list_page"], 1)

    def test_document_html_and_remote_images_are_plain_code(self):
        payload = '<script>alert(1)</script>\n![remote](https://example.invalid/tracker.png)\n테스트 본문'
        workspace = WebWorkspace()
        self.app.session_state["workspace"] = workspace
        self.app.session_state["snapshot"] = workspace.build_uploads([("본문안전.txt", payload.encode("utf-8"))], privacy=False)
        self.app.session_state["step"] = STEPS[1]
        app = self.run_ok()
        app.toggle(key="show_body").set_value(True)
        self.run_ok()
        self.assertTrue(any("<script>alert(1)</script>" in item.value and "tracker.png" in item.value for item in app.code))
        self.assertFalse(app.html)
        self.assertFalse(app.get("iframe"))
        self.assertFalse(any("tracker.png" in item.value for item in app.markdown))


if __name__ == "__main__":
    unittest.main()
