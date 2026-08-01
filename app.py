#!/usr/bin/env python3
"""
Control panel — start/stop/view apps on the VM.
Served at http://<tailscale-ip>/ (port 9000).
Safe to use without auth because access is Tailscale-only.
"""

import os
import subprocess
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

try:
    from food_routes import food_bp
    app.register_blueprint(food_bp, url_prefix="/food")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Food blueprint unavailable: %s", _e)

try:
    from plants_routes import plants_bp
    app.register_blueprint(plants_bp, url_prefix="/plants")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Plants blueprint unavailable: %s", _e)

try:
    from mealprep_routes import mealprep_bp
    app.register_blueprint(mealprep_bp, url_prefix="/mealprep")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Mealprep blueprint unavailable: %s", _e)

try:
    from workout_routes import workout_bp
    app.register_blueprint(workout_bp, url_prefix="/workout")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Workout blueprint unavailable: %s", _e)

try:
    from meds_routes import meds_bp
    app.register_blueprint(meds_bp, url_prefix="/meds")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Meds blueprint unavailable: %s", _e)

try:
    from wp_routes import wp_bp
    app.register_blueprint(wp_bp, url_prefix="/wp")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Willpower blueprint unavailable: %s", _e)

try:
    from shopping_routes import shopping_bp
    app.register_blueprint(shopping_bp, url_prefix="/shopping")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Shopping blueprint unavailable: %s", _e)

PORT = int(os.environ.get("CONTROL_PANEL_PORT", 9000))

# Franklin's web dashboard (todo_list/franklin/web.py) is an on-demand Flask
# server living inside the app-todo process, not its own systemd service —
# it's controlled via franklin/control.py, a tiny always-on sibling in that
# same process, reachable locally since panel and todo_list run on the same VM.
FRANKLIN_CONTROL_PORT = int(os.environ.get("FRANKLIN_CONTROL_PORT", 8766))
FRANKLIN_WEB_PORT     = int(os.environ.get("WEB_PORT", 8765))
FRANKLIN_CONTROL_URL  = f"http://localhost:{FRANKLIN_CONTROL_PORT}"

SERVICES = [
    {"id": "arcade",    "label": "Arcade",              "path": "/arcade/"},
    {"id": "plants",    "label": "Plants Tracker",       "path": "/plants/"},
    {"id": "todo",      "label": "Accountability Bot + Pinger + Franklin", "path": None},
    {"id": "adhd-bot",  "label": "ADHD Bot",             "path": None},
    {"id": "food",      "label": "Hub Bot (food/workout/meds)", "path": None},
    {"id": "ai-prep",   "label": "AI Prep (Discord)",    "path": None},
    {"id": "learn-bot", "label": "Learn Bot (Telegram)", "path": None},
    {"id": "wp-instinct", "label": "Willpower Instinct Bot", "path": None},
    {"id": "stm",         "label": "Semantic Task Manager",  "path": "/shopping/"},
    {"id": "cadonors",    "label": "CA Donor Research",      "path": None, "port": 5056},
]

# Sub-page dashboards served by the panel itself (no separate systemd service)
DASHBOARDS = [
    {"label": "Nutrition",         "path": "/food/"},
    {"label": "Meal Prep / Fridge", "path": "/mealprep/"},
    {"label": "Workout",           "path": "/workout/"},
    {"label": "Meds & Supplements", "path": "/meds/"},
    {"label": "Willpower Instinct", "path": "/wp/"},
    {"label": "Shopping Lists",    "path": "/shopping/"},
]


def _run(cmd: list[str]) -> tuple[str, int]:
    result = subprocess.run(
        ["sudo"] + cmd,
        capture_output=True, text=True, timeout=10
    )
    return (result.stdout + result.stderr).strip(), result.returncode


def service_status(service_id: str) -> str:
    out, _ = _run(["systemctl", "is-active", f"app-{service_id}"])
    return out.strip()


def service_logs(service_id: str, lines: int = 60) -> str:
    out, _ = _run([
        "journalctl", "-u", f"app-{service_id}",
        "-n", str(lines), "--no-pager", "-o", "short-iso"
    ])
    return out


@app.route("/")
def index():
    services = []
    for svc in SERVICES:
        status = service_status(svc["id"])
        services.append({**svc, "status": status})
    return render_template(
        "index.html", services=services, dashboards=DASHBOARDS,
        franklin_web_port=FRANKLIN_WEB_PORT,
    )


@app.route("/api/franklin-web/status")
def franklin_web_status():
    try:
        r = requests.get(f"{FRANKLIN_CONTROL_URL}/status", timeout=3)
        return jsonify(r.json())
    except Exception:
        return jsonify({"running": False, "unreachable": True})


@app.route("/api/franklin-web/start", methods=["POST"])
def franklin_web_start():
    try:
        r = requests.post(f"{FRANKLIN_CONTROL_URL}/start", timeout=8)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"running": False, "error": str(e)}), 502


@app.route("/api/franklin-web/stop", methods=["POST"])
def franklin_web_stop():
    try:
        r = requests.post(f"{FRANKLIN_CONTROL_URL}/stop", timeout=8)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"running": False, "error": str(e)}), 502


@app.route("/api/status")
def api_status():
    return jsonify({
        svc["id"]: service_status(svc["id"]) for svc in SERVICES
    })


@app.route("/api/action", methods=["POST"])
def api_action():
    data       = request.get_json(force=True)
    service_id = data.get("service", "")
    action     = data.get("action", "")

    valid_ids     = {s["id"] for s in SERVICES}
    valid_actions = {"start", "stop", "restart"}

    if service_id not in valid_ids or action not in valid_actions:
        return jsonify({"ok": False, "error": "Invalid service or action"}), 400

    _, code = _run(["systemctl", action, f"app-{service_id}"])
    new_status = service_status(service_id)
    return jsonify({"ok": code == 0, "status": new_status})


@app.route("/api/logs/<service_id>")
def api_logs(service_id: str):
    valid_ids = {s["id"] for s in SERVICES}
    if service_id not in valid_ids:
        return jsonify({"ok": False, "error": "Unknown service"}), 400
    lines = int(request.args.get("lines", 60))
    return jsonify({"ok": True, "logs": service_logs(service_id, lines)})


@app.route("/api/restart-panel", methods=["POST"])
def api_restart_panel():
    # Fire restart after a 1s delay so this response can be delivered first
    subprocess.Popen(
        ["sudo", "bash", "-c", "sleep 1 && systemctl restart app-panel"],
        start_new_session=True,
    )
    return jsonify({"ok": True})


@app.route("/api/monitor")
def api_monitor():
    log_path = Path.home() / "monitor.log"
    if not log_path.exists():
        return jsonify({"ok": True, "log": "No monitor log yet."})
    lines = log_path.read_text().splitlines()
    return jsonify({"ok": True, "log": "\n".join(lines[-80:])})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
