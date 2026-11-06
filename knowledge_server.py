"""Local-only PKOS desktop companion. Run through 지식맵.py.

The existing converter owns conversion; knowledge owns the graph. This module
connects both to a loopback browser interface without cloud services or a CDN.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def export_html(graph: dict) -> str:
    """Self-contained, read-only map: no original files or network assets."""
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    data = json.dumps(graph, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    import re
    page = re.sub(r'<link\b[^>]*href=["\'][^"\']*app\.css[^"\']*["\'][^>]*>', lambda _: "<style>" + css + "</style>", page)
    inline = "<script>window.PKOS_EXPORT=" + data + ";</script>\n<script>" + js.replace("</script", "<\\/script") + "</script>"
    page = re.sub(r'<script\b[^>]*src=["\'][^"\']*app\.js[^"\']*["\'][^>]*>\s*</script>', lambda _: inline, page)
    return page


class AppState:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.resolve()
        self.lock = threading.RLock()
        self.busy = False
        self.phase = "ready"
        self.message = "자료 폴더를 선택하거나 예제로 시작하세요."
        self.logs: list[str] = []
        self.error = ""
        self.graph = None
        self.stats: dict = {}
        self.project = {"source": "", "output": "", "title": "나의 지식맵", "mode": "convert", "privacy": True, "ocr": False}
        self.thread = None
        self.picker = None
        self.picker_cancelled = False
        self._restore()

    def _restore(self):
        from knowledge import build_graph
        config = self.state_dir / "last_project.json"
        if not config.exists():
            return
        try:
            saved = json.loads(config.read_text(encoding="utf-8"))
            project = saved.get("project", {})
            if not isinstance(project, dict):
                raise ValueError("저장된 프로젝트 형식이 올바르지 않습니다.")
            self.project.update({k: str(project[k]) for k in ("source", "output", "title", "mode") if k in project})
            out = Path(self.project["output"])
            if self.project["output"] and (out / "_index.json").is_file():
                self.project.update(self.saved_options(out))
                self.graph = build_graph(out, title=self.project["title"])
                self.message = "지난 지식맵을 불러왔습니다."
        except Exception as e:
            self.error = "지난 프로젝트를 열지 못했습니다. 결과 폴더를 다시 선택하세요. " + str(e)

    @staticmethod
    def saved_options(out: Path):
        try:
            options = json.loads((out / "_knowledge_settings.json").read_text(encoding="utf-8"))
            return {k: options[k] if isinstance(options.get(k), bool) else None for k in ("privacy", "ocr")}
        except (OSError, ValueError, TypeError):
            return {"privacy": None, "ocr": None}

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({"version": VERSION, "busy": self.busy, "phase": self.phase,
                                  "message": self.message, "logs": self.logs[-100:], "error": self.error,
                                  "graph": self.graph, "project": self.project, "stats": self.stats})

    def log(self, *parts):
        line = " ".join(str(x) for x in parts)
        with self.lock:
            self.logs.extend(line.splitlines())
            self.logs = self.logs[-100:]

    def output(self) -> Path:
        if not self.project["output"] or self.graph is None:
            raise ValueError("먼저 지식맵을 만들어 주세요.")
        return Path(self.project["output"])

    @staticmethod
    def validate_project(data):
        mode = data.get("mode", "convert")
        if mode not in ("convert", "existing"):
            raise ValueError("불러오기 방식을 확인하세요.")
        raw = str(data.get("source", "")).strip().strip('"')
        if not raw:
            raise ValueError("자료 폴더를 선택하세요.")
        source = Path(raw).expanduser().resolve()
        if not source.is_dir():
            raise ValueError("자료 폴더를 찾을 수 없습니다. 경로와 드라이브 연결을 확인하세요.")
        title = str(data.get("title", "나의 지식맵")).strip()[:100] or "나의 지식맵"
        if mode == "existing":
            out = source
            if not (out / "_index.json").is_file():
                raise ValueError("이 폴더에 _index.json이 없습니다. 기존 _변환결과 폴더를 선택하세요.")
        else:
            if (source / "_index.json").is_file():
                raise ValueError("변환 결과 폴더입니다. ‘기존 변환 결과’로 불러오거나 원본 자료 폴더를 선택하세요.")
            raw_out = str(data.get("output", "")).strip().strip('"')
            out = Path(raw_out).expanduser().resolve() if raw_out else source / "_변환결과"
            if out == source or source.is_relative_to(out):
                raise ValueError("결과 폴더는 원본과 다른 하위 폴더 또는 별도 폴더로 지정하세요.")
            if out.exists() and not out.is_dir():
                raise ValueError("결과 위치에 같은 이름의 파일이 있습니다.")
            if out.is_dir() and any(out.iterdir()) and not (out / "_index.json").is_file():
                raise ValueError("결과 폴더는 비어 있는 새 폴더 또는 기존 PKOS 결과 폴더를 선택하세요.")
            # A result folder belongs to a source: don't mix unrelated archives.
            if (out / "_index.json").is_file():
                try:
                    old = json.loads((out / "_index.json").read_text(encoding="utf-8-sig"))
                except (ValueError, OSError) as e:
                    raise ValueError("기존 변환 기록을 읽지 못했습니다. 새 결과 폴더를 지정하세요.") from e
                old_source = old.get("원본", "") if isinstance(old, dict) else ""
                if old_source and Path(old_source).resolve() != source:
                    raise ValueError("다른 원본 자료의 결과 폴더입니다. 이 자료용 새 결과 폴더를 지정하세요.")
        return {"source": str(source), "output": str(out), "title": title, "mode": mode}

    def start(self, data):
        project = self.validate_project(data)
        privacy = data.get("privacy", True) is not False
        ocr = data.get("ocr", False) is True
        project.update({"privacy": privacy, "ocr": ocr} if project["mode"] == "convert" else self.saved_options(Path(project["output"])))
        with self.lock:
            if self.busy:
                raise ValueError("자료를 처리하고 있습니다. 완료된 뒤 다시 시도하세요.")
            self.busy = True
            self.error = ""
            self.logs = []
            self.phase = "converting" if project["mode"] == "convert" else "mapping"
            self.message = "자료를 읽고 있습니다. 파일 수와 크기에 따라 시간이 걸릴 수 있습니다."
            self.thread = threading.Thread(target=self._build, args=(project, privacy, ocr), daemon=False)
            self.thread.start()

    def _build(self, project, privacy, ocr):
        from knowledge import build_graph
        try:
            stats = {}
            out = Path(project["output"])
            if project["mode"] == "convert":
                from engine import Converter, Settings
                if ocr:
                    from engine.ocr import available
                    ok, reason = available().get("tesseract", (False, "Tesseract를 찾지 못했습니다."))
                    if not ok:
                        raise ValueError("글자 인식 준비가 되지 않았습니다: " + reason + ". 사용설명서의 OCR 항목을 확인하거나 OCR을 끄세요.")
                options = {"privacy": privacy, "ocr": ocr, "report_original": False}
                previous_options = None
                options_path = out / "_knowledge_settings.json"
                if options_path.is_file():
                    try:
                        previous_options = json.loads(options_path.read_text(encoding="utf-8"))
                    except (ValueError, OSError):
                        pass
                # Converter's legacy cache does not include privacy settings.
                # Re-read files when options change so unmasked cached text is
                # never mistaken for output made with masking enabled.
                reuse = previous_options == options
                converter = Converter(Settings(src=project["source"], out=str(out), privacy_on=privacy,
                                               report_original=False, skip_existing=reuse,
                                               ocr_engine="tesseract" if ocr else "없음"))
                converter.log = self.log
                stats = converter.run()
                atomic_json(options_path, options)
            with self.lock:
                self.phase = "mapping"
                self.message = "태그와 자료 사이의 연결을 만들고 있습니다."
            graph = build_graph(out, title=project["title"])
            # Existing-mode imports use the source path recorded by the converter.
            if project["mode"] == "existing":
                manifest = json.loads((out / "_index.json").read_text(encoding="utf-8-sig"))
                if isinstance(manifest, dict) and manifest.get("원본"):
                    project["original_root"] = str(manifest["원본"])
            self.save_exports(out, graph)
            atomic_json(self.state_dir / "last_project.json", {"version": VERSION, "project": project})
            with self.lock:
                self.project = project
                self.graph = graph
                self.stats = stats
                self.phase = "complete"
                n = graph["stats"]["documents"]
                self.message = f"자료 {n}개로 지식맵을 만들었습니다." if n else "읽을 수 있는 자료가 없습니다. 변환 기록과 폴더를 확인하세요."
                if stats.get("errors"):
                    self.message += f" 읽지 못한 파일 {stats['errors']}개는 결과 폴더의 _오류.md를 확인하세요."
                for warning in graph.get("warnings", []):
                    self.log(warning)
        except Exception as e:
            with self.lock:
                self.error = str(e) or type(e).__name__
                self.message = "작업을 완료하지 못했습니다. 아래 안내를 확인하세요."
                self.phase = "error"
            self.log("오류:", self.error)
        finally:
            with self.lock:
                self.busy = False

    def save_exports(self, out: Path, graph):
        atomic_json(out / "지식맵.json", graph)
        dest = out / "지식맵.html"
        temp = dest.with_suffix(".html.tmp")
        temp.write_text(export_html(graph), encoding="utf-8")
        temp.replace(dest)

    def mutate(self, kind, data):
        from knowledge import update_document, add_link, remove_link
        with self.lock:
            if self.busy:
                raise ValueError("변환이 끝난 뒤 수정하세요.")
            out = self.output()
            if kind == "edit":
                graph = update_document(out, str(data.get("id", "")), {k: data[k] for k in ("title", "category", "tags", "notes") if k in data}, title=self.project["title"])
            elif kind == "link":
                graph = add_link(out, str(data.get("source", "")), str(data.get("target", "")), str(data.get("label", "")), title=self.project["title"])
            else:
                graph = remove_link(out, str(data.get("source", "")), str(data.get("target", "")), title=self.project["title"])
            self.graph = graph
            self.save_exports(out, graph)
            return graph

    def demo(self):
        # Examples are shipped with the app. Results stay in per-user local storage.
        out = self.state_dir / "예제_결과"
        self.start({"source": str(ROOT / "예제자료"), "output": str(out), "title": "나의 배움과 일상", "privacy": True})

    def choose_folder(self, kind):
        flags = {}
        if sys.platform == "win32":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1  # SW_SHOWNORMAL (winuser.h)
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startup}
        with self.lock:
            if self.picker is not None:
                raise ValueError("이미 열린 폴더 선택 창을 닫거나 선택을 취소하세요.")
            process = subprocess.Popen([sys.executable, str(ROOT / "지식맵.py"), "--pick-folder", kind],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       encoding="utf-8", **flags)
            self.picker = process
            self.picker_cancelled = False
        try:
            stdout, _ = process.communicate(timeout=300)
            with self.lock:
                if self.picker_cancelled:
                    return ""
            if process.returncode:
                raise ValueError("폴더 선택 창을 열지 못했습니다. 탐색기의 폴더 주소를 복사해 입력하세요.")
            return stdout.strip()
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise ValueError("폴더 선택을 종료했습니다. 다시 선택하거나 폴더 경로를 직접 입력하세요.")
        finally:
            with self.lock:
                if self.picker is process:
                    self.picker = None

    def cancel_browse(self):
        with self.lock:
            self.picker_cancelled = True
            if self.picker is not None and self.picker.poll() is None:
                self.picker.terminate()

    def resolve_document(self, doc_id, kind):
        from knowledge import read_document
        with self.lock:
            out = self.output()
            doc = read_document(out, doc_id)
            if kind == "md":
                base = out.resolve()
                rel = doc["md"]
            elif kind == "source":
                manifest = json.loads((out / "_index.json").read_text(encoding="utf-8-sig"))
                original = manifest.get("원본", "") if isinstance(manifest, dict) else ""
                if not original:
                    raise ValueError("원본 폴더 기록이 없습니다. 변환본을 열어 주세요.")
                base = Path(original).resolve()
                if base.is_file():
                    base = base.parent
                rel = doc["source"]
                if "!" in rel:
                    rel = rel.split("!", 1)[0]
            else:
                raise ValueError("열 파일 종류를 확인하세요.")
            path = (base / rel).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise ValueError("파일을 찾을 수 없습니다. 원본이 이동했다면 새 위치에서 다시 변환하세요.")
            allowed = {".md", ".txt", ".pdf", ".hwp", ".hwpx", ".hml", ".doc", ".docx", ".ppt", ".pptx", ".xlsx", ".xls", ".csv", ".tsv", ".odt", ".ods", ".odp", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".mp4", ".mp3", ".wav", ".zip", ".json"}
            if path.suffix.lower() not in allowed:
                raise ValueError("이 형식은 자동으로 열지 않습니다. 탐색기에서 확인하거나 변환본을 열어 주세요.")
            return path


def open_file(path: Path):
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state, port=0):
        self.app = state
        self.token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = "http://" + self.host
        self.cookie_name = "pkos_" + str(self.server_port)


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def log_message(self, *_):
        pass  # URLs may contain the one-time launch secret or local file labels.

    def send_bytes(self, data, mime="application/json; charset=utf-8", status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), status=status)

    def authorized(self):
        if self.headers.get("Host") != self.server.host:
            return False
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
            item = cookies.get(self.server.cookie_name)
            return item is not None and secrets.compare_digest(item.value, self.server.token)
        except Exception:
            return False

    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        token = query.get("session", [""])[0]
        if parsed.path == "/" and self.headers.get("Host") == self.server.host and token and secrets.compare_digest(token, self.server.token):
            self.send_bytes(b"", status=303, headers={"Location": "/", "Set-Cookie": f"{self.server.cookie_name}={self.server.token}; HttpOnly; SameSite=Strict; Path=/"})
            return
        if not self.authorized():
            self.json_response({"error": "프로그램 시작 시 표시된 주소로 다시 열어 주세요."}, 403)
            return
        try:
            path = parsed.path
            static = {"/": (ROOT / "web/index.html", "text/html; charset=utf-8"),
                      "/index.html": (ROOT / "web/index.html", "text/html; charset=utf-8"),
                      "/app.css": (ROOT / "web/app.css", "text/css; charset=utf-8"),
                      "/app.js": (ROOT / "web/app.js", "text/javascript; charset=utf-8"),
                      "/web/app.css": (ROOT / "web/app.css", "text/css; charset=utf-8"),
                      "/web/app.js": (ROOT / "web/app.js", "text/javascript; charset=utf-8"),
                      "/static/app.css": (ROOT / "web/app.css", "text/css; charset=utf-8"),
                      "/static/app.js": (ROOT / "web/app.js", "text/javascript; charset=utf-8"),
                      "/manual": (ROOT / "사용설명서.html", "text/html; charset=utf-8")}
            if path in static:
                file, mime = static[path]
                self.send_bytes(file.read_bytes(), mime)
            elif path == "/favicon.ico":
                self.send_bytes(b"", "image/x-icon", 204)
            elif path == "/api/state":
                self.json_response(self.server.app.snapshot())
            elif path == "/api/graph":
                self.json_response(self.server.app.snapshot()["graph"])
            elif path == "/api/document":
                from knowledge import read_document
                with self.server.app.lock:
                    self.json_response(read_document(self.server.app.output(), query.get("id", [""])[0]))
            elif path == "/api/export":
                graph = self.server.app.snapshot()["graph"]
                if graph is None:
                    raise ValueError("먼저 지식맵을 만들어 주세요.")
                fmt = query.get("format", ["html"])[0]
                if fmt == "html":
                    data = export_html(graph).encode("utf-8")
                    mime = "text/html; charset=utf-8"
                elif fmt == "json":
                    data = json.dumps(graph, ensure_ascii=False, indent=2).encode("utf-8")
                    mime = "application/json; charset=utf-8"
                else:
                    raise ValueError("내보내기 형식은 html 또는 json입니다.")
                self.send_bytes(data, mime, headers={"Content-Disposition": f'attachment; filename="PKOS-map.{fmt}"; filename*=UTF-8\'\'{quote("지식맵." + fmt)}'})
            else:
                self.json_response({"error": "페이지를 찾을 수 없습니다."}, 404)
        except (ValueError, OSError, KeyError) as e:
            self.json_response({"error": str(e)}, 400)
        except Exception as e:
            self.server.app.log("요청 오류:", str(e))
            self.json_response({"error": "요청을 처리하지 못했습니다. " + str(e)}, 500)

    def do_POST(self):
        if not self.authorized() or self.headers.get("Origin", self.server.origin) != self.server.origin:
            self.json_response({"error": "이 컴퓨터의 지식맵 화면에서 다시 시도하세요."}, 403)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.json_response({"error": "JSON 요청만 허용합니다."}, 415)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 100_000:
                raise ValueError("요청이 너무 큽니다.")
            data = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("요청 형식이 올바르지 않습니다.")
            path = urlsplit(self.path).path
            app = self.server.app
            if path == "/api/build":
                app.start(data)
                self.json_response({"ok": True})
            elif path == "/api/demo":
                app.demo()
                self.json_response({"ok": True})
            elif path in ("/api/edit", "/api/link", "/api/unlink"):
                self.json_response({"graph": app.mutate(path.rsplit("/", 1)[-1], data)})
            elif path == "/api/open":
                open_file(app.resolve_document(str(data.get("id", "")), data.get("kind", "source")))
                self.json_response({"ok": True})
            elif path == "/api/browse":
                kind = "output" if data.get("kind") == "output" else "source"
                self.json_response({"path": app.choose_folder(kind)})
            elif path == "/api/cancel-browse":
                app.cancel_browse()
                self.json_response({"ok": True})
            elif path == "/api/shutdown":
                if app.busy:
                    raise ValueError("변환이 진행 중입니다. 완료 후 종료하세요.")
                self.json_response({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.json_response({"error": "요청을 찾을 수 없습니다."}, 404)
        except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as e:
            self.json_response({"error": str(e)}, 400)
        except Exception as e:
            self.server.app.log("요청 오류:", str(e))
            self.json_response({"error": "요청을 처리하지 못했습니다. " + str(e)}, 500)


def main(argv=None):
    parser = argparse.ArgumentParser(description="PKOS 지식맵 — 내 컴퓨터에서 자료 변환·분류·연결")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    parser.add_argument("--port", type=int, default=0, help="로컬 포트 (기본: 빈 포트 자동 선택)")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".pkos_knowledge", help="최근 프로젝트 설정 폴더")
    parser.add_argument("--build", metavar="FOLDER", help="화면 없이 원본 자료로 지도 만들기")
    parser.add_argument("--existing", action="store_true", help="--build 경로가 기존 변환 결과임")
    parser.add_argument("--out", default="", help="변환 결과 위치")
    parser.add_argument("--title", default="나의 지식맵")
    parser.add_argument("--pick-folder", choices=["source", "output"], help=argparse.SUPPRESS)
    parser.add_argument("--자가진단", "--selftest", action="store_true", dest="selftest")
    args = parser.parse_args(argv)
    if args.pick_folder:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        window.update_idletasks()
        path = filedialog.askdirectory(parent=window, title="원본 자료 폴더 선택" if args.pick_folder == "source" else "결과를 저장할 폴더 선택", mustexist=args.pick_folder == "source")
        window.destroy()
        print(path, flush=True)
        return 0
    if args.selftest:
        import unittest
        loader = unittest.TestLoader()
        suite = unittest.TestSuite([loader.discover(str(ROOT / "tests"), pattern="test_knowledge.py"), loader.discover(str(ROOT / "tests"), pattern="test_knowledge_server.py")])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    app = AppState(args.state_dir)
    if args.build:
        app.start({"source": args.build, "output": args.out, "title": args.title, "mode": "existing" if args.existing else "convert"})
        app.thread.join()
        print(app.message)
        if app.error:
            print(app.error)
            return 1
        print(Path(app.project["output"]) / "지식맵.html")
        return 0
    server = LocalServer(app, args.port)
    address = server.origin + "/?session=" + server.token
    print("\nPKOS 지식맵 " + VERSION + "\n")
    print("이 컴퓨터에서만 실행됩니다. 자료를 인터넷으로 전송하지 않습니다.")
    print("이 창을 열어 두세요. 종료는 지식맵의 종료 버튼 또는 Ctrl+C입니다.\n")
    print(address, flush=True)
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(address,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n종료합니다. 진행 중인 변환이 있으면 완료까지 기다립니다.")
    finally:
        app.cancel_browse()
        server.server_close()
        if app.thread and app.thread.is_alive():
            app.thread.join()
    return 0
