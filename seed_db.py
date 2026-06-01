"""
Seed database from CSV files on first run.
This ensures data persists across Render redeploys.
"""

import csv
import sqlite3
import json
from pathlib import Path
from datetime import datetime

API_DIR = Path(__file__).parent
DB_PATH = API_DIR / "campaign_data.db"
CSV_DIR = API_DIR / "csv_data"


def seed_database():
    """Import all CSV data into SQLite database."""
    if not CSV_DIR.exists():
        print("[SEED] No CSV data folder found. Skipping seed.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ─── Recipients ───
    recipients_file = CSV_DIR / "recipients.csv"
    if recipients_file.exists():
        with open(recipients_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO recipients 
                        (id, sequence_id, email, name, org, extra_json, import_status, import_error, imported_at, batched)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row['id']), row['sequence_id'], row['email'].lower().strip(),
                        row['name'], row['org'], row.get('extra_json', '{}'),
                        row.get('import_status', 'success'), row.get('import_error', None),
                        row.get('imported_at', datetime.now().isoformat()),
                        int(row.get('batched', 0))
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Recipient error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} recipients")

    # ─── Batches ───
    batches_file = CSV_DIR / "batches.csv"
    if batches_file.exists():
        with open(batches_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO batches 
                        (id, name, sequence_id, status, scheduled_at, timezone, 
                         send_rate, stagger_minutes, day_offset, created_at, 
                         started_at, completed_at, parent_batch_id, campaign_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row['id']), row['name'], row['sequence_id'], row['status'],
                        row.get('scheduled_at') or None, row.get('timezone', 'Asia/Kolkata'),
                        int(row.get('send_rate', 0)), int(row.get('stagger_minutes', 0)),
                        int(row.get('day_offset', 1)), row.get('created_at'),
                        row.get('started_at') or None, row.get('completed_at') or None,
                        int(row['parent_batch_id']) if row.get('parent_batch_id') else None,
                        int(row['campaign_id']) if row.get('campaign_id') else None
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Batch error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} batches")

    # ─── Batch Recipients ───
    br_file = CSV_DIR / "batch_recipients.csv"
    if br_file.exists():
        with open(br_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO batch_recipients 
                        (batch_id, recipient_id, status, sent_at, opened_at, replied_at, bounced_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row['batch_id']), int(row['recipient_id']), row.get('status', 'pending'),
                        row.get('sent_at') or None, row.get('opened_at') or None,
                        row.get('replied_at') or None, row.get('bounced_at') or None
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Batch recipient error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} batch_recipient links")

    # ─── Blacklist ───
    bl_file = CSV_DIR / "blacklist.csv"
    if bl_file.exists():
        with open(bl_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO blacklist 
                        (id, email, reason, source, added_by, added_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        int(row['id']), row['email'].lower().strip(), row.get('reason', 'imported'),
                        row.get('source', 'user'), row.get('added_by', 'user'), row.get('added_at')
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Blacklist error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} blacklist entries")

    # ─── Templates ───
    tmpl_file = CSV_DIR / "templates.csv"
    if tmpl_file.exists():
        with open(tmpl_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO templates 
                        (sequence_id, day, subject, html_body, source, locked, cached_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row['sequence_id'], int(row['day']), row['subject'], row['html_body'],
                        row.get('source', 'synced'), int(row.get('locked', 0)), row.get('cached_at')
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Template error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} templates")

    # ─── Sends ───
    sends_file = CSV_DIR / "sends.csv"
    if sends_file.exists():
        with open(sends_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO sends 
                        (id, recipient_id, batch_id, day, subject, draft_id, status, created_at, sent_at, opened_at, clicked_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row['id']), int(row['recipient_id']),
                        int(row['batch_id']) if row.get('batch_id') else None,
                        int(row['day']), row.get('subject', ''), row.get('draft_id', ''),
                        row.get('status', 'drafted'), row.get('created_at'),
                        row.get('sent_at') or None, row.get('opened_at') or None,
                        row.get('clicked_at') or None
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Send error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} sends")

    # ─── Replies ───
    replies_file = CSV_DIR / "replies.csv"
    if replies_file.exists():
        with open(replies_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO replies 
                        (id, send_id, thread_id, message_id, from_addr, subject, body, 
                         sentiment, summary, draft_reply_id, status, received_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row['id']), int(row['send_id']) if row.get('send_id') else None,
                        row['thread_id'], row['message_id'], row.get('from_addr', ''),
                        row.get('subject', ''), row.get('body', ''), row.get('sentiment', ''),
                        row.get('summary', ''), row.get('draft_reply_id') or None,
                        row.get('status', 'pending'), row.get('received_at'),
                        row.get('created_at')
                    ))
                    count += 1
                except Exception as e:
                    print(f"[SEED] Reply error: {e}")
            conn.commit()
            print(f"[SEED] Imported {count} replies")

    conn.close()
    print("[SEED] Database seeding complete!")
