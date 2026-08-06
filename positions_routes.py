"""
fiData positions/analytics dashboard — mounted on the panel app at
/positions/. Always-current (refreshed by fiData's 3x/day pipeline run),
separate from /fidata's Sunday narrative weekly review. Reads directly from
fiData's app_data/*.json + data/mpt_summary.json, and serves the two
notebook-equivalent plots (efficient frontier, correlation heatmap) that
run_pipeline.py now regenerates on every run. No DB, no imports from the
fiData project itself — just files on disk, VM-path-first / laptop-fallback
like every other panel blueprint.
"""

from __future__ import annotations

import json
import os

from flask import Blueprint, abort, render_template, send_file

# VM/GitHub repo directory is lowercase "fidata"; local dev checkout is "fiData"
_FIDATA_DIR = next(
    (p for p in [
        os.path.expanduser("~/apps/fidata"),
        os.path.expanduser("~/Documents/fiData"),
    ] if os.path.isdir(p)),
    os.path.expanduser("~/apps/fidata"),
)
_APP_DATA = os.path.join(_FIDATA_DIR, "app_data")
_DATA_DIR = os.path.join(_FIDATA_DIR, "data")

positions_bp = Blueprint("positions", __name__, template_folder="templates")

_ALLOWED_IMAGES = {"efficient_frontier.png", "correlation_heatmap.png"}


def _load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


@positions_bp.route("/")
def dashboard():
    combined = _load_json(os.path.join(_APP_DATA, "combined.json")) or []
    sectors = _load_json(os.path.join(_APP_DATA, "sectors.json")) or {}
    targets = _load_json(os.path.join(_APP_DATA, "targets.json")) or {}
    flags = _load_json(os.path.join(_APP_DATA, "flags.json")) or {}
    mpt = _load_json(os.path.join(_DATA_DIR, "mpt_summary.json")) or {}

    holdings = sorted(
        [r for r in combined if r.get("Symbol") != "cash"],
        key=lambda r: r.get("Market_Value") or 0,
        reverse=True,
    )
    cash_row = next((r for r in combined if r.get("Symbol") == "cash"), None)

    return render_template(
        "positions_dashboard.html",
        holdings=holdings, cash=cash_row,
        by_gics=sectors.get("by_gics", []),
        by_cap=sectors.get("by_cap", []),
        by_vol=sectors.get("by_vol", []),
        targets=targets, flags=flags, mpt=mpt,
        has_plots=os.path.isdir(_DATA_DIR) or os.path.isdir(_FIDATA_DIR),
    )


@positions_bp.route("/img/<name>")
def img(name: str):
    if name not in _ALLOWED_IMAGES:
        abort(404)
    path = os.path.join(_FIDATA_DIR, name)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png")
