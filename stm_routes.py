"""STM (semantic task manager) bulk import page.

Two functions, mirroring the bot's Telegram flow:
1. Upload a script_data Google-Tasks scrape JSON → get the claude.ai
   grouping prompt back as a download. (Keep-notes filtering needs the
   anthropic package, which this venv doesn't have — do Keep via the bot.)
2. Paste claude.ai's PROJECT:/checkbox reply → preview → confirm → imported
   as parent tasks + subtasks straight into the bot's SQLite DB.

Imports the bot's own ingest/db modules from its app directory, so parsing
and import logic stay single-sourced.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from flask import Blueprint, Response, render_template, request

# Bot repo location: VM first, laptop dev fallback.
for _cand in (Path.home() / "apps" / "semantic_task_manager",
              Path.home() / "Documents" / "semantic_task_manager"):
    if _cand.is_dir():
        sys.path.insert(0, str(_cand))
        break

import ingest  # noqa: E402  (from the bot repo; ai is lazily imported there)

stm_bp = Blueprint("stm", __name__)


@stm_bp.route("/", methods=["GET"])
def home():
    return render_template("stm_import.html", preview=None, summary=None, raw="")


@stm_bp.route("/prompt", methods=["POST"])
def make_prompt():
    f = request.files.get("scrape")
    if f is None:
        return render_template("stm_import.html", preview=None, raw="",
                                summary="No file uploaded.")
    try:
        payload = json.loads(f.read().decode("utf-8", errors="replace"))
    except ValueError:
        return render_template("stm_import.html", preview=None, raw="",
                                summary="That file isn't valid JSON.")
    if "lists" not in payload:
        return render_template(
            "stm_import.html", preview=None, raw="",
            summary="Expected a Google Tasks scrape (with a 'lists' key). "
                    "Keep-notes JSONs need AI filtering — send those to the Telegram bot instead.")
    items = ingest.clean_from_parsed(payload)
    prompt = ingest.build_grouping_prompt(items, [])
    return Response(
        prompt, mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=grouping_prompt.txt"},
    )


@stm_bp.route("/import", methods=["POST"])
def do_import():
    raw = request.form.get("grouped", "")
    projects = ingest.parse_grouped_output(raw)
    if not projects:
        return render_template("stm_import.html", preview=None, raw=raw,
                                summary="No PROJECT:/checkbox lines found in that paste.")

    if request.form.get("confirm"):
        total_created = total_skipped = 0
        for p in projects:
            result = ingest.import_project(p)
            total_created += result["created"]
            total_skipped += result["skipped"]
        return render_template(
            "stm_import.html", preview=None, raw="",
            summary=f"Imported {total_created} tasks across {len(projects)} projects "
                    f"({total_skipped} duplicates skipped). They'll reach Google Tasks on "
                    "the bot's next sync cycle.")

    return render_template("stm_import.html", preview=projects, raw=raw, summary=None)
