"""
migrate_data.py -- Bulletproof desktop data migration
Handles column name variations, missing files, PostgreSQL compatibility
"""

import os
import csv
import json
from pathlib import Path
from db import Database

def safe_int(val, default=None):
    try:
        return int(float(val)) if val and str(val).strip() else default
    except:
        return default

def safe_str(val, default=''):
    return str(val).strip() if val else default

def migrate_all():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))

    results = {
        "recipients": 0,
        "batches": 0,
        "batch_recipients": 0,
        "blacklist": 0,
        "templates": 0,
        "sends": 0,
        "replies": 0,
        "errors": []
    }

    # ─── 1. Recipients ───
    try:
        path = os.path.join(base_path, 'recipients.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        email = safe_str(row.get('email', row.get('Email', ''))).lower()
                        if not email or '@' not in email:
                            continue
                        seq = safe_str(row.get('sequence_id', row.get('Sequence', 'school'))).lower()
                        name = safe_str(row.get('name', row.get('Name', row.get('Contact_Name', ''))))
                        org = safe_str(row.get('org', row.get('Org', row.get('School', row.get('Organization', '')))))
                        extra = safe_str(row.get('extra_json', '{}'))

                        db.execute("""
                            INSERT INTO recipients (sequence_id, email, name, org, extra_json, import_status, batched)
                            VALUES (?, ?, ?, ?, ?, 'success', 0)
                            ON CONFLICT(sequence_id, email) DO UPDATE SET
                                name=excluded.name, org=excluded.org, extra_json=excluded.extra_json,
                                import_status='success', import_error=NULL, batched=0
                        """, (seq, email, name, org, extra))
                        results["recipients"] += 1
                    except Exception as e:
                        results["errors"].append(f"recipient: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['recipients']} recipients")
    except Exception as e:
        results["errors"].append(f"recipients file: {e}")
        print(f"[MIGRATE] Recipients error: {e}")

    # ─── 2. Batches ───
    try:
        path = os.path.join(base_path, 'batches.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        name = safe_str(row.get('name', row.get('Name', '')))
                        seq = safe_str(row.get('sequence_id', row.get('Sequence', 'school'))).lower()
                        status = safe_str(row.get('status', row.get('Status', 'draft')))
                        scheduled = safe_str(row.get('scheduled_at', row.get('Scheduled', None)))
                        day_offset = safe_int(row.get('day_offset', row.get('Day', 1)), 1)
                        parent_id = safe_int(row.get('parent_batch_id', row.get('Parent', None)))

                        db.execute("""
                            INSERT INTO batches (name, sequence_id, status, scheduled_at, day_offset, parent_batch_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (name, seq, status, scheduled, day_offset, parent_id))
                        results["batches"] += 1
                    except Exception as e:
                        results["errors"].append(f"batch: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['batches']} batches")
    except Exception as e:
        results["errors"].append(f"batches file: {e}")
        print(f"[MIGRATE] Batches error: {e}")

    # ─── 3. Batch Recipients ───
    try:
        path = os.path.join(base_path, 'batch_recipients.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        bid = safe_int(row.get('batch_id', row.get('Batch_ID', 0)))
                        rid = safe_int(row.get('recipient_id', row.get('Recipient_ID', 0)))
                        status = safe_str(row.get('status', row.get('Status', 'pending')))

                        if bid and rid:
                            db.execute("""
                                INSERT INTO batch_recipients (batch_id, recipient_id, status)
                                VALUES (?, ?, ?)
                                ON CONFLICT(batch_id, recipient_id) DO UPDATE SET
                                    status=excluded.status
                            """, (bid, rid, status))
                            results["batch_recipients"] += 1
                    except Exception as e:
                        results["errors"].append(f"batch_recipient: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['batch_recipients']} batch_recipient links")
    except Exception as e:
        results["errors"].append(f"batch_recipients file: {e}")
        print(f"[MIGRATE] Batch recipients error: {e}")

    # ─── 4. Blacklist ───
    try:
        path = os.path.join(base_path, 'blacklist.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        email = safe_str(row.get('email', row.get('Email', ''))).lower()
                        reason = safe_str(row.get('reason', row.get('Reason', 'imported')))
                        if email and '@' in email:
                            db.execute("""
                                INSERT INTO blacklist (email, reason, source)
                                VALUES (?, ?, 'import')
                                ON CONFLICT(email) DO UPDATE SET
                                    reason=excluded.reason, source='import'
                            """, (email, reason))
                            results["blacklist"] += 1
                    except Exception as e:
                        results["errors"].append(f"blacklist: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['blacklist']} blacklisted emails")
    except Exception as e:
        results["errors"].append(f"blacklist file: {e}")
        print(f"[MIGRATE] Blacklist error: {e}")

    # ─── 5. Templates ───
    try:
        path = os.path.join(base_path, 'templates.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        seq = safe_str(row.get('sequence_id', row.get('Sequence', 'school'))).lower()
                        day = safe_int(row.get('day', row.get('Day', 1)), 1)
                        subject = safe_str(row.get('subject', row.get('Subject', '')))
                        body = safe_str(row.get('html_body', row.get('Body', row.get('HTML', ''))))
                        locked = safe_int(row.get('locked', row.get('Locked', 0)), 0)

                        db.execute("""
                            INSERT INTO templates (sequence_id, day, subject, html_body, source, locked)
                            VALUES (?, ?, ?, ?, 'imported', ?)
                            ON CONFLICT(sequence_id, day) DO UPDATE SET
                                subject=excluded.subject, html_body=excluded.html_body,
                                source=excluded.source, locked=excluded.locked
                        """, (seq, day, subject, body, locked))
                        results["templates"] += 1
                    except Exception as e:
                        results["errors"].append(f"template: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['templates']} templates")
    except Exception as e:
        results["errors"].append(f"templates file: {e}")
        print(f"[MIGRATE] Templates error: {e}")

    # ─── 6. Sends (skip if no file or columns don't match) ───
    try:
        path = os.path.join(base_path, 'sends.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        rid = safe_int(row.get('recipient_id', row.get('Recipient_ID', None)))
                        bid = safe_int(row.get('batch_id', row.get('Batch_ID', None)))
                        day = safe_int(row.get('day', row.get('Day', 1)), 1)
                        subject = safe_str(row.get('subject', row.get('Subject', '')))
                        status = safe_str(row.get('status', row.get('Status', 'sent')))
                        sent_at = safe_str(row.get('sent_at', row.get('Sent_At', None)))

                        if rid:
                            db.execute("""
                                INSERT INTO sends (recipient_id, batch_id, day, subject, status, sent_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (rid, bid, day, subject, status, sent_at))
                            results["sends"] += 1
                    except Exception as e:
                        results["errors"].append(f"send: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['sends']} sends")
    except Exception as e:
        results["errors"].append(f"sends file: {e}")
        print(f"[MIGRATE] Sends error: {e}")

    # ─── 7. Replies ───
    try:
        path = os.path.join(base_path, 'replies.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        thread_id = safe_str(row.get('thread_id', row.get('Thread_ID', '')))
                        msg_id = safe_str(row.get('message_id', row.get('Message_ID', '')))
                        from_addr = safe_str(row.get('from_addr', row.get('From', '')))
                        subject = safe_str(row.get('subject', row.get('Subject', '')))
                        body = safe_str(row.get('body', row.get('Body', '')))
                        status = safe_str(row.get('status', row.get('Status', 'pending')))

                        if msg_id:
                            db.execute("""
                                INSERT INTO replies (thread_id, message_id, from_addr, subject, body, status)
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT(message_id) DO UPDATE SET
                                    status=excluded.status, body=excluded.body
                            """, (thread_id, msg_id, from_addr, subject, body, status))
                            results["replies"] += 1
                    except Exception as e:
                        results["errors"].append(f"reply: {e}")
                db.commit()
            print(f"[MIGRATE] Imported {results['replies']} replies")
    except Exception as e:
        results["errors"].append(f"replies file: {e}")
        print(f"[MIGRATE] Replies error: {e}")

    # ─── Mark batched recipients ───
    try:
        db.execute("""
            UPDATE recipients SET batched=1
            WHERE id IN (SELECT DISTINCT recipient_id FROM batch_recipients)
        """)
        db.commit()
        print("[MIGRATE] Marked batched recipients")
    except Exception as e:
        print(f"[MIGRATE] Error marking batched: {e}")

    # ─── Summary ───
    print("\n" + "="*50)
    print("MIGRATION COMPLETE")
    print("="*50)
    print(f"Recipients:     {results['recipients']}")
    print(f"Batches:        {results['batches']}")
    print(f"Batch links:    {results['batch_recipients']}")
    print(f"Blacklist:      {results['blacklist']}")
    print(f"Templates:      {results['templates']}")
    print(f"Sends:          {results['sends']}")
    print(f"Replies:        {results['replies']}")
    if results['errors']:
        print(f"\nErrors ({len(results['errors'])}):")
        for err in results['errors'][:5]:
            print(f"  - {err}")
    print("="*50)

    return results

if __name__ == '__main__':
    migrate_all()
