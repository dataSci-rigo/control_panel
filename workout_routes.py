"""Workout dashboard — mounted at /workout/ on the control panel."""

from __future__ import annotations

import os
import sys
from datetime import datetime

_FOOD_DIR = next(
    (p for p in [os.path.expanduser("~/apps/food"), os.path.expanduser("~/Documents/food")]
     if os.path.isdir(p)),
    os.path.expanduser("~/apps/food"),
)
if _FOOD_DIR not in sys.path:
    sys.path.insert(0, _FOOD_DIR)

from flask import Blueprint, jsonify, render_template, request
import workout_db

workout_bp = Blueprint("workout", __name__, template_folder="templates")


def _today() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


@workout_bp.route("/")
def dashboard():
    workout_db.init_db()
    date    = request.args.get("date", _today())
    log     = workout_db.get_day_log(date)
    history = workout_db.get_history(14)
    return render_template("workout_dashboard.html", date=date, log=log, history=history)


@workout_bp.route("/api/today")
def api_today():
    workout_db.init_db()
    date = request.args.get("date", _today())
    return jsonify({"date": date, "log": workout_db.get_day_log(date)})


@workout_bp.route("/api/add", methods=["POST"])
def api_add():
    d = request.get_json(force=True)
    exercise = d.get("exercise", "").strip()
    if not exercise:
        return jsonify({"ok": False, "error": "exercise name required"}), 400
    workout_db.init_db()
    workout_db.log_exercise(
        exercise=exercise,
        sets=d.get("sets") or None,
        reps=d.get("reps") or None,
        weight_kg=d.get("weight_kg") or None,
        duration_min=d.get("duration_min") or None,
        distance_km=d.get("distance_km") or None,
        notes=d.get("notes") or None,
        date=d.get("date") or _today(),
    )
    return jsonify({"ok": True})


@workout_bp.route("/api/delete/<int:exercise_id>", methods=["POST"])
def api_delete(exercise_id: int):
    workout_db.init_db()
    workout_db.delete_exercise(exercise_id)
    return jsonify({"ok": True})
