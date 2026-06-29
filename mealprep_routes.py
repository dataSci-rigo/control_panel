"""Meal prep / fridge dashboard — mounted at /mealprep/ on the control panel."""

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
import mealprep_db

mealprep_bp = Blueprint("mealprep", __name__, template_folder="templates")


@mealprep_bp.route("/")
def dashboard():
    mealprep_db.init_db()
    fridge = mealprep_db.get_fridge()
    log    = mealprep_db.get_fridge_log(30)
    return render_template("mealprep_dashboard.html", fridge=fridge, log=log)


@mealprep_bp.route("/api/fridge")
def api_fridge():
    mealprep_db.init_db()
    return jsonify(mealprep_db.get_fridge())


@mealprep_bp.route("/api/add", methods=["POST"])
def api_add():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    qty  = float(data.get("quantity", 0))
    unit = data.get("unit", "g").strip()
    if not name or qty <= 0:
        return jsonify({"ok": False, "error": "name and quantity required"}), 400
    mealprep_db.init_db()
    mealprep_db.add_item(name, qty, unit)
    return jsonify({"ok": True})


@mealprep_bp.route("/api/update/<int:item_id>", methods=["POST"])
def api_update(item_id: int):
    data = request.get_json(force=True)
    qty  = float(data.get("quantity", 0))
    mealprep_db.init_db()
    mealprep_db.update_quantity(item_id, qty)
    return jsonify({"ok": True})


@mealprep_bp.route("/api/delete/<int:item_id>", methods=["POST"])
def api_delete(item_id: int):
    mealprep_db.init_db()
    mealprep_db.delete_item(item_id)
    return jsonify({"ok": True})
