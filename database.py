import os
import sqlite3
import datetime

# Absolute so the database is always the one next to this file. A relative
# path resolves against the working directory, which silently creates a second
# empty store when main.py is run from anywhere but the project folder.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'store.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category TEXT NOT NULL, price REAL NOT NULL, stock INTEGER NOT NULL,
            max_stock INTEGER NOT NULL DEFAULT 0
        )
    ''')
    # Migration: add max_stock column to existing databases
    try:
        cursor.execute('ALTER TABLE inventory ADD COLUMN max_stock INTEGER NOT NULL DEFAULT 0')
        cursor.execute('UPDATE inventory SET max_stock = stock WHERE max_stock = 0')
    except Exception:
        pass  # Column already exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, total REAL NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transaction_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER,
            item_name TEXT, quantity INTEGER, price REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, message TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            message TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL
        )
    ''')
    # --- NEW: Categories Table ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL
        )
    ''')
    # --- Settings Table (key/value store for admin-editable config) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )
    ''')
    # --- Restocks Table (one row per restock event) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS restocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE
        )
    ''')

    # Inventory is addressed by name everywhere (update, delete, checkout), so
    # two rows sharing a name make every one of those operations hit both:
    # selling 5 units would deduct 5 from each row. Enforce uniqueness at the
    # database level. On a database that already contains duplicates the index
    # cannot be built — warn loudly rather than merging rows automatically,
    # since only a manager knows which row holds the real count.
    try:
        cursor.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_name ON inventory(name)')
    except sqlite3.IntegrityError:
        dupes = cursor.execute(
            'SELECT name, COUNT(*) FROM inventory GROUP BY name HAVING COUNT(*) > 1'
        ).fetchall()
        print('WARNING: duplicate inventory names present, uniqueness NOT enforced:')
        for name, count in dupes:
            print(f'  {count}x "{name}"')
        print('  Merge them in the admin panel, then restart to enable the guard.')

    # Inject Starter Data
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        # Pre-fill standard categories
        cats = [('Drinks',), ('Shelf Snacks',), ('Microwave',), ('Frozen',), ('Candy',), ('Other',)]
        cursor.executemany('INSERT INTO categories (name) VALUES (?)', cats)
        
        sample_items = [
            ('White Monster', 'Drinks', 3.00, 24), ('Celsius (Peach)', 'Drinks', 2.75, 20),
            ('Cup Noodles', 'Microwave', 1.50, 30), ('Shin Ramyun', 'Microwave', 2.00, 25),
            ('Ben & Jerry\'s', 'Frozen', 5.50, 10), ('Ice Cream Sand.', 'Frozen', 2.00, 15),
            ('Quest Bar', 'Shelf Snacks', 2.50, 20), ('Doritos (Nacho)', 'Shelf Snacks', 1.50, 15)
        ]
        cursor.executemany('INSERT INTO inventory (name, category, price, stock, max_stock) VALUES (?, ?, ?, ?, ?)',
                           [(n, c, p, s, s) for n, c, p, s in sample_items])
        seed_ts = datetime.datetime.now().strftime("%m/%d/%Y · %I:%M %p")
        cursor.execute('INSERT INTO announcements (date, message) VALUES (?, ?)', (seed_ts, "Welcome to the new digital company store. Tap the screen to start your order!"))
        conn.commit()

    conn.close()
    print("Database upgraded with Categories and Delete functionality.")

def ensure_suggestions_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            message TEXT NOT NULL
        )
    ''')
    conn.commit(); conn.close()

# --- INVENTORY & TRANSACTIONS ---
def get_inventory():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, category, price, stock FROM inventory WHERE stock > 0')
    items = cursor.fetchall(); conn.close()
    return items

def get_all_inventory():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, category, price, stock, max_stock FROM inventory')
    items = cursor.fetchall(); conn.close()
    return items

def add_inventory_item(name, category, price, stock):
    name = name.strip()
    if not name:
        raise ValueError('Item name cannot be blank.')
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Checked here as well as by the unique index: the index is missing on any
    # database that still holds duplicates, and this message is the one the
    # manager actually sees in the admin panel.
    existing = cursor.execute('SELECT 1 FROM inventory WHERE name = ?', (name,)).fetchone()
    if existing:
        conn.close()
        raise ValueError(f'"{name}" is already in inventory — use Update to change it.')
    try:
        cursor.execute('INSERT INTO inventory (name, category, price, stock, max_stock) VALUES (?, ?, ?, ?, ?)',
                       (name, category, price, stock, stock))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError(f'"{name}" is already in inventory — use Update to change it.')
    finally:
        conn.close()

