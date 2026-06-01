"""
Raj Web App - Flask Backend v3.0
Fixed: SPA routing, Web OAuth, PostgreSQL support, CSV seeding
"""

import os
import sys
import re
import json
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, redirect, session
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
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'raj-secret-key-2026')
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
        print("[INIT] Gmail connected (desktop mode)")
    except Exception as e:
        print(f"[INIT] Gmail desktop not available: {e}")
        # Try web OAuth mode
        try:
            from gmail_web import GmailWebClient
            gmail = GmailWebClient(db)
            print("[INIT] Gmail web mode initialized")
        except Exception as e2:
            print(f"[INIT] Gmail web not available: {e2}")
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

# ─── Health Check (for Render) ───
@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "version": "3.0", "timestamp": datetime.now().isoformat()})

# ─── Gmail Web OAuth Callback ───
@app.route('/oauth2callback')
def oauth2callback():
    """Handle Gmail OAuth callback from Google."""
    try:
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        result = client.handle_callback(request.args.get('code'))
        if result.get('success'):
            # Re-initialize Gmail with new token
            global gmail, engine
            gmail = client
            engine = CampaignEngine(db, gmail)
            engine.start()
            return """
            <html><body style="font-family:Segoe UI;text-align:center;padding:50px;background:#0A1628;color:#fff;">
            <h1 style="color:#59ced9;">✅ Gmail Connected!</h1>
            <p>Raj can now send emails from the cloud.</p>
            <p><a href="/" style="color:#febe32;">Go to Dashboard</a></p>
            </body></html>
            """
        else:
            return f"""
            <html><body style="font-family:Segoe UI;text-align:center;padding:50px;background:#0A1628;color:#fff;">
            <h1 style="color:#ef4444;">❌ Connection Failed</h1>
            <p>{result.get('error', 'Unknown error')}</p>
            </body></html>
            """, 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/auth-url')
def api_gmail_auth_url():
    """Get Google OAuth URL for connecting Gmail."""
    try:
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
        has_gmail = gmail is not None
        is_web = hasattr(gmail, 'is_web') if gmail else False
        return jsonify({
            "success": True,
            "connected": has_gmail,
            "mode": "web" if is_web else "desktop" if has_gmail else "none",
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
        summary = engine.get_summary() if engine else {"sequences": {}, "global": {}}
        families = _get_batch_families()
        return jsonify({"success": True, "summary": summary, "families": families})
    except Exception as e:
        import traceback
        print(f"[ERROR] Dashboard: {e}")
        print(traceback.format_exc())
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
        if not family_name:
            family_name = name

        seq_id = b.get("sequence_id", "")
        day = b.get("day_offset", 1)
        status = b.get("status", "draft")
        batch_id = b.get("id")
        scheduled = b.get("scheduled_at", "")

        counts = db.batch_count_by_status(batch_id) if db else {}
        total = sum(counts.values())
        sent = counts.get("sent", 0)

        if family_name not in families_dict:
            families_dict[family_name] = {
                "name": family_name,
                "sequence_id": seq_id,
                "days": {}
            }

        families_dict[family_name]["days"][f"D{day}"] = {
            "batch_id": batch_id,
            "status": status,
            "sent": sent,
            "total": total,
            "scheduled": scheduled
        }

    return list(families_dict.values())

# ═══════════════════════════════════════════════
# BATCHES
# ═══════════════════════════════════════════════
@app.route('/api/batches')
def api_batches():
    try:
        batches = db.batch_get_all() if db else []
        return jsonify({"success": True, "batches": batches})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches', methods=['POST'])
def api_batch_create():
    try:
        data = request.json or {}
        name = data.get('name', '')
        sequence_id = data.get('sequence_id', 'school')
        batch_size = int(data.get('batch_size', 50))
        day_offset = int(data.get('day_offset', 1))
        scheduled_at = data.get('scheduled_at')

        if not name:
            return jsonify({"success": False, "error": "Name required"}), 400

        batch_id = db.batch_create(name, sequence_id, scheduled_at, day_offset=day_offset)
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

@app.route('/api/batches/<int:batch_id>/recipients')
def api_batch_recipients(batch_id):
    try:
        recipients = db.batch_get_recipients(batch_id) if db else []
        return jsonify({"success": True, "recipients": recipients})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/from-pool', methods=['POST'])
def api_batch_from_pool():
    try:
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

@app.route('/api/templates/<seq_id>/<int:day>/lock', methods=['POST'])
def api_template_lock(seq_id, day):
    try:
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
        return jsonify({"success": False, "error": "No email provided"}), 400
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
        return jsonify({"success": False, "error": "No email provided"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# REPLIES
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
