"""
migrate_batch_pipeline.py — Add existing batch to new pipeline system
Run this once after updating db.py with parent_batch_id column
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent / "campaign_data.db"

def migrate_existing_batch(batch_id=None, batch_name=None):
    """
    Add an existing completed Day 1 batch to the pipeline system.
    Creates Day 3, 5, 7, 10 follow-up batches linked to parent.

    Usage:
        python migrate_batch_pipeline.py

    Or in Raj chat:
        "migrate batch a to pipeline"
    """
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Find the batch
    if batch_id:
        batch = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    elif batch_name:
        batch = conn.execute("SELECT * FROM batches WHERE name=?", (batch_name,)).fetchone()
    else:
        # Find most recent completed batch
        batch = conn.execute(
            "SELECT * FROM batches WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()

    if not batch:
        print("❌ No batch found. Create or complete a batch first.")
        return

    batch = dict(batch)
    print(f"📦 Found batch: {batch['name']} (ID: {batch['id']})")
    print(f"   Sequence: {batch['sequence_id'].upper()}")
    print(f"   Day: {batch.get('day_offset', 1)}")
    print(f"   Status: {batch['status']}")

    # Set parent_batch_id to itself (it's the original)
    conn.execute("UPDATE batches SET parent_batch_id=? WHERE id=?", (batch['id'], batch['id']))
    conn.commit()
    print(f"✅ Set batch {batch['id']} as pipeline root")

    # Get recipients from this batch
    recipients = conn.execute("""
        SELECT r.id, r.email, r.name, r.org 
        FROM recipients r
        JOIN batch_recipients br ON r.id = br.recipient_id
        WHERE br.batch_id=? AND br.status='sent'
    """, (batch['id'],)).fetchall()

    if not recipients:
        print("⚠️ No sent recipients found in this batch")
        recipients = conn.execute("""
            SELECT r.id, r.email, r.name, r.org 
            FROM recipients r
            JOIN batch_recipients br ON r.id = br.recipient_id
            WHERE br.batch_id=?
        """, (batch['id'],)).fetchall()

    recipient_ids = [r['id'] for r in recipients]
    print(f"✅ Found {len(recipient_ids)} recipients to carry forward")

    # Define sequence days
    seq_days = {
        "school": [1, 3, 5, 7, 10],
        "csr": [1, 3, 5, 7, 10]
    }

    days = seq_days.get(batch['sequence_id'], [1, 3, 5, 7, 10])
    current_day = batch.get('day_offset', 1)

    try:
        current_idx = days.index(current_day)
    except ValueError:
        print(f"❌ Day {current_day} not in sequence {days}")
        return

    # Create follow-up batches for remaining days
    base_name = batch['name'].split("-D")[0] if "-D" in batch['name'] else batch['name']
    stagger = batch.get('stagger_minutes', 2)

    created = []
    for i in range(current_idx + 1, len(days)):
        next_day = days[i]
        next_name = f"{base_name}-D{next_day}"

        # Schedule each 2 days apart at 10 AM
        days_from_now = (i - current_idx) * 2
        scheduled = (datetime.now() + timedelta(days=days_from_now)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

        # Check if batch already exists
        existing = conn.execute("SELECT id FROM batches WHERE name=?", (next_name,)).fetchone()
        if existing:
            print(f"⏭️  Batch '{next_name}' already exists (ID: {existing['id']})")
            continue

        # Create batch
        cur = conn.execute("""
            INSERT INTO batches (name, sequence_id, status, scheduled_at, 
                               timezone, send_rate, stagger_minutes, day_offset, parent_batch_id)
            VALUES (?, ?, 'scheduled', ?, 'Asia/Kolkata', 1, ?, ?, ?)
        """, (next_name, batch['sequence_id'], scheduled.isoformat(), stagger, next_day, batch['id']))

        new_batch_id = cur.lastrowid

        # Copy recipients
        for rid in recipient_ids:
            conn.execute("INSERT OR IGNORE INTO batch_recipients (batch_id, recipient_id) VALUES (?, ?)",
                        (new_batch_id, rid))

        conn.commit()
        created.append({
            "id": new_batch_id,
            "name": next_name,
            "day": next_day,
            "scheduled": scheduled.strftime("%d %b %H:%M"),
            "recipients": len(recipient_ids)
        })
        print(f"✅ Created {next_name} for {scheduled.strftime('%d %b %H:%M')} ({len(recipient_ids)} recipients)")

    print("🎉 Pipeline migration complete!")
    print(f"   Root batch: {batch['name']} (Day {current_day}) ✅ Done")
    for c in created:
        print(f"   → {c['name']} (Day {c['day']}) ⏳ {c['scheduled']}")

    conn.close()
    return created

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Batch name provided
        migrate_existing_batch(batch_name=sys.argv[1])
    else:
        # Auto-find most recent completed batch
        migrate_existing_batch()
