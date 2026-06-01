"""
Raj Web App - Flask Backend v2.0
Production-ready with CSV database seeding + SPA routing
"""

import os
import sys
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ─── Paths ───
API_DIR = Path(__file__).parent
sys.path.insert(0, str(API_DIR))

# ─── Import RoboPirate modules ───
from db import Database
from engine import CampaignEngine

# ─── Seed database from CSVs (before Flask starts) ───
print("[INIT] Checking database...")
from seed_db import seed_database
seed_database()

# ─── Flask App ───
app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

# ─── Globals ───
db = None
gmail = None
engine = None
brain = None


def init_services():
    """Initialize database, engine, and brain. Gmail is optional."""
    global db, gmail, engine, brain

    db = Database()
    print("[INIT] Database connected")

    # Gmail is optional — app works without it
    try:
        from gmail import GmailClient
        gmail = GmailClient()
        print("[INIT] Gmail connected")
    except Exception as e:
        print(f"[INIT] Gmail not available: {e}")
        gmail = None

    engine = CampaignEngine(db, gmail) if gmail else CampaignEngine(db, None)
    print("[INIT] Engine initialized")

    # Start engine silently (no Gmail = no sending, but UI works)
    try:
        engine.start()
        print("[INIT] Engine started")
    except Exception as e:
        print(f"[INIT] Engine start warning: {e}")

    # Raj brain
    try:
        from raj_brain import RajBrain
        brain = RajBrain(engine)
        print("[INIT] Raj brain initialized")
    except Exception as e:
        print(f"[INIT] Brain init warning: {e}")
        brain = None