def update_inventory_item(name, category, price, stock):
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE inventory SET category = ?, price = ?, stock = ?, max_stock = MAX(max_stock, ?) WHERE name = ?',
        (category, price, stock, stock, name)
    )
    conn.commit(); conn.close()

# --- NEW: Delete Item ---
def delete_inventory_item(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE name = ?', (name,))
    conn.commit(); conn.close()

def _whole_quantity(name, details):
    """Extract a whole-number quantity from one cart line, or raise.

    Truncating would be wrong here: a request for 2.7 units is malformed, and
    silently selling 2 hides the defect behind a confusing "prices changed"
    message downstream when the client's total no longer matches.
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
    tampered or stale client could book a $3.00 sale as $0.01.

    total_amount, when supplied, is treated as a claim to be checked rather
    than a value to store: a mismatch means the kiosk's prices went stale
    mid-order, and the sale is rejected so the customer can re-review instead
    of being shown a Venmo QR for a different amount than the store records.
    """
    if not cart_dict:
        # An empty cart would otherwise commit a $0.00 transaction, inflating
        # tx_count — the divisor behind avg_order on the analytics page.
        raise ValueError('Cart is empty.')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        priced = []
        for name, details in cart_dict.items():
            qty = _whole_quantity(name, details)
            cursor.execute('SELECT stock, price FROM inventory WHERE name = ?', (name,))
            row = cursor.fetchone()
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
            if abs(claimed - server_total) > 0.005:
                raise ValueError('Prices changed — please review your order.')

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('INSERT INTO transactions (timestamp, total) VALUES (?, ?)',
                       (timestamp, server_total))
        transaction_id = cursor.lastrowid
        for name, qty, price in priced:
            cursor.execute('INSERT INTO transaction_items (transaction_id, item_name, quantity, price) VALUES (?, ?, ?, ?)',
                           (transaction_id, name, qty, price))
            # The stock check above ran in autocommit, before this transaction
            # opened, so a concurrent sale could have consumed the units since.
            # Re-check inside the UPDATE itself: if the row no longer has the
            # stock, it matches nothing and we roll the whole sale back rather
            # than driving stock negative.
            cursor.execute(
                'UPDATE inventory SET stock = stock - ? WHERE name = ? AND stock >= ?',
                (qty, name, qty))
            if cursor.rowcount != 1:
                raise ValueError(f'{name} just sold out — please review your order.')
        conn.commit()
        return server_total
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_total_revenue():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(total) FROM transactions')
    revenue = cursor.fetchone()[0]; conn.close()
    return revenue if revenue else 0.0

def get_recent_transactions(limit=50):
    """Fetches the most recent transactions and their associated items."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get the overarching transactions (Newest first)
    cursor.execute('SELECT id, timestamp, total FROM transactions ORDER BY id DESC LIMIT ?', (limit,))
    tx_rows = cursor.fetchall()
    
    transactions = []
    for tx in tx_rows:
        tx_id, timestamp, total = tx
        # For each transaction, grab the specific items bought
        cursor.execute('SELECT quantity, item_name, price FROM transaction_items WHERE transaction_id = ?', (tx_id,))
        items = cursor.fetchall()
        
        transactions.append({
            'id': tx_id,
            'timestamp': timestamp,
            'total': total,
            'items': items
        })
        
    conn.close()
    return transactions

# --- ANNOUNCEMENTS & CATEGORIES ---
def get_announcements():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT date, message FROM announcements ORDER BY id DESC LIMIT 15')
    news = cursor.fetchall(); conn.close()
    return news

def add_announcement(message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%m/%d/%Y · %I:%M %p")
    cursor.execute('INSERT INTO announcements (date, message) VALUES (?, ?)', (timestamp, message))
    conn.commit(); conn.close()

# --- SUGGESTIONS & FEEDBACK ---
def add_suggestion(message):
    clean_message = message.strip()
    if not clean_message:
        raise ValueError('Suggestion cannot be blank.')

    ensure_suggestions_table()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO suggestions (timestamp, message) VALUES (?, ?)', (timestamp, clean_message))
    conn.commit(); conn.close()

def get_suggestions(limit=50):
    ensure_suggestions_table()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, message FROM suggestions ORDER BY id DESC LIMIT ?', (limit,))
    suggestions = cursor.fetchall(); conn.close()
    return suggestions

# --- Settings (key/value) ---
def get_setting(key, default=''):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone(); conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit(); conn.close()

# --- Restock Tracking ---
def add_restock(date_str):
    """date_str: YYYY-MM-DD.  Silently ignores duplicate dates."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO restocks (date) VALUES (?)', (date_str,))
    conn.commit(); conn.close()

def get_restocks():
    """Returns [(id, 'YYYY-MM-DD'), ...] sorted ascending by date."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, date FROM restocks ORDER BY date ASC')
    rows = cursor.fetchall(); conn.close()
    return rows

def delete_restock(restock_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM restocks WHERE id = ?', (restock_id,))
    conn.commit(); conn.close()

def get_sales_for_period(start_date, end_date=None):
    """
    Aggregate units sold + revenue between restock dates.
    start_date inclusive, end_date exclusive (the day of the next restock).
    end_date=None means through present.
    Returns [(item_name, total_qty, total_rev), ...] sorted by qty DESC.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if end_date:
        cursor.execute('''
            SELECT ti.item_name, SUM(ti.quantity) AS qty,
                   SUM(ti.quantity * ti.price)    AS rev
            FROM transaction_items ti
            JOIN transactions t ON ti.transaction_id = t.id
            WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) < ?
            GROUP BY ti.item_name
            ORDER BY qty DESC
        ''', (start_date, end_date))
    else:
        cursor.execute('''
            SELECT ti.item_name, SUM(ti.quantity) AS qty,
                   SUM(ti.quantity * ti.price)    AS rev
            FROM transaction_items ti
            JOIN transactions t ON ti.transaction_id = t.id
            WHERE DATE(t.timestamp) >= ?
            GROUP BY ti.item_name
            ORDER BY qty DESC
        ''', (start_date,))
    rows = cursor.fetchall(); conn.close()
    return rows

# --- NEW: Category Functions ---
def get_categories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories ORDER BY name')
    cats = [row[0] for row in cursor.fetchall()]; conn.close()
    return cats

def add_category(name):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Ignores if you try to add a duplicate category
    finally:
        conn.close()

# --- EXPENSES ---
def add_expense(date, description, amount):
    if amount < 0:
        raise ValueError('Amount cannot be negative.')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO expenses (date, description, amount) VALUES (?, ?, ?)',
                   (date, description, amount))
    conn.commit(); conn.close()

