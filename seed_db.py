"""
seed_db.py -- Seed database from CSV files (desktop data migration)
Fixed: Imports ALL tables - recipients, batches, sends, blacklist, templates, replies, batch_recipients
Supports force re-import
"""

import os
import csv
from pathlib import Path
from db import Database

CSV_FILES = {
    'recipients': 'recipients.csv',
    'batches': 'batches.csv',
    'batch_recipients': 'batch_recipients.csv',
    'blacklist': 'blacklist.csv',
    'templates': 'templates.csv',
    'sends': 'sends.csv',
    'replies': 'replies.csv'
}

def seed_database(force=False):
    """Import CSV data into PostgreSQL database."""
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))

    # Check if we already have data
    count = db.recipient_count()
    if count > 0 and not force:
        print(f"[SEED] Database already has {count} recipients. Use force=True to re-import.")
        return

    if force and count > 0:
        print(f"[SEED] Force re-import requested. Clearing existing data...")
        # Clear existing data (keep structure)
        db.execute("DELETE FROM batch_recipients")
        db.execute("DELETE FROM sends")
        db.execute("DELETE FROM replies")
        db.execute("DELETE FROM batches")
        db.execute("DELETE FROM recipients")
        db.execute("DELETE FROM blacklist")
        db.execute("DELETE FROM templates")
        db.commit()
        print("[SEED] Existing data cleared.")

    # ─── Import Recipients ───
    recipients_path = os.path.join(base_path, CSV_FILES['recipients'])
    imported_recipients = 0
    if os.path.exists(recipients_path):
        try:
            with open(recipients_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        db.execute("""
                            INSERT INTO recipients (id, sequence_id, email, name, org, extra_json, import_status, batched)
                            VALUES (?, ?, ?, ?, ?, ?, 'success', 0)
                            ON CONFLICT(sequence_id, email) DO UPDATE SET
                                name=excluded.name, org=excluded.org, extra_json=excluded.extra_json,
                                import_status='success', import_error=NULL, batched=0
                        """, (
                            row.get('id'),
                            row.get('sequence_id', 'school'),
                            row.get('email', '').lower().strip(),
                            row.get('name', ''),
                            row.get('org', ''),
                            row.get('extra_json', '{}')
                        ))
                        imported_recipients += 1
                    except Exception as e:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_recipients} recipients from CSV")
        except Exception as e:
            print(f"[SEED] Error importing recipients: {e}")
    else:
        print(f"[SEED] No recipients.csv found")

    # ─── Import Batches ───
    batches_path = os.path.join(base_path, CSV_FILES['batches'])
    imported_batches = 0
    if os.path.exists(batches_path):
        try:
            with open(batches_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        db.execute("""
                            INSERT INTO batches (id, name, sequence_id, status, scheduled_at, timezone,
                                send_rate, stagger_minutes, day_offset, parent_batch_id, campaign_id,
                                created_at, started_at, completed_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                name=excluded.name, sequence_id=excluded.sequence_id,
                                status=excluded.status, scheduled_at=excluded.scheduled_at,
                                day_offset=excluded.day_offset, parent_batch_id=excluded.parent_batch_id
                        """, (
                            row.get('id'),
                            row.get('name', ''),
                            row.get('sequence_id', 'school'),
                            row.get('status', 'draft'),
                            row.get('scheduled_at'),
                            row.get('timezone', 'Asia/Kolkata'),
                            int(row.get('send_rate', 0)) if row.get('send_rate') else 0,
                            int(row.get('stagger_minutes', 0)) if row.get('stagger_minutes') else 0,
                            int(row.get('day_offset', 1)) if row.get('day_offset') else 1,
                            int(row.get('parent_batch_id')) if row.get('parent_batch_id') else None,
                            int(row.get('campaign_id')) if row.get('campaign_id') else None,
                            row.get('created_at'),
                            row.get('started_at'),
                            row.get('completed_at')
                        ))
                        imported_batches += 1
                    except Exception as e:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_batches} batches from CSV")
        except Exception as e:
            print(f"[SEED] Error importing batches: {e}")
    else:
        print(f"[SEED] No batches.csv found")

    # ─── Import Batch Recipients ───
    br_path = os.path.join(base_path, CSV_FILES['batch_recipients'])
    imported_br = 0
    if os.path.exists(br_path):
        try:
            with open(br_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        db.execute("""
                            INSERT INTO batch_recipients (batch_id, recipient_id, status, sent_at, opened_at, replied_at, bounced_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(batch_id, recipient_id) DO UPDATE SET
                                status=excluded.status, sent_at=excluded.sent_at
                        """, (
                            int(row.get('batch_id', 0)),
                            int(row.get('recipient_id', 0)),
                            row.get('status', 'pending'),
                            row.get('sent_at'),
                            row.get('opened_at'),
                            row.get('replied_at'),
                            row.get('bounced_at')
                        ))
                        imported_br += 1
                    except Exception as e:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_br} batch_recipient links from CSV")
        except Exception as e:
            print(f"[SEED] Error importing batch_recipients: {e}")
    else:
        print(f"[SEED] No batch_recipients.csv found")

    # ─── Import Blacklist ───
    bl_path = os.path.join(base_path, CSV_FILES['blacklist'])
    imported_bl = 0
    if os.path.exists(bl_path):
        try:
            with open(bl_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        email = row.get('email', '').strip().lower()
                        if email and '@' in email:
                            db.execute("""
                                INSERT INTO blacklist (id, email, reason, source, added_by, added_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT(email) DO UPDATE SET
                                    reason=excluded.reason, source=excluded.source
                            """, (
                                int(row.get('id')) if row.get('id') else None,
                                email,
                                row.get('reason', 'imported'),
                                row.get('source', 'import'),
                                row.get('added_by', 'system'),
                                row.get('added_at')
                            ))
                            imported_bl += 1
                    except:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_bl} blacklisted emails")
        except Exception as e:
            print(f"[SEED] Error importing blacklist: {e}")
    else:
        print(f"[SEED] No blacklist.csv found")

    # ─── Import Templates ───
    tmpl_path = os.path.join(base_path, CSV_FILES['templates'])
    imported_tmpl = 0
    if os.path.exists(tmpl_path):
        try:
            with open(tmpl_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        db.execute("""
                            INSERT INTO templates (sequence_id, day, subject, html_body, source, locked, cached_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(sequence_id, day) DO UPDATE SET
                                subject=excluded.subject, html_body=excluded.html_body,
                                source=excluded.source, locked=excluded.locked
                        """, (
                            row.get('sequence_id', 'school'),
                            int(row.get('day', 1)),
                            row.get('subject', ''),
                            row.get('html_body', ''),
                            row.get('source', 'imported'),
                            int(row.get('locked', 0)) if row.get('locked') else 0,
                            row.get('cached_at')
                        ))
                        imported_tmpl += 1
                    except:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_tmpl} templates")
        except Exception as e:
            print(f"[SEED] Error importing templates: {e}")
    else:
        print(f"[SEED] No templates.csv found")

    # ─── Import Sends ───
    sends_path = os.path.join(base_path, CSV_FILES['sends'])
    imported_sends = 0
    if os.path.exists(sends_path):
        try:
            with open(sends_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        db.execute("""
                            INSERT INTO sends (id, recipient_id, batch_id, day, subject, draft_id, status, created_at, sent_at, opened_at, clicked_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                status=excluded.status, sent_at=excluded.sent_at
                        """, (
                            int(row.get('id')) if row.get('id') else None,
                            int(row.get('recipient_id')) if row.get('recipient_id') else None,
                            int(row.get('batch_id')) if row.get('batch_id') else None,
                            int(row.get('day', 1)),
                            row.get('subject', ''),
                            row.get('draft_id', ''),
                            row.get('status', 'drafted'),
                            row.get('created_at'),
                            row.get('sent_at'),
                            row.get('opened_at'),
                            row.get('clicked_at')
                        ))
                        imported_sends += 1
                    except:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_sends} sends")
        except Exception as e:
            print(f"[SEED] Error importing sends: {e}")
    else:
        print(f"[SEED] No sends.csv found")

    # ─── Import Replies ───
    replies_path = os.path.join(base_path, CSV_FILES['replies'])
    imported_replies = 0
    if os.path.exists(replies_path):
        try:
            with open(replies_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        db.execute("""
                            INSERT INTO replies (id, send_id, thread_id, message_id, from_addr, subject, body,
                                sentiment, summary, draft_reply_id, status, received_at, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(message_id) DO UPDATE SET
                                status=excluded.status, body=excluded.body
                        """, (
                            int(row.get('id')) if row.get('id') else None,
                            int(row.get('send_id')) if row.get('send_id') else None,
                            row.get('thread_id', ''),
                            row.get('message_id', ''),
                            row.get('from_addr', ''),
                            row.get('subject', ''),
                            row.get('body', ''),
                            row.get('sentiment', ''),
                            row.get('summary', ''),
                            row.get('draft_reply_id', ''),
                            row.get('status', 'pending'),
                            row.get('received_at'),
                            row.get('created_at')
                        ))
                        imported_replies += 1
                    except:
                        pass
                db.commit()
            print(f"[SEED] Imported {imported_replies} replies")
        except Exception as e:
            print(f"[SEED] Error importing replies: {e}")
    else:
        print(f"[SEED] No replies.csv found")

    # ─── Mark batched recipients ───
    try:
        db.execute("""
            UPDATE recipients SET batched=1
            WHERE id IN (SELECT DISTINCT recipient_id FROM batch_recipients)
        """)
        db.commit()
        print("[SEED] Marked batched recipients")
    except Exception as e:
        print(f"[SEED] Error marking batched: {e}")

    print(f"[SEED] Done! Database now has {db.recipient_count()} recipients, {db.recipient_count('school')} school, {db.recipient_count('csr')} csr")
    print(f"[SEED] Batches: {len(db.batch_get_all())}, Blacklist: {len(db.blacklist_get_all())}, Templates: check /api/templates")

if __name__ == '__main__':
    import sys
    force = '--force' in sys.argv or '-f' in sys.argv
    seed_database(force=force)
