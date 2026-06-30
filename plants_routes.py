"""
Plants tracker routes — mounted on the panel app at /plants/.
Reads directly from the plants project's SQLite DB using synchronous sqlite3.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for
from dotenv import load_dotenv

load_dotenv()

_PLANTS_DIR = next(
    (p for p in [
        os.path.expanduser("~/apps/plants"),
        os.path.expanduser("~/Documents/plants"),
    ] if os.path.isdir(p)),
    os.path.expanduser("~/apps/plants"),
)

_DB_PATH = str(Path(_PLANTS_DIR) / "plants.db")
_TEMPLATE_DIR = str(Path(_PLANTS_DIR) / "templates")

plants_bp = Blueprint("plants", __name__, template_folder=_TEMPLATE_DIR)

_URL_PREFIX = "/plants"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _estimate_soil_volume_l(depth, width):
    import math
    if not depth or not width:
        return None
    return round(math.pi * (width / 2) ** 2 * depth / 1000, 2)


@plants_bp.route("/")
def index():
    owner_id = os.getenv("OWNER_CHAT_ID", "")
    second_id = os.getenv("SECOND_USER_CHAT_ID", "")

    conn = _get_db()
    rows = conn.execute("""
        SELECT p.*,
               MAX(wh.watered_at)    AS last_watered,
               COUNT(wh.id)          AS watering_count
        FROM plants p
        LEFT JOIN watering_history wh ON p.id = wh.plant_id
        GROUP BY p.id
        ORDER BY p.name
    """).fetchall()
    conn.close()

    plants = []
    for row in rows:
        p = dict(row)
        uid = str(p.get("user_id") or "")
        if uid == owner_id:
            p["user_label"] = "owner"
        elif uid == second_id:
            p["user_label"] = "guest"
        else:
            p["user_label"] = None
        plants.append(p)

    return render_template("plants_list.html", plants=plants, url_prefix=_URL_PREFIX)


@plants_bp.route("/plant/<int:plant_id>")
def plant_detail(plant_id):
    conn = _get_db()
    plant = conn.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not plant:
        abort(404)
    history = conn.execute(
        "SELECT * FROM watering_history WHERE plant_id = ? ORDER BY watered_at DESC",
        (plant_id,),
    ).fetchall()
    height_history = conn.execute(
        "SELECT * FROM height_history WHERE plant_id = ? ORDER BY measured_at DESC",
        (plant_id,),
    ).fetchall()
    issues = conn.execute(
        "SELECT * FROM issues WHERE plant_id = ? ORDER BY resolved ASC, observed_at DESC",
        (plant_id,),
    ).fetchall()
    treatments = conn.execute(
        "SELECT * FROM treatments WHERE plant_id = ? ORDER BY applied_at DESC",
        (plant_id,),
    ).fetchall()
    conn.close()
    return render_template(
        "plant.html", plant=plant, history=history,
        height_history=height_history, issues=issues, treatments=treatments,
        url_prefix=_URL_PREFIX,
    )


@plants_bp.route("/plant/<int:plant_id>/edit", methods=["GET", "POST"])
def plant_edit(plant_id):
    conn = _get_db()
    plant = conn.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not plant:
        conn.close()
        abort(404)

    if request.method == "POST":
        f = request.form

        def _float(key):
            v = f.get(key, "").strip()
            return float(v) if v else None

        def _int(key):
            v = f.get(key, "").strip()
            return int(v) if v else None

        def _str(key):
            v = f.get(key, "").strip()
            return v if v else None

        location = _str("location")
        pot_depth = _float("pot_depth_cm")
        pot_width = _float("pot_width_cm")
        soil_volume = _estimate_soil_volume_l(pot_depth, pot_width) if location == "pot" else None

        fields = dict(
            name=f.get("name", "").strip(),
            plant_type=_str("plant_type"),
            location=location,
            pot_depth_cm=pot_depth,
            pot_width_cm=pot_width,
            soil_volume_l=soil_volume,
            soil_alkalinity=_str("soil_alkalinity"),
            soil_type=_str("soil_type"),
            fertilizer_type=_str("fertilizer_type"),
            fertilizer_amount=_str("fertilizer_amount"),
            fertilizer_frequency_days=_int("fertilizer_frequency_days"),
            facing=_str("facing"),
            height_cm=_float("height_cm"),
            sunlight_hours_actual=_float("sunlight_hours_actual"),
            sunlight_hours_needed=_float("sunlight_hours_needed"),
            watering_frequency_days=_int("watering_frequency_days") or 7,
            watering_amount_ml=_int("watering_amount_ml") or 200,
            notes=_str("notes"),
        )

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [plant_id]
        conn.execute(f"UPDATE plants SET {set_clause} WHERE id = ?", values)

        photo = request.files.get("photo")
        if photo and photo.filename:
            conn.execute(
                "UPDATE plants SET image_data = ?, telegram_file_id = NULL WHERE id = ?",
                (photo.read(), plant_id),
            )

        conn.commit()
        conn.close()
        return redirect(url_for("plants.plant_detail", plant_id=plant_id))

    conn.close()
    return render_template("edit.html", plant=plant, url_prefix=_URL_PREFIX)


@plants_bp.route("/plant/<int:plant_id>/issue", methods=["POST"])
def plant_log_issue(plant_id):
    conn = _get_db()
    plant = conn.execute("SELECT id FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not plant:
        conn.close()
        abort(404)
    category = request.form.get("category", "other")
    description = request.form.get("description", "").strip()
    if description:
        conn.execute(
            "INSERT INTO issues (plant_id, category, description) VALUES (?, ?, ?)",
            (plant_id, category, description),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("plants.plant_detail", plant_id=plant_id))


@plants_bp.route("/plant/<int:plant_id>/issue/<int:issue_id>/resolve", methods=["POST"])
def plant_resolve_issue(plant_id, issue_id):
    conn = _get_db()
    conn.execute(
        "UPDATE issues SET resolved = 1, resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND plant_id = ?",
        (issue_id, plant_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("plants.plant_detail", plant_id=plant_id))


@plants_bp.route("/plant/<int:plant_id>/treat", methods=["POST"])
def plant_log_treatment(plant_id):
    conn = _get_db()
    plant = conn.execute("SELECT id FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not plant:
        conn.close()
        abort(404)
    f = request.form
    soap     = 1 if f.get("soap")     else 0
    spinosad = 1 if f.get("spinosad") else 0
    neem     = 1 if f.get("neem")     else 0
    kaolin   = 1 if f.get("kaolin")   else 0
    notes    = f.get("notes", "").strip() or None
    conn.execute(
        "INSERT INTO treatments (plant_id, soap, spinosad, neem, kaolin, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (plant_id, soap, spinosad, neem, kaolin, notes),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("plants.plant_detail", plant_id=plant_id))


@plants_bp.route("/plant/<int:plant_id>/water", methods=["POST"])
def plant_water(plant_id):
    conn = _get_db()
    plant = conn.execute("SELECT id FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not plant:
        conn.close()
        abort(404)
    amount_ml = int(request.form.get("amount_ml") or 200)
    conn.execute(
        "INSERT INTO watering_history (plant_id, amount_ml) VALUES (?, ?)",
        (plant_id, amount_ml),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("plants.plant_detail", plant_id=plant_id))


@plants_bp.route("/plant/<int:plant_id>/photo")
def plant_photo(plant_id):
    conn = _get_db()
    row = conn.execute("SELECT image_data FROM plants WHERE id = ?", (plant_id,)).fetchone()
    conn.close()
    if not row or not row["image_data"]:
        abort(404)
    return Response(bytes(row["image_data"]), mimetype="image/jpeg")