# ─── SPA Routing ───
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files or fallback to index.html for SPA routes."""
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


# ═══════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════
@app.route('/api/dashboard')
def api_dashboard():
    try:
        summary = engine.get_summary() if engine else {"sequences": {}, "global": {}}
        families = _get_batch_families()
        return jsonify({"success": True, "summary": summary, "families": families})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _get_batch_families():
    if not db:
        return []

    batches = db.batch_get_all()
    if not batches:
        return []

    families_dict = {}
    for b in batches:
        name = b.get("name", "")
        family_name = re.sub(r'[-_]D\d+$', '', name, flags=re.I)
        family_name = re.sub(r'(?<![Bb])[-_]B\d+$', '', family_name, flags=re.I)
        family_name = re.sub(r'[-_]+$', '', family_name)
        family_name = family_name.strip() or name

        if family_name not in families_dict:
            families_dict[family_name] = {
                "name": family_name,
                "sequence_id": b.get("sequence_id", ""),
                "total_recipients": 0,
                "days": {"D1": None, "D3": None, "D5": None, "D7": None, "D10": None}
            }

        day = "D1"
        m = re.search(r'[-_]D(\d+)', name, re.I)
        if m and m.group(1) in ["1", "3", "5", "7", "10"]:
            day = f"D{m.group(1)}"
        else:
            m = re.search(r'[-_]B(\d+)', name, re.I)
            if m:
                bn = int(m.group(1))
                day_map = {1: "D1", 2: "D1", 3: "D3", 4: "D3", 5: "D5", 6: "D5", 7: "D7", 8: "D7", 9: "D10", 10: "D10"}
                day = day_map.get(bn, "D1")

        try:
            counts = db.batch_count_by_status(b["id"])
            total = sum(counts.values())
            sent = counts.get("sent", 0)
        except:
            total = 0
            sent = 0

        scheduled = b.get("scheduled_at")
        date_text = ""
        if scheduled:
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S.%f"]:
                try:
                    dt = datetime.strptime(scheduled, fmt)
                    date_text = dt.strftime("%d %b")
                    break
                except ValueError:
                    continue
        else:
            day_num = int(day.replace("D", ""))
            date_text = (datetime.now() + timedelta(days=day_num)).strftime("%d %b")

        families_dict[family_name]["days"][day] = {
            "batch_id": b["id"],
            "batch_name": b["name"],
            "status": b.get("status", "draft"),
            "sent": sent,
            "total": total,
            "scheduled_at": scheduled,
            "date_text": date_text,
        }
        families_dict[family_name]["total_recipients"] = max(families_dict[family_name]["total_recipients"], total)

    return list(families_dict.values())


# ═══════════════════════════════════════════════
#  BATCHES
# ═══════════════════════════════════════════════
@app.route('/api/batches', methods=['GET'])
def api_batches_list():
    try:
        batches = db.batch_get_all() if db else []
        for b in batches:
            try:
                counts = db.batch_count_by_status(b["id"])
                b["total_recipients"] = sum(counts.values())
                b["sent"] = counts.get("sent", 0)
            except:
                b["total_recipients"] = 0
                b["sent"] = 0
        return jsonify({"success": True, "batches": batches})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/batches', methods=['POST'])
def api_batch_create():
    try:
        data = request.json or {}
        batch_id, error = db.batch_from_pool(
            name=data.get('name', 'New Batch'),
            sequence_id=data.get('sequence_id', 'school'),
            batch_size=data.get('size', 50),
            day_offset=data.get('day_offset', 1)
        )
        if error:
            return jsonify({"success": False, "error": error}), 400
        return jsonify({"success": True, "batch_id": batch_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/batches/<int:batch_id>/run', methods=['POST'])
def api_batch_run(batch_id):
    try:
        db.batch_update_status(batch_id, 'running')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/batches/<int:batch_id>/pause', methods=['POST'])
def api_batch_pause(batch_id):
    try:
        db.batch_update_status(batch_id, 'paused')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/batches/<int:batch_id>', methods=['DELETE'])
def api_batch_delete(batch_id):
    try:
        db.batch_delete(batch_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  CHAT
# ═══════════════════════════════════════════════
@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json or {}
        message = data.get('message', '')
        if not brain:
            return jsonify({"response": "Raj is initializing... Please wait a moment."})
        result = brain.process(message)
        return jsonify({
            "response": result.get("response", "I processed your request, sir."),
            "action": result.get("action"),
            "result": result.get("result"),
        })
    except Exception as e:
        return jsonify({"response": f"I'm having trouble right now. Error: {str(e)[:100]}"})


# ═══════════════════════════════════════════════
#  TEMPLATES
# ═══════════════════════════════════════════════
@app.route('/api/templates')
def api_templates():
    try:
        result = {}
        for seq_id in ["school", "csr"]:
            result[seq_id] = {}
            for day in [1, 3, 5, 7, 10]:
                tmpl = db.template_get(seq_id, day) if db else None
                if tmpl:
                    result[seq_id][day] = {
                        "sequence_id": seq_id, "day": day,
                        "subject": tmpl.get("subject", ""),
                        "locked": bool(tmpl.get("locked")),
                        "source": tmpl.get("source", "unknown"),
                        "has_body": bool(tmpl.get("html_body")),
                    }
        return jsonify({"success": True, "templates": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/templates/<seq_id>/<int:day>')
def api_template_get(seq_id, day):
    try:
        tmpl = db.template_get(seq_id, day) if db else None
        return jsonify({"success": True, "template": tmpl})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/templates/sync', methods=['POST'])
def api_templates_sync():
    try:
        if not engine or not hasattr(engine, 'sync_templates'):
            return jsonify({"success": False, "error": "Gmail not connected"})
        result = engine.sync_templates()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  IMPORT
# ═══════════════════════════════════════════════
@app.route('/api/import', methods=['POST'])
def api_import():
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"})
        file = request.files['file']
        sequence_id = request.form.get('sequence_id', 'school')
        if file.filename == '':
            return jsonify({"success": False, "error": "Empty filename"})

        upload_dir = API_DIR / 'uploads'
        upload_dir.mkdir(exist_ok=True)
        filepath = upload_dir / file.filename
        file.save(str(filepath))

        if engine and hasattr(engine, 'smart_import'):
            result = engine.smart_import(str(filepath), sequence_id)
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": "Engine not ready"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  BLACKLIST
# ═══════════════════════════════════════════════
@app.route('/api/blacklist')
def api_blacklist():
    try:
        entries = db.blacklist_get_all() if db else []
        return jsonify({"success": True, "blacklist": entries})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/blacklist', methods=['POST'])
def api_blacklist_add():
    try:
        data = request.json or {}
        email = data.get('email', '')
        if email:
            db.blacklist_add(email, data.get('reason', 'manual'))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/blacklist', methods=['DELETE'])
def api_blacklist_remove():
    try:
        data = request.json or {}
        email = data.get('email', '')
        if email:
            db.blacklist_remove(email)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  REPLIES
# ═══════════════════════════════════════════════
@app.route('/api/replies')
def api_replies():
    try:
        if not db:
            return jsonify({"success": True, "replies": []})
        rows = db.execute("SELECT * FROM replies ORDER BY received_at DESC LIMIT 100").fetchall()
        return jsonify({"success": True, "replies": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/replies/<int:reply_id>/handled', methods=['POST'])
def api_reply_handled(reply_id):
    try:
        if db:
            db.execute("UPDATE replies SET status='handled' WHERE id=?", (reply_id,))
            db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/scan-replies', methods=['POST'])
def api_scan_replies():
    try:
        if not engine or not hasattr(engine, 'scan_replies'):
            return jsonify({"success": False, "error": "Engine not ready"})
        count = engine.scan_replies()
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  BOUNCE SCAN
# ═══════════════════════════════════════════════
@app.route('/api/scan-bounces', methods=['POST'])
def api_scan_bounces():
    try:
        if not engine or not hasattr(engine, 'scan_bounces'):
            return jsonify({"success": False, "error": "Engine not ready"})
        result = engine.scan_bounces()
        return jsonify({"success": True, **(result if isinstance(result, dict) else {"count": result})})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  ENGINE CONTROL
# ═══════════════════════════════════════════════
@app.route('/api/engine/status')
def api_engine_status():
    try:
        return jsonify({
            "running": engine.is_running() if engine else False,
            "paused": engine.is_paused() if engine else False,
        })
    except:
        return jsonify({"running": False, "paused": False})


@app.route('/api/engine/<action>', methods=['POST'])
def api_engine_action(action):
    try:
        if not engine:
            return jsonify({"success": False, "error": "Engine not initialized"}), 500
        if action == 'start' and hasattr(engine, 'start'):
            engine.start()
        elif action == 'stop' and hasattr(engine, 'stop'):
            engine.stop()
        elif action == 'pause' and hasattr(engine, 'pause'):
            engine.pause()
        elif action == 'resume' and hasattr(engine, 'resume'):
            engine.resume()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════
@app.route('/api/settings')
def api_settings():
    try:
        settings = {
            "brief_email": db.get_meta("brief_email") or "itsomkarsingh@gmail.com" if db else "",
            "send_rate": db.get_meta("send_rate") or "45" if db else "45",
            "stagger_minutes": db.get_meta("stagger_minutes") or "2" if db else "2",
            "morning_hour": db.get_meta("morning_hour") or "8" if db else "8",
            "eod_hour": db.get_meta("eod_hour") or "19" if db else "19",
            "auto_advance": (db.get_meta("auto_advance") or "true") != "false" if db else True,
            "sunday_filter": (db.get_meta("sunday_filter") or "true") != "false" if db else True,
        }
        return jsonify({
            "success": True,
            "settings": settings,
            "engine": {
                "running": engine.is_running() if engine else False,
                "paused": engine.is_paused() if engine else False,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def api_settings_save():
    try:
        data = request.json or {}
        if db:
            for key in ['brief_email', 'send_rate', 'stagger_minutes', 'morning_hour', 'eod_hour']:
                if key in data:
                    db.set_meta(key, str(data[key]))
            for key in ['auto_advance', 'sunday_filter']:
                if key in data:
                    db.set_meta(key, 'true' if data[key] else 'false')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════
if __name__ == '__main__':
    init_services()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    init_services()
