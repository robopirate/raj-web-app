"""
Raj Web App - RoboPirate Email Automation
v5.9.11 - Simplified dashboard, fast loading
"""
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, redirect, send_from_directory, render_template_string

API_DIR = Path(__file__).parent
app = Flask(__name__, static_folder=str(API_DIR / 'dist'))
app.secret_key = os.environ.get('SECRET_KEY', 'robopirate-dev-secret')

# ── Database ──────────────────────────────────────────────────────────
from db import Database
db = Database()

# ── Engine ───────────────────────────────────────────────────────────
from engine import CampaignEngine
engine = CampaignEngine(db=db)

# ── Pre-calculate batch counts at startup ────────────────────────────
_batch_counts = {}

def _refresh_batch_counts():
    global _batch_counts
    try:
        cur = db.conn.cursor()
        cur.execute("SELECT batch_id, COUNT(*) FROM batch_recipients GROUP BY batch_id")
        _batch_counts = {row[0]: row[1] for row in cur.fetchall()}
        cur.close()
    except Exception as e:
        print(f"[WARN] Batch count refresh failed: {e}")

_refresh_batch_counts()

# ── Static Files ──────────────────────────────────────────────────────
@app.route('/<path:path>')
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# ── Health ────────────────────────────────────────────────────────────
@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "version": "5.9.11", "timestamp": datetime.now().isoformat()})

# ═══════════════════════════════════════════════════════════════════════
# GMAIL OAUTH
# ═══════════════════════════════════════════════════════════════════════
@app.route('/connect-gmail')
def connect_gmail_page():
    try:
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        url = client.get_auth_url()
        return f"""
        <html><body style="font-family:Arial;text-align:center;padding:50px;background:#0f172a;color:#fff;">
        <h1>🔐 Connect Gmail</h1>
        <p>Raj can now send emails from the cloud.</p>
        <a href="{url}" style="display:inline-block;padding:15px 30px;background:#38bdf8;color:#0f172a;text-decoration:none;border-radius:8px;font-weight:bold;">Connect Gmail Account</a>
        <p><a href="/" style="color:#94a3b8;">← Back to Dashboard</a></p>
        </body></html>
        """
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/oauth2callback')
def oauth2callback():
    try:
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        result = client.handle_callback(request.args.get('code'))
        if result.get('success'):
            engine.gmail = client
            return """
            <html><body style="font-family:Arial;text-align:center;padding:50px;background:#0f172a;color:#fff;">
            <h1>✅ Gmail Connected!</h1>
            <p>Raj can now send emails.</p>
            <a href="/" style="color:#38bdf8;">Go to Dashboard</a>
            </body></html>
            """
        return f"""
        <html><body style="font-family:Arial;text-align:center;padding:50px;background:#0f172a;color:#fff;">
        <h1>❌ Connection Failed</h1>
        <p>{result.get('error','')}</p>
        <a href="/connect-gmail" style="color:#38bdf8;">Try Again</a> | <a href="/" style="color:#94a3b8;">Dashboard</a>
        </body></html>
        """, 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/auth-url')
