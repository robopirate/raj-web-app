"""
app.py -- Raj Web App v5.9 (Clean Build)
Minimal, stable, web-safe
"""

import os
import re
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS

app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

API_DIR = Path(__file__).parent

engine = None
brain = None
_db_instance = None
_db_lock = threading.Lock()

# ─── Database Singleton ───
def get_db():
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                from db import Database
                _db_instance = Database()
    return _db_instance

# ─── Lazy Engine Init ───
def get_engine():
    global engine
    if engine is None:
        db = get_db()
        from engine import CampaignEngine
        engine = CampaignEngine(db)
        try:
            from gmail_web import GmailWebClient
            gmail = GmailWebClient(db)
            if gmail.is_authenticated():
                engine.gmail = gmail
                print("[App] Gmail auto-connected")
        except Exception as e:
            print(f"[App] Gmail auto-connect failed: {e}")
        engine.start()
    return engine

# ─── Lazy Brain Init ───
def get_brain():
    global brain
    if brain is None:
        from raj_brain import RajBrain
        brain = RajBrain(get_engine())
    return brain

@app.before_request
def before_request():
    g.db = get_db()
    if engine is None:
        get_engine()
    if brain is None:
        get_brain()

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "version": "5.9", "timestamp": datetime.now().isoformat()})

# ═══════════════════════════════════════════════
# GMAIL OAUTH
# ═══════════════════════════════════════════════

@app.route('/connect-gmail')
def connect_gmail_page():
    return """<html><head><meta charset="utf-8"><title>Connect Gmail</title>
    <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#e2e8f0;}
    .btn{display:inline-block;padding:16px 40px;background:#38bdf8;color:#0f172a;border-radius:10px;text-decoration:none;font-weight:700;font-size:16px;margin-top:20px;}
    .btn:hover{background:#7dd3fc;}</style></head>
    <body><h1 style="color:#38bdf8;">Connect Gmail</h1><p>Click below to authorize Raj to send emails.</p>
    <a href="/api/gmail/auth-url" class="btn">Connect Gmail Account</a><br><br>
    <a href="/" style="color:#94a3b8;text-decoration:none;">Back to Dashboard</a></body></html>"""

@app.route('/oauth2callback')
def oauth2callback():
    try:
        db = get_db()
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        result = client.handle_callback(request.args.get('code'))
        if result.get('success'):
            eng = get_engine()
            eng.gmail = client
            return "<html><body style='text-align:center;padding:50px;background:#0f172a;color:#34d399;font-family:sans-serif;'><h1>Gmail Connected!</h1><p>Raj can now send emails.</p><a href='/' style='color:#38bdf8;font-size:18px;'>Go to Dashboard</a></body></html>"
        else:
            return "<html><body style='text-align:center;padding:50px;background:#0f172a;color:#f87171;font-family:sans-serif;'><h1>Connection Failed</h1><p>" + result.get('error','') + "</p><a href='/connect-gmail' style='color:#38bdf8;'>Try Again</a></body></html>", 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/auth-url')
