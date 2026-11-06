"""Convert the PKOS manifest into a portable, editable knowledge graph.

No cloud API, embedding model, or third-party package is needed.  The automatic
links are suggestions based on shared tags, and their labels explain the reason.
Manual edits live beside the conversion results, never in the source documents.
"""

from __future__ import annotations

import collections
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
import threading
import unicodedata


EDITS_FILENAME = "_knowledge_edits.json"
GRAPH_FILENAME = "_knowledge_map.json"
MAX_DOCUMENT_CHARS = 2_000_000
MAX_TAGS = 12
AUTO_TAGS = 6
MAX_NEIGHBORS = 3
_LOCK = threading.RLock()
_COLORS = ("#137f77", "#bd692c", "#536bc7", "#9b5695", "#65892f", "#be5362", "#3a86a3", "#8b7151")
_WORDS = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9+#-]{1,29}")
_STOP_WORDS = set("""
그리고 그러나 그래서 따라서 또한 또는 대한 위해 통해 관한 경우 해당 이것 저것
있는 없는 있다 없다 한다 합니다 입니다 됩니다 된다 함께 모두 자료 문서 내용 제목
파일 폴더 사용 활용 방법 다음 이번 지난 오늘 우리 나의 여러분 자신 위한
이러한 그러한 수업의 것으로 것을 것이 하는 하여 하며 하거나 있습니다 없습니다
있으며 있으며 위한 대해서 이후 이전 먼저 가장 같은 다른 여러 관련 각각 등으로
the and for with that this from are was were have has can will not you your
https http www com net org png jpg jpeg gif svg pdf docx pptx xlsx md txt
title source format format_label group tags date images chars detected
""".split())
_PARTICLES = ("으로부터", "에서는", "에게서", "이라면", "이라고", "이라는", "으로써", "으로서", "에서의", "에서", "에게", "까지", "부터", "처럼", "보다", "으로", "이란", "이며", "이고", "이나", "과의", "와의", "에는", "에도", "들을", "들의", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도")


def _text(value, limit: int = 500) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()[:limit]


def _relative(value) -> str:
    """A source/converted path must stay relative on both Windows and POSIX."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("빈 경로나 잘못된 경로입니다.")
    value = value.replace("\\", "/")
    if (PureWindowsPath(value).drive or PurePosixPath(value).is_absolute()
            or ":" in value or any(part == ".." for part in value.split("/"))):
        raise ValueError("결과 폴더 밖의 경로는 읽을 수 없습니다.")
    normalized = str(PurePosixPath(value))
    if normalized in ("", "."):
        raise ValueError("파일 경로가 필요합니다.")
    return normalized


def _inside(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    relative = _relative(relative)
    candidate = (root / relative).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("결과 폴더 밖의 경로는 읽거나 쓸 수 없습니다.")
    if must_exist and not candidate.is_file():
        raise FileNotFoundError(f"변환 파일을 찾지 못했습니다: {relative}")
    return candidate


def _root(output_dir) -> Path:
    root = Path(output_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("변환 결과 폴더를 찾지 못했습니다.")
    return root


def _read_json(path: Path):
    try:
        with path.open(encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"JSON 파일을 읽지 못했습니다: {path.name}") from exc


def _atomic_json(root: Path, name: str, data) -> Path:
    target = _inside(root, name, must_exist=False)
    # Use a same-directory replacement so interrupted writes cannot leave half JSON.
    handle, tmp = tempfile.mkstemp(prefix=".pkos-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


def _frontmatter(text: str) -> tuple[dict, str]:
    """Read only simple PKOS YAML fields; never evaluate YAML constructors."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    match = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.S)
    if not match:
        return {}, text
    meta = {}
    active_list = None
    for line in match.group(1).splitlines():
        if active_list and re.match(r"^\s+-\s+", line):
            meta[active_list].append(_scalar(re.sub(r"^\s+-\s+", "", line)))
            continue
        active_list = None
        found = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not found:
            continue
        key, value = found.groups()
        if not value and key == "tags":
            meta[key] = []
            active_list = key
        else:
            meta[key] = _scalar(value)
    return meta, text[match.end():].lstrip("\n")


def _scalar(value: str):
    value = value.strip()
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        if value.startswith("[") and value.endswith("]"):
            return [part.strip().strip("\"'") for part in value[1:-1].split(",") if part.strip()]
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1].replace("''", "'")
        return value


