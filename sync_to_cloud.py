"""
sync_to_cloud.py -- Direct SQLite to PostgreSQL sync for RoboPirate
Run this on your DESKTOP computer to sync all data to the cloud.

Requirements:
  pip install psycopg2-binary

Usage:
  python sync_to_cloud.py
"""

import os
import sys
import sqlite3
from pathlib import Path

# ─── CONFIG ───
# Path to your desktop SQLite database
SQLITE_PATH = Path(__file__).parent / "campaign_data.db"

# Render PostgreSQL URL (from your Render dashboard Environment tab)
# Copy this from: https://dashboard.render.com/web/srv-d8emvdurnols73afjbpg → Environment
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL not set!")
    print("   Copy your Render DATABASE_URL and set it as environment variable.")
    print("   Windows: set DATABASE_URL=postgres://...")
    print("   Or edit this file and paste it in the DATABASE_URL variable above.")
    sys.exit(1)

if not SQLITE_PATH.exists():
    print(f"❌ ERROR: SQLite database not found at {SQLITE_PATH}")
    print("   Make sure this script is in the same folder as campaign_data.db")
    sys.exit(1)

import psycopg2
from psycopg2.extras import execute_values

def sync_table(sqlite_cur, pg_conn, table_name, columns, pk_columns=None):
    """Sync one table from SQLite to PostgreSQL."""
    print(f"\n[SYNC] {table_name}...")

    # Read from SQLite
    sqlite_cur.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
    rows = sqlite_cur.fetchall()

    if not rows:
        print(f"  → No data in {table_name}")
        return 0

    # Build INSERT with ON CONFLICT
    placeholders = ', '.join(['%s'] * len(columns))

    if pk_columns:
        # For tables with composite PK (recipients, batch_recipients, templates, blacklist)
        conflict_target = ', '.join(pk_columns)
        update_set = ', '.join([f"{col}=EXCLUDED.{col}" for col in columns if col not in pk_columns])
        sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES %s
            ON CONFLICT ({conflict_target}) DO UPDATE SET {update_set}
        """
    else:
        # For tables with auto-increment PK (batches, sends, replies)
        # Just insert, skip duplicates by checking all columns
        sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES %s
            ON CONFLICT DO NOTHING
        """

    pg_cur = pg_conn.cursor()

    # Insert in batches of 100
    batch_size = 100
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        try:
            execute_values(pg_cur, sql, batch)
            pg_conn.commit()
            inserted += len(batch)
            if inserted % 500 == 0:
                print(f"  → Imported {inserted}/{len(rows)}...")
        except Exception as e:
            print(f"  ⚠️ Batch error: {e}")
            pg_conn.rollback()

    pg_cur.close()
    print(f"  ✅ {table_name}: {inserted}/{len(rows)} rows synced")
    return inserted

def main():
    print("="*60)
    print("ROBOPIRATE DESKTOP → CLOUD SYNC")
    print("="*60)
    print(f"SQLite: {SQLITE_PATH}")
    print(f"PostgreSQL: {DATABASE_URL[:50]}...")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(DATABASE_URL)

    total_synced = 0

    try:
        # 1. Recipients
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'recipients',
            ['sequence_id', 'email', 'name', 'org', 'extra_json', 'import_status', 'import_error', 'imported_at', 'batched'],
            pk_columns=['sequence_id', 'email']
        )

        # 2. Batches
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'batches',
            ['name', 'sequence_id', 'status', 'scheduled_at', 'timezone', 'send_rate', 'stagger_minutes', 'day_offset', 'parent_batch_id', 'campaign_id', 'created_at', 'started_at', 'completed_at']
        )

        # 3. Batch Recipients
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'batch_recipients',
            ['batch_id', 'recipient_id', 'status', 'sent_at', 'opened_at', 'replied_at', 'bounced_at'],
            pk_columns=['batch_id', 'recipient_id']
        )

        # 4. Sends
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'sends',
            ['recipient_id', 'batch_id', 'day', 'subject', 'draft_id', 'status', 'created_at', 'sent_at', 'opened_at', 'clicked_at']
        )

        # 5. Blacklist
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'blacklist',
            ['email', 'reason', 'source', 'added_by', 'added_at'],
            pk_columns=['email']
        )

        # 6. Templates
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'templates',
            ['sequence_id', 'day', 'subject', 'html_body', 'source', 'locked', 'cached_at'],
            pk_columns=['sequence_id', 'day']
        )

        # 7. Replies
        total_synced += sync_table(
            sqlite_cur, pg_conn, 'replies',
            ['send_id', 'thread_id', 'message_id', 'from_addr', 'subject', 'body', 'sentiment', 'summary', 'draft_reply_id', 'status', 'received_at', 'created_at'],
            pk_columns=['message_id']
        )

        # Mark batched recipients
        pg_cur = pg_conn.cursor()
        pg_cur.execute("""
            UPDATE recipients SET batched=1
            WHERE id IN (SELECT DISTINCT recipient_id FROM batch_recipients)
        """)
        pg_conn.commit()
        pg_cur.close()

        print("\n" + "="*60)
        print(f"SYNC COMPLETE: {total_synced} total rows synced")
        print("="*60)
        print("\n✅ Your desktop data is now in the cloud!")
        print("   Go to https://raj-web-app.onrender.com to see it.")

    except Exception as e:
        print(f"\n❌ SYNC FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == '__main__':
    main()
