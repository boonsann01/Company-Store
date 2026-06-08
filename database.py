import sqlite3
import datetime

def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category TEXT NOT NULL, price REAL NOT NULL, stock INTEGER NOT NULL
        )
    ''')
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
        cursor.executemany('INSERT INTO inventory (name, category, price, stock) VALUES (?, ?, ?, ?)', sample_items)
        seed_ts = datetime.datetime.now().strftime("%m/%d/%Y · %I:%M %p")
        cursor.execute('INSERT INTO announcements (date, message) VALUES (?, ?)', (seed_ts, "Welcome to the new digital company store. Tap the screen to start your order!"))
        conn.commit()

    conn.close()
    print("Database upgraded with Categories and Delete functionality.")

def ensure_suggestions_table():
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, category, price, stock FROM inventory WHERE stock > 0')
    items = cursor.fetchall(); conn.close()
    return items

def get_all_inventory():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, category, price, stock FROM inventory')
    items = cursor.fetchall(); conn.close()
    return items

def add_inventory_item(name, category, price, stock):
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO inventory (name, category, price, stock) VALUES (?, ?, ?, ?)', (name, category, price, stock))
    conn.commit(); conn.close()

def update_inventory_item(name, category, price, stock):
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE inventory SET category = ?, price = ?, stock = ? WHERE name = ?', (category, price, stock, name))
    conn.commit(); conn.close()

# --- NEW: Delete Item ---
def delete_inventory_item(name):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE name = ?', (name,))
    conn.commit(); conn.close()

def log_transaction(cart_dict, total_amount):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    try:
        for name, details in cart_dict.items():
            qty = details['quantity']
            cursor.execute('SELECT stock FROM inventory WHERE name = ?', (name,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f'{name} is no longer in inventory.')
            if qty < 1 or qty > row[0]:
                raise ValueError(f'Only {row[0]} {name} in stock.')

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('INSERT INTO transactions (timestamp, total) VALUES (?, ?)', (timestamp, total_amount))
        transaction_id = cursor.lastrowid
        for name, details in cart_dict.items():
            qty = details['quantity']; price = details['price']
            cursor.execute('INSERT INTO transaction_items (transaction_id, item_name, quantity, price) VALUES (?, ?, ?, ?)', (transaction_id, name, qty, price))
            cursor.execute('UPDATE inventory SET stock = stock - ? WHERE name = ?', (qty, name))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_total_revenue():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(total) FROM transactions')
    revenue = cursor.fetchone()[0]; conn.close()
    return revenue if revenue else 0.0

def get_recent_transactions(limit=50):
    """Fetches the most recent transactions and their associated items."""
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, message FROM announcements ORDER BY id DESC LIMIT 15')
    news = cursor.fetchall(); conn.close()
    return news

def add_announcement(message):
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO suggestions (timestamp, message) VALUES (?, ?)', (timestamp, clean_message))
    conn.commit(); conn.close()

def get_suggestions(limit=50):
    ensure_suggestions_table()
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, message FROM suggestions ORDER BY id DESC LIMIT ?', (limit,))
    suggestions = cursor.fetchall(); conn.close()
    return suggestions

# --- Settings (key/value) ---
def get_setting(key, default=''):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone(); conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit(); conn.close()

# --- Restock Tracking ---
def add_restock(date_str):
    """date_str: YYYY-MM-DD.  Silently ignores duplicate dates."""
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO restocks (date) VALUES (?)', (date_str,))
    conn.commit(); conn.close()

def get_restocks():
    """Returns [(id, 'YYYY-MM-DD'), ...] sorted ascending by date."""
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, date FROM restocks ORDER BY date ASC')
    rows = cursor.fetchall(); conn.close()
    return rows

def delete_restock(restock_id):
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories ORDER BY name')
    cats = [row[0] for row in cursor.fetchall()]; conn.close()
    return cats

def add_category(name):
    try:
        conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO expenses (date, description, amount) VALUES (?, ?, ?)',
                   (date, description, amount))
    conn.commit(); conn.close()

def delete_expense(expense_id):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
    conn.commit(); conn.close()

def get_expense_log(limit=100):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, date, description, amount FROM expenses ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall(); conn.close()
    return rows

def get_total_expenses():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(amount) FROM expenses')
    result = cursor.fetchone()[0]; conn.close()
    return result if result else 0.0

# --- ANALYTICS ---
def get_transaction_count():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM transactions')
    count = cursor.fetchone()[0]; conn.close()
    return count

def get_top_items(limit=10):
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
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
    conn = sqlite3.connect('store.db')
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