def delete_expense(expense_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
    conn.commit(); conn.close()

def get_expense_log(limit=100):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, date, description, amount FROM expenses ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall(); conn.close()
    return rows

def get_total_expenses():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(amount) FROM expenses')
    result = cursor.fetchone()[0]; conn.close()
    return result if result else 0.0

# --- ANALYTICS ---
def get_transaction_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM transactions')
    count = cursor.fetchone()[0]; conn.close()
    return count

def get_top_items(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT item_name, SUM(quantity) AS total_qty, SUM(quantity * price) AS total_rev
        FROM transaction_items
        GROUP BY item_name
        ORDER BY total_qty DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall(); conn.close()
    return rows  # [(name, qty, revenue), ...]

def get_category_revenue():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(i.category, 'Unknown') AS category,
               SUM(ti.quantity * ti.price) AS total_rev
        FROM transaction_items ti
        LEFT JOIN inventory i ON ti.item_name = i.name
        GROUP BY category
        ORDER BY total_rev DESC
    ''')
    rows = cursor.fetchall(); conn.close()
    return rows  # [(category, revenue), ...]

def get_daily_revenue(days=7):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DATE(timestamp) AS day, SUM(total) AS day_total
        FROM transactions
        WHERE DATE(timestamp) >= DATE('now', ?)
        GROUP BY day
        ORDER BY day ASC
    ''', (f'-{days - 1} days',))
    rows = cursor.fetchall(); conn.close()
    return rows  # [(date_str, revenue), ...]

if __name__ == "__main__":
    init_db()
