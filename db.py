"""
db.py -- RoboPirate Campaign Database v5.1
Dual database: SQLite (local) + PostgreSQL (Render cloud)
Auto-detects via DATABASE_URL environment variable.
"""

import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "campaign_data.db"

class Database:
    def __init__(self, db_path=None):
        self.db_url = os.environ.get('DATABASE_URL')
        self.is_postgres = bool(self.db_url)

        if self.is_postgres:
            import psycopg2
            self.conn = psycopg2.connect(self.db_url)
            print("[DB] Connected to PostgreSQL (cloud)")
        else:
            self.db_path = db_path or str(DB_PATH)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            print("[DB] Connected to SQLite (local)")

        self._init_tables()
        self._migrate_schema()

    def _placeholder(self):
        """Return placeholder character for current DB."""
        return '%s' if self.is_postgres else '?'

    def _execute(self, sql, params=()):
        """Execute SQL with auto-converted placeholders."""
        if self.is_postgres:
            # Convert ? to %s for PostgreSQL
            sql = sql.replace('?', '%s')
        return self.conn.execute(sql, params)

    def execute(self, sql, params=()):
        return self._execute(sql, params)

    def commit(self):
        self.conn.commit()

    def _init_tables(self):
        if self.is_postgres:
            self._init_postgres()
        else:
            self._init_sqlite()

    def _init_sqlite(self):
        self.conn.executescript("""
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                audience TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id TEXT,
                email TEXT NOT NULL,
                name TEXT,
                org TEXT,
                extra_json TEXT,
                import_status TEXT DEFAULT 'pending',
                import_error TEXT,
                imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
                batched INTEGER DEFAULT 0,
                UNIQUE(sequence_id, email)
            );
            CREATE INDEX IF NOT EXISTS idx_recipients_sequence ON recipients(sequence_id);
            CREATE INDEX IF NOT EXISTS idx_recipients_batched ON recipients(batched);

            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sequence_id TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                scheduled_at TEXT,
                timezone TEXT DEFAULT 'Asia/Kolkata',
                send_rate INTEGER DEFAULT 0,
                stagger_minutes INTEGER DEFAULT 0,
                day_offset INTEGER DEFAULT 1,
                parent_batch_id INTEGER,
                campaign_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS batch_recipients (
                batch_id INTEGER,
                recipient_id INTEGER,
                status TEXT DEFAULT 'pending',
                sent_at TEXT,
                opened_at TEXT,
                replied_at TEXT,
                bounced_at TEXT,
                PRIMARY KEY (batch_id, recipient_id)
            );

            CREATE TABLE IF NOT EXISTS templates (
                sequence_id TEXT,
                day INTEGER,
                subject TEXT,
                html_body TEXT,
                source TEXT DEFAULT 'unknown',
                locked INTEGER DEFAULT 0,
                cached_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (sequence_id, day)
            );

            CREATE TABLE IF NOT EXISTS sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER,
                batch_id INTEGER,
                day INTEGER,
                subject TEXT,
                draft_id TEXT,
                status TEXT DEFAULT 'drafted',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                sent_at TEXT,
                opened_at TEXT,
                clicked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sends_recipient ON sends(recipient_id);
            CREATE INDEX IF NOT EXISTS idx_sends_batch ON sends(batch_id);
            CREATE INDEX IF NOT EXISTS idx_sends_status ON sends(status);

            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                reason TEXT,
                source TEXT DEFAULT 'manual',
                added_by TEXT DEFAULT 'user',
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_blacklist_email ON blacklist(email);

            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                send_id INTEGER,
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                from_addr TEXT,
                subject TEXT,
                body TEXT,
                sentiment TEXT,
                summary TEXT,
                draft_reply_id TEXT,
                status TEXT DEFAULT 'pending',
                received_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_replies_status ON replies(status);

            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reply_id INTEGER,
                event_id TEXT,
                calendar_link TEXT,
                scheduled_at TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS drive_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT,
                file_id TEXT,
                file_name TEXT,
                file_url TEXT,
                validated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pending_resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id TEXT NOT NULL,
                day INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                subject TEXT,
                status TEXT DEFAULT 'pending',
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                resumed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS outreach_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sequence_id TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                total_leads INTEGER DEFAULT 0,
                auto_advance INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT,
                user TEXT DEFAULT 'system',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
        """)

        for seq_id, name, audience in [("school","SCHOOL","private_school"), ("csr","CSR","csr")]:
            self.execute("INSERT OR IGNORE INTO campaigns (id, name, audience) VALUES (?, ?, ?)", 
                        (seq_id, name, audience))
        self.conn.commit()

    def _init_postgres(self):
        cur = self.conn.cursor()

        # PostgreSQL schema (uses SERIAL instead of AUTOINCREMENT)
        tables = [
            """CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                audience TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS recipients (
                id SERIAL PRIMARY KEY,
                sequence_id TEXT,
                email TEXT NOT NULL,
                name TEXT,
                org TEXT,
                extra_json TEXT,
                import_status TEXT DEFAULT 'pending',
                import_error TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                batched INTEGER DEFAULT 0,
                UNIQUE(sequence_id, email)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_recipients_sequence ON recipients(sequence_id)""",
            """CREATE INDEX IF NOT EXISTS idx_recipients_batched ON recipients(batched)""",
            """CREATE TABLE IF NOT EXISTS batches (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                sequence_id TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                scheduled_at TIMESTAMP,
                timezone TEXT DEFAULT 'Asia/Kolkata',
                send_rate INTEGER DEFAULT 0,
                stagger_minutes INTEGER DEFAULT 0,
                day_offset INTEGER DEFAULT 1,
                parent_batch_id INTEGER,
                campaign_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS batch_recipients (
                batch_id INTEGER,
                recipient_id INTEGER,
                status TEXT DEFAULT 'pending',
                sent_at TIMESTAMP,
                opened_at TIMESTAMP,
                replied_at TIMESTAMP,
                bounced_at TIMESTAMP,
                PRIMARY KEY (batch_id, recipient_id)
            )""",
            """CREATE TABLE IF NOT EXISTS templates (
                sequence_id TEXT,
                day INTEGER,
                subject TEXT,
                html_body TEXT,
                source TEXT DEFAULT 'unknown',
                locked INTEGER DEFAULT 0,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (sequence_id, day)
            )""",
            """CREATE TABLE IF NOT EXISTS sends (
                id SERIAL PRIMARY KEY,
                recipient_id INTEGER,
                batch_id INTEGER,
                day INTEGER,
                subject TEXT,
                draft_id TEXT,
                status TEXT DEFAULT 'drafted',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP
            )""",
            """CREATE INDEX IF NOT EXISTS idx_sends_recipient ON sends(recipient_id)""",
            """CREATE INDEX IF NOT EXISTS idx_sends_batch ON sends(batch_id)""",
            """CREATE INDEX IF NOT EXISTS idx_sends_status ON sends(status)""",
            """CREATE TABLE IF NOT EXISTS blacklist (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                reason TEXT,
                source TEXT DEFAULT 'manual',
                added_by TEXT DEFAULT 'user',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE INDEX IF NOT EXISTS idx_blacklist_email ON blacklist(email)""",
            """CREATE TABLE IF NOT EXISTS replies (
                id SERIAL PRIMARY KEY,
                send_id INTEGER,
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                from_addr TEXT,
                subject TEXT,
                body TEXT,
                sentiment TEXT,
                summary TEXT,
                draft_reply_id TEXT,
                status TEXT DEFAULT 'pending',
                received_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE INDEX IF NOT EXISTS idx_replies_status ON replies(status)""",
            """CREATE TABLE IF NOT EXISTS calendar_events (
                id SERIAL PRIMARY KEY,
                reply_id INTEGER,
                event_id TEXT,
                calendar_link TEXT,
                scheduled_at TIMESTAMP,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS drive_files (
                id SERIAL PRIMARY KEY,
                template_id TEXT,
                file_id TEXT,
                file_name TEXT,
                file_url TEXT,
                validated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS pending_resumes (
                id SERIAL PRIMARY KEY,
                sequence_id TEXT NOT NULL,
                day INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                subject TEXT,
                status TEXT DEFAULT 'pending',
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resumed_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS outreach_campaigns (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                sequence_id TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                total_leads INTEGER DEFAULT 0,
                auto_advance INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                details TEXT,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)""",
        ]

        for sql in tables:
            cur.execute(sql)

        # Insert default campaigns
        for seq_id, name, audience in [("school","SCHOOL","private_school"), ("csr","CSR","csr")]:
            cur.execute("""
                INSERT INTO campaigns (id, name, audience) VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (seq_id, name, audience))

        self.conn.commit()
        cur.close()

    def _migrate_schema(self):
        """Auto-migrate database schema when code updates."""
        # Add parent_batch_id to batches if missing
        try:
            self.execute("SELECT parent_batch_id FROM batches LIMIT 1")
        except:
            print("[DB] Migrating: Adding parent_batch_id to batches...")
            self.execute("ALTER TABLE batches ADD COLUMN parent_batch_id INTEGER")
            self.commit()
            print("[DB] Migration complete: parent_batch_id added")

        # Add batched flag to recipients if missing
        try:
            self.execute("SELECT batched FROM recipients LIMIT 1")
        except:
            print("[DB] Migrating: Adding batched flag to recipients...")
            self.execute("ALTER TABLE recipients ADD COLUMN batched INTEGER DEFAULT 0")
            self.execute("CREATE INDEX IF NOT EXISTS idx_recipients_batched ON recipients(batched)")
            self.commit()
            print("[DB] Migration complete: batched flag added")
            # Fix existing batch recipients
            self.execute("""
                UPDATE recipients SET batched=1 
                WHERE id IN (SELECT DISTINCT recipient_id FROM batch_recipients)
            """)
            self.commit()

        # Add campaign_id to batches if missing
        try:
            self.execute("SELECT campaign_id FROM batches LIMIT 1")
        except:
            print("[DB] Migrating: Adding campaign_id to batches...")
            self.execute("ALTER TABLE batches ADD COLUMN campaign_id INTEGER")
            self.commit()
            print("[DB] Migration complete: campaign_id added")

    # ─── RECIPIENTS / POOL ───
    def recipient_add(self, sequence_id, email, name, org, extra_json=None):
        try:
            self.execute("""
                INSERT INTO recipients (sequence_id, email, name, org, extra_json, import_status, batched)
                VALUES (?, ?, ?, ?, ?, 'success', 0)
                ON CONFLICT(sequence_id, email) DO UPDATE SET
                    name=excluded.name, org=excluded.org, extra_json=excluded.extra_json,
                    import_status='success', import_error=NULL, batched=0
            """, (sequence_id, email.lower().strip(), name, org, extra_json))
            self.commit()
            return True, None
        except Exception as e:
            return False, str(e)

    def recipient_get_by_sequence(self, sequence_id):
        rows = self.execute("SELECT * FROM recipients WHERE sequence_id=? ORDER BY id", (sequence_id,)).fetchall()
        return [dict(r) for r in rows]

    def recipient_count(self, sequence_id=None):
        if sequence_id:
            row = self.execute("SELECT COUNT(*) FROM recipients WHERE sequence_id=?", (sequence_id,)).fetchone()
        else:
            row = self.execute("SELECT COUNT(*) FROM recipients").fetchone()
        return row[0] if row else 0

    def recipient_delete(self, recipient_id):
        self.execute("DELETE FROM recipients WHERE id=?", (recipient_id,))
        self.commit()

    # ─── POOL METHODS ───
    def get_pool(self, sequence_id, limit=None):
        sql = "SELECT * FROM recipients WHERE sequence_id=? AND batched=0 ORDER BY id"
        params = [sequence_id]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_pool_count(self, sequence_id):
        row = self.execute(
            "SELECT COUNT(*) FROM recipients WHERE sequence_id=? AND batched=0", 
            (sequence_id,)
        ).fetchone()
        return row[0] if row else 0

    def mark_batched(self, recipient_ids):
        if not recipient_ids:
            return
        placeholders = ','.join(self._placeholder() for _ in recipient_ids)
        self.execute(f"UPDATE recipients SET batched=1 WHERE id IN ({placeholders})", recipient_ids)
        self.commit()

    def unmark_batched(self, recipient_ids):
        if not recipient_ids:
            return
        placeholders = ','.join(self._placeholder() for _ in recipient_ids)
        self.execute(f"UPDATE recipients SET batched=0 WHERE id IN ({placeholders})", recipient_ids)
        self.commit()

    # ─── BATCHES ───
    def batch_create(self, name, sequence_id, scheduled_at=None, timezone='Asia/Kolkata', 
                     send_rate=0, stagger_minutes=0, day_offset=1, parent_batch_id=None, campaign_id=None):
        cur = self.execute("""
            INSERT INTO batches (name, sequence_id, status, scheduled_at, timezone, send_rate, stagger_minutes, day_offset, parent_batch_id, campaign_id)
            VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)
        """, (name, sequence_id, scheduled_at, timezone, send_rate, stagger_minutes, day_offset, parent_batch_id, campaign_id))
        self.commit()
        if self.is_postgres:
            # Get last inserted ID
            id_row = self.execute("SELECT lastval()").fetchone()
            return id_row[0]
        return cur.lastrowid

    def batch_add_recipient(self, batch_id, recipient_id):
        try:
            self.execute("INSERT INTO batch_recipients (batch_id, recipient_id) VALUES (?, ?)",
                        (batch_id, recipient_id))
            self.commit()
            return True
        except:
            return False

    def batch_get(self, batch_id):
        row = self.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        return dict(row) if row else None

    def batch_get_all(self, sequence_id=None):
        if sequence_id:
            rows = self.execute("SELECT * FROM batches WHERE sequence_id=? ORDER BY created_at DESC", (sequence_id,)).fetchall()
        else:
            rows = self.execute("SELECT * FROM batches ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_running_batches(self):
        rows = self.execute("SELECT * FROM batches WHERE status='running' ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def get_scheduled_batches(self):
        rows = self.execute("SELECT * FROM batches WHERE status='scheduled' ORDER BY scheduled_at").fetchall()
        return [dict(r) for r in rows]

    def batch_update_status(self, batch_id, status):
        self.execute("UPDATE batches SET status=? WHERE id=?", (status, batch_id))
        if status == 'running':
            self.execute("UPDATE batches SET started_at=CURRENT_TIMESTAMP WHERE id=?", (batch_id,))
        elif status == 'completed':
            self.execute("UPDATE batches SET completed_at=CURRENT_TIMESTAMP WHERE id=?", (batch_id,))
        self.commit()

    def batch_get_recipients(self, batch_id):
        rows = self.execute("""
            SELECT r.*, br.status as batch_status, br.sent_at 
            FROM recipients r 
            JOIN batch_recipients br ON r.id = br.recipient_id 
            WHERE br.batch_id=?
        """, (batch_id,)).fetchall()
        return [dict(r) for r in rows]

    def batch_delete(self, batch_id):
        recipient_ids = [r["id"] for r in self.batch_get_recipients(batch_id)]
        self.unmark_batched(recipient_ids)
        self.execute("DELETE FROM sends WHERE batch_id=?", (batch_id,))
        self.execute("DELETE FROM batch_recipients WHERE batch_id=?", (batch_id,))
        self.execute("DELETE FROM batches WHERE id=?", (batch_id,))
        self.commit()

    def batch_count_recipients(self, batch_id):
        row = self.execute("SELECT COUNT(*) FROM batch_recipients WHERE batch_id=?", (batch_id,)).fetchone()
        return row[0] if row else 0

    def batch_count_by_status(self, batch_id):
        rows = self.execute("""
            SELECT status, COUNT(*) FROM batch_recipients WHERE batch_id=? GROUP BY status
        """, (batch_id,)).fetchall()
        return {r[0]: r[1] for r in rows}

    # ─── CREATE BATCH FROM POOL ───
    def batch_from_pool(self, name, sequence_id, batch_size, day_offset=1, 
                        scheduled_at=None, timezone='Asia/Kolkata', send_rate=0, stagger_minutes=0, campaign_id=None):
        pool = self.get_pool(sequence_id, limit=batch_size)
        if not pool:
            return None, "No unbatched leads in pool for this sequence"

        verified_pool = []
        for lead in pool:
            check = self.execute("SELECT batched FROM recipients WHERE id=?", (lead["id"],)).fetchone()
            if check and check[0] == 0:
                verified_pool.append(lead)

        if not verified_pool:
            return None, "All available leads were taken by another batch. Try again."

        batch_id = self.batch_create(
            name=name, sequence_id=sequence_id, scheduled_at=scheduled_at,
            timezone=timezone, send_rate=send_rate, stagger_minutes=stagger_minutes,
            day_offset=day_offset, campaign_id=campaign_id
        )

        recipient_ids = []
        for lead in verified_pool:
            self.batch_add_recipient(batch_id, lead["id"])
            recipient_ids.append(lead["id"])

        self.mark_batched(recipient_ids)
        return batch_id, None

    # ─── TEMPLATES ───
    def template_put(self, sequence_id, day, subject, html_body, source="synced"):
        self.execute("""
            INSERT INTO templates (sequence_id, day, subject, html_body, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sequence_id, day) DO UPDATE SET
                subject=excluded.subject, html_body=excluded.html_body, 
                source=excluded.source, cached_at=CURRENT_TIMESTAMP
        """, (sequence_id, day, subject, html_body, source))
        self.commit()

    def template_get(self, sequence_id, day):
        row = self.execute("SELECT subject, html_body, source, locked FROM templates WHERE sequence_id=? AND day=?", 
                          (sequence_id, day)).fetchone()
        return {"subject": row[0], "html_body": row[1], "source": row[2], "locked": bool(row[3])} if row else None

    def template_lock(self, sequence_id, day):
        self.execute("UPDATE templates SET locked=1 WHERE sequence_id=? AND day=?", (sequence_id, day))
        self.commit()

    def template_unlock(self, sequence_id, day):
        self.execute("UPDATE templates SET locked=0 WHERE sequence_id=? AND day=?", (sequence_id, day))
        self.commit()

    def template_is_locked(self, sequence_id, day):
        row = self.execute("SELECT locked FROM templates WHERE sequence_id=? AND day=?", (sequence_id, day)).fetchone()
        return bool(row[0]) if row else False

    # ─── SENDS / PIPELINE ───
    def campaign_queue_send(self, recipient_id, day, subject, draft_id, status="drafted", batch_id=None):
        self.execute("""
            INSERT INTO sends (recipient_id, day, subject, draft_id, status, batch_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (recipient_id, day, subject, draft_id, status, batch_id))
        self.commit()

    def get_pipeline(self, sequence_id=None):
        sql = """
            SELECT 
                r.sequence_id,
                COUNT(DISTINCT r.id) as total_recipients,
                COUNT(DISTINCT CASE WHEN s.status='drafted' THEN s.recipient_id END) as drafted,
                COUNT(DISTINCT CASE WHEN s.status='sent' THEN s.recipient_id END) as sent,
                COUNT(DISTINCT CASE WHEN s.status='bounced' THEN s.recipient_id END) as bounced,
                COUNT(DISTINCT CASE WHEN s.status='replied' THEN s.recipient_id END) as replied
            FROM recipients r
            LEFT JOIN sends s ON r.id = s.recipient_id
        """
        if sequence_id:
            sql += " WHERE r.sequence_id=?"
            rows = self.execute(sql + " GROUP BY r.sequence_id", (sequence_id,)).fetchall()
        else:
            rows = self.execute(sql + " GROUP BY r.sequence_id").fetchall()
        return [dict(r) for r in rows]

    def get_day_wise_pipeline(self, sequence_id):
        rows = self.execute("""
            SELECT day,
                COUNT(DISTINCT recipient_id) as total,
                COUNT(DISTINCT CASE WHEN status='sent' THEN recipient_id END) as sent,
                COUNT(DISTINCT CASE WHEN status='bounced' THEN recipient_id END) as bounced,
                COUNT(DISTINCT CASE WHEN status='replied' THEN recipient_id END) as replied
            FROM sends
            WHERE recipient_id IN (SELECT id FROM recipients WHERE sequence_id=?)
            GROUP BY day
            ORDER BY day
        """, (sequence_id,)).fetchall()
        return {r[0]: {"total": r[1], "sent": r[2], "bounced": r[3], "replied": r[4]} for r in rows}

    # ─── BLACKLIST ───
    def blacklist_add(self, email, reason="manual", source="user"):
        self.execute("""
            INSERT INTO blacklist (email, reason, source) 
            VALUES (?, ?, ?) 
            ON CONFLICT(email) DO UPDATE SET reason=excluded.reason, source=excluded.source
        """, (email.lower().strip(), reason, source))
        self.commit()

    def blacklist_remove(self, email_or_id):
        if isinstance(email_or_id, int):
            self.execute("DELETE FROM blacklist WHERE id=?", (email_or_id,))
        else:
            self.execute("DELETE FROM blacklist WHERE email=?", (email_or_id.lower().strip(),))
        self.commit()

    def blacklist_has(self, email):
        return self.execute("SELECT 1 FROM blacklist WHERE email=?", (email.lower().strip(),)).fetchone() is not None

    def blacklist_get_all(self):
        rows = self.execute("SELECT * FROM blacklist ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ─── META ───
    def set_meta(self, key, value):
        self.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.commit()

    def get_meta(self, key):
        row = self.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    # ─── AUDIT LOG ───
    def log_action(self, action, details=None, user='system'):
        self.execute("INSERT INTO audit_log (action, details, created_by) VALUES (?, ?, ?)", (action, details, user))
        self.commit()

    def get_audit_log(self, limit=50):
        rows = self.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ─── BATCH PIPELINE TRACKING ───
    def batch_get_pipeline(self, batch_id: int) -> dict:
        batch = self.batch_get(batch_id)
        if not batch:
            return {}

        root_id = batch.get("parent_batch_id") or batch_id
        if batch.get("parent_batch_id") and batch["parent_batch_id"] != batch_id:
            root = self.batch_get(batch["parent_batch_id"])
            if root:
                root_id = root["id"]

        rows = self.execute("""
            SELECT * FROM batches 
            WHERE parent_batch_id=? OR id=? 
            ORDER BY day_offset
        """, (root_id, root_id)).fetchall()

        pipeline_batches = []
        for r in rows:
            b = dict(r)
            counts = self.batch_count_by_status(b["id"])
            b["counts"] = counts
            b["total_recipients"] = sum(counts.values())
            b["sent"] = counts.get("sent", 0)
            pipeline_batches.append(b)

        return {
            "root_batch_id": root_id,
            "root_name": self.batch_get(root_id)["name"] if self.batch_get(root_id) else "Unknown",
            "sequence_id": batch.get("sequence_id", ""),
            "batches": pipeline_batches,
            "total_days": len(pipeline_batches),
            "completed_days": sum(1 for b in pipeline_batches if b["status"] == "completed"),
            "running_days": sum(1 for b in pipeline_batches if b["status"] == "running"),
        }

    def batch_get_all_pipelines(self, sequence_id: str = None) -> list:
        if sequence_id:
            roots = self.execute("""
                SELECT DISTINCT parent_batch_id FROM batches 
                WHERE sequence_id=? AND parent_batch_id IS NOT NULL
            """, (sequence_id,)).fetchall()
        else:
            roots = self.execute("""
                SELECT DISTINCT parent_batch_id FROM batches 
                WHERE parent_batch_id IS NOT NULL
            """).fetchall()

        pipelines = []
        for (root_id,) in roots:
            if root_id:
                pipe = self.batch_get_pipeline(root_id)
                if pipe:
                    pipelines.append(pipe)
        return pipelines

    # ─── CAMPAIGNS ───
    def campaign_create(self, name, sequence_id, total_leads=0, auto_advance=1):
        cur = self.execute("""
            INSERT INTO outreach_campaigns (name, sequence_id, status, total_leads, auto_advance)
            VALUES (?, ?, 'draft', ?, ?)
        """, (name, sequence_id, total_leads, auto_advance))
        self.commit()
        if self.is_postgres:
            id_row = self.execute("SELECT lastval()").fetchone()
            return id_row[0]
        return cur.lastrowid

    def campaign_get(self, campaign_id):
        row = self.execute("SELECT * FROM outreach_campaigns WHERE id=?", (campaign_id,)).fetchone()
        return dict(row) if row else None

    def campaign_get_all(self, status=None):
        if status:
            rows = self.execute("SELECT * FROM outreach_campaigns WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = self.execute("SELECT * FROM outreach_campaigns ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def campaign_update_status(self, campaign_id, status):
        self.execute("UPDATE outreach_campaigns SET status=? WHERE id=?", (status, campaign_id))
        if status == 'active':
            self.execute("UPDATE outreach_campaigns SET started_at=CURRENT_TIMESTAMP WHERE id=?", (campaign_id,))
        elif status == 'completed':
            self.execute("UPDATE outreach_campaigns SET completed_at=CURRENT_TIMESTAMP WHERE id=?", (campaign_id,))
        self.commit()

    def campaign_get_batches(self, campaign_id):
        rows = self.execute("""
            SELECT * FROM batches WHERE campaign_id=? ORDER BY day_offset, created_at
        """, (campaign_id,)).fetchall()
        return [dict(r) for r in rows]

    def campaign_get_pipeline(self, campaign_id):
        campaign = self.campaign_get(campaign_id)
        if not campaign:
            return None

        batches = self.campaign_get_batches(campaign_id)
        pipeline = []
        for b in batches:
            counts = self.batch_count_by_status(b["id"])
            total = sum(counts.values())
            sent = counts.get("sent", 0)
            pipeline.append({
                "batch_id": b["id"],
                "name": b["name"],
                "day": b["day_offset"],
                "status": b["status"],
                "total": total,
                "sent": sent,
                "scheduled_at": b.get("scheduled_at")
            })

        return {
            "campaign": campaign,
            "pipeline": pipeline,
            "total_days": len(pipeline),
            "completed_days": sum(1 for p in pipeline if p["status"] == "completed"),
            "active_days": sum(1 for p in pipeline if p["status"] in ["running", "scheduled"])
        }

    def get_next_batch_in_sequence(self, batch_id):
        batch = self.batch_get(batch_id)
        if not batch:
            return None

        campaign_id = batch.get("campaign_id")
        if not campaign_id:
            return None

        current_day = batch.get("day_offset", 1)
        rows = self.execute("""
            SELECT * FROM batches 
            WHERE campaign_id=? AND day_offset > ? AND status='draft'
            ORDER BY day_offset LIMIT 1
        """, (campaign_id, current_day)).fetchall()

        return dict(rows[0]) if rows else None

    # ─── DASHBOARD SUMMARY ───
    def get_dashboard_summary(self):
        summary = {"sequences": {}, "global": {}}

        for seq_id in ["school", "csr"]:
            seq = {}
            seq["recipients"] = self.recipient_count(seq_id)
            seq["pool_count"] = self.get_pool_count(seq_id)

            tmpl_rows = self.execute("SELECT day, source, locked FROM templates WHERE sequence_id=?", (seq_id,)).fetchall()
            seq["templates"] = {r[0]: {"source": r[1], "locked": bool(r[2])} for r in tmpl_rows}
            seq["templates_total"] = len(tmpl_rows)
            seq["templates_locked"] = sum(1 for t in tmpl_rows if t[2])

            pipeline = self.get_pipeline(seq_id)
            if pipeline:
                p = pipeline[0]
                seq["pipeline"] = {
                    "total": p["total_recipients"],
                    "drafted": p["drafted"],
                    "sent": p["sent"],
                    "bounced": p["bounced"],
                    "replied": p["replied"]
                }
            else:
                seq["pipeline"] = {"total": 0, "drafted": 0, "sent": 0, "bounced": 0, "replied": 0}

            seq["day_wise"] = self.get_day_wise_pipeline(seq_id)
            seq["batches"] = self.batch_get_all(seq_id)

            summary["sequences"][seq_id] = seq

        summary["global"] = {
            "total_recipients": self.recipient_count(),
            "blacklist_count": self.execute("SELECT COUNT(*) FROM blacklist").fetchone()[0],
            "pending_replies": self.execute("SELECT COUNT(*) FROM replies WHERE status='pending'").fetchone()[0],
            "drafted_replies": self.execute("SELECT COUNT(*) FROM replies WHERE status='drafted'").fetchone()[0],
            "active_batches": self.execute("SELECT COUNT(*) FROM batches WHERE status IN ('scheduled','running')").fetchone()[0]
        }

        return summary

    def get_recent_activity(self, batch_id=None, limit=10):
        try:
            self.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.commit()

            if batch_id:
                rows = self.execute(
                    "SELECT * FROM activity_log WHERE batch_id = ? ORDER BY created_at DESC LIMIT ?",
                    (batch_id, limit)
                ).fetchall()
            else:
                rows = self.execute(
                    "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"Activity log error: {e}")
            return []
