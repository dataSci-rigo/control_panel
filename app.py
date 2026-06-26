#!/usr/bin/env python3
"""
Control panel — start/stop/view apps on the VM.
Served at http://<tailscale-ip>/ (port 9000).
Safe to use without auth because access is Tailscale-only.
"""

import os
import subprocess
from pathlib import Path

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
PORT = int(os.environ.get("CONTROL_PANEL_PORT", 9000))

SERVICES = [
    {"id": "arcade",    "label": "Arcade",             "path": "/arcade/"},
    {"id": "plants",    "label": "Plants Tracker",      "path": "/plants/"},
    {"id": "todo",      "label": "Accountability Bot",  "path": None},
    {"id": "todo-ping", "label": "Todo Pinger",         "path": None},
    {"id": "adhd-bot",  "label": "ADHD Bot",            "path": None},
    {"id": "food",      "label": "Food / Nutrition",    "path": "/food/"},
    {"id": "ai-prep",   "label": "Learn Bot (Telegram)", "path": None},
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
    return render_template("index.html", services=services)


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


@app.route("/api/monitor")
def api_monitor():
    log_path = Path.home() / "monitor.log"
    if not log_path.exists():
        return jsonify({"ok": True, "log": "No monitor log yet."})
    lines = log_path.read_text().splitlines()
    return jsonify({"ok": True, "log": "\n".join(lines[-80:])})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
