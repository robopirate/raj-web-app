"""
app.py -- Raj Web App v5.6.1
Fixed: Simplified connect-gmail page that ALWAYS shows the button
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

def get_db():
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                from db import Database
                _db_instance = Database()
    return _db_instance

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
                print("[App] Gmail auto-connected from stored token")
        except Exception as e:
            print(f"[App] Gmail auto-connect failed: {e}")
        engine.start()
    return engine

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
    return jsonify({"status": "ok", "version": "5.6.1", "timestamp": datetime.now().isoformat()})

# ═══════════════════════════════════════════════
# GMAIL WEB OAUTH
# ═══════════════════════════════════════════════

CONNECT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connect Gmail - Raj</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: #0f172a; 
            color: #e2e8f0; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh; 
            padding: 20px;
        }
        .card { 
            background: #1e293b; 
            border-radius: 16px; 
            padding: 40px; 
            max-width: 500px; 
            width: 100%; 
            box-shadow: 0 20px 60px rgba(0,0,0,0.4); 
            text-align: center; 
        }
        .logo { font-size: 48px; margin-bottom: 10px; }
        h1 { color: #38bdf8; margin-bottom: 8px; font-size: 26px; }
        .subtitle { color: #94a3b8; margin-bottom: 30px; font-size: 15px; }
        .status-box { 
            padding: 14px 20px; 
            border-radius: 10px; 
            margin-bottom: 25px; 
            font-weight: 600; 
            font-size: 15px;
        }
        .status-box.connected { background: #064e3b; color: #34d399; border: 1px solid #059669; }
        .status-box.disconnected { background: #450a0a; color: #f87171; border: 1px solid #dc2626; }
        .btn { 
            display: inline-block; 
            padding: 16px 40px; 
            border-radius: 10px; 
            text-decoration: none;
            font-weight: 700; 
            font-size: 16px; 
            cursor: pointer; 
            border: none; 
            transition: all 0.2s; 
            width: 100%;
        }
        .btn-primary { 
            background: #38bdf8; 
            color: #0f172a; 
        }
        .btn-primary:hover { 
            background: #7dd3fc; 
            transform: translateY(-2px); 
            box-shadow: 0 8px 25px rgba(56,189,248,0.3);
        }
        .btn-secondary { 
            background: #334155; 
            color: #e2e8f0; 
            margin-top: 12px; 
            font-size: 14px;
            padding: 12px 24px;
        }
        .btn-secondary:hover { background: #475569; }
        .info { 
            margin-top: 30px; 
            padding: 18px; 
            background: #0f172a; 
            border-radius: 10px; 
            font-size: 13px; 
            color: #64748b; 
            text-align: left; 
            line-height: 1.6;
        }
        .info strong { color: #94a3b8; }
        .info code { 
            color: #38bdf8; 
            background: #1e293b; 
            padding: 2px 6px; 
            border-radius: 4px; 
            font-family: monospace;
            font-size: 12px;
        }
        .spinner {
            width: 24px;
            height: 24px;
            border: 3px solid #334155;
            border-top-color: #38bdf8;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
            display: none;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .hidden { display: none !important; }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">🔐</div>
        <h1>Connect Gmail</h1>
        <p class="subtitle">Allow Raj to send emails from info@robopirate.in</p>

        <div class="spinner" id="spinner"></div>

        <div id="status-box" class="status-box disconnected">
            Checking Gmail status...
        </div>

        <div id="action-area">
            <button class="btn btn-primary" id="connect-btn" onclick="connectGmail()">
                Connect Gmail Account
            </button>
        </div>

        <a href="/" class="btn btn-secondary">← Back to Dashboard</a>

        <div class="info">
            <strong>How it works:</strong><br>
            1. Click the button above<br>
            2. Sign in with Google (info@robopirate.in)<br>
            3. Grant permission to send emails<br>
            4. Raj will handle the rest automatically<br><br>
            <strong>Redirect URI:</strong> <code>https://raj-web-app.onrender.com/oauth2callback</code>
        </div>
    </div>

    <script>
        async function checkStatus() {
            try {
                const res = await fetch('/api/gmail/status');
                const data = await res.json();
                const box = document.getElementById('status-box');
                const btn = document.getElementById('connect-btn');

                if (data.connected) {
                    box.className = 'status-box connected';
                    box.textContent = '✅ Gmail Connected & Ready';
                    btn.textContent = 'Gmail Already Connected';
                    btn.disabled = true;
                    btn.style.opacity = '0.6';
                    btn.style.cursor = 'default';
                } else {
                    box.className = 'status-box disconnected';
                    box.textContent = '❌ Gmail Not Connected';
                }
            } catch(e) {
                console.error('Status check failed:', e);
                document.getElementById('status-box').className = 'status-box disconnected';
                document.getElementById('status-box').textContent = '⚠️ Could not check status';
            }
        }

        async function connectGmail() {
            const spinner = document.getElementById('spinner');
            const btn = document.getElementById('connect-btn');

            spinner.style.display = 'block';
            btn.disabled = true;
            btn.textContent = 'Loading...';

            try {
                const res = await fetch('/api/gmail/auth-url');
                const data = await res.json();

                if (data.auth_url) {
                    window.location.href = data.auth_url;
                } else {
                    alert('Error: ' + (data.error || 'Could not get auth URL'));
                    spinner.style.display = 'none';
                    btn.disabled = false;
                    btn.textContent = 'Connect Gmail Account';
                }
            } catch(e) {
                alert('Failed to get auth URL. Check console.');
                console.error(e);
                spinner.style.display = 'none';
                btn.disabled = false;
                btn.textContent = 'Connect Gmail Account';
            }
        }

        // Check status on page load
        checkStatus();
    </script>
</body>
</html>
"""

