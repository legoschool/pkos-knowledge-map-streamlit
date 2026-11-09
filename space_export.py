"""Turn a PKOS knowledge graph into a space map and a 3D classroom.

The output uses the same data shape as the 레고학교.com map (``window.DX`` with
``hub``, ``zones`` and ``areas[].items[]``), so one ``data.js`` drives both
pages.  Only titles, summaries, tags and notes already shown in the knowledge
map are written; source paths and document bodies are left out.
"""
from __future__ import annotations

import collections
import io
import json
import zipfile
from pathlib import Path

TEMPLATE_DIR = Path(__file__).with_name("templates") / "space_map"
PALETTE = ("#2563C9", "#C9452C", "#3C8D40", "#6540B2", "#B23A7A", "#0097A7",
           "#D98E04", "#5E8A2E", "#8E1E3C", "#3B86D9", "#A9622B", "#4B6CC2")
DEFAULT_PER_AREA = 18
MAX_PER_AREA = 40
_KINDS = {
    "video": {"mp4", "mov", "avi", "mkv", "webm", "video", "youtube"},
    "site": {"html", "htm", "url", "web", "mhtml"},
    "tool": {"py", "js", "ts", "ipynb", "java", "c", "cpp", "cs", "gs", "code", "json", "csv"},
    "post": {"blog", "post"},
    "book": {"epub", "book"},
}
KIND_LABEL = {"video": "영상", "site": "사이트", "tool": "도구", "post": "글", "book": "책", "doc": "자료"}


def kind_of(fmt: str) -> str:
    value = str(fmt or "").strip().lower().lstrip(".")
    for kind, formats in _KINDS.items():
        if value in formats:
            return kind
    return "doc"


