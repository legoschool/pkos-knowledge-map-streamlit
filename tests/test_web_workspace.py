"""Public-web upload, isolation, transaction, and export contracts."""
from pathlib import Path
import io
import json
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_workspace import (WebWorkspace, UploadLimits, WorkspaceError,
                           WorkspaceBusyError, UploadValidationError)


def packed(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return stream.getvalue()


class WebWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pkos-web-tests-")
        self.ws = WebWorkspace(temp_parent=self.temp.name)

    def tearDown(self):
        self.ws.close()
        self.assertTrue(Path(self.temp.name).resolve().name.startswith("pkos-web-tests-"))
        self.temp.cleanup()

    def documents(self):
        return [("연구/관찰.md", "---\ntags: [관찰, 탐구]\n---\n# 관찰\n관찰 자료를 모읍니다.".encode()),
                ("수업/질문.txt", "질문 만들기\n관찰과 질문을 함께 탐구합니다.".encode())]

    def test_demo_and_edit_link_exports(self):
        result = self.ws.build_demo()
        self.assertEqual(result["graph"]["stats"]["documents"], 16)
        self.assertEqual(result["errors"], [])
        a, b = result["graph"]["nodes"][:2]
        edited = self.ws.edit(a["id"], {"title": "내 관찰 자료", "category": "내 연구", "tags": ["관찰", "탐구"], "notes": "다음 주에 참고"})
        self.assertTrue(any(n["title"] == "내 관찰 자료" for n in edited["graph"]["nodes"]))
        linked = self.ws.link(a["id"], b["id"], "함께 읽고 비교한다")
        self.assertTrue(any(e["kind"] == "manual" for e in linked["graph"]["edges"]))
        self.assertIn("body", self.ws.document(a["id"]))
        exported = json.loads(self.ws.export_json())
        self.assertEqual(exported["stats"]["documents"], 16)
        html = self.ws.export_html()
        self.assertIn(b"window.PKOS_EXPORT=", html)
        self.assertNotIn(b"<script src=", html)
        with zipfile.ZipFile(io.BytesIO(self.ws.export_markdown_zip())) as archive:
            self.assertIn("지식맵.html", archive.namelist())
            self.assertIn("편집정보.json", archive.namelist())
            documents = [n for n in archive.namelist() if n.startswith("문서/")]
            self.assertEqual(len(documents), 16)
            self.assertTrue(all(n.endswith(".md") for n in documents))
            self.assertIn("내 관찰 자료", archive.read("문서/" + a["md"]).decode())
            self.assertNotIn("원본/", "\n".join(archive.namelist()))
        unlinked = self.ws.unlink(a["id"], b["id"])
        self.assertFalse(any({e["source"], e["target"]} == {a["id"], b["id"]} for e in unlinked["graph"]["edges"]))

    def test_privacy_default_and_safe_inline_export(self):
        self.ws.build_uploads([("연락.txt", "합성 연락처입니다. 전화번호: 010-1234-5678".encode())])
        node = self.ws.graph["nodes"][0]
        self.assertNotIn("010-1234-5678", self.ws.document(node["id"])["body"])
        self.assertNotIn("010-1234-5678", self.ws.export_json().decode())
        self.ws.edit(node["id"], {"title": "</script><script>OWNED_SCRIPT</script>"})
        self.assertNotIn(b"</script><script>OWNED_SCRIPT", self.ws.export_html())
        assert self.ws._output is not None
        privacy = json.loads((self.ws._output / "_개인정보.json").read_text(encoding="utf-8"))
        self.assertTrue(all("original" not in r and "context" not in r for r in privacy["rows"]))
        with zipfile.ZipFile(io.BytesIO(self.ws.export_markdown_zip())) as archive:
            for name in archive.namelist():
                content = archive.read(name).decode("utf-8")
                self.assertNotIn("010-1234-5678", content, name)
                self.assertNotIn(str(self.ws._root), content, name)
                self.assertNotIn(self.ws._root.as_posix(), content, name)
            self.assertNotIn("연락.txt", archive.namelist())

    def test_safe_zip_and_nested_zip(self):
        nested = packed([("관찰.txt", "합성 관찰 기록입니다.")])
        outer = packed([("한글/", b""), ("한글/연구.zip", nested)])
        result = self.ws.build_uploads([("자료.zip", outer)])
        self.assertEqual(result["graph"]["stats"]["documents"], 1)
        self.assertIn("자료.zip_내용/한글/연구.zip_내용/관찰.txt", result["graph"]["nodes"][0]["source"])
        self.assertEqual(result["stats"]["inspected_entries"], 4)

    def test_invalid_names_reject_whole_batch_and_preserve_previous_map(self):
        self.ws.build_uploads(self.documents())
        assert self.ws._output is not None
        before, project = self.ws.snapshot(), self.ws._output.parent
        names = ["../escape.txt", "/absolute.txt", "C:/outside.txt", "C:relative.txt", "a\\b.txt",
                 "//server/share.txt", "NUL.txt", "COM1.md", "COM¹.md", "a/../b.txt", "a//b.txt",
                 "trailing .txt.", "file.txt ", "alternate:stream.txt", "bad\x00.txt", "bad\u202e.txt"]
        for name in names:
            with self.subTest(name=name), self.assertRaises(UploadValidationError):
                self.ws.build_uploads([("valid.txt", b"Some new valid document."), (name, b"payload")])
            self.assertEqual(self.ws.snapshot(), before)
            self.assertEqual(list(self.ws._root.iterdir()), [project])

    def test_unsafe_archive_members_and_symlinks(self):
        bad = ["../escape.txt", "/root.txt", "C:/escape.txt", "NUL.md"]
        for name in bad:
            with self.subTest(name=name), self.assertRaises(UploadValidationError):
                self.ws.build_uploads([("bad.zip", packed([(name, b"x")]))])
        # Windows' ZIP writer normalizes backslashes; patch both header names
        # to exercise hostile archives exactly as received from other systems.
        for before, after in [(b"a/b.txt", b"a\\b.txt"), (b"bad_0.txt", b"bad\x000.txt")]:
            archive = packed([(before.decode(), b"x")]).replace(before, after)
            with self.assertRaises(UploadValidationError):
                self.ws.build_uploads([("bad.zip", archive)])
        link = zipfile.ZipInfo("link.txt")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(UploadValidationError):
            self.ws.build_uploads([("link.zip", packed([(link, b"../outside")]))])

    def test_duplicate_case_and_file_directory_conflicts(self):
        for files in [ [("A.txt", b"a"), ("a.txt", b"b")],
                       [("a.txt", b"a"), ("a.txt/b.md", b"b")],
                       [("자료.zip", packed([("A.txt", b"a"), ("a.txt", b"b")]))] ]:
            with self.subTest(files=[n for n, _ in files]), self.assertRaises(UploadValidationError):
                self.ws.build_uploads(files)
            self.assertEqual(list(self.ws._root.iterdir()), [])

    def test_truncated_and_encrypted_archives_are_validation_errors(self):
        normal = packed([("note.txt", b"sample")])
        encrypted = bytearray(normal)
        struct.pack_into("<H", encrypted, 6, struct.unpack_from("<H", encrypted, 6)[0] | 1)
        center = encrypted.index(b"PK\x01\x02")
        struct.pack_into("<H", encrypted, center + 8, struct.unpack_from("<H", encrypted, center + 8)[0] | 1)
        for data in [normal[:20], bytes(encrypted), b"not a ZIP"]:
            with self.subTest(data=len(data)), self.assertRaises(UploadValidationError):
                self.ws.build_uploads([("bad.zip", data)])

    def test_size_count_and_depth_budgets(self):
        cases = [
            (UploadLimits(max_file_bytes=8), [("a.txt", b"123456789")]),
            (UploadLimits(max_total_bytes=10), [("a.txt", b"123456"), ("b.txt", b"123456")]),
            (UploadLimits(max_expanded_bytes=500), [("a.zip", packed([("b.txt", b"a" * 1000)]))]),
            (UploadLimits(max_files=2), [("a.zip", packed([("folder/", b""), ("b.txt", b"text")]))]),
            (UploadLimits(max_zip_depth=1), [("a.zip", packed([("b.zip", packed([("c.txt", b"sample")]))]))]),
        ]
        for limits, files in cases:
            with self.subTest(limits=limits):
                ws = WebWorkspace(limits=limits, temp_parent=self.temp.name)
                try:
                    with self.assertRaises(UploadValidationError):
                        ws.build_uploads(files)
                    self.assertEqual(list(ws._root.iterdir()), [])
                finally:
                    ws.close()

    def test_office_zip_bombs_and_embedded_archives_are_checked_before_readers(self):
        packages = [
            packed([("word/document.xml", b"a" * 5000)]),
            packed([("word/document.xml", b"<document/>"), ("word/embeddings/data.zip", packed([("huge.txt", b"a" * 5000)]))]),
        ]
        for package in packages:
            with self.subTest(size=len(package)):
                ws = WebWorkspace(limits=UploadLimits(max_expanded_bytes=2000), temp_parent=self.temp.name)
                try:
                    with patch("web_workspace.Converter.run") as converter, self.assertRaises(UploadValidationError):
                        ws.build_uploads([("document.docx", package)])
                    converter.assert_not_called()
                finally:
                    ws.close()

    def test_regular_office_package_is_read_without_extracting_images(self):
        from docx import Document
        doc = Document()
        doc.add_heading("합성 연구 관찰", 0)
        doc.add_paragraph("관찰 자료를 정리하고 다음 연구 질문을 만듭니다.")
        stream = io.BytesIO()
        doc.save(stream)
        result = self.ws.build_uploads([("연구.docx", stream.getvalue())])
        self.assertEqual(result["graph"]["nodes"][0]["format"], "docx")
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["stats"]["inspected_entries"], 1)
        assert self.ws._output is not None
        self.assertEqual(list(self.ws._output.rglob("*.png")), [])

    def test_corrupt_document_errors_are_separate_from_batch_validation(self):
        result = self.ws.build_uploads(self.documents() + [("빈파일.txt", b"")])
        self.assertEqual(result["graph"]["stats"]["documents"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["file"], "빈파일.txt")
        before = self.ws.snapshot()
        with self.assertRaises(UploadValidationError):
            self.ws.build_uploads([("빈파일.txt", b"")])
        self.assertEqual(self.ws.snapshot(), before)

    def test_unexpected_failure_rolls_back_and_success_cleans_old_project(self):
        self.ws.build_uploads(self.documents())
        assert self.ws._output is not None
        old, before = self.ws._output.parent, self.ws.snapshot()
        with patch("web_workspace.Converter.run", side_effect=RuntimeError("test failure")):
            with self.assertRaises(WorkspaceError):
                self.ws.build_uploads([("new.txt", b"new source")])
        self.assertEqual(self.ws.snapshot(), before)
        self.assertEqual(list(self.ws._root.iterdir()), [old])
        self.ws.build_uploads([("new.txt", b"new unique source document")])
        self.assertFalse(old.exists())
        self.assertEqual(len(list(self.ws._root.iterdir())), 1)

    def test_isolation_busy_closed_and_snapshot_copy(self):
        self.ws.build_uploads(self.documents())
        other = WebWorkspace(temp_parent=self.temp.name)
        try:
            self.assertNotEqual(self.ws._root, other._root)
            self.assertIsNone(other.graph)
            copied = self.ws.graph
            copied["nodes"].clear()
            self.assertEqual(len(self.ws.graph["nodes"]), 2)
            self.ws._lock.acquire()
            try:
                with self.assertRaises(WorkspaceBusyError):
                    self.ws.build_uploads(self.documents())
                with self.assertRaises(WorkspaceBusyError):
                    self.ws.close()
            finally:
                self.ws._lock.release()
            location = other._root
            other.close()
            self.assertFalse(location.exists())
            for method in [other.snapshot, other.export_json, lambda: other.build_uploads(self.documents())]:
                with self.assertRaises(WorkspaceError):
                    method()
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
