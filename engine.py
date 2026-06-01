"""
engine.py -- RoboPirate Campaign Engine v5.5
Fixed: Thread-safe DB connections, graceful error handling
"""

import os
import re
import time
import json
import random
import threading
from datetime import datetime, timedelta
from pathlib import Path

class CampaignEngine:
    """Email campaign engine with auto-advance and pipeline tracking."""

    def __init__(self, db, gmail=None):
        self.db = db
        self.gmail = gmail
        self.running = False
        self.paused = False
        self.thread = None
        self._stop_event = threading.Event()
        self.last_tick = 0
        self.tick_interval = 30  # seconds
        self.send_rate = 45
        self.stagger_minutes = 2
        self.morning_hour = 8
        self.eod_hour = 19
        self.auto_advance = True
        self.sunday_filter = True
        self.timezone = 'Asia/Kolkata'
        self._load_settings()

    def _load_settings(self):
        if not self.db:
            return
        try:
            self.send_rate = int(self.db.get_meta("send_rate") or 45)
            self.stagger_minutes = int(self.db.get_meta("stagger_minutes") or 2)
            self.morning_hour = int(self.db.get_meta("morning_hour") or 8)
            self.eod_hour = int(self.db.get_meta("eod_hour") or 19)
            self.auto_advance = (self.db.get_meta("auto_advance") or "true") != "false"
            self.sunday_filter = (self.db.get_meta("sunday_filter") or "true") != "false"
        except:
            pass

    def start(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[Engine] Raj Engine started")

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        print("[Engine] Raj Engine stopped")

    def pause(self):
        self.paused = True
        print("[Engine] Paused")

    def resume(self):
        self.paused = False
        print("[Engine] Resumed")

    def is_running(self):
        return self.running

    def is_paused(self):
        return self.paused

    def _loop(self):
        print("[Engine] [RESUME] No running batches from previous session")
        while self.running and not self._stop_event.is_set():
            try:
                if not self.paused:
                    self._tick()
            except Exception as e:
                print(f"[Engine] LOOP ERROR: {e}")
            time.sleep(self.tick_interval)

    def _tick(self):
        now = datetime.now()

        # Check scheduled batches
        try:
            scheduled = self.db.get_scheduled_batches() if self.db else []
            for batch in scheduled:
                scheduled_time = batch.get("scheduled_at")
                if scheduled_time:
                    try:
                        if isinstance(scheduled_time, str):
                            scheduled_time = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
                        if now >= scheduled_time:
                            self._start_batch(batch["id"])
                    except:
                        pass
        except Exception as e:
            print(f"[Engine] Scheduled batch check error: {e}")

        # Process running batches
        try:
            self._process_running_batches()
        except Exception as e:
            print(f"[Engine] Running batch process error: {e}")

        # Scan bounces (only if Gmail available)
        if self.gmail and self.running:
            try:
                self.scan_bounces()
            except Exception as e:
                print(f"[Engine] Bounce scan error: {e}")

        # Scan replies (only if Gmail available)
        if self.gmail and self.running:
            try:
                self.scan_replies()
            except Exception as e:
                print(f"[Engine] Reply scan error: {e}")

    def _start_batch(self, batch_id):
        try:
            self.db.batch_update_status(batch_id, 'running')
            print(f"[Engine] Auto-started batch {batch_id}")
        except Exception as e:
            print(f"[Engine] Error starting batch {batch_id}: {e}")

    def _process_running_batches(self):
        if not self.gmail:
            return

        try:
            running = self.db.get_running_batches() if self.db else []
            for batch in running:
                try:
                    self._send_batch_emails(batch)
                except Exception as e:
                    print(f"[Engine] Error sending batch {batch.get('id', '?')}: {e}")
        except Exception as e:
            print(f"[Engine] Error getting running batches: {e}")

    def _send_batch_emails(self, batch):
        batch_id = batch.get("id")
        sequence_id = batch.get("sequence_id", "school")
        day_offset = batch.get("day_offset", 1)

        try:
            template = self.db.template_get(sequence_id, day_offset) if self.db else None
            if not template:
                print(f"[Engine] No template for {sequence_id} day {day_offset}")
                return

            recipients = self.db.batch_get_recipients(batch_id) if self.db else []
            if not recipients:
                return

            for recipient in recipients:
                if recipient.get("batch_status") != "pending":
                    continue

                try:
                    email = recipient.get("email", "")
                    if not email or self.db.blacklist_has(email):
                        continue

                    if not self._check_send_rate():
                        break

                    subject = template.get("subject", "")
                    html_body = template.get("html_body", "")

                    name = recipient.get("name", "")
                    org = recipient.get("org", "")
                    subject = subject.replace("{{name}}", name).replace("{{org}}", org)
                    html_body = html_body.replace("{{name}}", name).replace("{{org}}", org)

                    if self.gmail and hasattr(self.gmail, 'send_email'):
                        result = self.gmail.send_email(email, subject, html_body)
                        if result.get("success"):
                            self.db.execute(
                                "UPDATE batch_recipients SET status='sent', sent_at=CURRENT_TIMESTAMP WHERE batch_id=? AND recipient_id=?",
                                (batch_id, recipient.get("id"))
                            )
                            self.db.commit()
                            print(f"[Engine] Sent to {email}")
                        else:
                            print(f"[Engine] Failed to send to {email}: {result.get('error')}")

                    time.sleep(self.stagger_minutes * 60)

                except Exception as e:
                    print(f"[Engine] Error sending to {recipient.get('email', '?')}: {e}")
        except Exception as e:
            print(f"[Engine] Error in batch {batch_id}: {e}")

    def _check_send_rate(self):
        try:
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
            cur = self.db.execute(
                "SELECT COUNT(*) FROM sends WHERE sent_at > ? AND status='sent'",
                (one_hour_ago,)
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            return count < self.send_rate
        except:
            return True

    def scan_bounces(self):
        if not self.gmail or not hasattr(self.gmail, 'search_messages'):
            print("[Engine] Bounce scan skipped: Gmail not available")
            return {"count": 0, "new_blacklisted": 0}

        try:
            bounces = self.gmail.search_messages("subject:bounce OR subject:delivery failed OR subject:undelivered")

            new_blacklisted = 0
            for msg in bounces:
                try:
                    email = self._extract_bounce_email(msg)
                    if email and not self.db.blacklist_has(email):
                        if email.endswith("@robopirate.in") or email == "info@robopirate.in":
                            continue
                        self.db.blacklist_add(email, "bounce", "auto")
                        new_blacklisted += 1
                except:
                    pass

            print(f"[Engine] Bounce scan: {new_blacklisted} new blacklisted")
            return {"count": len(bounces), "new_blacklisted": new_blacklisted}
        except Exception as e:
            print(f"[Engine] Bounce scan error: {e}")
            return {"count": 0, "new_blacklisted": 0}

    def _extract_bounce_email(self, msg):
        try:
            body = msg.get("body", "")
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body)
            for email in emails:
                if not any(x in email.lower() for x in ['noreply', 'no-reply', 'postmaster', 'mailer-daemon']):
                    if email.endswith("@robopirate.in") or email == "info@robopirate.in":
                        continue
                    return email
            return None
        except:
            return None

    def scan_replies(self):
        if not self.gmail or not hasattr(self.gmail, 'search_messages'):
            print("[Engine] Reply scan skipped: Gmail not available")
            return 0

        try:
            replies = self.gmail.search_messages("is:unread in:inbox newer_than:1d")

            count = 0
            for msg in replies:
                try:
                    from_addr = msg.get("from", "")
                    subject = msg.get("subject", "")
                    body = msg.get("body", "")

                    self.db.execute("""
                        INSERT INTO replies (thread_id, message_id, from_addr, subject, body, status, received_at)
                        VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
                        ON CONFLICT(message_id) DO NOTHING
                    """, (
                        msg.get("thread_id", ""),
                        msg.get("id", ""),
                        from_addr,
                        subject,
                        body
                    ))
                    self.db.commit()
                    count += 1
                except:
                    pass

            print(f"[Engine] Reply scan: {count} new replies")
            return count
        except Exception as e:
            print(f"[Engine] Reply scan error: {e}")
            return 0

    def get_summary(self):
        if not self.db:
            return {"sequences": {}, "global": {}}
        try:
            return self.db.get_dashboard_summary()
        except Exception as e:
            print(f"[Engine] Summary error: {e}")
            return {"sequences": {}, "global": {}}

    def get_pool_count(self, sequence_id):
        if not self.db:
            return 0
        try:
            return self.db.get_pool_count(sequence_id)
        except:
            return 0

    def create_batch_from_pool(self, name, sequence_id, batch_size, day_offset=1):
        if not self.db:
            return {"success": False, "error": "Database not available"}

        try:
            batch_id, error = self.db.batch_from_pool(
                name=name,
                sequence_id=sequence_id,
                batch_size=batch_size,
                day_offset=day_offset
            )

            if error:
                return {"success": False, "error": error}

            return {
                "success": True,
                "batch_id": batch_id,
                "message": f"Batch '{name}' created with {batch_size} leads"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_templates(self):
        if not self.gmail or not hasattr(self.gmail, 'search_messages'):
            return {"success": False, "error": "Gmail not connected", "synced": 0, "locked": 0}

        try:
            drafts = self.gmail.search_messages("in:drafts subject:TEMPLATE")

            synced = 0
            locked = 0
            for draft in drafts:
                try:
                    subject = draft.get("subject", "")
                    match = re.search(r'TEMPLATE\s+(SCHOOL|CSR)\s+D(\d+)', subject, re.I)
                    if match:
                        seq_id = match.group(1).lower()
                        day = int(match.group(2))

                        body = draft.get("body", "")
                        self.db.template_put(seq_id, day, subject, body, "synced")
                        synced += 1

                        if self.db.template_is_locked(seq_id, day):
                            locked += 1
                except:
                    pass

            return {"success": True, "synced": synced, "locked": locked}
        except Exception as e:
            return {"success": False, "error": str(e), "synced": 0, "locked": 0}

    def smart_import(self, filepath, sequence_id):
        if not self.db:
            return {"success": False, "error": "Database not available"}

        try:
            import pandas as pd

            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath)
            elif filepath.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(filepath)
            else:
                return {"success": False, "error": "Unsupported file format"}

            email_col = None
            name_col = None
            org_col = None

            for col in df.columns:
                col_lower = col.lower()
                if 'email' in col_lower or 'e-mail' in col_lower:
                    email_col = col
                elif 'name' in col_lower or 'contact' in col_lower:
                    name_col = col
                elif 'org' in col_lower or 'school' in col_lower or 'company' in col_lower or 'institution' in col_lower:
                    org_col = col

            if not email_col:
                return {"success": False, "error": "Could not find email column"}

            imported = 0
            for _, row in df.iterrows():
                try:
                    email = str(row[email_col]).strip().lower()
                    if not email or '@' not in email:
                        continue

                    name = str(row[name_col]) if name_col else ""
                    org = str(row[org_col]) if org_col else ""

                    self.db.recipient_add(sequence_id, email, name, org)
                    imported += 1
                except:
                    pass

            return {
                "success": True,
                "imported": imported,
                "message": f"Imported {imported} leads into {sequence_id} pool"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
