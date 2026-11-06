"""Pure presentation helpers. No file reads, user caches, or Streamlit state."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

MAP_LIMIT = 220
PAGE_SIZE = 100
PALETTE = ["#35654b", "#718b52", "#bb9150", "#5e8991", "#927f9e", "#a66e59", "#52756b", "#9b9b62"]


def category_labels(graph: dict[str, Any]) -> dict[str, str]:
    return {str(item["id"]): str(item.get("label", item["id"])) for item in graph.get("categories", [])}


def filter_nodes(graph: dict[str, Any], query: str = "", category: str = "") -> list[dict[str, Any]]:
    labels = category_labels(graph)
    terms = query.casefold().split()
    matches = []
    for node in graph.get("nodes", []):
        if category and node.get("category") != category:
            continue
        text = " ".join(str(value or "") for value in [node.get("title"), node.get("summary"),
                        node.get("notes"), labels.get(str(node.get("category")), node.get("category")),
                        *node.get("tags", [])]).casefold()
        if all(term in text for term in terms):
            matches.append(node)
    return matches


def balanced_sample(nodes: list[dict[str, Any]], limit: int = MAP_LIMIT, selected: str | None = None) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if len(nodes) <= limit:
        return list(nodes)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        buckets.setdefault(str(node.get("category", "")), []).append(node)
    counts = dict.fromkeys(buckets, 0)
    remaining = limit
    while remaining:
        for key, bucket in buckets.items():
            if counts[key] < len(bucket):
                counts[key] += 1
                remaining -= 1
            if not remaining:
                break
    result = [bucket[min(len(bucket) - 1, int((i + .5) * len(bucket) / counts[key]))]
              for key, bucket in buckets.items() for i in range(counts[key])]
    chosen = next((node for node in nodes if node.get("id") == selected), None)
    if chosen and not any(node.get("id") == selected for node in result):
        index = next((i for i, node in enumerate(result) if node.get("category") == chosen.get("category")), len(result) - 1)
        result[index] = chosen
    return result


def document_label(node: dict[str, Any]) -> str:
    title = " ".join(str(node.get("title") or "제목 없는 자료").split())
    return f'{title[:100]} · {node.get("format", "문서")} · {str(node["id"])[-6:]}'


def parse_tags(value: str) -> list[str]:
    return list(dict.fromkeys(tag.strip().lstrip("#").strip() for tag in re.split(r"[,，\n]", value) if tag.strip().lstrip("#").strip()))


def table_rows(nodes: list[dict[str, Any]], graph: dict[str, Any]) -> list[dict[str, Any]]:
    labels = category_labels(graph)
    return [{"제목": str(node.get("title", "")), "분야": labels.get(str(node.get("category")), str(node.get("category", ""))),
             "형식": str(node.get("format", "")), "태그": ", ".join(node.get("tags", []))} for node in nodes]


def graph_option(graph: dict[str, Any], matched: list[dict[str, Any]], selected: str | None = None) -> dict[str, Any]:
    """A native ECharts graph. User strings stay plain text, including tooltips."""
    sample = balanced_sample(matched, selected=selected)
    counts = Counter(str(node.get("category", "")) for node in matched)
    labels = category_labels(graph)
    category_ids = [str(item["id"]) for item in graph.get("categories", []) if str(item["id"]) in counts]
    category_ids.extend(key for key in counts if key not in category_ids)
    colors = {key: PALETTE[i % len(PALETTE)] for i, key in enumerate(category_ids)}
    chart_nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    number_of_categories = max(1, len(category_ids))
    for index, category in enumerate(category_ids):
        angle = -math.pi / 2 + index * math.tau / number_of_categories
        cx, cy = math.cos(angle) * 330, math.sin(angle) * 250
        label = labels.get(category, category or "미분류")
        chart_nodes.append({"id": f"category:{category}", "name": f"{label}\n{counts[category]:,}개",
                            "x": cx, "y": cy, "symbolSize": 48, "itemStyle": {"color": colors[category], "opacity": .85},
                            "label": {"show": True, "fontSize": 12, "position": "bottom", "color": "#244732"}})
        members = [node for node in sample if str(node.get("category", "")) == category]
        for i, node in enumerate(members):
            tier = i // 12
            ring_size = min(12, len(members) - tier * 12)
            node_angle = angle + (i % 12) * math.tau / max(1, ring_size) + tier * .3
            radius = 88 + tier * 45
            chart_nodes.append({"id": f'doc:{node["id"]}', "name": str(node.get("title", "제목 없는 자료")),
                                "x": cx + math.cos(node_angle) * radius, "y": cy + math.sin(node_angle) * radius,
                                "symbolSize": 17 if node["id"] == selected else 9,
                                "itemStyle": {"color": colors[category], "borderColor": "#fff", "borderWidth": 1},
                                "label": {"show": len(sample) <= 24 or node["id"] == selected, "fontSize": 11,
                                          "position": "bottom", "width": 110, "overflow": "truncate"}})
            links.append({"source": f"category:{category}", "target": f'doc:{node["id"]}',
                          "lineStyle": {"color": colors[category], "opacity": .18}})
    visible = {node["id"] for node in sample}
    relationships = [edge for edge in graph.get("edges", []) if edge.get("source") in visible and edge.get("target") in visible]
    if selected:
        relationships = [edge for edge in relationships if selected in (edge.get("source"), edge.get("target"))]
    for edge in relationships[:150]:
        links.append({"source": f'doc:{edge["source"]}', "target": f'doc:{edge["target"]}',
                      "name": str(edge.get("label", "공통 태그")),
                      "lineStyle": {"color": "#ab8646" if edge.get("kind") == "manual" else "#547b65",
                                    "opacity": .75 if selected else .3, "width": 2 if selected else 1,
                                    "type": "solid" if edge.get("kind") == "manual" else "dashed"}})
    return {"animation": False, "tooltip": {"trigger": "item", "renderMode": "richText", "formatter": "{b}"},
            "series": [{"type": "graph", "layout": "none", "data": chart_nodes, "links": links,
                        "roam": True, "draggable": False, "cursor": "default", "symbol": "circle",
                        "label": {"color": "#244732"}, "emphasis": {"focus": "adjacency"},
                        "scaleLimit": {"min": .4, "max": 4}, "left": "8%", "right": "8%", "top": "12%", "bottom": "12%"}]}
