"""
Raj Web App - FULL SYSTEM CHECKUP
"""
import psycopg2
import os
import sys
from datetime import datetime

DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    print("ERROR: Set DATABASE_URL")
    sys.exit(1)

print("=" * 70)
print("  RAJ WEB APP - FULL SYSTEM CHECKUP")
print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 70)

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    print("
✅ DATABASE: Connected")
except Exception as e:
    print(f"
❌ DATABASE: FAILED - {e}")
    sys.exit(1)

# TABLE COUNTS
print("
" + "-" * 70)
print("1. TABLE COUNTS")
print("-" * 70)
for table in ['recipients', 'batches', 'batch_recipients', 'sends', 'replies', 'blacklist', 'templates', 'meta']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"   {table:20s}: {cur.fetchone()[0]:6d} rows")
    except Exception as e:
        print(f"   {table:20s}: ERROR - {e}")

# RECIPIENTS
print("
" + "-" * 70)
print("2. RECIPIENTS BY SEQUENCE")
print("-" * 70)
cur.execute("SELECT sequence_id, COUNT(*) FROM recipients GROUP BY sequence_id")
for row in cur.fetchall():
    print(f"   {row[0]:20s}: {row[1]:6d} leads")

# BATCH STATUS
print("
" + "-" * 70)
print("3. BATCH STATUS")
print("-" * 70)
cur.execute("SELECT status, COUNT(*) FROM batches GROUP BY status")
for row in cur.fetchall():
    print(f"   {row[0]:20s}: {row[1]:6d} batches")

# 0 recipient batches
cur.execute("""
    SELECT b.id, b.name, b.status, COUNT(br.recipient_id)
    FROM batches b LEFT JOIN batch_recipients br ON b.id = br.batch_id
    GROUP BY b.id HAVING COUNT(br.recipient_id) = 0 ORDER BY b.id
""")
zero = cur.fetchall()
print(f"
   ⚠️  BATCHES WITH 0 RECIPIENTS: {len(zero)}")
for row in zero[:5]:
    print(f"      #{row[0]} {row[1]} ({row[2]})")
if len(zero) > 5:
    print(f"      ... and {len(zero)-5} more")

# SENDS
print("
" + "-" * 70)
print("4. SEND STATUS")
print("-" * 70)
cur.execute("SELECT status, COUNT(*) FROM sends GROUP BY status")
for row in cur.fetchall():
    print(f"   {row[0]:20s}: {row[1]:6d} sends")
cur.execute("SELECT day, COUNT(*) FROM sends WHERE status='sent' GROUP BY day ORDER BY day")
print("
   Sends by Day:")
for row in cur.fetchall():
    print(f"   Day {row[0]:2d}: {row[1]:6d} sends")

# LINKS
print("
" + "-" * 70)
print("5. BATCH RECIPIENT LINKS")
print("-" * 70)
cur.execute("SELECT COUNT(*) FROM batch_recipients")
print(f"   Total links: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM batch_recipients WHERE batch_id NOT IN (SELECT id FROM batches)")
print(f"   Orphaned batch_id: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM batch_recipients WHERE recipient_id NOT IN (SELECT id FROM recipients)")
print(f"   Orphaned recipient_id: {cur.fetchone()[0]}")

# TEMPLATES - FIXED COLUMN NAME
print("
" + "-" * 70)
print("6. TEMPLATES")
print("-" * 70)
try:
    cur.execute("SELECT sequence_id, day, subject, locked, status FROM templates ORDER BY sequence_id, day")
    for row in cur.fetchall():
        seq, day, subject, locked, status = row
        print(f"   {seq:10s} D{day:2d}: {'🔒' if locked else '🔓'} {status:10s} | {subject[:40]}")
except Exception as e:
    print(f"   ERROR: {e}")

# REPLIES
print("
" + "-" * 70)
print("7. REPLIES (Last 7 days)")
print("-" * 70)
cur.execute("SELECT category, COUNT(*) FROM replies WHERE received_at > NOW() - INTERVAL '7 days' GROUP BY category")
for row in cur.fetchall():
    print(f"   {row[0]:20s}: {row[1]:6d}")

# BLACKLIST
print("
" + "-" * 70)
print("8. BLACKLIST")
print("-" * 70)
cur.execute("SELECT COUNT(*) FROM blacklist")
bl = cur.fetchone()[0]
print(f"   Total: {bl}")
cur.execute("SELECT reason, COUNT(*) FROM blacklist GROUP BY reason ORDER BY COUNT(*) DESC")
for row in cur.fetchall():
    print(f"   {row[0]:20s}: {row[1]:6d}")

# SETTINGS
print("
" + "-" * 70)
print("9. ENGINE SETTINGS")
print("-" * 70)
cur.execute("SELECT key, value FROM meta WHERE key IN ('send_rate', 'stagger_minutes', 'auto_advance', 'morning_hour', 'eod_hour')")
for row in cur.fetchall():
    print(f"   {row[0]:20s}: {row[1]}")

# GMAIL
print("
" + "-" * 70)
print("10. GMAIL CONNECTION")
print("-" * 70)
cur.execute("SELECT key, value FROM meta WHERE key LIKE '%gmail%' OR key LIKE '%token%'")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"   {row[0]:20s}: {row[1][:50] if row[1] else 'None'}...")
    print("   ✅ Gmail tokens found")
else:
    print("   ❌ No Gmail tokens - connect at /connect-gmail")

# DUPLICATES
print("
" + "-" * 70)
print("11. DUPLICATE BATCH NAMES")
print("-" * 70)
cur.execute("SELECT name, COUNT(*) FROM batches GROUP BY name HAVING COUNT(*) > 1")
dups = cur.fetchall()
if dups:
    print(f"   ⚠️  {len(dups)} duplicates:")
    for row in dups:
        print(f"      '{row[0]}' x{row[1]}")
else:
    print("   ✅ No duplicates")

# SUMMARY
print("
" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
cur.execute("SELECT COUNT(*) FROM recipients")
rec = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM sends WHERE status='sent'")
sent = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM batches WHERE status='running'")
run = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM batches WHERE status='draft'")
draft = cur.fetchone()[0]

print(f"
  📊 Recipients: {rec}")
print(f"  📧 Sent:       {sent}")
print(f"  🚀 Running:    {run}")
print(f"  📝 Draft:      {draft}")
print(f"  ⛔ Blacklist:  {bl}")
print(f"
  🔴 CRITICAL:")
print(f"  1. Google Workspace expires June 5 - UPDATE PAYMENT")
print(f"  2. {len(zero)} batches have 0 recipients (delete duplicates)")
print(f"  3. 3 batches show RUNNING but may not actually be sending")
print(f"  4. Check if engine is truly running in Settings tab")

cur.close()
conn.close()
print("
✅ Checkup complete!")
