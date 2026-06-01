"""
seed_db.py — Import CSV data into database on startup.
Works with both SQLite and PostgreSQL.
"""

import os
import csv
from pathlib import Path
from db import Database

def seed_database():
    """Import all CSV files into the database."""
    db = Database()

    base_dir = Path(__file__).parent

    # Import recipients from CSV
    recipients_file = base_dir / "batch_recipients.csv"
    if recipients_file.exists():
        print(f"[Seed] Importing recipients from {recipients_file}")
        with open(recipients_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            imported = 0
            for row in reader:
                try:
                    batch_id = row.get("batch_id", "")
                    sequence_id = row.get("sequence_id", "school")
                    email = row.get("email", "").strip().lower()
                    name = row.get("name", "").strip()
                    org = row.get("org", "").strip()
                    extra = row.get("extra_json", "")

                    if not email or "@" not in email:
                        continue

                    # Add to recipients
                    db.recipient_add(sequence_id, email, name, org, extra)
                    imported += 1
                except Exception as e:
                    print(f"[Seed] Skip row: {e}")
            print(f"[Seed] Imported {imported} recipients")

    # Import batches from CSV
    batches_file = base_dir / "batches.csv"
    if batches_file.exists():
        print(f"[Seed] Importing batches from {batches_file}")
        with open(batches_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            imported = 0
            for row in reader:
                try:
                    name = row.get("name", "").strip()
                    sequence_id = row.get("sequence_id", "school").strip()
                    status = row.get("status", "draft").strip()
                    scheduled_at = row.get("scheduled_at", "").strip()
                    day_offset = int(row.get("day_offset", 1))

                    if not name:
                        continue

                    # Check if batch already exists
                    existing = db.execute(
                        "SELECT id FROM batches WHERE name=?", (name,)
                    ).fetchone()

                    if not existing:
                        batch_id = db.batch_create(
                            name=name,
                            sequence_id=sequence_id,
                            scheduled_at=scheduled_at if scheduled_at else None,
                            day_offset=day_offset
                        )
                        db.batch_update_status(batch_id, status)
                        imported += 1
                except Exception as e:
                    print(f"[Seed] Skip batch row: {e}")
            print(f"[Seed] Imported {imported} batches")

    # Import blacklist from CSV
    blacklist_file = base_dir / "blacklist.csv"
    if blacklist_file.exists():
        print(f"[Seed] Importing blacklist from {blacklist_file}")
        with open(blacklist_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            imported = 0
            for row in reader:
                try:
                    email = row.get("email", "").strip().lower()
                    reason = row.get("reason", "imported").strip()

                    if not email or "@" not in email:
                        continue

                    if not db.blacklist_has(email):
                        db.blacklist_add(email, reason, "csv_import")
                        imported += 1
                except Exception as e:
                    print(f"[Seed] Skip blacklist row: {e}")
            print(f"[Seed] Imported {imported} blacklisted emails")

    print("[Seed] Database seeding complete")

if __name__ == "__main__":
    seed_database()
