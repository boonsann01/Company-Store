"""
One-time pre-launch reset — clears all test transaction and expense data.

Run ONCE before going live:
    python reset_analytics.py

Keeps untouched: inventory, categories, settings, restocks, announcements, suggestions.
"""
import sqlite3
import os

DB = 'store.db'

if not os.path.exists(DB):
    print(f"ERROR: {DB} not found. Run main.py first to create the database.")
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cursor = conn.cursor()

# Count rows before deletion so user can confirm what was cleared
cursor.execute('SELECT COUNT(*) FROM transactions')
tx_count = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM transaction_items')
ti_count = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM expenses')
ex_count = cursor.fetchone()[0]

print(f"\nAbout to delete:")
print(f"  {tx_count:>6} transaction(s)")
print(f"  {ti_count:>6} transaction item(s)")
print(f"  {ex_count:>6} expense(s)")

confirm = input("\nType YES to confirm: ").strip()
if confirm != 'YES':
    print("Aborted — nothing was changed.")
    conn.close()
    raise SystemExit(0)

cursor.execute('DELETE FROM transaction_items')
cursor.execute('DELETE FROM transactions')
cursor.execute('DELETE FROM expenses')

# Reset auto-increment ID counters so new records start from 1
cursor.execute(
    "DELETE FROM sqlite_sequence WHERE name IN ('transactions', 'transaction_items', 'expenses')"
)

conn.commit()
conn.close()

print("\nDone. Analytics data cleared. IDs reset to 1.")
print("Inventory, categories, settings, restocks, and announcements are untouched.")
