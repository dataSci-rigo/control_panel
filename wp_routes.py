"""
Willpower Instinct dashboard — mounted at /wp/.
Reads and writes the bot's SQLite DB directly using synchronous sqlite3.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, url_for

# Resolve DB path: VM first, laptop fallback
_DB_PATH = next(
    (str(Path(p) / "data" / "tracker.db") for p in [
        os.path.expanduser("~/apps/wpi"),
        os.path.expanduser("~/Documents/wp_instinct"),
    ] if Path(p).is_dir()),
    os.path.expanduser("~/apps/wpi/data/tracker.db"),
)

wp_bp = Blueprint("wp", __name__, template_folder="templates")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _get_active_cycle(owner_id: int) -> dict | None:
    conn = _db()
    row = conn.execute(
        "SELECT * FROM cycles WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (owner_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _week_date_range(started_at: str, week_number: int) -> tuple[date, date]:
    start = date.fromisoformat(started_at) + timedelta(weeks=week_number - 1)
    return start, start + timedelta(days=6)


def _get_week_entries(cycle_id: int, week_number: int) -> list[dict]:
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM daily_entries WHERE cycle_id=? AND week_number=? ORDER BY date",
        (cycle_id, week_number),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_week_urges(cycle_id: int, start: date, end: date) -> list[dict]:
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM urges WHERE cycle_id=? AND date(timestamp) BETWEEN ? AND ? ORDER BY timestamp",
        (cycle_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_week_boosters(cycle_id: int, start: date, end: date) -> list[dict]:
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM boosters WHERE cycle_id=? AND date BETWEEN ? AND ?",
        (cycle_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()
    return {r["date"]: dict(r) for r in rows}


def _get_entry_for_date(cycle_id: int, entry_date: str) -> dict | None:
    conn = _db()
    row = conn.execute(
        "SELECT * FROM daily_entries WHERE cycle_id=? AND date=?",
        (cycle_id, entry_date),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _get_boosters_for_date(cycle_id: int, entry_date: str) -> dict | None:
    conn = _db()
    row = conn.execute(
        "SELECT * FROM boosters WHERE cycle_id=? AND date=?",
        (cycle_id, entry_date),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _get_synthesis(cycle_id: int, week_number: int) -> dict | None:
    conn = _db()
    row = conn.execute(
        "SELECT * FROM weekly_syntheses WHERE cycle_id=? AND week_number=?",
        (cycle_id, week_number),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _load_program() -> dict:
    import yaml
    for p in [
        os.path.expanduser("~/apps/wpi/program/program.yaml"),
        os.path.expanduser("~/Documents/wp_instinct/program/program.yaml"),
    ]:
        if Path(p).exists():
            with open(p) as f:
                data = yaml.safe_load(f)
            return {w["week_number"]: w for w in data["weeks"]}
    return {}


def _owner_id() -> int:
    raw = os.getenv("OWNER_CHAT_ID", "8879485812")
    return int(raw.strip("'\""))


# ── routes ────────────────────────────────────────────────────────────────────

@wp_bp.route("/")
def dashboard():
    owner_id = _owner_id()
    cycle = _get_active_cycle(owner_id)
    if not cycle:
        return render_template("wp_dashboard.html", cycle=None, program=None,
                               week=None, entries=[], urges=[], boosters={},
                               synthesis=None, week_start=None, week_end=None,
                               all_days=[], today=date.today().isoformat())

    # Allow ?week= override for browsing past weeks
    try:
        view_week = int(request.args.get("week", cycle["current_week"]))
    except (ValueError, TypeError):
        view_week = cycle["current_week"]
    view_week = max(1, min(10, view_week))

    program = _load_program()
    week_data = program.get(view_week, {})
    week_start, week_end = _week_date_range(cycle["started_at"], view_week)

    entries_list = _get_week_entries(cycle["id"], view_week)
    entries_by_date = {e["date"]: e for e in entries_list}
    urges = _get_week_urges(cycle["id"], week_start, week_end)
    boosters = _get_week_boosters(cycle["id"], week_start, week_end)
    synthesis = _get_synthesis(cycle["id"], view_week)

    # Build one row per day even if no entry exists yet
    all_days = []
    for i in range(7):
        d = (week_start + timedelta(days=i)).isoformat()
        all_days.append({
            "date": d,
            "entry": entries_by_date.get(d),
            "boosters": boosters.get(d),
        })

    today = date.today().isoformat()

    return render_template(
        "wp_dashboard.html",
        cycle=cycle,
        program=program,
        week=week_data,
        view_week=view_week,
        entries=all_days,
        urges=urges,
        boosters=boosters,
        synthesis=synthesis,
        week_start=week_start,
        week_end=week_end,
        today=today,
    )


@wp_bp.route("/entry/<entry_date>", methods=["GET", "POST"])
def edit_entry(entry_date: str):
    owner_id = _owner_id()
    cycle = _get_active_cycle(owner_id)
    if not cycle:
        return redirect(url_for("wp.dashboard"))

    if request.method == "POST":
        f = request.form

        def _int(k): v = f.get(k, "").strip(); return int(v) if v else None
        def _float(k): v = f.get(k, "").strip(); return float(v) if v else None
        def _str(k): v = f.get(k, "").strip(); return v if v else None
        def _bool(k): return 1 if f.get(k) else 0

        # Determine week number from date
        started = date.fromisoformat(cycle["started_at"])
        entry_d = date.fromisoformat(entry_date)
        week_num = max(1, min(10, (entry_d - started).days // 7 + 1))

        conn = _db()
        # Upsert daily entry
        entry_fields = {
            "energy_level":        _int("energy_level"),
            "challenge_adherence": _str("challenge_adherence"),
            "urge_count":          _int("urge_count") or 0,
            "microscope_obs":      _str("microscope_obs"),
            "reflection_text":     _str("reflection_text"),
        }
        cols = ", ".join(entry_fields.keys())
        placeholders = ", ".join("?" * len(entry_fields))
        updates = ", ".join(f"{k}=?" for k in entry_fields)
        vals = list(entry_fields.values())
        conn.execute(
            f"INSERT INTO daily_entries (user_id, cycle_id, date, week_number, {cols}) "
            f"VALUES (?, ?, ?, ?, {placeholders}) "
            f"ON CONFLICT(cycle_id, date) DO UPDATE SET {updates}",
            [owner_id, cycle["id"], entry_date, week_num, *vals, *vals],
        )

        # Upsert boosters
        booster_fields = {
            "sleep_hours":        _float("sleep_hours"),
            "exercise_done":      _bool("exercise_done"),
            "meditation_minutes": _int("meditation_minutes") or 0,
            "breathing_done":     _bool("breathing_done"),
        }
        b_cols = ", ".join(booster_fields.keys())
        b_placeholders = ", ".join("?" * len(booster_fields))
        b_updates = ", ".join(f"{k}=?" for k in booster_fields)
        b_vals = list(booster_fields.values())
        conn.execute(
            f"INSERT INTO boosters (user_id, cycle_id, date, {b_cols}) "
            f"VALUES (?, ?, ?, {b_placeholders}) "
            f"ON CONFLICT(cycle_id, date) DO UPDATE SET {b_updates}",
            [owner_id, cycle["id"], entry_date, *b_vals, *b_vals],
        )
        conn.commit()
        conn.close()

        # Redirect back to the week view
        started = date.fromisoformat(cycle["started_at"])
        entry_d = date.fromisoformat(entry_date)
        week_num = max(1, min(10, (entry_d - started).days // 7 + 1))
        return redirect(url_for("wp.dashboard", week=week_num))

    # GET — show edit form
    entry = _get_entry_for_date(cycle["id"], entry_date)
    boosters = _get_boosters_for_date(cycle["id"], entry_date)
    program = _load_program()
    started = date.fromisoformat(cycle["started_at"])
    entry_d = date.fromisoformat(entry_date)
    week_num = max(1, min(10, (entry_d - started).days // 7 + 1))
    week_data = program.get(week_num, {})

    return render_template(
        "wp_edit.html",
        cycle=cycle,
        entry_date=entry_date,
        entry=entry,
        boosters=boosters,
        week=week_data,
        week_num=week_num,
    )


@wp_bp.route("/urge/<int:urge_id>/delete", methods=["POST"])
def delete_urge(urge_id: int):
    owner_id = _owner_id()
    conn = _db()
    conn.execute("DELETE FROM urges WHERE id=? AND user_id=?", (urge_id, owner_id))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("wp.dashboard"))


# ── challenges ────────────────────────────────────────────────────────────────

def _get_challenges(cycle_id: int) -> list[dict]:
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM challenges WHERE cycle_id=? ORDER BY sort_order, id",
        (cycle_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@wp_bp.route("/challenges", methods=["GET", "POST"])
def challenges():
    owner_id = _owner_id()
    cycle = _get_active_cycle(owner_id)
    if not cycle:
        return redirect(url_for("wp.dashboard"))

    if request.method == "POST":
        action = request.form.get("action")
        conn = _db()

        if action == "add":
            c_type = request.form.get("challenge_type", "i_will").strip()
            c_text = request.form.get("challenge_text", "").strip()
            if c_text:
                conn.execute(
                    "INSERT INTO challenges (user_id, cycle_id, challenge_type, challenge_text) "
                    "VALUES (?, ?, ?, ?)",
                    (owner_id, cycle["id"], c_type, c_text),
                )
        elif action == "delete":
            c_id = int(request.form.get("challenge_id", 0))
            conn.execute("DELETE FROM challenges WHERE id=? AND user_id=?", (c_id, owner_id))
        elif action == "edit":
            c_id = int(request.form.get("challenge_id", 0))
            c_type = request.form.get("challenge_type", "i_will").strip()
            c_text = request.form.get("challenge_text", "").strip()
            if c_text:
                conn.execute(
                    "UPDATE challenges SET challenge_type=?, challenge_text=? "
                    "WHERE id=? AND user_id=?",
                    (c_type, c_text, c_id, owner_id),
                )

        conn.commit()
        conn.close()
        return redirect(url_for("wp.challenges"))

    challenge_list = _get_challenges(cycle["id"])
    return render_template("wp_challenges.html", cycle=cycle, challenges=challenge_list)
