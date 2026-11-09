"""Space map and 3D classroom export: python -m pytest tests/test_space_export.py -q"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
import space_export as se
from web_workspace import WebWorkspace


def sample_graph() -> dict:
    nodes = [{"id": f"n{i}", "title": f"자료 {i}", "category": "수업" if i < 30 else "연구", "format": "md",
              "summary": f"요약 {i}", "tags": ["수업", f"t{i}"], "notes": ""} for i in range(40)]
    nodes[0]["title"] = "</script><img src=x onerror=alert(1)>"
    nodes[1]["format"] = "mp4"
    nodes[2]["format"] = "html"
    nodes[3]["notes"] = "직접 쓴 메모"
    edges = [{"source": "n5", "target": f"n{i}", "weight": 2} for i in range(6, 12)]
    edges.append({"source": "n5", "target": "n31", "weight": 1})
    return {"title": "시험 지도", "nodes": nodes, "edges": edges, "generated_at": "2026-11-09T00:00:00+00:00"}


class BuildTests(unittest.TestCase):
    def test_areas_follow_categories_and_limit_items(self):
        dx = se.build_dx(sample_graph(), per_area=10)
        self.assertEqual([a["name"] for a in dx["areas"]], ["수업", "연구"])
        self.assertEqual([a["count"] for a in dx["areas"]], [30, 10])
        self.assertEqual(len(dx["areas"][0]["items"]), 10)
        self.assertEqual(dx["areas"][0]["items"][0]["id"], "n5")  # most connected first
        self.assertIn("연결이 많은 자료 10건", " ".join(dx["areas"][0]["story"]))
        self.assertEqual(dx["hub"]["sub"], "자료 40건 · 분야 2개 · 연결 7개")

    def test_items_carry_kind_notes_and_related(self):
        dx = se.build_dx(sample_graph(), per_area=40)
        items = {it["id"]: it for a in dx["areas"] for it in a["items"]}
        self.assertEqual(items["n1"]["kind"], "video")
        self.assertEqual(items["n2"]["kind"], "site")
        self.assertEqual(items["n4"]["kind"], "doc")
        self.assertEqual(items["n3"]["desc"], "직접 쓴 메모")
        related = [r["id"] for r in items["n5"]["related"]]
        self.assertEqual(len(related), 3)
        self.assertTrue(set(related) <= {f"n{i}" for i in range(6, 12)})  # weight 2 before weight 1
        self.assertNotIn("source", items["n5"])

    def test_per_area_bounds_and_missing_graph(self):
        self.assertEqual(len(se.build_dx(sample_graph(), per_area=0)["areas"][0]["items"]), 1)
        self.assertEqual(len(se.build_dx(sample_graph(), per_area=999)["areas"][0]["items"]), 30)
        with self.assertRaises(ValueError):
            se.build_dx({"title": "빈 지도"})

    def test_data_js_cannot_close_the_script(self):
        script = se.data_js(se.build_dx(sample_graph()))
        self.assertNotIn("</script", script)
        self.assertNotIn("<img", script)
        payload = script.split("window.DX = ", 1)[1].rstrip().rstrip(";")
        self.assertEqual(json.loads(payload)["areas"][0]["count"], 30)

    def test_zip_and_standalone_pages(self):
        dx = se.build_dx(sample_graph())
        with zipfile.ZipFile(io.BytesIO(se.package_zip(dx))) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {"나의_우주지도/index.html", "나의_우주지도/school.html", "나의_우주지도/data.js", "나의_우주지도/읽어주세요.txt"})
            for page in ("index.html", "school.html"):
                self.assertIn('<script src="data.js"></script>', archive.read("나의_우주지도/" + page).decode("utf-8"))
        for page in ("index.html", "school.html"):
            html = se.standalone_html(dx, page)
            self.assertNotIn('<script src="data.js"></script>', html)
            self.assertIn("window.PKOS_PREVIEW = true;", html)
            self.assertNotIn("PKOS_PREVIEW = true", se.standalone_html(dx, page, preview=False))
        with self.assertRaises(ValueError):
            se.standalone_html(dx, "../secret.html")


class WorkspaceTests(unittest.TestCase):
    def test_demo_map_exports_space(self):
        workspace = WebWorkspace()
        try:
            workspace.build_demo()
            space = workspace.export_space(title="예제 우주", byline="예제 선생님", per_area=3)
            self.assertEqual(space["areas"], 4)
            self.assertEqual(space["items"], 12)
            self.assertIn("예제 선생님", space["map"])
            with zipfile.ZipFile(io.BytesIO(space["zip"])) as archive:
                self.assertIn("나의_우주지도/data.js", archive.namelist())
        finally:
            workspace.close()


class AppTests(unittest.TestCase):
    def test_space_form_offers_zip_and_previews(self):
        app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120)
        app.run()
        app.button(key="build_demo").click()
        app.run()
        app.get_by_key("step").set_value("3 · 내려받기")
        app.run()
        self.assertIsNone(app.session_state["space"])
        app.text_input(key="space_hub").set_value("예제 선생님")
        app.button(key="FormSubmitter:space_form-우주 지도 만들기").click()
        app.run()
        self.assertFalse(app.exception)
        space = app.session_state["space"]
        self.assertEqual(space["areas"], 4)
        self.assertIsNotNone(app.get_by_key("download_space"))
        self.assertEqual(len(app.get("iframe")), 2)


if __name__ == "__main__":
    unittest.main()
