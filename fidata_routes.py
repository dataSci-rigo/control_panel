"""
fiData weekly portfolio review — mounted on the panel app at /fidata/.
Reads directly from fiData's app_data/*.json and data/weekly_review_*.json
(written by fiData's Sunday weekly-review job). No DB, no imports from the
fiData project itself — just JSON files on disk, VM-path-first / laptop-
fallback like every other panel blueprint.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from flask import Blueprint, render_template

_FIDATA_DIR = next(
    (p for p in [
        os.path.expanduser("~/apps/fiData"),
        os.path.expanduser("~/Documents/fiData"),
    ] if os.path.isdir(p)),
    os.path.expanduser("~/apps/fiData"),
)
_APP_DATA = os.path.join(_FIDATA_DIR, "app_data")
_DATA_DIR = os.path.join(_FIDATA_DIR, "data")

fidata_bp = Blueprint("fidata", __name__, template_folder="templates")


def _load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _available_weeks() -> list[str]:
    """Sunday dates (YYYY-MM-DD) with a saved weekly_review_<date>.json, newest first."""
    if not os.path.isdir(_DATA_DIR):
        return []
    weeks = [
        fn[len("weekly_review_"):-len(".json")]
        for fn in os.listdir(_DATA_DIR)
        if fn.startswith("weekly_review_") and fn.endswith(".json")
    ]
    return sorted(weeks, reverse=True)


@fidata_bp.route("/")
@fidata_bp.route("/<week_date>")
def dashboard(week_date: str | None = None):
    weeks = _available_weeks()
    if week_date is None:
        week_date = weeks[0] if weeks else None

    review = _load_json(os.path.join(_DATA_DIR, f"weekly_review_{week_date}.json")) if week_date else None
    combined = _load_json(os.path.join(_APP_DATA, "combined.json")) or []
    sectors = _load_json(os.path.join(_APP_DATA, "sectors.json")) or {}

    idx = weeks.index(week_date) if week_date in weeks else -1
    prev_week = weeks[idx + 1] if 0 <= idx < len(weeks) - 1 else None
    next_week = weeks[idx - 1] if idx > 0 else None

    holdings = sorted(
        [r for r in combined if r.get("Symbol") != "cash"],
        key=lambda r: r.get("Market_Value") or 0,
        reverse=True,
    )

    return render_template(
        "fidata_dashboard.html",
        week_date=week_date, weeks=weeks, review=review,
        holdings=holdings, sectors=sectors.get("by_gics", []),
        prev_week=prev_week, next_week=next_week,
    )
