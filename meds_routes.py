"""Meds dashboard — mounted at /meds/ on the control panel."""

from __future__ import annotations

import os
import sys

_FOOD_DIR = next(
    (p for p in [os.path.expanduser("~/apps/food"), os.path.expanduser("~/Documents/food")]
     if os.path.isdir(p)),
    os.path.expanduser("~/apps/food"),
)
if _FOOD_DIR not in sys.path:
    sys.path.insert(0, _FOOD_DIR)

from flask import Blueprint, jsonify, render_template, request
import meds_db

meds_bp = Blueprint("meds", __name__, template_folder="templates")


@meds_bp.route("/")
def dashboard():
    meds_db.init_db()
    catalog = meds_db.get_catalog(active_only=False)
    doses   = meds_db.get_today_doses()
    return render_template("meds_dashboard.html", catalog=catalog, doses=doses)


@meds_bp.route("/api/catalog")
def api_catalog():
    meds_db.init_db()
    return jsonify(meds_db.get_catalog(active_only=False))


@meds_bp.route("/api/add_med", methods=["POST"])
def api_add_med():
    d = request.get_json(force=True)
    name = d.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    meds_db.init_db()
    meds_db.add_med(
        name=name,
        dose_amount=d.get("dose_amount") or None,
        dose_unit=d.get("dose_unit") or None,
        category=d.get("category", "supplement"),
        notes=d.get("notes") or None,
    )
    return jsonify({"ok": True})


@meds_bp.route("/api/toggle/<int:med_id>", methods=["POST"])
def api_toggle(med_id: int):
    d      = request.get_json(force=True)
    active = 1 if d.get("active") else 0
    meds_db.init_db()
    meds_db.update_med(med_id, active=active)
    return jsonify({"ok": True})


@meds_bp.route("/api/log_dose", methods=["POST"])
def api_log_dose():
    d = request.get_json(force=True)
    name = d.get("med_name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "med_name required"}), 400
    meds_db.init_db()
    meds_db.log_dose(
        med_name=name,
        dose_amount=d.get("dose_amount") or None,
        dose_unit=d.get("dose_unit") or None,
        notes=d.get("notes") or None,
    )
    return jsonify({"ok": True})


@meds_bp.route("/api/delete_dose/<int:dose_id>", methods=["POST"])
def api_delete_dose(dose_id: int):
    meds_db.init_db()
    meds_db.delete_dose(dose_id)
    return jsonify({"ok": True})


@meds_bp.route("/api/today_doses")
def api_today_doses():
    meds_db.init_db()
    return jsonify(meds_db.get_today_doses())
