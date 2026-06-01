"""
export_desktop_data.py — Export your desktop Raj database to CSV files.
Run this on your Windows computer where the desktop app works.
"""

import sqlite3
import csv
from pathlib import Path

def export_database():
    # Find the database file
    db_path = Path("campaign_data.db")
    if not db_path.exists():
        db_path = Path("raj.db")
    if not db_path.exists():
        print("❌ Database not found. Look for 'campaign_data.db' or 'raj.db' in your RP Gmail folder.")
        return

    print(f"📁 Found database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Export recipients
    print("📤 Exporting recipients...")
    rows = conn.execute("SELECT * FROM recipients").fetchall()
    with open("batch_recipients.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        print(f"   ✅ {len(rows)} recipients exported")

    # Export batches
    print("📤 Exporting batches...")
    rows = conn.execute("SELECT * FROM batches").fetchall()
    with open("batches.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        print(f"   ✅ {len(rows)} batches exported")

    # Export blacklist
    print("📤 Exporting blacklist...")
    rows = conn.execute("SELECT * FROM blacklist").fetchall()
    with open("blacklist.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        print(f"   ✅ {len(rows)} blacklisted emails exported")

    # Export templates
    print("📤 Exporting templates...")
    rows = conn.execute("SELECT * FROM templates").fetchall()
    with open("templates.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        print(f"   ✅ {len(rows)} templates exported")

    conn.close()
    print("
🎉 All data exported! Files created:")
    print("   - batch_recipients.csv")
    print("   - batches.csv")
    print("   - blacklist.csv")
    print("   - templates.csv")
    print("
👉 Upload these files to your GitHub repo (raj-web-app)")
    print("👉 The web app will auto-import them on next deploy.")

if __name__ == "__main__":
    export_database()
