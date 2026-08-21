"""Data-layer tests: inventory integrity, sale pricing, stock accounting.

Every case here corresponds to a bug that actually reached the working tree.
"""
import sys
import threading

from _harness import Results, use_temp_database
import database

r = Results('database')
use_temp_database()


# ── Database location ─────────────────────────────────────────────────────────
r.section('database file resolves next to the code, not the working directory')
import os
r.check('DB_PATH is absolute', os.path.isabs(database.DB_PATH), database.DB_PATH)

# A relative path silently created a second empty store whenever main.py ran
# from anywhere but the project folder.
import tempfile
elsewhere = tempfile.mkdtemp()
prev = os.getcwd()
try:
    os.chdir(elsewhere)
    seen = len(database.get_all_inventory())
    r.check('reads the same database from another directory', seen > 0, f'{seen} items')
    r.check('creates no stray store.db in the working directory',
            not os.path.exists(os.path.join(elsewhere, 'store.db')))
finally:
    os.chdir(prev)


# ── Inventory name uniqueness ─────────────────────────────────────────────────
r.section('duplicate item names cannot be created')
# Two rows sharing a name meant update/delete/checkout hit BOTH: selling 5
# units deducted 5 from each.
database.add_inventory_item('Widget', 'Other', 1.50, 10)
r.raises('adding the same name twice raises',
         ValueError, database.add_inventory_item, 'Widget', 'Other', 9.99, 5)
r.raises('whitespace-padded duplicate also raises',
         ValueError, database.add_inventory_item, '  Widget  ', 'Other', 9.99, 5)
names = [i[1] for i in database.get_all_inventory()]
r.check('exactly one row named Widget', names.count('Widget') == 1, f'{names.count("Widget")}')

r.raises('blank name rejected', ValueError, database.add_inventory_item, '', 'Other', 1.0, 1)
r.raises('whitespace-only name rejected', ValueError,
         database.add_inventory_item, '   ', 'Other', 1.0, 1)
r.check('no blank-named rows exist',
        not any(i[1].strip() == '' for i in database.get_all_inventory()))

r.section('one sale deducts one row')
before = sum(i[4] for i in database.get_all_inventory() if i[1] == 'Widget')
database.log_transaction({'Widget': {'quantity': 5, 'price': 1.50}}, 7.50)
after = sum(i[4] for i in database.get_all_inventory() if i[1] == 'Widget')
r.check('selling 5 removes exactly 5 units', before - after == 5, f'{before} -> {after}')


# ── Sale pricing ──────────────────────────────────────────────────────────────
r.section('the server prices the sale, never the client')
database.add_inventory_item('Cola', 'Drinks', 3.00, 50)

rev0 = database.get_total_revenue()
r.raises('understated total rejected', ValueError,
         database.log_transaction, {'Cola': {'quantity': 1, 'price': 3.00}}, 0.01)
r.check('no revenue booked from the rejected order',
        database.get_total_revenue() == rev0, f'{database.get_total_revenue()}')

r.raises('inflated total rejected', ValueError,
         database.log_transaction, {'Cola': {'quantity': 1, 'price': 3.00}}, 999.0)
r.raises('forged unit price rejected', ValueError,
         database.log_transaction, {'Cola': {'quantity': 2, 'price': 0.01}}, 0.02)

rev1 = database.get_total_revenue()
total = database.log_transaction({'Cola': {'quantity': 3, 'price': 3.00}}, 9.00)
r.check('honest order accepted and returns the authoritative total', total == 9.00, f'{total}')
r.check('revenue reflects the database price',
        round(database.get_total_revenue() - rev1, 2) == 9.00)
line_prices = [item[2] for item in database.get_recent_transactions(1)[0]['items']]
r.check('line items store the database price', all(p == 3.00 for p in line_prices), f'{line_prices}')

r.section('quantities must be whole numbers')
# Truncating 2.7 to 2 hid the defect behind a confusing "prices changed" error.
for bad in [2.7, 0.5, 'abc', None, True, [1], -1, 0]:
    r.raises(f'quantity={bad!r} rejected', ValueError,
             database.log_transaction, {'Cola': {'quantity': bad, 'price': 3.00}}, 3.00)
ok = database.log_transaction({'Cola': {'quantity': 2.0, 'price': 3.00}}, 6.00)
r.check('whole-number float (2.0) accepted', ok == 6.00, f'{ok}')

r.section('an empty cart is not a sale')
# An empty cart committed a $0.00 transaction, inflating the tx_count that
# avg_order divides by.
n0 = database.get_transaction_count()
r.raises('empty cart rejected', ValueError, database.log_transaction, {}, 0)
r.check('no phantom transaction row', database.get_transaction_count() == n0)

r.section('unknown items and oversells are refused')
r.raises('unknown item rejected', ValueError,
         database.log_transaction, {'Nonexistent': {'quantity': 1, 'price': 1.0}}, 1.0)
stock = [i[4] for i in database.get_all_inventory() if i[1] == 'Cola'][0]
r.raises('oversell rejected', ValueError,
         database.log_transaction, {'Cola': {'quantity': stock + 1, 'price': 3.00}},
         round(3.00 * (stock + 1), 2))
r.check('stock unchanged after refused oversell',
        [i[4] for i in database.get_all_inventory() if i[1] == 'Cola'][0] == stock)


# ── Concurrency ───────────────────────────────────────────────────────────────
r.section('concurrent sales cannot oversell')
# The stock check runs before the write transaction opens, so two callers could
# both pass it and both commit. The UPDATE re-checks stock in its WHERE clause.
def contend(item_name, units, threads):
    database.add_inventory_item(item_name, 'Other', 2.00, units)
    errors = []

    def buy():
        try:
            database.log_transaction({item_name: {'quantity': 1, 'price': 2.00}}, 2.00)
        except Exception as exc:
            errors.append(str(exc))

    workers = [threading.Thread(target=buy) for _ in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    left = [i[4] for i in database.get_all_inventory() if i[1] == item_name][0]
    return errors, left

errs, left = contend('Solo', 1, 2)
r.check('2 buyers, 1 unit: one rejected', len(errs) == 1, f'rejected={len(errs)}')
r.check('2 buyers, 1 unit: stock lands on 0, never negative', left == 0, f'stock={left}')

errs, left = contend('Trio', 3, 8)
r.check('8 buyers, 3 units: exactly 5 rejected', len(errs) == 5, f'rejected={len(errs)}')
r.check('8 buyers, 3 units: stock lands on 0', left == 0, f'stock={left}')


# ── Low stock rule ────────────────────────────────────────────────────────────
r.section('low-stock rule is defined once')
from admin_server import is_low_stock
database.add_inventory_item('BigBox', 'Other', 1.0, 50)
database.update_inventory_item('BigBox', 'Other', 1.0, 10)      # 10/50 = 20%
inv = database.get_all_inventory()
row = [i for i in inv if i[1] == 'BigBox'][0]
r.check('item at 20% of baseline counts as low', is_low_stock(row[4], row[5]), f'{row[4]}/{row[5]}')
r.check('item at full stock does not', not is_low_stock(50, 50))
r.check('item with no baseline falls back to a flat threshold', is_low_stock(0, 0))

sys.exit(r.finish())
