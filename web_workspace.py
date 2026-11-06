"""Session-local PKOS workspace for the Streamlit front end.

Keep one WebWorkspace in st.session_state, never in st.cache_resource. Uploads
are staged and validated before conversion; only a completed map replaces the
current project. No source-opening, external OCR or external API is exposed.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import copy
import io
import json
from pathlib import Path, PureWindowsPath
import re
import stat
import tempfile
import threading
import unicodedata
import zipfile
import zlib

from engine import Converter, Settings
from engine.sniff import sniff_bytes
from knowledge import add_link, build_graph, read_document, remove_link, update_document
from knowledge_server import export_html as render_html

ROOT = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = tuple("txt md markdown csv tsv html htm pdf doc docx dotx rtf hwp hwpx odt ppt pptx pptm ppsx potx xls xlsx xlsm xltx xltm srt vtt smi jpg jpeg png gif bmp webp tif tiff svg zip".split())
_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)}


class WorkspaceError(RuntimeError):
    """A closed workspace, missing map, or failed conversion."""


class WorkspaceBusyError(ValueError):
    """The same session already has an operation in progress."""


class UploadValidationError(ValueError):
    """An upload name, archive, or processing budget is invalid."""


@dataclass(frozen=True)
class UploadLimits:
    max_total_bytes: int = 50 * 1024 * 1024
    max_file_bytes: int = 20 * 1024 * 1024
    max_expanded_bytes: int = 100 * 1024 * 1024
    # Uploaded items plus ALL archive entries, including directories and Office
    # document parts. Nested compressed bytes count again when decompressed.
    max_files: int = 300
    max_zip_depth: int = 2

    def __post_init__(self):
        for field in ("max_total_bytes", "max_file_bytes", "max_expanded_bytes", "max_files", "max_zip_depth"):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field} 값은 양의 정수여야 합니다.")


def _safe_name(name: str, *, directory=False) -> str:
    if not isinstance(name, str) or not name:
        raise UploadValidationError("파일 이름이 비어 있습니다.")
    name = unicodedata.normalize("NFC", name)
    if directory and name.endswith("/"):
        name = name[:-1]
    if not name or len(name) > 240 or "\\" in name or PureWindowsPath(name).drive or name.startswith("/"):
        raise UploadValidationError("절대 경로·Windows 경로·너무 긴 파일 이름은 사용할 수 없습니다.")
    parts = name.split("/")
    for part in parts:
        if part in ("", ".", "..") or len(part) > 120 or part.endswith((".", " ")):
            raise UploadValidationError("빈 경로·상위 폴더 경로·끝의 점/공백이 있는 이름은 사용할 수 없습니다.")
        if any(c in '<>:"|?*' or unicodedata.category(c) in ("Cc", "Cf") for c in part):
            raise UploadValidationError("파일 이름에 허용하지 않는 문자가 있습니다.")
        if unicodedata.normalize("NFKC", part.split(".", 1)[0].rstrip(" .")).casefold() in _RESERVED:
            raise UploadValidationError("Windows 예약 파일 이름은 사용할 수 없습니다.")
    return "/".join(parts)


def _member_name(info: zipfile.ZipInfo) -> str:
    name = info.orig_filename
    if not info.flag_bits & 0x800:
        try:
            raw = name.encode("cp437")
            for encoding in ("utf-8", "cp949"):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    pass
        except UnicodeEncodeError:
            pass
    return name


class _UploadBatch:
    def __init__(self, source: Path, limits: UploadLimits):
        self.source, self.limits = source, limits
        self.uploaded_bytes = self.expanded_bytes = self.entries = self.documents = 0
        self.paths: set[str] = set()

    def count(self):
        self.entries += 1
        if self.entries > self.limits.max_files:
            raise UploadValidationError(f"업로드와 압축 내부 항목은 디렉토리·문서 내부 부품을 포함해 최대 {self.limits.max_files}개입니다.")

    def expand(self, size: int):
        self.expanded_bytes += size
        if self.expanded_bytes > self.limits.max_expanded_bytes:
            raise UploadValidationError("전체 압축 해제 크기 한도를 초과했습니다.")

    def add(self, name, payload):
        name = _safe_name(name)
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise UploadValidationError("업로드 내용은 바이트 데이터여야 합니다.")
        size = len(payload)
        if size > self.limits.max_file_bytes:
            raise UploadValidationError("개별 업로드 파일 크기 한도를 초과했습니다.")
        self.uploaded_bytes += size
        if self.uploaded_bytes > self.limits.max_total_bytes:
            raise UploadValidationError("업로드 묶음의 전체 크기 한도를 초과했습니다.")
        self.count()
        self.expand(size)
        self._process(name, bytes(payload), depth=0)

    def _process(self, name: str, data: bytes, depth: int):
        suffix = Path(name).suffix.lower().lstrip(".")
        if suffix not in ALLOWED_EXTENSIONS:
            raise UploadValidationError(f"웹판에서 지원하지 않는 확장자입니다: {suffix or '(확장자 없음)'}")
        is_archive = zipfile.is_zipfile(io.BytesIO(data))
        if data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")) and not is_archive:
            raise UploadValidationError("ZIP 또는 압축 문서가 손상되었거나 잘렸습니다.")
        if suffix == "zip" and not is_archive:
            raise UploadValidationError("ZIP 파일을 읽을 수 없습니다. 압축을 다시 만들어 주세요.")
        if is_archive:
            # Inspect BEFORE sniff_bytes: the format detector may read mimetype.
            parts = self._inspect_archive(data, depth + 1)
            kind = sniff_bytes(data, name=name).fmt
            if kind == "zip":
                if not parts:
                    raise UploadValidationError("압축 파일 안에 읽을 파일이 없습니다.")
                prefix = name + "_내용/"
                for member, contents in parts:
                    self._process(_safe_name(prefix + member), contents, depth + 1)
                return
            # Office/HWPX/ODT contents were bounded too. Preserve the package for
            # the existing reader rather than unpacking document parts as notes.
            for _, contents in parts:
                self._inspect_embedded(contents, depth + 2)
        self._write(name, data)

    def _inspect_embedded(self, data: bytes, depth: int):
        if zipfile.is_zipfile(io.BytesIO(data)):
            for _, contents in self._inspect_archive(data, depth):
                self._inspect_embedded(contents, depth + 1)
        elif data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
            raise UploadValidationError("문서 안에 손상된 압축 자료가 있습니다.")

    def _inspect_archive(self, data: bytes, depth: int) -> list[tuple[str, bytes]]:
        if depth > self.limits.max_zip_depth:
            raise UploadValidationError(f"ZIP/압축 문서 중첩은 최대 {self.limits.max_zip_depth}단계까지 허용합니다.")
        result, seen = [], set()
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.infolist()) + self.entries > self.limits.max_files:
                    raise UploadValidationError("압축 내부 항목 수 한도를 초과했습니다.")
                for info in archive.infolist():
                    self.count()
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise UploadValidationError("심볼릭 링크나 특수 파일이 들어 있는 압축은 사용할 수 없습니다.")
                    name = _safe_name(_member_name(info), directory=info.is_dir())
                    key = name.casefold()
                    if key in seen:
                        raise UploadValidationError("압축 안에 이름이 겹치는 항목이 있습니다.")
                    seen.add(key)
                    if info.flag_bits & 1:
                        raise UploadValidationError("암호가 걸린 압축은 풀어서 올려 주세요.")
                    if info.file_size > self.limits.max_file_bytes:
                        raise UploadValidationError("압축 내부 개별 파일 크기 한도를 초과했습니다.")
                    if info.is_dir():
                        if info.file_size:
                            raise UploadValidationError("내용이 든 디렉토리 항목은 사용할 수 없습니다.")
                        continue
                    if self.expanded_bytes + info.file_size > self.limits.max_expanded_bytes:
                        raise UploadValidationError("전체 압축 해제 크기 한도를 초과했습니다.")
                    chunks, size = [], 0
                    with archive.open(info) as stream:
                        while chunk := stream.read(64 * 1024):
                            size += len(chunk)
                            self.expand(len(chunk))
                            if size > self.limits.max_file_bytes or size > info.file_size:
                                raise UploadValidationError("압축 내부 개별 파일 크기 한도를 초과했습니다.")
                            chunks.append(chunk)
                    if size != info.file_size:
                        raise UploadValidationError("압축 내부 파일 크기가 올바르지 않습니다.")
                    contents = b"".join(chunks)
                    # Validate embedded packages too, even if an Office reader
                    # happens not to use their parts. Generic ZIP children are
                    # processed below, once, and share this same total budget.
                    result.append((name, contents))
        except UploadValidationError:
            raise
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, OSError, ValueError, zlib.error) as exc:
            raise UploadValidationError("압축 파일을 읽을 수 없습니다. 암호·손상·지원하지 않는 압축 방식을 확인해 주세요.") from exc
        return result

    def _write(self, name: str, data: bytes):
        key = name.casefold()
        if key in self.paths or any(key.startswith(p + "/") or p.startswith(key + "/") for p in self.paths):
            raise UploadValidationError("업로드 파일의 이름 또는 폴더 경로가 겹칩니다.")
        self.paths.add(key)
        path = (self.source / name).resolve()
        if not path.is_relative_to(self.source.resolve()):
            raise UploadValidationError("파일 경로가 임시 자료 폴더를 벗어납니다.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.documents += 1


class WebWorkspace:
    def __init__(self, *, limits: UploadLimits | None = None, temp_parent=None):
        self.limits = limits or UploadLimits()
        self._session = tempfile.TemporaryDirectory(prefix="pkos-web-", dir=temp_parent)
        self._root = Path(self._session.name).resolve()
        self._project = None
        self._output: Path | None = None
        self._graph = None
        self._stats, self._errors = {}, []
        self._lock = threading.Lock()
        self._closed = False

    @contextmanager
    def _operation(self):
        if not self._lock.acquire(blocking=False):
            raise WorkspaceBusyError("이 세션에서 자료를 처리 중입니다. 완료된 뒤 다시 시도하세요.")
        try:
            self._ensure_open()
            yield
        finally:
            self._lock.release()

    def _ensure_open(self):
        if self._closed:
            raise WorkspaceError("이미 정리한 세션입니다. 새 작업공간을 만들어 주세요.")

    def _require_map(self):
        self._ensure_open()
        if self._graph is None or self._output is None:
            raise WorkspaceError("먼저 예제 또는 업로드 자료로 지식맵을 만들어 주세요.")

    @property
    def graph(self):
        self._ensure_open()
        return copy.deepcopy(self._graph)

    @property
    def stats(self):
        self._ensure_open()
        return copy.deepcopy(self._stats)

    @property
    def errors(self):
        self._ensure_open()
        return copy.deepcopy(self._errors)

    def snapshot(self):
        self._ensure_open()
        return {"graph": self.graph, "stats": self.stats, "errors": self.errors}

    def build_demo(self, *, title="나의 배움과 일상", privacy=True):
        demo = ROOT / "예제자료"
        if not demo.is_dir():
            raise WorkspaceError("배포판의 예제자료 폴더를 찾지 못했습니다.")
        return self.build_uploads(((p.relative_to(demo).as_posix(), p.read_bytes()) for p in sorted(demo.rglob("*")) if p.is_file()), title=title, privacy=privacy)

    def build_uploads(self, uploads, *, title="나의 지식맵", privacy=True):
        with self._operation():
            if not isinstance(title, str) or not isinstance(privacy, bool):
                raise UploadValidationError("지도 제목과 개인정보 설정을 확인해 주세요.")
            staged = tempfile.TemporaryDirectory(prefix="project-", dir=self._root)
            committed = False
            try:
                source, output = Path(staged.name) / "원본", Path(staged.name) / "결과"
                source.mkdir()
                batch = _UploadBatch(source, self.limits)
                for item in uploads:
                    if not isinstance(item, (tuple, list)) or len(item) != 2:
                        raise UploadValidationError("업로드 목록은 (파일 이름, 바이트) 쌍이어야 합니다.")
                    batch.add(*item)
                if not batch.documents:
                    raise UploadValidationError("읽을 자료를 한 개 이상 올려 주세요.")
                converter = Converter(Settings(src=str(source), out=str(output), privacy_on=privacy,
                                               report_original=False, extract_images=False, copy_photos=False,
                                               open_archives=False, skip_existing=False, ocr_engine="없음",
                                               max_mb=self.limits.max_file_bytes / 1048576, verbose=False))
                stats = converter.run()
                manifest = json.loads((output / "_index.json").read_text(encoding="utf-8"))
                errors = copy.deepcopy(manifest.get("오류", []))
                for error in errors:
                    message = str(error.get("error", ""))
                    for internal in (str(self._root), self._root.as_posix(), str(self._root).replace("\\", "\\\\")):
                        message = message.replace(internal, "(세션 임시폴더)")
                    error["error"] = message
                graph = build_graph(output, title=title)
                if not graph["nodes"]:
                    detail = errors[0].get("error", "") if errors else "읽을 수 있는 본문을 찾지 못했습니다."
                    raise UploadValidationError("지식맵으로 만들 수 있는 자료가 없습니다. " + detail)
                stats.update(uploaded_bytes=batch.uploaded_bytes, expanded_bytes=batch.expanded_bytes,
                             inspected_entries=batch.entries, source_files=batch.documents)
                old = self._project
                self._project, self._output = staged, output
                self._graph, self._stats, self._errors = graph, stats, errors
                committed = True
                if old is not None:
                    try:
                        old.cleanup()
                    except OSError:
                        # The committed map stays valid; the session directory
                        # owns any remainder and close()/finalization retries it.
                        self._stats["cleanup_warning"] = "이전 임시파일 일부를 즉시 정리하지 못했습니다. 세션 정리 시 다시 처리합니다."
                return self.snapshot()
            except (UploadValidationError, WorkspaceError):
                raise
            except Exception as exc:
                raise WorkspaceError("자료 처리 중 오류가 발생했습니다. 이전 지식맵은 유지됩니다.") from exc
            finally:
                if not committed:
                    staged.cleanup()

    def document(self, doc_id):
        with self._operation():
            self._require_map()
            return read_document(self._output, doc_id)

    def edit(self, doc_id, changes):
        with self._operation():
            self._require_map()
            self._graph = update_document(self._output, doc_id, changes, title=self._graph["title"])
            return self.snapshot()

    def link(self, source, target, label):
        with self._operation():
            self._require_map()
            self._graph = add_link(self._output, source, target, label, title=self._graph["title"])
            return self.snapshot()

    def unlink(self, source, target):
        with self._operation():
            self._require_map()
            self._graph = remove_link(self._output, source, target, title=self._graph["title"])
            return self.snapshot()

    def export_html(self) -> bytes:
        with self._operation():
            self._require_map()
            return render_html(self._graph).encode("utf-8")

    def export_json(self) -> bytes:
        with self._operation():
            self._require_map()
            return json.dumps(self._graph, ensure_ascii=False, indent=2).encode("utf-8")

    def export_markdown_zip(self) -> bytes:
        with self._operation():
            self._require_map()
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("지식맵.json", json.dumps(self._graph, ensure_ascii=False, indent=2))
                archive.writestr("지식맵.html", render_html(self._graph))
                archive.writestr("처리결과.json", json.dumps({"stats": self._stats, "errors": self._errors}, ensure_ascii=False, indent=2))
                archive.writestr("읽어주세요.txt", "정리된 Markdown과 읽기 전용 지식맵입니다.\n업로드 원본과 그림 파일은 포함하지 않습니다.\nJSON/ZIP을 웹앱의 편집 가능한 프로젝트로 복원하는 기능은 없습니다.\n")
                edits = self._output / "_knowledge_edits.json"
                if edits.is_file():
                    archive.writestr("편집정보.json", edits.read_bytes())
                for node in self._graph["nodes"]:
                    relative = _safe_name(node["md"])
                    path = (self._output / relative).resolve()
                    if not path.is_relative_to(self._output.resolve()) or path.is_symlink():
                        raise WorkspaceError("변환 자료의 경로를 확인할 수 없습니다.")
                    text = path.read_text(encoding="utf-8-sig")
                    body = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", text, count=1, flags=re.S).lstrip()
                    body = re.sub(r"\A# [^\n]*\n?", "", body, count=1).lstrip()
                    metadata = {k: node.get(k, "") for k in ("title", "source", "category", "tags", "notes")}
                    front = "---\n" + "\n".join(k + ": " + json.dumps(v, ensure_ascii=False) for k, v in metadata.items()) + "\n---\n\n"
                    archive.writestr("문서/" + relative, front + "# " + node["title"] + "\n\n" + body)
            return buffer.getvalue()

    def close(self):
        if self._closed:
            return
        with self._operation():
            if self._project is not None:
                self._project.cleanup()
            self._session.cleanup()
            self._project = None
            self._output = self._graph = None
            self._stats, self._errors = {}, []
            self._closed = True
