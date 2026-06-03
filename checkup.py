import psycopg2
import os
import sys
from datetime import datetime

DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    print("ERROR: Set DATABASE_URL")
    sys.exit(1)

print("=" * 70)
print("RAJ WEB APP - FULL SYSTEM CHECKUP")
print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 70)

try:
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()
    print("DATABASE: Connected")
except Exception as e:
    print("DATABASE FAILED: " + str(e))
    sys.exit(1)

print("-" * 70)
print("1. TABLE COUNTS")
print("-" * 70)
for table in ['recipients', 'batches', 'batch_recipients', 'sends', 'replies', 'blacklist', 'templates', 'meta']:
    try:
        cur.execute("SELECT COUNT(*) FROM " + table)
        print(table + ": " + str(cur.fetchone()[0]))
    except Exception as e:
        print(table + " ERROR: " + str(e))

print("-" * 70)
print("2. RECIPIENTS BY SEQUENCE")
print("-" * 70)
cur.execute("SELECT sequence_id, COUNT(*) FROM recipients GROUP BY sequence_id")
for row in cur.fetchall():
    print(row[0] + ": " + str(row[1]) + " leads")

print("-" * 70)
print("3. BATCH STATUS")
print("-" * 70)
cur.execute("SELECT status, COUNT(*) FROM batches GROUP BY status")
for row in cur.fetchall():
    print(row[0] + ": " + str(row[1]) + " batches")

cur.execute("SELECT b.id, b.name, b.status, COUNT(br.recipient_id) FROM batches b LEFT JOIN batch_recipients br ON b.id = br.batch_id GROUP BY b.id HAVING COUNT(br.recipient_id) = 0 ORDER BY b.id")
zero = cur.fetchall()
print("BATCHES WITH 0 RECIPIENTS: " + str(len(zero)))
for row in zero[:5]:
    print("  #" + str(row[0]) + " " + row[1] + " (" + row[2] + ")")
if len(zero) > 5:
    print("  ... and " + str(len(zero)-5) + " more")

print("-" * 70)
print("4. SEND STATUS")
print("-" * 70)
cur.execute("SELECT status, COUNT(*) FROM sends GROUP BY status")
for row in cur.fetchall():
    print(row[0] + ": " + str(row[1]) + " sends")
cur.execute("SELECT day, COUNT(*) FROM sends WHERE status='sent' GROUP BY day ORDER BY day")
print("Sends by Day:")
for row in cur.fetchall():
    print("Day " + str(row[0]) + ": " + str(row[1]) + " sends")

print("-" * 70)
print("5. LINKS")
print("-" * 70)
cur.execute("SELECT COUNT(*) FROM batch_recipients")
print("Total links: " + str(cur.fetchone()[0]))
cur.execute("SELECT COUNT(*) FROM batch_recipients WHERE batch_id NOT IN (SELECT id FROM batches)")
print("Orphaned batch_id: " + str(cur.fetchone()[0]))
cur.execute("SELECT COUNT(*) FROM batch_recipients WHERE recipient_id NOT IN (SELECT id FROM recipients)")
print("Orphaned recipient_id: " + str(cur.fetchone()[0]))

print("-" * 70)
print("6. TEMPLATES")
print("-" * 70)
try:
    cur.execute("SELECT sequence_id, day, subject, locked FROM templates ORDER BY sequence_id, day")
    for row in cur.fetchall():
        seq, day, subject, locked = row
        lock_str = "LOCKED" if locked else "UNLOCKED"
        print(seq + " D" + str(day) + ": " + lock_str + " | " + subject[:40])
except Exception as e:
    print("ERROR: " + str(e))

print("-" * 70)
print("7. REPLIES (Last 7 days)")
print("-" * 70)
try:
    cur.execute("SELECT category, COUNT(*) FROM replies WHERE received_at > NOW() - INTERVAL '7 days' GROUP BY category")
    for row in cur.fetchall():
        print(row[0] + ": " + str(row[1]))
except Exception as e:
    print("ERROR: " + str(e))

print("-" * 70)
print("8. BLACKLIST")
print("-" * 70)
cur.execute("SELECT COUNT(*) FROM blacklist")
bl = cur.fetchone()[0]
print("Total: " + str(bl))
cur.execute("SELECT reason, COUNT(*) FROM blacklist GROUP BY reason ORDER BY COUNT(*) DESC")
for row in cur.fetchall():
    print(row[0] + ": " + str(row[1]))

print("-" * 70)
print("9. SETTINGS")
print("-" * 70)
cur.execute("SELECT key, value FROM meta WHERE key IN ('send_rate', 'stagger_minutes', 'auto_advance', 'morning_hour', 'eod_hour')")
for row in cur.fetchall():
    print(row[0] + ": " + str(row[1]))

print("-" * 70)
print("10. GMAIL")
print("-" * 70)
cur.execute("SELECT key, value FROM meta WHERE key LIKE '%gmail%' OR key LIKE '%token%'")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(row[0] + ": " + str(row[1][:50] if row[1] else 'None'))
    print("Gmail tokens found")
else:
    print("No Gmail tokens - connect at /connect-gmail")

print("-" * 70)
print("11. DUPLICATES")
print("-" * 70)
cur.execute("SELECT name, COUNT(*) FROM batches GROUP BY name HAVING COUNT(*) > 1")
dups = cur.fetchall()
if dups:
    print("Duplicates: " + str(len(dups)))
    for row in dups:
        print("  '" + row[0] + "' x" + str(row[1]))
else:
    print("No duplicates")

print("=" * 70)
print("SUMMARY")
print("=" * 70)
cur.execute("SELECT COUNT(*) FROM recipients")
rec = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM sends WHERE status='sent'")
sent = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM batches WHERE status='running'")
run = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM batches WHERE status='draft'")
draft = cur.fetchone()[0]

print("Recipients: " + str(rec))
print("Sent: " + str(sent))
print("Running batches: " + str(run))
print("Draft batches: " + str(draft))
print("Blacklist: " + str(bl))
print("Zero-recipient batches: " + str(len(zero)))
print("CRITICAL ISSUES:")
print("1. Google Workspace expires June 5 - UPDATE PAYMENT")
print("2. " + str(len(zero)) + " batches have 0 recipients (delete duplicates)")
print("3. 3 batches show RUNNING - check if actually sending")
print("4. Check Settings tab for engine status")

cur.close()
conn.close()
print("Checkup complete!")
