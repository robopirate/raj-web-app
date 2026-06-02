"""
Raj Web App - RoboPirate Email Automation
v5.9.5 - Fixed batch recipient counts
"""
import os
import sys
import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, request, redirect, session, send_from_directory, render_template_string

# ── App Setup ─────────────────────────────────────────────────────────
API_DIR = Path(__file__).parent
app = Flask(__name__, static_folder=str(API_DIR / 'dist'))
app.secret_key = os.environ.get('SECRET_KEY', 'robopirate-dev-secret')

# ── Database ──────────────────────────────────────────────────────────
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL')
_db_conn = None

def get_db():
    global _db_conn
    if _db_conn is None and DATABASE_URL:
        _db_conn = psycopg2.connect(DATABASE_URL)
        _db_conn.autocommit = True
    return _db_conn

# ── Engine & Brain ────────────────────────────────────────────────────
_engine = None
_brain = None

def get_engine():
    global _engine
    if _engine is None:
        try:
            from engine import RajEngine
            db = get_db()
            _engine = RajEngine(db_conn=db)
            _engine.start()
        except Exception as e:
            print(f"[Engine] Init error: {e}")
    return _engine

def get_brain():
    global _brain
    if _brain is None:
        try:
            from raj_brain import RajBrain
            _brain = RajBrain()
        except Exception as e:
            print(f"[Brain] Init error: {e}")
    return _brain

# ── Static Files ────────────────────────────────────────────────────────
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
    return jsonify({"status": "ok", "version": "5.9.5", "timestamp": datetime.now().isoformat()})

# ═══════════════════════════════════════════════════════════════════════
# GMAIL OAUTH
# ═══════════════════════════════════════════════════════════════════════

@app.route('/connect-gmail')
def connect_gmail_page():
    try:
        db = get_db()
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
        db = get_db()
        from gmail_web import GmailWebClient
        client = GmailWebClient(db)
        result = client.handle_callback(request.args.get('code'))
        if result.get('success'):
            eng = get_engine()
            if eng:
                eng.gmail = client
            return """
            <html><body style="font-family:Arial;text-align:center;padding:50px;background:#0f172a;color:#fff;">
            <h1>✅ Gmail Connected!</h1>
            <p>Raj can now send emails.</p>
            <a href="/" style="color:#38bdf8;">Go to Dashboard</a>
            </body></html>
            """
        else:
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

# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/dashboard')
def api_dashboard():
    try:
        db = get_db()
        if not db:
            return jsonify({"success": False, "error": "DB not connected"}), 500

        cur = db.cursor()

        # Recipients by sequence
        cur.execute("SELECT sequence_id, COUNT(*) FROM recipients GROUP BY sequence_id")
        recipients_by_seq = {r[0]: r[1] for r in cur.fetchall()}

        # Per-sequence sends using JOIN
        cur.execute("""
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
        cur.execute("SELECT COUNT(*) FROM blacklist")
        bl_count = cur.fetchone()[0]

        # Active batches (non-completed) with recipient counts
        cur.execute("""
            SELECT b.id, b.name, b.sequence_id, b.day_offset, b.status,
                   b.created_at, b.scheduled_at, b.started_at,
                   COUNT(br.recipient_id) as recipient_count
            FROM batches b
            LEFT JOIN batch_recipients br ON b.id = br.batch_id
            WHERE b.status != 'completed'
            GROUP BY b.id
            ORDER BY b.created_at DESC
            LIMIT 5
        """)
        active = []
        for row in cur.fetchall():
            active.append({
                'id': row[0], 'name': row[1], 'sequence_id': row[2],
                'day_offset': row[3], 'status': row[4], 'created_at': row[5],
                'scheduled_at': row[6], 'started_at': row[7],
                'recipient_count': row[8] or 0
            })

        # Templates
        cur.execute("SELECT sequence_id, COUNT(*) FROM templates GROUP BY sequence_id")
        templates_by_seq = {r[0]: r[1] for r in cur.fetchall()}

        # Day-wise sends per sequence
        day_wise = {}
        for seq_id in ["school", "csr"]:
            cur.execute("""
                SELECT s.day_offset, COUNT(*)
                FROM sends s
                JOIN recipients r ON s.recipient_id = r.id
                WHERE r.sequence_id = %s AND s.status = 'sent'
                GROUP BY s.day_offset ORDER BY s.day_offset
            """, (seq_id,))
            day_wise[seq_id] = {r[0]: r[1] for r in cur.fetchall()}

        cur.close()

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
            "active_batches": len(active)
        }

        return jsonify({"success": True, "summary": summary, "active_batches": active})
    except Exception as e:
        import traceback
        print(f"[ERROR] Dashboard: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# BATCHES - FIXED WITH RECIPIENT COUNTS
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/batches')
def api_batches():
    try:
        db_conn = get_db()
        if not db_conn:
            return jsonify({"success": False, "error": "DB not connected"}), 500

        cur = db_conn.cursor()

        # Get all batches with recipient counts via JOIN
        cur.execute("""
            SELECT b.id, b.name, b.sequence_id, b.day_offset, b.status, 
                   b.created_at, b.scheduled_at, b.started_at, b.completed_at,
                   b.parent_batch_id, b.stagger_minutes, b.send_rate,
                   COUNT(br.recipient_id) as recipient_count
            FROM batches b
            LEFT JOIN batch_recipients br ON b.id = br.batch_id
            GROUP BY b.id
            ORDER BY b.created_at DESC
        """)

        batches = []
        for row in cur.fetchall():
            batches.append({
                'id': row[0],
                'name': row[1],
                'sequence_id': row[2],
                'day_offset': row[3],
                'status': row[4],
                'created_at': row[5].isoformat() if row[5] else None,
                'scheduled_at': row[6].isoformat() if row[6] else None,
                'started_at': row[7].isoformat() if row[7] else None,
                'completed_at': row[8].isoformat() if row[8] else None,
                'parent_batch_id': row[9],
                'stagger_minutes': row[10],
                'send_rate': row[11],
                'recipient_count': row[12] or 0  # <-- THE FIX
            })

        cur.close()
        return jsonify({"success": True, "batches": batches})
    except Exception as e:
        import traceback
        print(f"[ERROR] Batches: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>')
def api_batch_get(batch_id):
    try:
        db_conn = get_db()
        if not db_conn:
            return jsonify({"success": False, "error": "DB not connected"}), 500

        cur = db_conn.cursor()
        cur.execute("SELECT * FROM batches WHERE id = %s", (batch_id,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return jsonify({"success": False, "error": "Batch not found"}), 404

        # Get column names
        cols = [desc[0] for desc in cur.description]
        batch = dict(zip(cols, row))

        # Get recipients
        cur.execute("""
            SELECT r.id, r.email, r.name, r.org, r.import_status
            FROM recipients r
            JOIN batch_recipients br ON r.id = br.recipient_id
            WHERE br.batch_id = %s
            ORDER BY r.name
        """, (batch_id,))
        recipients = []
        for r in cur.fetchall():
            recipients.append({
                'id': r[0], 'email': r[1], 'name': r[2],
                'org': r[3], 'import_status': r[4]
            })

        # Get send counts by status
        cur.execute("""
            SELECT status, COUNT(*) FROM sends WHERE batch_id = %s GROUP BY status
        """, (batch_id,))
        counts = {r[0]: r[1] for r in cur.fetchall()}

        cur.close()
        return jsonify({"success": True, "batch": batch, "recipients": recipients, "counts": counts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>/run', methods=['POST'])
def api_batch_run(batch_id):
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("UPDATE batches SET status = 'running', started_at = NOW() WHERE id = %s", (batch_id,))
        db_conn.commit()
        cur.close()
        eng = get_engine()
        if eng and hasattr(eng, 'start_batch'):
            eng.start_batch(batch_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>/pause', methods=['POST'])
def api_batch_pause(batch_id):
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("UPDATE batches SET status = 'paused' WHERE id = %s", (batch_id,))
        db_conn.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/batches/<int:batch_id>', methods=['DELETE'])
def api_batch_delete(batch_id):
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("DELETE FROM batch_recipients WHERE batch_id = %s", (batch_id,))
        cur.execute("DELETE FROM batches WHERE id = %s", (batch_id,))
        db_conn.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# POOL
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/pool/<sequence_id>')
def api_pool(sequence_id):
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM recipients WHERE sequence_id = %s", (sequence_id,))
        total = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM recipients r
            WHERE r.sequence_id = %s AND r.id NOT IN (
                SELECT DISTINCT recipient_id FROM batch_recipients
            )
        """, (sequence_id,))
        unbatched = cur.fetchone()[0]
        cur.close()
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
        br = get_brain()
        if not br:
            return jsonify({"response": "Raj is initializing..."})
        result = br.process(message)
        return jsonify({
            "response": result.get("response", "I processed your request, sir."),
            "action": result.get("action"),
            "result": result.get("result")
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Chat: {e}")
        print(traceback.format_exc())
        return jsonify({"response": f"Error: {str(e)[:100]}"})

# ═══════════════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/templates')
def api_templates():
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        result = {}
        for seq_id in ["school", "csr"]:
            result[seq_id] = {}
            for day in [1, 3, 5, 7, 10]:
                cur.execute("""
                    SELECT id, sequence_id, day_offset, subject, body, status, locked
                    FROM templates WHERE sequence_id = %s AND day_offset = %s
                """, (seq_id, day))
                row = cur.fetchone()
                if row:
                    result[seq_id][day] = {
                        "sequence_id": row[1], "day": row[2],
                        "subject": row[3], "locked": bool(row[6]),
                        "source": "db", "has_body": bool(row[4])
                    }
        cur.close()
        return jsonify({"success": True, "templates": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/templates/<seq_id>/<int:day>')
def api_template_get(seq_id, day):
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("""
            SELECT id, sequence_id, day_offset, subject, body, status, locked
            FROM templates WHERE sequence_id = %s AND day_offset = %s
        """, (seq_id, day))
        row = cur.fetchone()
        cur.close()
        if row:
            tmpl = {
                "id": row[0], "sequence_id": row[1], "day_offset": row[2],
                "subject": row[3], "body": row[4], "status": row[5], "locked": bool(row[6])
            }
            return jsonify({"success": True, "template": tmpl})
        return jsonify({"success": False, "error": "Template not found"}), 404
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
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute(
            "UPDATE templates SET locked = true WHERE sequence_id = %s AND day_offset = %s",
            (seq_id, day)
        )
        db_conn.commit()
        cur.close()
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

# ═══════════════════════════════════════════════════════════════════════
# BLACKLIST
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/blacklist')
def api_blacklist():
    try:
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("SELECT email, reason, added_at FROM blacklist ORDER BY added_at DESC")
        entries = []
        for row in cur.fetchall():
            entries.append({'email': row[0], 'reason': row[1], 'added_at': row[2].isoformat() if row[2] else None})
        cur.close()
        return jsonify({"success": True, "blacklist": entries})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/blacklist', methods=['POST'])
def api_blacklist_add():
    try:
        db_conn = get_db()
        data = request.json or {}
        email = data.get('email', '')
        if email:
            cur = db_conn.cursor()
            cur.execute(
                "INSERT INTO blacklist (email, reason, added_at) VALUES (%s, %s, NOW()) ON CONFLICT (email) DO NOTHING",
                (email, data.get('reason', 'manual'))
            )
            db_conn.commit()
            cur.close()
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
        db_conn = get_db()
        cur = db_conn.cursor()
        cur.execute("""
            SELECT id, email, subject, received_at, category, status
            FROM replies ORDER BY received_at DESC LIMIT 100
        """)
        replies = []
        for row in cur.fetchall():
            replies.append({
                'id': row[0], 'email': row[1], 'subject': row[2],
                'received_at': row[3].isoformat() if row[3] else None,
                'category': row[4], 'status': row[5]
            })
        cur.close()
        return jsonify({"success": True, "replies": replies})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# ENGINE CONTROL
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/engine/status')
def api_engine_status():
    try:
        eng = get_engine()
        return jsonify({
            "running": eng.is_running() if eng else False,
            "paused": eng.is_paused() if eng else False
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

# ═══════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════
@app.route('/api/settings')
def api_settings():
    try:
        db_conn = get_db()
        cur = db_conn.cursor()

        settings = {}
        for key in ['brief_email', 'send_rate', 'stagger_minutes', 'morning_hour', 'eod_hour']:
            cur.execute("SELECT value FROM meta WHERE key = %s", (key,))
            row = cur.fetchone()
            settings[key] = row[0] if row else ''

        for key in ['auto_advance', 'sunday_filter']:
            cur.execute("SELECT value FROM meta WHERE key = %s", (key,))
            row = cur.fetchone()
            settings[key] = (row[0] if row else 'true') != 'false'

        # Defaults
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

        cur.close()

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
                "paused": eng.is_paused() if eng else False
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
        db_conn = get_db()
        data = request.json or {}
        cur = db_conn.cursor()

        for key in ['brief_email', 'send_rate', 'stagger_minutes', 'morning_hour', 'eod_hour']:
            if key in data:
                cur.execute("""
                    INSERT INTO meta (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, (key, str(data[key])))

        for key in ['auto_advance', 'sunday_filter']:
            if key in data:
                cur.execute("""
                    INSERT INTO meta (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, (key, 'true' if data[key] else 'false'))

        db_conn.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
