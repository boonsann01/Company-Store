"""SQLite data layer for the company store kiosk.

Every function here opens the database, does one job, and closes it. The store
is a single file next to this module; there is no server and no ORM. Callers
are the Flask routes in admin_server.py.

Connections are opened through the `_cursor` context manager below rather than
by hand, so that closing (and, for writes, committing or rolling back) is
structural instead of something each function has to remember.
"""
import os
import sqlite3
import datetime
from contextlib import contextmanager

# Absolute so the database is always the one next to this file. A relative
# path resolves against the working directory, which silently creates a second
# empty store when main.py is run from anywhere but the project folder.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'store.db')

# How much history each view shows.
ANNOUNCEMENT_LIMIT = 15
TRANSACTION_LIMIT = 50
SUGGESTION_LIMIT = 50
EXPENSE_LIMIT = 100
TOP_ITEMS_LIMIT = 10
REVENUE_CHART_DAYS = 7

# Money is compared to the half-cent; anything closer is float noise.
CENT_TOLERANCE = 0.005


@contextmanager
def _cursor(commit=False):
    """Yield a cursor against the store, closing the connection afterwards.

    Read helpers call this bare. Writers pass commit=True, which commits when
    the body finishes cleanly and rolls back if it raises — so a half-applied
    sale can never be left behind.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn.cursor()
        if commit:
            conn.commit()
    except BaseException:
        # Deliberately BaseException: a KeyboardInterrupt mid-write must roll
        # back too. The exception is re-raised untouched.
        if commit:
            conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    """Create any missing tables and indexes. Safe to run on every start."""
    with _cursor(commit=True) as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                category TEXT NOT NULL, price REAL NOT NULL, stock INTEGER NOT NULL,
                max_stock INTEGER NOT NULL DEFAULT 0
            )
        ''')
        # Migration: max_stock arrived after the first databases were created.
        try:
            cur.execute('ALTER TABLE inventory ADD COLUMN max_stock INTEGER NOT NULL DEFAULT 0')
            cur.execute('UPDATE inventory SET max_stock = stock WHERE max_stock = 0')
        except sqlite3.OperationalError:
            pass  # Column already exists — this database has been through it
        cur.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, total REAL NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS transaction_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER,
                item_name TEXT, quantity INTEGER, price REAL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, message TEXT NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, message TEXT NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
                description TEXT NOT NULL, amount REAL NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL
            )
        ''')
        # Key/value store for admin-editable config, e.g. the Venmo handle.
        cur.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )
        ''')
        # One row per restock event; sales are reported between these dates.
        cur.execute('''
            CREATE TABLE IF NOT EXISTS restocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE
            )
        ''')

        # Inventory is addressed by name everywhere (update, delete, checkout),
        # so two rows sharing a name make every one of those operations hit
        # both: selling 5 units would deduct 5 from each. Enforce uniqueness in
        # the database. On a database that already holds duplicates the index
        # cannot be built — warn loudly rather than merging rows automatically,
        # since only a manager knows which row holds the real count.
        try:
            cur.execute(
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_name ON inventory(name)')
        except sqlite3.IntegrityError:
            dupes = cur.execute(
                'SELECT name, COUNT(*) FROM inventory GROUP BY name HAVING COUNT(*) > 1'
            ).fetchall()
            print('WARNING: duplicate inventory names present, uniqueness NOT enforced:')
            for name, count in dupes:
                print(f'  {count}x "{name}"')
            print('  Merge them in the admin panel, then restart to enable the guard.')

        _seed_starter_data(cur)


def _seed_starter_data(cur):
    """Populate a brand-new database so a fresh clone has something to show."""
    cur.execute('SELECT COUNT(*) FROM categories')
    if cur.fetchone()[0] != 0:
        return

    categories = [('Drinks',), ('Shelf Snacks',), ('Microwave',),
                  ('Frozen',), ('Candy',), ('Other',)]
    cur.executemany('INSERT INTO categories (name) VALUES (?)', categories)

    sample_items = [
        ('White Monster', 'Drinks', 3.00, 24), ('Celsius (Peach)', 'Drinks', 2.75, 20),
        ('Cup Noodles', 'Microwave', 1.50, 30), ('Shin Ramyun', 'Microwave', 2.00, 25),
        ("Ben & Jerry's", 'Frozen', 5.50, 10), ('Ice Cream Sand.', 'Frozen', 2.00, 15),
        ('Quest Bar', 'Shelf Snacks', 2.50, 20), ('Doritos (Nacho)', 'Shelf Snacks', 1.50, 15),
    ]
    # An item's first stock level becomes its restock baseline (max_stock).
    cur.executemany(
        'INSERT INTO inventory (name, category, price, stock, max_stock) VALUES (?, ?, ?, ?, ?)',
        [(n, c, p, s, s) for n, c, p, s in sample_items])

    cur.execute('INSERT INTO announcements (date, message) VALUES (?, ?)',
                (datetime.datetime.now().strftime('%m/%d/%Y · %I:%M %p'),
                 'Welcome to the new digital company store. Tap the screen to start your order!'))


# ── Inventory ─────────────────────────────────────────────────────────────────

def get_all_inventory():
    """Returns [(id, name, category, price, stock, max_stock), ...]."""
    with _cursor() as cur:
        return cur.execute(
            'SELECT id, name, category, price, stock, max_stock FROM inventory').fetchall()


def add_inventory_item(name, category, price, stock):
    name = name.strip()
    if not name:
        raise ValueError('Item name cannot be blank.')
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')

    duplicate = f'"{name}" is already in inventory — use Update to change it.'
    with _cursor(commit=True) as cur:
        # Checked here as well as by the unique index: the index is absent on
        # any database that still holds duplicates, and this is the message the
        # manager actually sees in the admin panel.
        if cur.execute('SELECT 1 FROM inventory WHERE name = ?', (name,)).fetchone():
            raise ValueError(duplicate)
        try:
            cur.execute(
                'INSERT INTO inventory (name, category, price, stock, max_stock) '
                'VALUES (?, ?, ?, ?, ?)',
                (name, category, price, stock, stock))
        except sqlite3.IntegrityError:
            raise ValueError(duplicate)


def update_inventory_item(name, category, price, stock):
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')
    with _cursor(commit=True) as cur:
        # max_stock only ever grows: it is the item's restock baseline, so
        # selling down to 2 must not redefine "full" as 2.
        cur.execute(
            'UPDATE inventory SET category = ?, price = ?, stock = ?, '
            'max_stock = MAX(max_stock, ?) WHERE name = ?',
            (category, price, stock, stock, name))


def delete_inventory_item(name):
    with _cursor(commit=True) as cur:
        cur.execute('DELETE FROM inventory WHERE name = ?', (name,))


# ── Sales ─────────────────────────────────────────────────────────────────────

def _whole_quantity(name, details):
    """Extract a whole-number quantity from one cart line, or raise.

    Truncating would be wrong here: a request for 2.7 units is malformed, and
    silently selling 2 hides the defect behind a confusing "prices changed"
    message downstream.
    """
    try:
        raw = details['quantity']
    except (TypeError, KeyError):
        raise ValueError(f'Invalid quantity for {name}.')
    # bool is an int subclass — True would otherwise slip through as 1.
    if isinstance(raw, bool):
        raise ValueError(f'Invalid quantity for {name}.')
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f'Invalid quantity for {name}.')
    if qty != raw:
        raise ValueError(f'Invalid quantity for {name}.')
    return qty


def log_transaction(cart_dict, total_amount=None):
    """Record a sale and deduct stock. Returns the authoritative total.

    Prices and the order total come from the database, never from the client.
    The kiosk posts whatever total it computed, and every analytics figure
    (revenue, profit, margin, average order) derives from that number — so a
    tampered or stale client could otherwise book a $3.00 sale as $0.01.

    total_amount, when supplied, is treated as a claim to be checked rather
    than a value to store: a mismatch means the kiosk's prices went stale
    mid-order, and the sale is rejected so the customer can re-review instead
    of being shown a Venmo QR for a different amount than the store records.
    """
    if not cart_dict:
        # An empty cart would otherwise commit a $0.00 transaction, inflating
        # tx_count — the divisor behind avg_order on the analytics page.
        raise ValueError('Cart is empty.')

    with _cursor(commit=True) as cur:
        priced = []
        for name, details in cart_dict.items():
            qty = _whole_quantity(name, details)
            row = cur.execute('SELECT stock, price FROM inventory WHERE name = ?',
                              (name,)).fetchone()
            if row is None:
                raise ValueError(f'{name} is no longer in inventory.')
            stock, price = row
            if qty < 1 or qty > stock:
                raise ValueError(f'Only {stock} {name} in stock.')
            priced.append((name, qty, price))

        server_total = round(sum(qty * price for _, qty, price in priced), 2)

        if total_amount is not None:
            try:
                claimed = round(float(total_amount), 2)
            except (TypeError, ValueError):
                raise ValueError('Invalid order total.')
            if abs(claimed - server_total) > CENT_TOLERANCE:
                raise ValueError('Prices changed — please review your order.')

        cur.execute('INSERT INTO transactions (timestamp, total) VALUES (?, ?)',
                    (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), server_total))
        transaction_id = cur.lastrowid

        for name, qty, price in priced:
            cur.execute(
                'INSERT INTO transaction_items (transaction_id, item_name, quantity, price) '
                'VALUES (?, ?, ?, ?)',
                (transaction_id, name, qty, price))
            # The stock check above ran before this transaction opened, so a
            # concurrent sale could have taken the units since. Re-check inside
            # the UPDATE itself: if the row no longer has the stock it matches
            # nothing, and the whole sale rolls back rather than going negative.
            cur.execute(
                'UPDATE inventory SET stock = stock - ? WHERE name = ? AND stock >= ?',
                (qty, name, qty))
            if cur.rowcount != 1:
                raise ValueError(f'{name} just sold out — please review your order.')

        return server_total


def get_recent_transactions(limit=TRANSACTION_LIMIT):
    """Most recent transactions, newest first, each with its line items.

    Returns [{'id', 'timestamp', 'total', 'items': [(qty, name, price), ...]}].
    """
    with _cursor() as cur:
        # One query, not one per transaction. The previous version issued a
        # follow-up SELECT for every row returned, which dominated the cost of
        # the admin page's 8-second poll.
        rows = cur.execute('''
            SELECT t.id, t.timestamp, t.total, ti.quantity, ti.item_name, ti.price
            FROM (SELECT id, timestamp, total FROM transactions
                  ORDER BY id DESC LIMIT ?) AS t
            LEFT JOIN transaction_items ti ON ti.transaction_id = t.id
            ORDER BY t.id DESC
        ''', (limit,)).fetchall()

    transactions = []
    by_id = {}
    for tx_id, timestamp, total, qty, item_name, price in rows:
        transaction = by_id.get(tx_id)
        if transaction is None:
            transaction = {'id': tx_id, 'timestamp': timestamp, 'total': total, 'items': []}
            by_id[tx_id] = transaction
            transactions.append(transaction)
        # LEFT JOIN yields a NULL row for a transaction with no line items.
        if item_name is not None:
            transaction['items'].append((qty, item_name, price))
    return transactions


def get_transaction_count():
    with _cursor() as cur:
        return cur.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]


def get_total_revenue():
    with _cursor() as cur:
        revenue = cur.execute('SELECT SUM(total) FROM transactions').fetchone()[0]
    return revenue or 0.0


def get_sales_for_period(start_date, end_date=None):
    """Units sold and revenue per item between two restock dates.

    start_date is inclusive; end_date is exclusive (the day of the next
    restock). end_date=None means "through the present".
    Returns [(item_name, total_qty, total_rev), ...] sorted by qty descending.
    """
    clause = 'DATE(t.timestamp) >= ?'
    params = [start_date]
    if end_date:
        clause += ' AND DATE(t.timestamp) < ?'
        params.append(end_date)

    with _cursor() as cur:
        return cur.execute(f'''
            SELECT ti.item_name, SUM(ti.quantity) AS qty, SUM(ti.quantity * ti.price) AS rev
            FROM transaction_items ti
            JOIN transactions t ON ti.transaction_id = t.id
            WHERE {clause}
            GROUP BY ti.item_name
            ORDER BY qty DESC
        ''', params).fetchall()


# ── Announcements ─────────────────────────────────────────────────────────────

def get_announcements():
    with _cursor() as cur:
        return cur.execute(
            'SELECT date, message FROM announcements ORDER BY id DESC LIMIT ?',
            (ANNOUNCEMENT_LIMIT,)).fetchall()


def add_announcement(message):
    with _cursor(commit=True) as cur:
        cur.execute('INSERT INTO announcements (date, message) VALUES (?, ?)',
                    (datetime.datetime.now().strftime('%m/%d/%Y · %I:%M %p'), message))


# ── Suggestions (read-only) ───────────────────────────────────────────────────
# The kiosk's suggestion box was removed; entries collected while it was live
# are retained and still shown in the admin panel.

def get_suggestions(limit=SUGGESTION_LIMIT):
    with _cursor() as cur:
        return cur.execute(
            'SELECT id, timestamp, message FROM suggestions ORDER BY id DESC LIMIT ?',
            (limit,)).fetchall()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, default=''):
    with _cursor() as cur:
        row = cur.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with _cursor(commit=True) as cur:
        cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))


# ── Restocks ──────────────────────────────────────────────────────────────────

def add_restock(date_str):
    """date_str: YYYY-MM-DD. Silently ignores a date already logged."""
    with _cursor(commit=True) as cur:
        cur.execute('INSERT OR IGNORE INTO restocks (date) VALUES (?)', (date_str,))


def get_restocks():
    """Returns [(id, 'YYYY-MM-DD'), ...] oldest first."""
    with _cursor() as cur:
        return cur.execute('SELECT id, date FROM restocks ORDER BY date ASC').fetchall()


def delete_restock(restock_id):
    with _cursor(commit=True) as cur:
        cur.execute('DELETE FROM restocks WHERE id = ?', (restock_id,))


# ── Categories ────────────────────────────────────────────────────────────────

def get_categories():
    with _cursor() as cur:
        return [row[0] for row in
                cur.execute('SELECT name FROM categories ORDER BY name').fetchall()]


def add_category(name):
    """Adding a category that already exists is a no-op, not an error."""
    with _cursor(commit=True) as cur:
        cur.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (name,))


# ── Expenses ──────────────────────────────────────────────────────────────────

def add_expense(date, description, amount):
    if amount < 0:
        raise ValueError('Amount cannot be negative.')
    with _cursor(commit=True) as cur:
        cur.execute('INSERT INTO expenses (date, description, amount) VALUES (?, ?, ?)',
                    (date, description, amount))


def delete_expense(expense_id):
    with _cursor(commit=True) as cur:
        cur.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))


def get_expense_log(limit=EXPENSE_LIMIT):
    with _cursor() as cur:
        return cur.execute(
            'SELECT id, date, description, amount FROM expenses ORDER BY id DESC LIMIT ?',
            (limit,)).fetchall()


def get_total_expenses():
    with _cursor() as cur:
        total = cur.execute('SELECT SUM(amount) FROM expenses').fetchone()[0]
    return total or 0.0


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_top_items(limit=TOP_ITEMS_LIMIT):
    """Returns [(name, units_sold, revenue), ...] best-selling first."""
    with _cursor() as cur:
        return cur.execute('''
            SELECT item_name, SUM(quantity) AS total_qty, SUM(quantity * price) AS total_rev
            FROM transaction_items
            GROUP BY item_name
            ORDER BY total_qty DESC
            LIMIT ?
        ''', (limit,)).fetchall()


def get_category_revenue():
    """Returns [(category, revenue), ...] highest first.

    Items sold and later deleted from inventory have no category to join
    against, so they are grouped under 'Unknown' rather than dropped.
    """
    with _cursor() as cur:
        return cur.execute('''
            SELECT COALESCE(i.category, 'Unknown') AS category,
                   SUM(ti.quantity * ti.price) AS total_rev
            FROM transaction_items ti
            LEFT JOIN inventory i ON ti.item_name = i.name
            GROUP BY category
            ORDER BY total_rev DESC
        ''').fetchall()


def get_daily_revenue(days=REVENUE_CHART_DAYS):
    """Returns [(YYYY-MM-DD, revenue), ...] oldest first. Days with no sales are absent."""
    with _cursor() as cur:
        return cur.execute('''
            SELECT DATE(timestamp) AS day, SUM(total) AS day_total
            FROM transactions
            WHERE DATE(timestamp) >= DATE('now', ?)
            GROUP BY day
            ORDER BY day ASC
        ''', (f'-{days - 1} days',)).fetchall()


if __name__ == '__main__':
    init_db()