@app.route('/connect-gmail')
def connect_gmail_page():
    return CONNECT_HTML

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
            return """
            <html><head><meta charset="utf-8"><title>Gmail Connected</title>
            <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#e2e8f0;}
            .success{color:#34d399;font-size:28px;margin-bottom:20px;}a{color:#38bdf8;font-size:18px;text-decoration:none;}
            .btn{display:inline-block;padding:14px 32px;background:#38bdf8;color:#0f172a;border-radius:8px;margin-top:20px;font-weight:600;}</style></head>
            <body><div class="success">✅ Gmail Connected!</div>
            <p>Raj can now send emails from the cloud.</p>
            <a href="/" class="btn">Go to Dashboard</a></body></html>
            """
        else:
            return f"""
            <html><head><meta charset="utf-8"><title>Connection Failed</title>
            <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#e2e8f0;}
            .error{color:#f87171;font-size:28px;margin-bottom:20px;}a{color:#38bdf8;}</style></head>
            <body><div class="error">❌ Connection Failed</div>
            <p>{result.get('error', 'Unknown error')}</p>
            <a href="/connect-gmail">Try Again</a> | <a href="/">Dashboard</a></body></html>
            """, 400
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
        eng = get_engine()
        summary = eng.get_summary() if eng else {"sequences": {}, "global": {}}
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
        family_name = re.sub(r'(?i)(-day\s*\d+|\s*day\s*\d+|\s*D\d+)$', '', family_name).strip()
        if family_name not in families_dict:
            families_dict[family_name] = {"family_name": family_name, "sequence_id": b.get("sequence_id", ""), "days": {}}
        day_match = re.search(r'(?i)(?:D|Day)\s*(\d+)', name)
        day = int(day_match.group(1)) if day_match else b.get("day_offset", 1)
        counts = db.batch_count_by_status(b["id"]) if db else {}
        total = sum(counts.values())
        sent = counts.get("sent", 0)
        families_dict[family_name]["days"][day] = {
            "batch_id": b["id"], "name": b["name"], "status": b.get("status", "draft"),
            "total": total, "sent": sent, "scheduled_at": b.get("scheduled_at"), "day_offset": day
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

@app.route('/api/batches/<batch_id>/recipients')
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
        eng = get_engine()
        if not eng or not hasattr(eng, 'create_batch_from_pool'):
            return jsonify({"success": False, "error": "Engine not ready"}), 500
        result = eng.create_batch_from_pool(name, sequence_id, batch_size, day_offset)
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
            return jsonify({"response": "Raj is initializing... Please wait a moment."})
        result = br.process(message)
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
        eng = get_engine()
        if not eng or not hasattr(eng, 'sync_templates'):
            return jsonify({"success": False, "error": "Gmail not connected"})
        result = eng.sync_templates()
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

@app.route('/api/replies/<reply_id>/handled', methods=['POST'])
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
        eng = get_engine()
        if not eng or not hasattr(eng, 'scan_replies'):
            return jsonify({"success": False, "error": "Engine not ready"})
        count = eng.scan_replies()
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# BOUNCE SCAN
# ═══════════════════════════════════════════════
@app.route('/api/scan-bounces', methods=['POST'])
def api_scan_bounces():
    try:
        eng = get_engine()
        if not eng or not hasattr(eng, 'scan_bounces'):
            return jsonify({"success": False, "error": "Engine not ready"})
        result = eng.scan_bounces()
        return jsonify({"success": True, **(result if isinstance(result, dict) else {"count": result})})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════
# ENGINE CONTROL
# ═══════════════════════════════════════════════
@app.route('/api/engine/status')
def api_engine_status():
    try:
        eng = get_engine()
        return jsonify({
            "running": eng.is_running() if eng else False,
            "paused": eng.is_paused() if eng else False,
        })
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
        return jsonify({
            "success": True,
            "settings": settings,
            "engine": {
                "running": eng.is_running() if eng else False,
                "paused": eng.is_paused() if eng else False,
            },
            "gmail": {
                "connected": gmail_status,
                "connect_url": "/connect-gmail"
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
# DATA MIGRATION
# ═══════════════════════════════════════════════
@app.route('/api/migrate-csv', methods=['GET', 'POST'])
def api_migrate_csv():
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from seed_db import seed_database
        seed_database(force=True)
        if request.method == 'GET':
            return """
            <html><head><meta charset="utf-8"><title>Migration Complete</title>
            <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#e2e8f0;}
            .success{color:#34d399;font-size:28px;margin-bottom:20px;}a{color:#38bdf8;font-size:18px;text-decoration:none;}
            .btn{display:inline-block;padding:14px 32px;background:#38bdf8;color:#0f172a;border-radius:8px;margin-top:20px;font-weight:600;}</style></head>
            <body><div class="success">✅ Desktop Data Migrated!</div>
            <p>All your CSV data has been imported into the cloud database.</p>
            <a href="/" class="btn">Go to Dashboard</a></body></html>
            """
        return jsonify({"success": True, "message": "CSV data re-imported"})
    except Exception as e:
        import traceback
        err_msg = str(e)
        print("[MIGRATE ERROR] " + err_msg)
        print(traceback.format_exc())
        if request.method == 'GET':
            html = "<html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#e2e8f0;'>"
            html += "<div style='color:#f87171;font-size:28px;margin-bottom:20px;'>❌ Migration Failed</div>"
            html += "<p>" + err_msg + "</p>"
            html += "<p><a href='/' style='color:#38bdf8;font-size:18px;'>Back to Dashboard</a></p>"
            html += "</body></html>"
            return html, 500
        return jsonify({"success": False, "error": err_msg}), 500

# ═══════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