def _clip(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_dx(graph: dict, *, title: str | None = None, byline: str = "",
             per_area: int = DEFAULT_PER_AREA) -> dict:
    """Return a ``window.DX`` object for the space map and 3D classroom."""
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise ValueError("지식맵 데이터가 없습니다. 먼저 지도를 만들어 주세요.")
    per_area = max(1, min(int(per_area), MAX_PER_AREA))
    nodes = [node for node in graph["nodes"] if isinstance(node, dict) and node.get("id")]
    by_id = {node["id"]: node for node in nodes}
    degree = collections.Counter()
    neighbours = collections.defaultdict(list)
    for edge in graph.get("edges") or []:
        source, target = edge.get("source"), edge.get("target")
        if source in by_id and target in by_id:
            weight = int(edge.get("weight") or 1)
            degree[source] += weight
            degree[target] += weight
            neighbours[source].append((weight, target))
            neighbours[target].append((weight, source))

    groups = collections.defaultdict(list)
    for node in nodes:
        groups[_clip(node.get("category"), 80) or "모아 둔 자료"].append(node)
    ordered = sorted(groups, key=lambda name: (-len(groups[name]), name.casefold()))

    areas, shown = [], {}
    for index, name in enumerate(ordered):
        members = sorted(groups[name], key=lambda n: (-degree[n["id"]], str(n.get("title", "")).casefold()))
        picked = members[:per_area]
        for node in picked:
            shown[node["id"]] = name
        tag_count = collections.Counter(tag for node in groups[name] for tag in node.get("tags") or [])
        top_tags = [tag for tag, _ in tag_count.most_common(4)]
        kinds = collections.Counter(kind_of(node.get("format")) for node in groups[name])
        kind_text = ", ".join(f"{KIND_LABEL[k]} {v}" for k, v in kinds.most_common())
        story = [f"‘{name}’ 분야에는 자료 {len(groups[name])}건이 있습니다. 종류는 {kind_text}입니다."]
        if top_tags:
            story.append("자주 나온 태그는 " + ", ".join(top_tags) + "입니다.")
        if len(groups[name]) > len(picked):
            story.append(f"연결이 많은 자료 {len(picked)}건을 골라 올렸습니다.")
        areas.append({
            "id": f"a{index + 1}", "name": name, "short": _clip(name, 12),
            "sub": " · ".join(top_tags[:3]) or f"자료 {len(groups[name])}건",
            "color": PALETTE[index % len(PALETTE)], "count": len(groups[name]),
            "story": story, "items": [],
        })

    area_by_name = {area["name"]: area for area in areas}
    for name in ordered:
        for node in sorted(groups[name], key=lambda n: (-degree[n["id"]], str(n.get("title", "")).casefold())):
            if shown.get(node["id"]) != name:
                continue
            related = []
            for _, other in sorted(neighbours[node["id"]], key=lambda pair: (-pair[0], pair[1])):
                if other in shown and other not in related:
                    related.append(other)
                if len(related) == 3:
                    break
            kind = kind_of(node.get("format"))
            area_by_name[name]["items"].append({
                "id": node["id"], "kind": kind, "kl": KIND_LABEL[kind],
                "title": _clip(node.get("title"), 120) or "제목 없음",
                "desc": _clip(node.get("notes") or node.get("summary"), 220),
                "tags": [_clip(tag, 30) for tag in (node.get("tags") or [])[:6]],
                "links": degree[node["id"]],
                "related": [{"id": other, "title": _clip(by_id[other].get("title"), 80)} for other in related],
            })

    map_title = _clip(title or graph.get("title") or "나의 지식맵", 60)
    total = len(nodes)
    return {
        "title": map_title,
        "byline": _clip(byline, 40),
        "intro": {"h": map_title, "s": f"자료 {total}건을 분야 {len(areas)}개로 나눠 그린 지식 지도입니다."},
        "hub": {"id": "hub", "name": _clip(byline, 20) or map_title,
                "sub": f"자료 {total}건 · 분야 {len(areas)}개 · 연결 {len(graph.get('edges') or [])}개",
                "story": [f"가운데 해에서 분야 {len(areas)}개가 궤도를 돕니다. 행성 크기는 분야의 자료 수를 따릅니다."]},
        "zones": [],
        "areas": areas,
        "generated_by": "PKOS 나의 지식맵",
        "generated_at": graph.get("generated_at", ""),
    }


def data_js(dx: dict) -> str:
    """Serialize ``dx`` as a script that is safe to inline in HTML."""
    payload = json.dumps(dx, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return "/* PKOS 나의 지식맵에서 만든 지도 데이터 */\nwindow.DX = " + payload + ";\n"


def _template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def standalone_html(dx: dict, page: str, *, preview: bool = True) -> str:
    """Return ``index.html`` or ``school.html`` with the data inlined.

    ``preview`` hides the links between the two pages, which do not exist
    when one page is shown alone inside the app.
    """
    if page not in {"index.html", "school.html"}:
        raise ValueError(page)
    html = _template(page)
    marker = '<script src="data.js"></script>'
    if marker not in html:
        raise RuntimeError("지도 틀에서 data.js 자리를 찾지 못했습니다.")
    flag = "window.PKOS_PREVIEW = true; " if preview else ""
    return html.replace(marker, "<script>" + flag + data_js(dx) + "</script>", 1)


README = """나의 우주 지식지도

index.html  우주 지도. 브라우저로 열면 분야가 행성으로, 자료가 위성으로 보입니다.
school.html 3D 교실. 분야마다 교실 한 칸, 자료마다 책상 하나가 놓입니다.
            WASD 또는 방향키로 걷고, 바닥을 누르면 그 자리로 갑니다. 책상을 누르면 자료가 열립니다.
data.js     두 화면이 함께 읽는 데이터입니다. 레고학교.com 지도와 같은 구조(window.DX)입니다.

3D 교실은 three.js를 인터넷(cdnjs)에서 불러오므로 인터넷이 연결되어 있어야 합니다.
우주 지도는 인터넷 없이 열립니다.
공개 사이트로 올리기 전에 data.js 안의 제목과 설명에 개인정보가 없는지 확인하세요.
"""


def export_zip(graph: dict, *, title: str | None = None, byline: str = "",
               per_area: int = DEFAULT_PER_AREA) -> bytes:
    return package_zip(build_dx(graph, title=title, byline=byline, per_area=per_area))


def package_zip(dx: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("나의_우주지도/index.html", _template("index.html"))
        archive.writestr("나의_우주지도/school.html", _template("school.html"))
        archive.writestr("나의_우주지도/data.js", data_js(dx))
        archive.writestr("나의_우주지도/읽어주세요.txt", README)
    return buffer.getvalue()
