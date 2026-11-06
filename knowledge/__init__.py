"""Offline knowledge maps built from the existing PKOS conversion results."""

from .graph import (
    add_link,
    build_graph,
    export_graph,
    read_document,
    remove_link,
    update_document,
)

__all__ = [
    "build_graph", "update_document", "add_link", "remove_link",
    "read_document", "export_graph",
]
