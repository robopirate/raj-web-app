"""
simple_migrate.py -- Direct CSV to PostgreSQL migration
No fancy logic. Just read CSV, insert rows, show results.
"""

import os
import csv
import json
from db import Database

def migrate_recipients():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'recipients.csv')

    if not os.path.exists(path):
        print(f"[MIGRATE] ERROR: {path} not found!")
        return 0

    count = 0
    errors = []

    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                email = str(row.get('email', '')).strip().lower()
                if not email or '@' not in email:
                    continue

                seq = str(row.get('sequence_id', 'school')).strip().lower()
                name = str(row.get('name', '')).strip()
                org = str(row.get('org', '')).strip()
                extra = str(row.get('extra_json', '{}')).strip()

                # Simple INSERT with conflict handling
                db.execute("""
                    INSERT INTO recipients (sequence_id, email, name, org, extra_json, import_status, batched)
                    VALUES (%s, %s, %s, %s, %s, 'success', 0)
                    ON CONFLICT(sequence_id, email) DO UPDATE SET
                        name=EXCLUDED.name, org=EXCLUDED.org, extra_json=EXCLUDED.extra_json,
                        import_status='success', batched=0
                """, (seq, email, name, org, extra))
                count += 1

                # Commit every 100 rows to avoid memory issues
                if count % 100 == 0:
                    db.commit()
                    print(f"[MIGRATE] Imported {count} recipients...")

            except Exception as e:
                errors.append(f"Row {count+1}: {e}")
                if len(errors) <= 5:
                    print(f"[MIGRATE] Error on row {count+1}: {e}")

    db.commit()
    print(f"[MIGRATE] DONE: {count} recipients imported")
    if errors:
        print(f"[MIGRATE] {len(errors)} errors total")
    return count

def migrate_batches():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'batches.csv')

    if not os.path.exists(path):
        print(f"[MIGRATE] batches.csv not found, skipping")
        return 0

    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                name = str(row.get('name', '')).strip()
                seq = str(row.get('sequence_id', 'school')).strip().lower()
                status = str(row.get('status', 'draft')).strip()
                scheduled = row.get('scheduled_at', None)
                day = int(row.get('day_offset', 1)) if row.get('day_offset') else 1
                parent = int(row.get('parent_batch_id')) if row.get('parent_batch_id') else None

                db.execute("""
                    INSERT INTO batches (name, sequence_id, status, scheduled_at, day_offset, parent_batch_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (name, seq, status, scheduled, day, parent))
                count += 1
            except Exception as e:
                print(f"[MIGRATE] Batch error: {e}")

    db.commit()
    print(f"[MIGRATE] {count} batches imported")
    return count

def migrate_batch_recipients():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'batch_recipients.csv')

    if not os.path.exists(path):
        print(f"[MIGRATE] batch_recipients.csv not found, skipping")
        return 0

    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                bid = int(row.get('batch_id', 0))
                rid = int(row.get('recipient_id', 0))
                status = str(row.get('status', 'pending')).strip()

                if bid and rid:
                    db.execute("""
                        INSERT INTO batch_recipients (batch_id, recipient_id, status)
                        VALUES (%s, %s, %s)
                        ON CONFLICT(batch_id, recipient_id) DO UPDATE SET status=EXCLUDED.status
                    """, (bid, rid, status))
                    count += 1
            except Exception as e:
                pass

    db.commit()
    print(f"[MIGRATE] {count} batch_recipient links imported")
    return count

def migrate_blacklist():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'blacklist.csv')

    if not os.path.exists(path):
        return 0

    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                email = str(row.get('email', '')).strip().lower()
                reason = str(row.get('reason', 'imported')).strip()
                if email and '@' in email:
                    db.execute("""
                        INSERT INTO blacklist (email, reason, source)
                        VALUES (%s, %s, 'import')
                        ON CONFLICT(email) DO UPDATE SET reason=EXCLUDED.reason
                    """, (email, reason))
                    count += 1
            except:
                pass

    db.commit()
    print(f"[MIGRATE] {count} blacklist entries imported")
    return count

def migrate_templates():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'templates.csv')

    if not os.path.exists(path):
        return 0

    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                seq = str(row.get('sequence_id', 'school')).strip().lower()
                day = int(row.get('day', 1)) if row.get('day') else 1
                subject = str(row.get('subject', '')).strip()
                body = str(row.get('html_body', '')).strip()
                locked = int(row.get('locked', 0)) if row.get('locked') else 0

                db.execute("""
                    INSERT INTO templates (sequence_id, day, subject, html_body, source, locked)
                    VALUES (%s, %s, %s, %s, 'imported', %s)
                    ON CONFLICT(sequence_id, day) DO UPDATE SET
                        subject=EXCLUDED.subject, html_body=EXCLUDED.html_body, locked=EXCLUDED.locked
                """, (seq, day, subject, body, locked))
                count += 1
            except:
                pass

    db.commit()
    print(f"[MIGRATE] {count} templates imported")
    return count

def migrate_sends():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'sends.csv')

    if not os.path.exists(path):
        return 0

    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rid = int(row.get('recipient_id')) if row.get('recipient_id') else None
                bid = int(row.get('batch_id')) if row.get('batch_id') else None
                day = int(row.get('day', 1)) if row.get('day') else 1
                subject = str(row.get('subject', '')).strip()
                status = str(row.get('status', 'sent')).strip()
                sent_at = row.get('sent_at', None)

                if rid:
                    db.execute("""
                        INSERT INTO sends (recipient_id, batch_id, day, subject, status, sent_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (rid, bid, day, subject, status, sent_at))
                    count += 1
            except:
                pass

    db.commit()
    print(f"[MIGRATE] {count} sends imported")
    return count

def migrate_replies():
    db = Database()
    base_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_path, 'replies.csv')

    if not os.path.exists(path):
        return 0

    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                thread_id = str(row.get('thread_id', '')).strip()
                msg_id = str(row.get('message_id', '')).strip()
                from_addr = str(row.get('from_addr', '')).strip()
                subject = str(row.get('subject', '')).strip()
                body = str(row.get('body', '')).strip()
                status = str(row.get('status', 'pending')).strip()

                if msg_id:
                    db.execute("""
                        INSERT INTO replies (thread_id, message_id, from_addr, subject, body, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT(message_id) DO UPDATE SET status=EXCLUDED.status
                    """, (thread_id, msg_id, from_addr, subject, body, status))
                    count += 1
            except:
                pass

    db.commit()
    print(f"[MIGRATE] {count} replies imported")
    return count

def run_all():
    print("="*60)
    print("DESKTOP DATA MIGRATION")
    print("="*60)

    r = migrate_recipients()
    b = migrate_batches()
    br = migrate_batch_recipients()
    bl = migrate_blacklist()
    t = migrate_templates()
    s = migrate_sends()
    rp = migrate_replies()

    # Mark batched recipients
    db = Database()
    db.execute("""
        UPDATE recipients SET batched=1
        WHERE id IN (SELECT DISTINCT recipient_id FROM batch_recipients)
    """)
    db.commit()

    print("="*60)
    print("SUMMARY:")
    print(f"  Recipients:  {r}")
    print(f"  Batches:     {b}")
    print(f"  Batch Links: {br}")
    print(f"  Blacklist:   {bl}")
    print(f"  Templates:   {t}")
    print(f"  Sends:       {s}")
    print(f"  Replies:     {rp}")
    print("="*60)

    return {"recipients": r, "batches": b, "batch_recipients": br, "blacklist": bl, "templates": t, "sends": s, "replies": rp}

if __name__ == '__main__':
    run_all()