def _plain(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^\n]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\n]*?\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?m)^\s*[#>*|`~-]+\s*", "", text)
    text = re.sub(r"[*_`|]", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _analysis_body(body: str, source: str, meta: dict) -> str:
    """Exclude only the converter's known provenance line from analysis.

    Match its front-matter signature and exact source/date text at the start,
    after the generated H1. Ordinary prose about sources anywhere else stays.
    The stored/readable Markdown body is never changed.
    """
    if (meta.get("source") != source or "detected" not in meta
            or "format_label" not in meta):
        return body
    shown = source.replace("`", "'")
    note = f"*원본 `{shown}`"
    if meta.get("ext_mismatch") is True:
        note += f" · ⚠ 이름은 {_text(meta.get('ext'))} 인데 실제로는 {_text(meta.get('format_label'))}"
    if meta.get("date"):
        note += " · " + _text(meta["date"])
    note += "*"
    pattern = r"\A(#[^\n]*\n(?:[ \t]*\n)*)" + re.escape(note) + r"[ \t]*(?:\n|$)(?:[ \t]*\n)*"
    return re.sub(pattern, lambda match: match.group(1), body, count=1)


def _tags(value) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    if not isinstance(value, list):
        return []
    result, seen = [], set()
    for item in value:
        tag = _text(item, 40).strip("# ")
        key = tag.casefold()
        if tag and key not in seen:
            result.append(tag)
            seen.add(key)
        if len(result) >= MAX_TAGS:
            break
    return result


def _tokens(text: str):
    for word in _WORDS.findall(text):
        if re.fullmatch(r"[가-힣]+", word):
            for suffix in _PARTICLES:
                if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                    word = word[:-len(suffix)]
                    break
        else:
            word = word.casefold()
        if word not in _STOP_WORDS and len(word) >= 2:
            yield word


def _default_category(source: str, record: dict, meta: dict) -> str:
    explicit = _text(meta.get("category"), 80)
    if explicit:
        return explicit
    if "/" in source:
        return _text(source.split("/", 1)[0], 80)
    return _text(record.get("group") or meta.get("group"), 80) or "모아 둔 자료"


def _load_records(root: Path) -> tuple[list[dict], list[str]]:
    index_path = _inside(root, "_index.json")
    manifest = _read_json(index_path)
    records = manifest if isinstance(manifest, list) else manifest.get("문서") if isinstance(manifest, dict) else None
    if not isinstance(records, list):
        raise ValueError("PKOS 변환 기록에 '문서' 목록이 없습니다. _index.json이 있는 결과 폴더를 선택하세요.")
    warnings = []
    expanded = []
    blog_sources = []
    for record in records:
        if isinstance(record, dict) and record.get("blog"):
            blog_sources.append(record)
        else:
            expanded.append(record)
    if blog_sources:
        try:
            blog_index = _read_json(_inside(root, "블로그/_index.json"))
            if not isinstance(blog_index, list):
                raise ValueError("블로그 색인은 목록이어야 합니다.")
            active = {PurePosixPath(_relative(rec["src"])).name: rec for rec in blog_sources}
            for post in blog_index:
                if not isinstance(post, dict) or post.get("src") not in active:
                    continue
                backup = active[post["src"]]
                filename = _relative(post.get("file"))
                expanded.append({**post, "src": backup["src"], "md": "블로그/" + filename,
                                 "fmt": "blogpost", "group": "블로그", "_identity": "blog:" + filename})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Preserve the backup index as a usable document if the old nested
            # format is not present. Tell the caller instead of losing the backup.
            expanded.extend(blog_sources)
            warnings.append(f"블로그 개별 글을 읽지 못해 백업 목차로 표시합니다: {exc}")
    return expanded, warnings


def _documents(root: Path) -> tuple[list[dict], list[str], int]:
    records, warnings = _load_records(root)
    docs, seen, skipped = [], set(), 0
    for record in records:
        try:
            if not isinstance(record, dict):
                raise ValueError("문서 항목이 객체가 아닙니다.")
            source = _relative(record.get("src"))
            md = _relative(record.get("md"))
            if not md.lower().endswith(".md"):
                raise ValueError("Markdown 변환본이 아닙니다.")
            path = _inside(root, md)
            with path.open(encoding="utf-8-sig", errors="replace") as stream:
                text = stream.read(MAX_DOCUMENT_CHARS + 1)
            truncated = len(text) > MAX_DOCUMENT_CHARS
            meta, body = _frontmatter(text[:MAX_DOCUMENT_CHARS])
            identity = _text(record.get("_identity"), 4096) or source
            doc_id = "doc-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            title = _text(record.get("title") or meta.get("title"), 200) or PurePosixPath(source).stem
            existing_tags = _tags(record.get("tags")) + _tags(meta.get("tags"))
            content = _analysis_body(body, source, meta)
            plain = _plain(content)
            if plain.startswith(title):
                plain = plain[len(title):].lstrip(" ·:-")
            summary = plain[:220] + ("…" if len(plain) > 220 else "")
            docs.append({"id": doc_id, "title": title, "source": source, "md": md,
                         "format": _text(record.get("format") or record.get("fmt") or meta.get("format"), 40) or "md",
                         "category": _default_category(source, record, meta),
                         "tags": _tags(existing_tags), "summary": summary,
                         "notes": "", "_body": body, "_content": content, "_truncated": truncated})
            if truncated:
                warnings.append(f"{md}: 내용이 길어 앞 {MAX_DOCUMENT_CHARS:,}자만 지도에 사용했습니다.")
        except (OSError, ValueError, TypeError) as exc:
            skipped += 1
            label = _text(record.get("md"), 160) if isinstance(record, dict) else "항목"
            warnings.append(f"{label or '항목'}: {exc}")
    return sorted(docs, key=lambda doc: (doc["source"].casefold(), doc["md"].casefold())), warnings, skipped


def _load_edits(root: Path) -> dict:
    path = _inside(root, EDITS_FILENAME, must_exist=False)
    if not path.exists():
        return {"version": 1, "documents": {}, "links": [], "hidden_links": []}
    edits = _read_json(path)
    if (not isinstance(edits, dict) or not isinstance(edits.get("documents", {}), dict)
            or not isinstance(edits.get("links", []), list)
            or not isinstance(edits.get("hidden_links", []), list)):
        raise ValueError("사용자 분류 기록 형식이 잘못되었습니다. _knowledge_edits.json을 확인하세요.")
    return {"version": 1, "documents": edits.get("documents", {}),
            "links": edits.get("links", []), "hidden_links": edits.get("hidden_links", [])}


def _apply_tags(docs: list[dict], edits: dict):
    frequencies = []
    document_frequency = collections.Counter()
    for doc in docs:
        counts = collections.Counter(_tokens(_plain(doc["_content"][:120_000])))
        for token in _tokens(doc["title"]):
            counts[token] += 5
        frequencies.append(counts)
        document_frequency.update(counts.keys())
    total = len(docs)
    for doc, counts in zip(docs, frequencies):
        if not doc["tags"]:
            # TF-IDF ranking favors discriminative terms but keeps strong title
            # vocabulary. Labels remain ordinary words that users can edit.
            ranked = sorted(counts, key=lambda token: (
                -(1 + math.log(counts[token])) * (1 + math.log((1 + total) / (1 + document_frequency[token]))),
                token))
            doc["tags"] = ranked[:AUTO_TAGS]
        change = edits["documents"].get(doc["id"], {})
        if not isinstance(change, dict):
            continue
        for key, limit in (("title", 200), ("category", 80), ("notes", 6000)):
            if key in change:
                value = _text(change[key], limit)
                if value or key == "notes":
                    doc[key] = value
        if "tags" in change:
            doc["tags"] = _tags(change["tags"])


def _pair(source: str, target: str) -> tuple[str, str]:
    return tuple(sorted((source, target)))


def _edges(docs: list[dict], edits: dict) -> list[dict]:
    ids = {doc["id"] for doc in docs}
    tag_index = collections.defaultdict(list)
    tag_labels = {}
    for doc in docs:
        for tag in doc["tags"]:
            key = tag.casefold()
            tag_labels.setdefault(key, tag)
            tag_index[key].append(doc["id"])
    tag_positions = {tag: {doc_id: position for position, doc_id in enumerate(members)}
                     for tag, members in tag_index.items() if len(members) > 80}
    hidden = {tuple(link) for link in edits["hidden_links"]
              if isinstance(link, list) and len(link) == 2 and all(isinstance(x, str) for x in link)}
    edges = {}
    for doc in docs:
        neighbors = collections.defaultdict(list)
        for tag in doc["tags"]:
            key = tag.casefold()
            # Very common tags produce an unreadable complete graph. Use a
            # deterministic window around each node rather than materializing
            # every pair (bounded by tags * 80 candidates per document).
            members = tag_index[key]
            if len(members) > 80:
                position = tag_positions[key][doc["id"]]
                members = [members[(position + offset) % len(members)] for offset in range(-40, 41)]
            for other in members:
                if other != doc["id"] and _pair(doc["id"], other) not in hidden:
                    neighbors[other].append(tag_labels[key])
        top = sorted(neighbors, key=lambda other: (-len(neighbors[other]), other))[:MAX_NEIGHBORS]
        for other in top:
            pair = _pair(doc["id"], other)
            shared = sorted(set(neighbors[other]), key=str.casefold)
            edges[pair] = {"source": pair[0], "target": pair[1], "label": "공통 태그: " + ", ".join(shared),
                           "kind": "tag", "weight": len(shared)}
    for link in edits["links"]:
        if not isinstance(link, dict):
            continue
        source, target = link.get("source"), link.get("target")
        if isinstance(source, str) and isinstance(target, str) and source in ids and target in ids and source != target:
            pair = _pair(source, target)
            edges[pair] = {"source": pair[0], "target": pair[1], "label": _text(link.get("label"), 160) or "직접 연결",
                           "kind": "manual", "weight": 1}
    return [edges[key] for key in sorted(edges)]


def build_graph(output_dir, title: str = "나의 지식맵") -> dict:
    """Read a PKOS output folder and return a JSON-serializable graph."""
    with _LOCK:
        root = _root(output_dir)
        docs, warnings, skipped = _documents(root)
        edits = _load_edits(root)
        _apply_tags(docs, edits)
        edges = _edges(docs, edits)
        counts = collections.Counter(doc["category"] for doc in docs)
        categories = [{"id": label, "label": label, "count": counts[label],
                       "color": _COLORS[int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16) % len(_COLORS)]}
                      for label in sorted(counts, key=str.casefold)]
        nodes = [{key: value for key, value in doc.items() if not key.startswith("_")} for doc in docs]
        return {"version": 1, "title": _text(title, 120) or "나의 지식맵",
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "stats": {"documents": len(nodes), "categories": len(categories), "links": len(edges),
                          "skipped": skipped},
                "categories": categories, "nodes": nodes, "edges": edges, "warnings": warnings}


def read_document(output_dir, doc_id: str) -> dict:
    """Return the active converted document body, never an arbitrary file path."""
    with _LOCK:
        root = _root(output_dir)
        records, _ = _load_records(root)
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                source = _relative(record.get("src"))
                identity = _text(record.get("_identity"), 4096) or source
                candidate_id = "doc-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
                if candidate_id != doc_id:
                    continue
                md = _relative(record.get("md"))
                if not md.lower().endswith(".md"):
                    continue
                path = _inside(root, md)
                with path.open(encoding="utf-8-sig", errors="replace") as stream:
                    text = stream.read(MAX_DOCUMENT_CHARS + 1)
                _, body = _frontmatter(text[:MAX_DOCUMENT_CHARS])
                return {"id": doc_id, "body": body, "source": source, "md": md,
                        "truncated": len(text) > MAX_DOCUMENT_CHARS}
            except (OSError, ValueError, TypeError):
                continue
    raise ValueError("지도에서 해당 자료를 찾지 못했습니다. 지도를 다시 만들어 주세요.")


def _valid_id(root: Path, doc_id: str):
    if isinstance(doc_id, str):
        records, _ = _load_records(root)
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                source = _relative(record.get("src"))
                identity = _text(record.get("_identity"), 4096) or source
                if "doc-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20] != doc_id:
                    continue
                md = _relative(record.get("md"))
                if not md.lower().endswith(".md"):
                    continue
                _inside(root, md)
                return
            except (OSError, ValueError, TypeError):
                continue
    raise ValueError("지도에 없는 자료입니다.")


def update_document(output_dir, doc_id: str, changes: dict, *, title: str = "나의 지식맵") -> dict:
    """Save user metadata independently from the converter's Markdown output."""
    if not isinstance(changes, dict):
        raise ValueError("수정 내용은 객체여야 합니다.")
    with _LOCK:
        root = _root(output_dir)
        _valid_id(root, doc_id)
        edits = _load_edits(root)
        change = dict(edits["documents"].get(doc_id, {}))
        for key, limit in (("title", 200), ("category", 80), ("notes", 6000)):
            if key in changes:
                if not isinstance(changes[key], str):
                    raise ValueError(f"{key} 값은 글자여야 합니다.")
                value = _text(changes[key], limit)
                if not value and key != "notes":
                    raise ValueError("제목과 분야는 비워 둘 수 없습니다.")
                change[key] = value
        if "tags" in changes:
            if not isinstance(changes["tags"], (list, str)):
                raise ValueError("태그는 목록 또는 쉼표로 나눈 글자여야 합니다.")
            change["tags"] = _tags(changes["tags"])
        edits["documents"][doc_id] = change
        _atomic_json(root, EDITS_FILENAME, edits)
        return build_graph(root, title)


def add_link(output_dir, source_id: str, target_id: str, label: str, *, title: str = "나의 지식맵") -> dict:
    """Create or replace an undirected manual relationship with its reason."""
    with _LOCK:
        root = _root(output_dir)
        _valid_id(root, source_id)
        _valid_id(root, target_id)
        if source_id == target_id:
            raise ValueError("서로 다른 두 자료를 선택하세요.")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("두 자료를 연결하는 이유를 적어 주세요.")
        pair = _pair(source_id, target_id)
        edits = _load_edits(root)
        edits["links"] = [link for link in edits["links"] if not isinstance(link, dict)
                          or _pair(_text(link.get("source")), _text(link.get("target"))) != pair]
        edits["links"].append({"source": pair[0], "target": pair[1], "label": _text(label, 160)})
        edits["hidden_links"] = [link for link in edits["hidden_links"] if link != list(pair)]
        _atomic_json(root, EDITS_FILENAME, edits)
        return build_graph(root, title)


def remove_link(output_dir, source_id: str, target_id: str, *, title: str = "나의 지식맵") -> dict:
    """Hide a pair, including automatic links, until it is explicitly added again."""
    with _LOCK:
        root = _root(output_dir)
        _valid_id(root, source_id)
        _valid_id(root, target_id)
        pair = _pair(source_id, target_id)
        edits = _load_edits(root)
        edits["links"] = [link for link in edits["links"] if not isinstance(link, dict)
                          or _pair(_text(link.get("source")), _text(link.get("target"))) != pair]
        if list(pair) not in edits["hidden_links"]:
            edits["hidden_links"].append(list(pair))
        _atomic_json(root, EDITS_FILENAME, edits)
        return build_graph(root, title)


def export_graph(output_dir, title: str = "나의 지식맵") -> Path:
    """Write the current portable graph as UTF-8 JSON in the output folder."""
    with _LOCK:
        root = _root(output_dir)
        return _atomic_json(root, GRAPH_FILENAME, build_graph(root, title))