def api_gmail_auth_url():
    try:
        db = get_db()
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        url = client.get_auth_url()
        return jsonify({"success": True, "auth_url": url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/gmail/status')
def api_gmail_status():
    try:
        eng = get_engine()
        has_gmail = False
        try:
            has_gmail = eng.gmail is not None and hasattr(eng.gmail, 'is_authenticated') and eng.gmail.is_authenticated()
        except:
            pass
        return jsonify({"success": True, "connected": has_gmail, "mode": "web" if has_gmail else "none"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════
@app.route('/api/dashboard')
def api_dashboard():
    try:
        db = get_db()

        # Recipients by sequence
        cur = db.execute("SELECT sequence_id, COUNT(*) FROM recipients GROUP BY sequence_id")
        recipients_by_seq = {r[0]: r[1] for r in cur.fetchall()}

        # Per-sequence sends using JOIN (now IDs are fixed!)
        cur = db.execute("""
            SELECT r.sequence_id, s.status, COUNT(*) 
            FROM sends s 
            JOIN recipients r ON s.recipient_id = r.id 
            GROUP BY r.sequence_id, s.status
        """)
        sends_by_seq_status = {}
        for row in cur.fetchall():
            seq, status, count = row
            if seq not in sends_by_seq_status:
                sends_by_seq_status[seq] = {}
            sends_by_seq_status[seq][status] = count

        # Blacklist count
        cur = db.execute("SELECT COUNT(*) FROM blacklist")
        bl_count = cur.fetchone()[0]

        # Active batches
        cur = db.execute("SELECT COUNT(*) FROM batches WHERE status != 'completed'")
        active_batches = cur.fetchone()[0]

        # Templates
        cur = db.execute("SELECT sequence_id, COUNT(*) FROM templates GROUP BY sequence_id")
        templates_by_seq = {r[0]: r[1] for r in cur.fetchall()}

        # Day-wise sends per sequence
        day_wise = {}
        for seq_id in ["school", "csr"]:
            cur = db.execute("""
                SELECT s.day, COUNT(*) 
                FROM sends s 
                JOIN recipients r ON s.recipient_id = r.id 
                WHERE r.sequence_id = ? AND s.status = 'sent'
                GROUP BY s.day ORDER BY s.day
            """, (seq_id,))
            day_wise[seq_id] = {r[0]: r[1] for r in cur.fetchall()}

        # Build summary
        summary = {"sequences": {}, "global": {}}

        for seq_id in ["school", "csr"]:
            seq_sends = sends_by_seq_status.get(seq_id, {})
            seq_day = day_wise.get(seq_id, {})

            seq = {
                "recipients": recipients_by_seq.get(seq_id, 0),
                "pool_count": recipients_by_seq.get(seq_id, 0),
                "sent": seq_sends.get('sent', 0),
                "bounced": seq_sends.get('bounced', 0),
                "replied": seq_sends.get('replied', 0),
                "templates": templates_by_seq.get(seq_id, 0),
                "pipeline": {
                    "total": recipients_by_seq.get(seq_id, 0),
                    "drafted": 0,
                    "sent": seq_sends.get('sent', 0),
                    "bounced": seq_sends.get('bounced', 0),
                    "replied": seq_sends.get('replied', 0)
                },
                "day_wise": {
                    1: {"total": seq_day.get(1, 0), "sent": seq_day.get(1, 0), "bounced": 0, "replied": 0, "status": "Done" if seq_day.get(1,0) > 0 else "Pending"},
                    3: {"total": seq_day.get(3, 0), "sent": seq_day.get(3, 0), "bounced": 0, "replied": 0, "status": "Done" if seq_day.get(3,0) > 0 else "Pending"},
                    5: {"total": seq_day.get(5, 0), "sent": seq_day.get(5, 0), "bounced": 0, "replied": 0, "status": "Done" if seq_day.get(5,0) > 0 else "Pending"},
                    7: {"total": seq_day.get(7, 0), "sent": seq_day.get(7, 0), "bounced": 0, "replied": 0, "status": "Done" if seq_day.get(7,0) > 0 else "Pending"},
                    10: {"total": seq_day.get(10, 0), "sent": seq_day.get(10, 0), "bounced": 0, "replied": 0, "status": "Done" if seq_day.get(10,0) > 0 else "Pending"},
                },
                "batches": []
            }
            summary["sequences"][seq_id] = seq

        # Global totals
        total_sent = sum(s.get('sent', 0) for s in sends_by_seq_status.values())
        total_bounced = sum(s.get('bounced', 0) for s in sends_by_seq_status.values())
        total_replied = sum(s.get('replied', 0) for s in sends_by_seq_status.values())

        summary["global"] = {
            "total_recipients": sum(recipients_by_seq.values()),
            "blacklist_count": bl_count,
            "pending_replies": 0,
            "drafted_replies": 0,
            "active_batches": active_batches
        }

        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        import traceback
        print(f"[ERROR] Dashboard: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# BATCHES
# ═══════════════════════════════════════════════
@app.route('/api/batches')
def api_batches():
    try:
        db = get_db()
        batches = db.batch_get_all() if db else []
        return jsonify({"success": True, "batches": batches})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<batch_id>')
def api_batch_get(batch_id):
    try:
        db = get_db()
        batch = db.batch_get(batch_id) if db else None
        if not batch:
            return jsonify({"success": False, "error": "Batch not found"}), 404
        recipients = db.batch_get_recipients(batch_id) if db else []
        counts = db.batch_count_by_status(batch_id) if db else {}
        return jsonify({"success": True, "batch": batch, "recipients": recipients, "counts": counts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<batch_id>/run', methods=['POST'])
def api_batch_run(batch_id):
    try:
        db = get_db()
        db.batch_update_status(batch_id, 'running')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<batch_id>/pause', methods=['POST'])
def api_batch_pause(batch_id):
    try:
        db = get_db()
        db.batch_update_status(batch_id, 'paused')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<batch_id>', methods=['DELETE'])
def api_batch_delete(batch_id):
    try:
        db = get_db()
        db.batch_delete(batch_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# POOL
# ═══════════════════════════════════════════════
@app.route('/api/pool/<sequence_id>')
def api_pool(sequence_id):
    try:
        db = get_db()
        eng = get_engine()
        count = eng.get_pool_count(sequence_id) if eng else 0
        total = db.recipient_count(sequence_id) if db else 0
        return jsonify({"success": True, "unbatched": count, "total": total})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════
@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json or {}
        message = data.get('message', '')
        br = get_brain()
        if not br:
            return jsonify({"response": "Raj is initializing..."})
        result = br.process(message)
        return jsonify({"response": result.get("response", "I processed your request, sir."), "action": result.get("action"), "result": result.get("result")})
    except Exception as e:
        import traceback
        print(f"[ERROR] Chat: {e}")
        print(traceback.format_exc())
        return jsonify({"response": f"Error: {str(e)[:100]}"})

# ═══════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════
@app.route('/api/templates')
def api_templates():
    try:
        db = get_db()
        result = {}
        for seq_id in ["school", "csr"]:
            result[seq_id] = {}
            for day in [1, 3, 5, 7, 10]:
                tmpl = db.template_get(seq_id, day) if db else None
                if tmpl:
                    result[seq_id][day] = {"sequence_id": seq_id, "day": day, "subject": tmpl.get("subject", ""), "locked": bool(tmpl.get("locked")), "source": tmpl.get("source", "unknown"), "has_body": bool(tmpl.get("html_body"))}
        return jsonify({"success": True, "templates": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/<seq_id>/<int:day>')
def api_template_get(seq_id, day):
    try:
        db = get_db()
        tmpl = db.template_get(seq_id, day) if db else None
        return jsonify({"success": True, "template": tmpl})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/sync', methods=['POST'])
def api_templates_sync():
    try:
        eng = get_engine()
        if not eng or not hasattr(eng, 'sync_templates'):
            return jsonify({"success": False, "error": "Gmail not connected"})
        result = eng.sync_templates()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/<seq_id>/<int:day>/lock', methods=['GET', 'POST'])
def api_template_lock(seq_id, day):
    try:
        db = get_db()
        db.template_lock(seq_id, day)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# IMPORT
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
        eng = get_engine()
        if eng and hasattr(eng, 'smart_import'):
            result = eng.smart_import(str(filepath), sequence_id)
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": "Engine not ready"})
    except Exception as e:
        import traceback
        print(f"[ERROR] Import: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# BLACKLIST
# ═══════════════════════════════════════════════
@app.route('/api/blacklist')
def api_blacklist():
    try:
        db = get_db()
        entries = db.blacklist_get_all() if db else []
        return jsonify({"success": True, "blacklist": entries})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/blacklist', methods=['POST'])
def api_blacklist_add():
    try:
        db = get_db()
        data = request.json or {}
        email = data.get('email', '')
        if email:
            db.blacklist_add(email, data.get('reason', 'manual'))
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "No email provided"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# REPLIES
# ═══════════════════════════════════════════════
@app.route('/api/replies')
def api_replies():
    try:
        db = get_db()
        if not db:
            return jsonify({"success": True, "replies": []})
        rows = db.execute("SELECT * FROM replies ORDER BY received_at DESC LIMIT 100").fetchall()
        return jsonify({"success": True, "replies": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# ENGINE CONTROL
# ═══════════════════════════════════════════════
@app.route('/api/engine/status')
def api_engine_status():
    try:
        eng = get_engine()
        return jsonify({"running": eng.is_running() if eng else False, "paused": eng.is_paused() if eng else False})
    except:
        return jsonify({"running": False, "paused": False})

@app.route('/api/engine/<action>', methods=['POST'])
def api_engine_action(action):
    try:
        eng = get_engine()
        if not eng:
            return jsonify({"success": False, "error": "Engine not initialized"}), 500
        if action == 'start' and hasattr(eng, 'start'):
            eng.start()
        elif action == 'stop' and hasattr(eng, 'stop'):
            eng.stop()
        elif action == 'pause' and hasattr(eng, 'pause'):
            eng.pause()
        elif action == 'resume' and hasattr(eng, 'resume'):
            eng.resume()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════
@app.route('/api/settings')
def api_settings():
    try:
        db = get_db()
        settings = {
            "brief_email": db.get_meta("brief_email") or "itsomkarsinghhh@gmail.com" if db else "",
            "send_rate": db.get_meta("send_rate") or "45" if db else "45",
            "stagger_minutes": db.get_meta("stagger_minutes") or "2" if db else "2",
            "morning_hour": db.get_meta("morning_hour") or "8" if db else "8",
            "eod_hour": db.get_meta("eod_hour") or "19" if db else "19",
            "auto_advance": (db.get_meta("auto_advance") or "true") != "false" if db else True,
            "sunday_filter": (db.get_meta("sunday_filter") or "true") != "false" if db else True,
        }
        eng = get_engine()
        gmail_status = False
        try:
            gmail_status = eng.gmail is not None and hasattr(eng.gmail, 'is_authenticated') and eng.gmail.is_authenticated()
        except:
            pass
        return jsonify({"success": True, "settings": settings, "engine": {"running": eng.is_running() if eng else False, "paused": eng.is_paused() if eng else False}, "gmail": {"connected": gmail_status, "connect_url": "/connect-gmail"}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def api_settings_save():
    try:
        db = get_db()
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
# INIT
# ═══════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
