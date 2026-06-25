"""
Food tracking routes — mounted on the panel app at /food/.
Reads directly from the food project's SQLite DB.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

# Make food project importable — check VM path first, fall back to laptop dev path
_FOOD_DIR = next(
    (p for p in [
        os.path.expanduser("~/apps/food"),
        os.path.expanduser("~/Documents/food"),
    ] if os.path.isdir(p)),
    os.path.expanduser("~/apps/food"),
)
if _FOOD_DIR not in sys.path:
    sys.path.insert(0, _FOOD_DIR)

from flask import Blueprint, jsonify, render_template, request

import db as food_db
import config as food_config
import cooking as food_cooking

food_bp = Blueprint("food", __name__, template_folder="templates")


def _today() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


@food_bp.route("/")
def dashboard():
    date = _today()
    food_db.init_db()
    log = food_db.get_day_log(date)
    totals = food_db.get_day_totals(date)
    limits = food_config.DAILY_LIMITS
    history = food_db.get_history_totals(7)
    return render_template(
        "food_dashboard.html",
        date=date,
        log=log,
        totals=totals,
        limits=limits,
        history=history,
    )


@food_bp.route("/api/today")
def api_today():
    date = _today()
    food_db.init_db()
    return jsonify({
        "date": date,
        "totals": food_db.get_day_totals(date),
        "limits": food_config.DAILY_LIMITS,
        "log": food_db.get_day_log(date),
    })


@food_bp.route("/api/history")
def api_history():
    days = int(request.args.get("days", 7))
    food_db.init_db()
    return jsonify(food_db.get_history_totals(days))


@food_bp.route("/api/delete/<int:log_id>", methods=["POST"])
def api_delete(log_id: int):
    food_db.init_db()
    food_db.delete_log(log_id)
    return jsonify({"ok": True})


@food_bp.route("/api/cooking")
def api_cooking():
    return jsonify({"content": food_cooking.get_cooking_md()})
