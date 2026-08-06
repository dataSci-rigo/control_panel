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
import subprocess
from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request

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

fidata_bp = Blueprint("fidata", __name__, template_folder="templates")

# Each job is a oneshot systemd service triggered by its own timer — there's
# no single always-on "app-fidata" daemon, so these get their own
# run-now/enable/disable controls instead of reusing panel's generic
# start/stop/restart (which assumes one long-running service per app).
JOBS = [
    {"id": "pipeline", "label": "Pipeline (3x/day)", "unit": "fidata-pipeline"},
    {"id": "daily-review", "label": "Daily Review", "unit": "fidata-daily-review"},
    {"id": "weekly-review", "label": "Weekly Review", "unit": "fidata-weekly-review"},
]
_JOB_UNITS = {j["id"]: j["unit"] for j in JOBS}


def _run(cmd: list[str]) -> tuple[str, int]:
    result = subprocess.run(["sudo"] + cmd, capture_output=True, text=True, timeout=10)
    return (result.stdout + result.stderr).strip(), result.returncode


def _job_status(unit: str) -> dict:
    enabled, _ = _run(["systemctl", "is-enabled", f"{unit}.timer"])
    active, _ = _run(["systemctl", "is-active", f"{unit}.service"])
    result, _ = _run(["systemctl", "show", f"{unit}.service", "--property=Result", "--value"])
    last_run, _ = _run(["systemctl", "show", f"{unit}.service", "--property=ExecMainExitTimestamp", "--value"])
    next_run, _ = _run(["systemctl", "show", f"{unit}.timer", "--property=NextElapseUSecRealtime", "--value"])
    return {
        "enabled": enabled.strip() == "enabled",
        "active": active.strip(),
        "last_result": result.strip() or None,
        "last_run": last_run.strip() or None,
        "next_run": next_run.strip() or None,
    }


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
        prev_week=prev_week, next_week=next_week, jobs=JOBS,
    )


@fidata_bp.route("/api/status")
def api_status():
    return jsonify({j["id"]: _job_status(j["unit"]) for j in JOBS})


@fidata_bp.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json(force=True)
    job_id = data.get("job", "")
    action = data.get("action", "")

    if job_id not in _JOB_UNITS:
        return jsonify({"ok": False, "error": "Unknown job"}), 400
    if action not in {"run_now", "enable", "disable"}:
        return jsonify({"ok": False, "error": "Invalid action"}), 400

    unit = _JOB_UNITS[job_id]
    if action == "run_now":
        _, code = _run(["systemctl", "start", f"{unit}.service"])
    elif action == "enable":
        _, code = _run(["systemctl", "enable", "--now", f"{unit}.timer"])
    else:
        _, code = _run(["systemctl", "disable", f"{unit}.timer"])

    return jsonify({"ok": code == 0, "status": _job_status(unit)})
