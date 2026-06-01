"""
seed_db.py -- Seed database from CSV files (desktop data migration)
Fixed for PostgreSQL compatibility
"""

import os
import csv
from db import Database

def seed_database():
    """Import CSV data into PostgreSQL database."""
    db = Database()

    # Check if we already have data
    count = db.recipient_count()
    if count > 0:
        print(f"[SEED] Database already has {count} recipients, skipping seed")
        return

    csv_files = {
        'recipients': 'recipients.csv',
        'batches': 'batches.csv',
        'batch_recipients': 'batch_recipients.csv',
        'blacklist': 'blacklist.csv',
        'templates': 'templates.csv',
        'sends': 'sends.csv',
        'replies': 'replies.csv'
    }

    base_path = os.path.dirname(os.path.abspath(__file__))

    # Import recipients
    recipients_path = os.path.join(base_path, csv_files['recipients'])
    if os.path.exists(recipients_path):
        try:
            with open(recipients_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                imported = 0
                for row in reader:
                    try:
                        db.recipient_add(
                            sequence_id=row.get('sequence_id', 'school'),
                            email=row.get('email', ''),
                            name=row.get('name', ''),
                            org=row.get('org', ''),
                            extra_json=row.get('extra_json', '{}')
                        )
                        imported += 1
                    except Exception as e:
                        pass
                print(f"[SEED] Imported {imported} recipients from CSV")
        except Exception as e:
            print(f"[SEED] Error importing recipients: {e}")
    else:
        print(f"[SEED] No recipients.csv found")

    # Import blacklist
    blacklist_path = os.path.join(base_path, csv_files['blacklist'])
    if os.path.exists(blacklist_path):
        try:
            with open(blacklist_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                imported = 0
                for row in reader:
                    try:
                        email = row.get('email', '').strip()
                        if email and '@' in email:
                            db.blacklist_add(email, row.get('reason', 'imported'))
                            imported += 1
                    except:
                        pass
                print(f"[SEED] Imported {imported} blacklisted emails")
        except Exception as e:
            print(f"[SEED] Error importing blacklist: {e}")

    print(f"[SEED] Done! Database has {db.recipient_count()} recipients")

if __name__ == '__main__':
    seed_database()