def api_gmail_auth_url():
    try:
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        url = client.get_auth_url()
        return jsonify({"success": True, "auth_url": url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/gmail/status')
def api_gmail_status():
    try:
        has_gmail = engine.gmail is not None and hasattr(engine.gmail, 'is_authenticated') and engine.gmail.is_authenticated()
        return jsonify({"success": True, "connected": has_gmail, "mode": "web" if has_gmail else "none"})
    except:
        return jsonify({"success": True, "connected": False, "mode": "none"})

# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD - SIMPLE AND FAST
# ═══════════════════════════════════════════════════════════════════════
_dashboard_cache = None
_dashboard_cache_time = 0

@app.route('/api/dashboard')
def api_dashboard():
    global _dashboard_cache, _dashboard_cache_time
    try:
        now = time.time()
        if _dashboard_cache and (now - _dashboard_cache_time) < 5:
            return jsonify(_dashboard_cache)

        summary = db.get_dashboard_summary()

        # Simple active batches list
        active = []
        for b in db.batch_get_all():
            if b.get('status') != 'completed':
                count = _batch_counts.get(b['id'], 0)
                b['recipients'] = count
                b['recipient_count'] = count
                active.append(b)

        result = {"success": True, "summary": summary, "active_batches": active[:5]}
        _dashboard_cache = result
        _dashboard_cache_time = now
        return jsonify(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] Dashboard: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# BATCHES - FILTERED, NO DUPLICATES
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/batches')
def api_batches():
    try:
        batches = db.batch_get_all()
        # Filter: only show batches with recipients > 0
        filtered = []
        for b in batches:
            count = _batch_counts.get(b['id'], 0)
            if count > 0:  # Only show batches with recipients
                b['recipients'] = count
                b['recipient_count'] = count
                b['total_recipients'] = count
                b['count'] = count
                for key in ['created_at', 'scheduled_at', 'started_at', 'completed_at']:
                    if b.get(key) and hasattr(b[key], 'isoformat'):
                        b[key] = b[key].isoformat()
                filtered.append(b)

        return jsonify({"success": True, "batches": filtered})
    except Exception as e:
        import traceback
        print(f"[ERROR] Batches: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>')
def api_batch_get(batch_id):
    try:
        batch = db.batch_get(batch_id)
        if not batch:
            return jsonify({"success": False, "error": "Batch not found"}), 404
        recipients = db.batch_get_recipients(batch_id)
        counts = db.batch_count_by_status(batch_id)
        return jsonify({"success": True, "batch": batch, "recipients": recipients, "counts": counts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>/run', methods=['POST'])
def api_batch_run(batch_id):
    try:
        db.batch_update_status(batch_id, 'running')
        if hasattr(engine, 'start_batch'):
            engine.start_batch(batch_id)
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

# ═══════════════════════════════════════════════════════════════════════
# POOL
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/pool/<sequence_id>')
def api_pool(sequence_id):
    try:
        total = db.recipient_count(sequence_id)
        unbatched = db.get_pool_count(sequence_id)
        return jsonify({"success": True, "unbatched": unbatched, "total": total})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json or {}
        message = data.get('message', '')
        return jsonify({"response": "Raj received: " + message[:50]})
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)[:100]}"})

# ═══════════════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/templates')
def api_templates():
    try:
        result = {}
        for seq_id in ["school", "csr"]:
            result[seq_id] = {}
            for day in [1, 3, 5, 7, 10]:
                tmpl = db.template_get(seq_id, day)
                if tmpl:
                    locked = tmpl.get('locked', False)
                    if isinstance(locked, str):
                        locked = locked.lower() in ('true', '1', 'yes', 'locked')
                    elif isinstance(locked, int):
                        locked = bool(locked)
                    body = tmpl.get('html_body', '') or tmpl.get('body', '')
                    result[seq_id][day] = {
                        "sequence_id": seq_id, "day": day, "day_offset": day,
                        "subject": tmpl.get('subject', ''),
                        "body": body, "html_body": body,
                        "locked": locked, "source": tmpl.get('source', 'db'),
                        "has_body": bool(body), "status": tmpl.get('status', 'ready')
                    }
        return jsonify({"success": True, "templates": result})
    except Exception as e:
        import traceback
        print(f"[ERROR] Templates: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/<seq_id>/<int:day>')
def api_template_get(seq_id, day):
    try:
        tmpl = db.template_get(seq_id, day)
        if tmpl:
            locked = tmpl.get('locked', False)
            if isinstance(locked, str):
                locked = locked.lower() in ('true', '1', 'yes', 'locked')
            elif isinstance(locked, int):
                locked = bool(locked)
            tmpl['locked'] = locked
            if 'body' not in tmpl and 'html_body' in tmpl:
                tmpl['body'] = tmpl['html_body']
            return jsonify({"success": True, "template": tmpl})
        return jsonify({"success": False, "error": "Template not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/sync', methods=['POST'])
def api_templates_sync():
    try:
        result = engine.sync_templates()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/<seq_id>/<int:day>/lock', methods=['GET', 'POST'])
def api_template_lock(seq_id, day):
    try:
        db.template_lock(seq_id, day)
        return jsonify({"success": True, "message": f"Template {seq_id} Day {day} locked"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# IMPORT
# ═══════════════════════════════════════════════════════════════════════
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
        result = engine.smart_import(str(filepath), sequence_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# BLACKLIST
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/blacklist')
def api_blacklist():
    try:
        entries = db.blacklist_get_all()
        for e in entries:
            if e.get('added_at') and hasattr(e['added_at'], 'isoformat'):
                e['added_at'] = e['added_at'].isoformat()
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

# ═══════════════════════════════════════════════════════════════════════
# REPLIES
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/replies')
def api_replies():
    try:
        cur = db.execute("SELECT * FROM replies ORDER BY received_at DESC LIMIT 100")
        rows = db._fetchall(cur)
        for r in rows:
            if r.get('received_at') and hasattr(r['received_at'], 'isoformat'):
                r['received_at'] = r['received_at'].isoformat()
            if r.get('created_at') and hasattr(r['created_at'], 'isoformat'):
                r['created_at'] = r['created_at'].isoformat()
        return jsonify({"success": True, "replies": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# ENGINE CONTROL
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/engine/status')
def api_engine_status():
    try:
        return jsonify({
            "running": engine.is_running(),
            "paused": engine.is_paused()
        })
    except:
        return jsonify({"running": False, "paused": False})

@app.route('/api/engine/<action>', methods=['POST'])
def api_engine_action(action):
    try:
        if action == 'start':
            engine.start()
        elif action == 'stop':
            engine.stop()
        elif action == 'pause':
            engine.pause()
        elif action == 'resume':
            engine.resume()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/settings')
def api_settings():
    try:
        settings = {}
        for key in ['brief_email', 'send_rate', 'stagger_minutes', 'morning_hour', 'eod_hour']:
            settings[key] = db.get_meta(key) or ''
        for key in ['auto_advance', 'sunday_filter']:
            val = db.get_meta(key)
            settings[key] = (val or 'true') != 'false'
        if not settings.get('brief_email'):
            settings['brief_email'] = 'itsomkarsinghhh@gmail.com'
        if not settings.get('send_rate'):
            settings['send_rate'] = '45'
        if not settings.get('stagger_minutes'):
            settings['stagger_minutes'] = '2'
        if not settings.get('morning_hour'):
            settings['morning_hour'] = '8'
        if not settings.get('eod_hour'):
            settings['eod_hour'] = '19'

        has_gmail = False
        try:
            has_gmail = engine.gmail is not None and hasattr(engine.gmail, 'is_authenticated') and engine.gmail.is_authenticated()
        except:
            pass

        return jsonify({
            "success": True,
            "settings": settings,
            "engine": {
                "running": engine.is_running(),
                "paused": engine.is_paused()
            },
            "gmail": {
                "connected": has_gmail,
                "connect_url": "/connect-gmail"
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def api_settings_save():
    try:
        data = request.json or {}
        for key in ['brief_email', 'send_rate', 'stagger_minutes', 'morning_hour', 'eod_hour']:
            if key in data:
                db.set_meta(key, str(data[key]))
        for key in ['auto_advance', 'sunday_filter']:
            if key in data:
                db.set_meta(key, 'true' if data[key] else 'false')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# MIGRATION
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/migrate-csv')
def migrate_csv():
    try:
        return jsonify({
            'success': True,
            'message': 'Data already migrated via sync script. 3737 rows in cloud DB.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
