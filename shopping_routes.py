"""
Shopping list editor — mounted on the panel app at /shopping/.
Reads/writes the semantic_task_manager project's SQLite DB directly using
synchronous sqlite3 (same pattern as plants_routes.py).
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from flask import Blueprint, redirect, render_template, request, url_for

_STM_DIR = next(
    (p for p in [
        os.path.expanduser("~/apps/semantic_task_manager"),
        os.path.expanduser("~/Documents/semantic_task_manager"),
    ] if os.path.isdir(p)),
    os.path.expanduser("~/apps/semantic_task_manager"),
)

_DB_PATH = str(Path(_STM_DIR) / "data" / "tasks.db")

shopping_bp = Blueprint("shopping", __name__, template_folder="templates")

_URL_PREFIX = "/shopping"

LISTS = [
    ("supply store run", "Supply store"),
    ("online shopping", "Online"),
    ("groceries", "Groceries"),
]


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _deduped_items(conn: sqlite3.Connection, list_name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT sli.entity_id, e.canonical_name FROM shopping_list_items sli "
        "JOIN shopping_lists sl ON sl.id = sli.list_id "
        "JOIN entities e ON e.id = sli.entity_id "
        "WHERE sl.name = ? AND sli.purchased = 0",
        (list_name,),
    ).fetchall()
    seen: dict[int, str] = {}
    for r in rows:
        seen.setdefault(r["entity_id"], r["canonical_name"])
    return [{"entity_id": eid, "name": name} for eid, name in seen.items()]


@shopping_bp.route("/")
def index():
    conn = _get_db()
    lists = [
        {"key": key, "label": label, "entries": _deduped_items(conn, key)}
        for key, label in LISTS
    ]
    conn.close()
    return render_template("shopping.html", lists=lists, url_prefix=_URL_PREFIX)


@shopping_bp.route("/own/<int:entity_id>", methods=["POST"])
def own(entity_id: int):
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE task_requirements SET satisfied = 1 WHERE entity_id = ?",
            (entity_id,),
        )
        conn.execute(
            "INSERT INTO inventory (entity_id, on_hand, last_confirmed_at) VALUES (?, 1, ?) "
            "ON CONFLICT(entity_id) DO UPDATE SET on_hand = 1, last_confirmed_at = excluded.last_confirmed_at",
            (entity_id, time.time()),
        )
        conn.execute("DELETE FROM shopping_list_items WHERE entity_id = ?", (entity_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("shopping.index"))


@shopping_bp.route("/remove/<list_key>/<int:entity_id>", methods=["POST"])
def remove(list_key: str, entity_id: int):
    valid_keys = {key for key, _ in LISTS}
    if list_key not in valid_keys:
        return "Unknown list", 400
    conn = _get_db()
    try:
        conn.execute(
            "DELETE FROM shopping_list_items WHERE entity_id = ? AND "
            "list_id = (SELECT id FROM shopping_lists WHERE name = ?)",
            (entity_id, list_key),
        )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("shopping.index"))
