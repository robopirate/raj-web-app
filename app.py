"""
Raj Web App - RoboPirate Email Automation
Flask backend wrapping the engine and database
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from flask_cors import CORS
import os
import sys
import json
import threading
import time
from datetime import datetime, timedelta

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "raj-secret-key-2026")
CORS(app)

# --- Import existing modules (adapted for web) ---
# We'll create lightweight wrappers that work with web

# Database wrapper
import sqlite3
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "raj_web.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Batches table
    c.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sequence_id TEXT,
            status TEXT DEFAULT 'draft',
            scheduled_at TEXT,
            parent_batch_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Recipients table
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            email TEXT NOT NULL,
            name TEXT,
            org TEXT,
            status TEXT DEFAULT 'pending',
            sent_at TEXT,
            extra_json TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (batch_id) REFERENCES batches(id)
        )
    """)

    # Templates table
    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject TEXT,
            body TEXT,
            sequence_id TEXT,
            day_num INTEGER,
            locked INTEGER DEFAULT 0
        )
    """)

    # Blacklist table
    c.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            reason TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Meta table
    c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Activity log
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Initialized")

init_db()

# --- Database helpers ---

def db_query(sql, params=(), one=False):
    conn = get_db()
    c = conn.cursor()
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    if one:
        return rows[0] if rows else None
    return [dict(r) for r in rows]

def db_execute(sql, params=()):
    conn = get_db()
    c = conn.cursor()
    c.execute(sql, params)
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return last_id

# --- Engine state ---
engine_running = False
engine_thread = None

def log_activity(msg):
    db_execute("INSERT INTO activity_log (message) VALUES (?)", (msg,))
    print(f"[LOG] {msg}")

# --- Routes ---

@app.route("/")
def index():
    """Main dashboard"""
    return render_template("dashboard.html")

@app.route("/chat")
def chat():
    """Raj chat interface"""
    return render_template("chat.html")

# --- API: Dashboard ---

@app.route("/api/dashboard")
def api_dashboard():
    """Get dashboard summary data"""
    # Day-wise totals
    days = db_query("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status='bounced' THEN 1 ELSE 0 END) as bounced,
            SUM(CASE WHEN status='replied' THEN 1 ELSE 0 END) as replied
        FROM recipients
    """)[0]

    # Active batches grouped by family
    batches = db_query("SELECT * FROM batches ORDER BY created_at DESC")

    families = {}
    for b in batches:
        fam = extract_family_name(b["name"])
        if fam not in families:
            families[fam] = {"D1": None, "D3": None, "D5": None, "D7": None, "D10": None}
        day = extract_day_from_name(b["name"])
        if day in families[fam]:
            families[fam][day] = b

    # Add counts to each batch
    for fam_name, days_dict in families.items():
        for day_code, batch in days_dict.items():
            if batch:
                counts = db_query("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) as sent
                    FROM recipients WHERE batch_id = ?
                """, (batch["id"],))[0]
                batch["total"] = counts["total"] or 0
                batch["sent"] = counts["sent"] or 0
                batch["due"] = batch["total"] - batch["sent"]

    return jsonify({
        "days": days,
        "families": families,
        "engine_running": engine_running
    })

# --- API: Batches ---

@app.route("/api/batches")
def api_batches():
    batches = db_query("SELECT * FROM batches ORDER BY created_at DESC")
    for b in batches:
        counts = db_query("""
            SELECT status, COUNT(*) as count FROM recipients WHERE batch_id = ? GROUP BY status
        """, (b["id"],))
        b["counts"] = {c["status"]: c["count"] for c in counts}
    return jsonify(batches)

@app.route("/api/batch/<int:batch_id>/start", methods=["POST"])
def api_batch_start(batch_id):
    db_execute("UPDATE batches SET status = 'running' WHERE id = ?", (batch_id,))
    log_activity(f"Batch {batch_id} started")
    return jsonify({"success": True, "status": "running"})

@app.route("/api/batch/<int:batch_id>/pause", methods=["POST"])
def api_batch_pause(batch_id):
    db_execute("UPDATE batches SET status = 'paused' WHERE id = ?", (batch_id,))
    log_activity(f"Batch {batch_id} paused")
    return jsonify({"success": True, "status": "paused"})

@app.route("/api/batch/<int:batch_id>/recipients")
def api_batch_recipients(batch_id):
    recs = db_query("SELECT * FROM recipients WHERE batch_id = ?", (batch_id,))
    return jsonify(recs)

# --- API: Templates ---

@app.route("/api/templates")
def api_templates():
    templates = db_query("SELECT * FROM templates ORDER BY sequence_id, day_num")
    return jsonify(templates)

# --- API: Blacklist ---

@app.route("/api/blacklist")
def api_blacklist():
    items = db_query("SELECT * FROM blacklist ORDER BY added_at DESC LIMIT 100")
    return jsonify(items)

# --- API: Activity Log ---

@app.route("/api/activity")
def api_activity():
    logs = db_query("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 50")
    return jsonify(logs)

# --- API: Import ---

@app.route("/api/import", methods=["POST"])
def api_import():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    sequence = request.form.get("sequence", "school")
    batch_size = int(request.form.get("batch_size", 50))

    # TODO: Parse Excel/CSV and create batches
    log_activity(f"Import requested: {file.filename} ({sequence}, batch_size={batch_size})")
    return jsonify({"success": True, "message": "Import processing..."})

# --- API: Bounce Scan ---

@app.route("/api/scan/bounces", methods=["POST"])
def api_scan_bounces():
    # TODO: Integrate with Gmail API for bounce scan
    log_activity("Bounce scan requested")
    return jsonify({"success": True, "message": "Bounce scan started"})

# --- API: Chat ---

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    message = data.get("message", "").lower()

    # Simple command parser (expand later)
    response = "I didn't understand that. Try: 'start batch', 'show dashboard', 'scan bounces', 'help'"

    if "start" in message and "batch" in message:
        response = "To start a batch, click the ▶ button on any Ready pill in the dashboard."
    elif "bounce" in message or "scan" in message:
        response = "Click the 'Scan' button in the top bar to run a bounce scan."
    elif "help" in message:
        response = "Commands: start batch, pause batch, scan bounces, show dashboard, create batch, import leads"
    elif "dashboard" in message or "status" in message:
        response = "Dashboard shows all active batches with Day 1/3/5/7/10 pipeline. Green = Done, Yellow = Ready, Grey = Queue."
    elif "import" in message or "upload" in message:
        response = "Go to the Import tab to upload Excel/CSV files with leads."
    elif "hello" in message or "hi" in message:
        response = "Hello! I'm Raj, your email automation assistant. How can I help?"

    return jsonify({"response": response})

# --- Helpers ---

def extract_family_name(name):
    """Extract family name from batch name"""
    if not name:
        return "Unknown"
    # Remove day suffixes
    name = re.sub(r'[-_]?D\d+.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[-_]?Day\s*\d+.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[-_]?B\d+.*$', '', name, flags=re.IGNORECASE)
    return name.strip() or "Unknown"

def extract_day_from_name(name):
    """Extract day code from batch name"""
    if not name:
        return "D1"
    match = re.search(r'[D-](\d+)', name, re.IGNORECASE)
    if match:
        day_num = int(match.group(1))
        day_map = {1: "D1", 3: "D3", 5: "D5", 7: "D7", 10: "D10"}
        return day_map.get(day_num, f"D{day_num}")
    return "D1"

# --- Engine runner (background thread) ---

def engine_loop():
    """Background engine that sends emails from running batches"""
    global engine_running
    while engine_running:
        try:
            # Find running batches
            running = db_query("SELECT * FROM batches WHERE status = 'running'")
            for batch in running:
                # Get next pending recipient
                pending = db_query(
                    "SELECT * FROM recipients WHERE batch_id = ? AND status = 'pending' LIMIT 1",
                    (batch["id"],)
                )
                if pending:
                    rec = pending[0]
                    # TODO: Send email via Gmail API
                    db_execute("UPDATE recipients SET status = 'sent', sent_at = ? WHERE id = ?",
                              (datetime.now().isoformat(), rec["id"]))
                    log_activity(f"Sent to {rec['email']} ({batch['name']})")
                    time.sleep(120)  # 2 min stagger
                else:
                    # All sent - mark completed
                    db_execute("UPDATE batches SET status = 'completed' WHERE id = ?", (batch["id"],))
                    log_activity(f"Batch {batch['name']} completed")
            time.sleep(10)
        except Exception as e:
            log_activity(f"Engine error: {e}")
            time.sleep(30)

@app.route("/api/engine/start", methods=["POST"])
def api_engine_start():
    global engine_running, engine_thread
    if not engine_running:
        engine_running = True
        engine_thread = threading.Thread(target=engine_loop, daemon=True)
        engine_thread.start()
        log_activity("Engine started")
    return jsonify({"running": engine_running})

@app.route("/api/engine/stop", methods=["POST"])
def api_engine_stop():
    global engine_running
    engine_running = False
    log_activity("Engine stopped")
    return jsonify({"running": engine_running})

@app.route("/api/engine/status")
def api_engine_status():
    return jsonify({"running": engine_running})

# --- Run ---

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
