"""
app.py -- Raj Web App - Flask Backend v3.3
Fixed: Engine gets its own DB connection, auto-reconnect support
"""

import os
import re
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, session, g
from flask_cors import CORS

# ─── Flask Setup ───
app = Flask(__name__, static_folder='dist', static_url_path='')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'raj-web-secret-2026-robopirate')
CORS(app, supports_credentials=True)

API_DIR = Path(__file__).parent

# ─── Globals ───
engine = None
brain = None

# ─── Thread-safe DB access ───
def get_db():
    """Get thread-local database connection."""
    if not hasattr(g, 'db'):
        from db import Database
        g.db = Database()
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection at end of request."""
    if hasattr(g, 'db'):
        try:
            g.db.conn.close()
        except:
            pass

# ─── Init ───
def init_services():
    global engine, brain

    print("[INIT] Starting Raj Web App v3.3...")

    # Engine gets its own DB connection (separate from web requests)
    from engine import CampaignEngine
    from db import Database

    engine_db = Database()

    # Gmail (optional - web OAuth)
    gmail = None
    try:
        from gmail_web import GmailWebClient
        gmail = GmailWebClient(engine_db)
        # Check if token exists
        token_path = Path(__file__).parent / 'token.json'
        if token_path.exists():
            print("[INIT] Gmail Web OAuth connected")
        else:
            print("[INIT] Gmail Web OAuth not authenticated - connect via /api/gmail/auth-url")
            gmail = None
    except Exception as e:
        print(f"[INIT] Gmail Web not available: {e}")
        gmail = None

    engine = CampaignEngine(engine_db, gmail)
    engine.start()
    print("[INIT] Engine started")

    # Brain
    try:
        from raj_brain import RajBrain
        brain = RajBrain(engine_db, engine)
        print("[INIT] Raj brain initialized")
    except Exception as e:
        print(f"[INIT] Brain not available: {e}")
        brain = None

# ═══════════════════════════════════════════════
# STATIC / SPA
# ═══════════════════════════════════════════════
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ─── Health Check (for Render) ───
@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "version": "3.3", "timestamp": datetime.now().isoformat()})

# ═══════════════════════════════════════════════
# GMAIL WEB OAUTH
# ═══════════════════════════════════════════════
@app.route('/oauth2callback')
def oauth2callback():
    """Handle Gmail OAuth callback from Google."""
    try:
        db = get_db()
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        result = client.handle_callback(request.args.get('code'))
        if result.get('success'):
            global engine
            engine = CampaignEngine(db, client)
            engine.start()
            return """
            <html><body style="font-family:Arial;text-align:center;padding:50px">
            <h1 style="color:#22c55e">✅ Gmail Connected!</h1>
            <p>Raj can now send emails from the cloud.</p>
            <a href="/" style="display:inline-block;margin-top:20px;padding:12px 24px;background:#3b82f6;color:white;text-decoration:none;border-radius:6px">Go to Dashboard</a>
            </body></html>
            """
        else:
            return f"""
            <html><body style="font-family:Arial;text-align:center;padding:50px">
            <h1 style="color:#ef4444">❌ Connection Failed</h1>
            <p>{result.get('error', 'Unknown error')}</p>
            </body></html>
            """, 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/auth-url')
def api_gmail_auth_url():
    """Get Google OAuth URL for connecting Gmail."""
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
    """Check if Gmail is connected."""
    try:
        has_gmail = engine and hasattr(engine, 'gmail') and engine.gmail is not None
        return jsonify({
            "success": True,
            "connected": has_gmail,
            "mode": "web" if has_gmail else "none",
            "email": os.environ.get('GMAIL_USER', 'info@robopirate.in')
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════
@app.route('/api/dashboard')
def api_dashboard():
    try:
        db = get_db()
        summary = engine.get_summary() if engine else {"sequences": {}, "global": {}}
        families = _get_batch_families(db)
        return jsonify({"success": True, "summary": summary, "families": families})
    except Exception as e:
        import traceback
        print(f"[ERROR] Dashboard: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

def _get_batch_families(db):
    if not db:
        return []

    batches = db.batch_get_all()
    if not batches:
        return []

    families_dict = {}
    for b in batches:
        name = b.get("name", "")
        family_name = re.sub(r'[-_]D\d+$', '', name, flags=re.I)
        family_name = re.sub(r'(?i)(-day\s*\d+|\s*day\s*\d+|\s*d\d+)$', '', family_name).strip()

        if family_name not in families_dict:
            families_dict[family_name] = {
                "family_name": family_name,
                "sequence_id": b.get("sequence_id", ""),
                "days": {}
            }

        day_match = re.search(r'(?i)(?:D|Day)\s*(\d+)', name)
        day = int(day_match.group(1)) if day_match else b.get("day_offset", 1)

        counts = db.batch_count_by_status(b["id"]) if db else {}
        total = sum(counts.values())
        sent = counts.get("sent", 0)

        families_dict[family_name]["days"][day] = {
            "batch_id": b["id"],
            "name": b["name"],
            "status": b.get("status", "draft"),
            "total": total,
            "sent": sent,
            "scheduled_at": b.get("scheduled_at"),
            "day_offset": day
        }

    return list(families_dict.values())

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

@app.route('/api/batches/<int:batch_id>')
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

@app.route('/api/batches/<int:batch_id>/run', methods=['POST'])
def api_batch_run(batch_id):
    try:
        db = get_db()
        db.batch_update_status(batch_id, 'running')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>/pause', methods=['POST'])
def api_batch_pause(batch_id):
    try:
        db = get_db()
        db.batch_update_status(batch_id, 'paused')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>', methods=['DELETE'])
def api_batch_delete(batch_id):
    try:
        db = get_db()
        db.batch_delete(batch_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>/recipients')
def api_batch_recipients(batch_id):
    try:
        db = get_db()
        recipients = db.batch_get_recipients(batch_id) if db else []
        return jsonify({"success": True, "recipients": recipients})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/from-pool', methods=['POST'])
def api_batch_from_pool():
    try:
        db = get_db()
        data = request.json or {}
        name = data.get('name', '')
        sequence_id = data.get('sequence_id', 'school')
        batch_size = int(data.get('batch_size', 50))
        day_offset = int(data.get('day_offset', 1))

        if not engine or not hasattr(engine, 'create_batch_from_pool'):
            return jsonify({"success": False, "error": "Engine not ready"}), 500

        result = engine.create_batch_from_pool(name, sequence_id, batch_size, day_offset)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# POOL
# ═══════════════════════════════════════════════
@app.route('/api/pool/<sequence_id>')
def api_pool(sequence_id):
    try:
        db = get_db()
        count = engine.get_pool_count(sequence_id) if engine else 0
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
        if not brain:
            return jsonify({"response": "Raj is initializing... Please wait a moment."})
        result = brain.process(message)
        return jsonify({
            "response": result.get("response", "I processed your request, sir."),
            "action": result.get("action"),
            "result": result.get("result"),
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Chat: {e}")
        print(traceback.format_exc())
        return jsonify({"response": f"I'm having trouble right now. Error: {str(e)[:100]}"})

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
        db = get_db()
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

@app.route('/api/templates/<seq_id>/<int:day>/lock', methods=['POST'])
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

        if engine and hasattr(engine, 'smart_import'):
            result = engine.smart_import(str(filepath), sequence_id)
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

@app.route('/api/blacklist', methods=['DELETE'])
def api_blacklist_remove():
    try:
        db = get_db()
        data = request.json or {}
        email = data.get('email', '')
        if email:
            db.blacklist_remove(email)
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

@app.route('/api/replies/<int:reply_id>/handled', methods=['POST'])
def api_reply_handled(reply_id):
    try:
        db = get_db()
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
# BOUNCE SCAN
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
# ENGINE CONTROL
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
# DATA MIGRATION (one-time CSV import)
# ═══════════════════════════════════════════════
@app.route('/api/migrate-csv', methods=['POST'])
def api_migrate_csv():
    """Force re-import all CSV files into database."""
    try:
        from seed_db import seed_database
        seed_database()
        return jsonify({"success": True, "message": "CSV data re-imported"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════
if __name__ == '__main__':
    init_services()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    init_services()
