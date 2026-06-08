import os
import io
import base64
import datetime
from functools import wraps
from secrets import compare_digest
from urllib.parse import quote

from flask import (Flask, render_template, render_template_string,
                   request, redirect, session, url_for, jsonify)
import database

# Set VENMO_USERNAME env var before fielding on Pi
VENMO_USERNAME = os.environ.get('VENMO_USERNAME', 'YourVenmoHere')

_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(_BASE, 'templates'),
            static_folder=os.path.join(_BASE, 'static'))
app.secret_key = os.environ.get('STORE_ADMIN_SECRET_KEY', 'change-this-before-fielding')

ADMIN_USERNAME = os.environ.get('STORE_ADMIN_USERNAME', 'b1_admin')
ADMIN_PASSWORD = os.environ.get('STORE_ADMIN_PASSWORD', 'Letsgobarbs01$')

# ── Helpers ───────────────────────────────────────────────────────────────────

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)
    return wrapped_view


def set_admin_alert(message, style='danger'):
    session['admin_alert'] = {'message': message, 'style': style}


def parse_inventory_values():
    try:
        price = float(request.form.get('price', ''))
        stock = int(request.form.get('stock', ''))
    except ValueError:
        raise ValueError('Price and stock must be valid numbers.')
    if price < 0 or stock < 0:
        raise ValueError('Price and stock cannot be negative.')
    return price, stock


def stock_percent(stock):
    return max(0, min(100, round((stock / 50) * 100)))


def stock_color(stock):
    ratio = max(0, min(1, stock / 50))
    hue = round(ratio * 120)
    return f'hsl({hue}, 75%, 45%)'


def stock_text_color(stock):
    return '#111111' if stock >= 18 else '#ffffff'


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Store Admin Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container min-vh-100 d-flex align-items-center justify-content-center">
        <div class="card shadow-sm" style="width:100%;max-width:420px;">
            <div class="card-body p-4">
                <h1 class="h3 mb-1 text-primary fw-bold">Company Store</h1>
                <p class="text-muted mb-4">Admin Portal</p>
                {% if error %}
                    <div class="alert alert-danger">{{ error }}</div>
                {% endif %}
                <form method="POST" action="/login">
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Username</label>
                        <input type="text" name="username" class="form-control" autocomplete="username" required autofocus>
                    </div>
                    <div class="mb-4">
                        <label class="form-label fw-semibold">Password</label>
                        <input type="password" name="password" class="form-control" autocomplete="current-password" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 fw-bold">Log In</button>
                </form>
            </div>
        </div>
    </div>
</body>
</html>
"""

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if compare_digest(username, ADMIN_USERNAME) and compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password.'
    return render_template_string(LOGIN_TEMPLATE, error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    inventory    = database.get_all_inventory()
    categories   = database.get_categories()
    transactions = database.get_recent_transactions()
    suggestions  = database.get_suggestions()
    last_tx_id   = transactions[0]['id'] if transactions else 0
    admin_alert  = session.pop('admin_alert', None)
    active_tab   = request.args.get('tab', 'inventory')

    # ── Analytics ──
    revenue        = database.get_total_revenue()
    expenses_total = database.get_total_expenses()
    profit         = revenue - expenses_total
    profit_margin  = round((profit / revenue * 100), 1) if revenue > 0 else 0.0
    tx_count       = database.get_transaction_count()
    avg_order      = round(revenue / tx_count, 2) if tx_count > 0 else 0.0

    top_items      = database.get_top_items(10)
    top_items_max  = max((i[1] for i in top_items), default=1)

    category_revenue = database.get_category_revenue()
    cat_rev_max      = max((c[1] for c in category_revenue), default=1)

    daily_revenue  = database.get_daily_revenue(7)
    daily_max      = max((d[1] for d in daily_revenue), default=0.01)

    expense_log    = database.get_expense_log()

    # Low stock items (≤ 5)
    low_stock = [i for i in inventory if i[4] <= 5]

    # Settings
    venmo_username = database.get_setting('venmo_username', VENMO_USERNAME)

    # Restock periods — build a list of dicts sorted most-recent-first
    restocks_raw = database.get_restocks()   # [(id, 'YYYY-MM-DD'), ...] ASC
    restock_periods = []
    for i, (rid, date_str) in enumerate(restocks_raw):
        end_str = restocks_raw[i + 1][1] if i + 1 < len(restocks_raw) else None
        try:
            display_start = datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%m/%d/%Y')
        except ValueError:
            display_start = date_str
        if end_str:
            try:
                display_end = datetime.datetime.strptime(end_str, '%Y-%m-%d').strftime('%m/%d/%Y')
            except ValueError:
                display_end = end_str
        else:
            display_end = 'Present'
        restock_periods.append({
            'id':            rid,
            'start':         date_str,
            'end':           end_str or '',
            'display_start': display_start,
            'display_end':   display_end,
            'is_current':    end_str is None,
        })
    restock_periods.reverse()   # show most-recent period first

    today_str = datetime.date.today().strftime('%Y-%m-%d')

    return render_template(
        'admin.html',
        inventory=inventory,
        categories=categories,
        transactions=transactions,
        suggestions=suggestions,
        admin_alert=admin_alert,
        active_tab=active_tab,
        revenue=revenue,
        expenses_total=expenses_total,
        profit=profit,
        profit_margin=profit_margin,
        tx_count=tx_count,
        avg_order=avg_order,
        top_items=top_items,
        top_items_max=top_items_max,
        category_revenue=category_revenue,
        cat_rev_max=cat_rev_max,
        daily_revenue=daily_revenue,
        daily_max=daily_max,
        expense_log=expense_log,
        low_stock=low_stock,
        stock_color=stock_color,
        stock_percent=stock_percent,
        stock_text_color=stock_text_color,
        venmo_username=venmo_username,
        restock_periods=restock_periods,
        today=today_str,
        last_tx_id=last_tx_id,
    )


# ── Inventory routes ──────────────────────────────────────────────────────────

@app.route('/add', methods=['POST'])
@login_required
def add_item():
    name     = request.form.get('name', '').strip()
    category = request.form.get('category', '')
    try:
        price, stock = parse_inventory_values()
        database.add_inventory_item(name, category, price, stock)
        set_admin_alert(f'Added "{name}" to inventory.', 'success')
    except ValueError as exc:
        set_admin_alert(str(exc))
    return redirect('/?tab=inventory')


@app.route('/update', methods=['POST'])
@login_required
def update_item():
    name     = request.form.get('name', '').strip()
    category = request.form.get('category', '')
    try:
        price, stock = parse_inventory_values()
        database.update_inventory_item(name, category, price, stock)
        set_admin_alert(f'Updated "{name}".', 'success')
    except ValueError as exc:
        set_admin_alert(str(exc))
    return redirect('/?tab=inventory')


@app.route('/delete', methods=['POST'])
@login_required
def delete_item():
    name = request.form.get('name', '').strip()
    if name:
        database.delete_inventory_item(name)
        set_admin_alert(f'Deleted "{name}".', 'warning')
    return redirect('/?tab=inventory')


@app.route('/add_category', methods=['POST'])
@login_required
def create_category():
    new_cat = request.form.get('new_category', '').strip()
    if new_cat:
        database.add_category(new_cat)
        set_admin_alert(f'Category "{new_cat}" added.', 'success')
    return redirect('/?tab=inventory')


@app.route('/post_news', methods=['POST'])
@login_required
def post_news():
    message = request.form.get('message', '').strip()
    if message:
        database.add_announcement(message)
        set_admin_alert('Announcement pushed to kiosk.', 'success')
    return redirect('/?tab=inventory')


@app.route('/update_venmo', methods=['POST'])
@login_required
def update_venmo():
    username = request.form.get('venmo_username', '').strip().lstrip('@')
    if username:
        database.set_setting('venmo_username', username)
        set_admin_alert(f'Venmo username updated to @{username}.', 'success')
    return redirect('/?tab=inventory')


# ── Restock / Sales routes ────────────────────────────────────────────────────

@app.route('/add_restock', methods=['POST'])
@login_required
def add_restock():
    date_str = request.form.get('restock_date', '').strip()
    if date_str:
        try:
            datetime.datetime.strptime(date_str, '%Y-%m-%d')   # validate
            database.add_restock(date_str)
            set_admin_alert('Restock date logged.', 'success')
        except ValueError:
            set_admin_alert('Invalid date — please use the date picker.', 'danger')
    return redirect('/?tab=sales')


@app.route('/delete_restock', methods=['POST'])
@login_required
def delete_restock():
    restock_id = request.form.get('restock_id')
    if restock_id:
        database.delete_restock(int(restock_id))
        set_admin_alert('Restock date removed.', 'warning')
    return redirect('/?tab=sales')


@app.route('/api/sales_period')
@login_required
def api_sales_period():
    start = request.args.get('start', '')
    end   = request.args.get('end', '') or None
    if not start:
        return jsonify({'error': 'start parameter required'}), 400
    rows        = database.get_sales_for_period(start, end)
    total_units = sum(r[1] for r in rows)
    total_rev   = round(sum(r[2] for r in rows), 2)
    return jsonify({
        'items':       [{'name': r[0], 'qty': r[1], 'rev': round(r[2], 2)} for r in rows],
        'total_units': total_units,
        'total_rev':   total_rev,
    })


@app.route('/api/live_data')
@login_required
def api_live_data():
    """Single endpoint polled every 8 s by the admin page for live updates."""
    since_tx = request.args.get('since_tx', 0, type=int)

    inventory        = database.get_all_inventory()
    transactions     = database.get_recent_transactions(50)
    revenue          = database.get_total_revenue()
    expenses_total   = database.get_total_expenses()
    profit           = revenue - expenses_total
    profit_margin    = round((profit / revenue * 100), 1) if revenue > 0 else 0.0
    tx_count         = database.get_transaction_count()
    avg_order        = round(revenue / tx_count, 2) if tx_count > 0 else 0.0
    top_items        = database.get_top_items(10)
    top_items_max    = max((i[1] for i in top_items), default=1)
    category_revenue = database.get_category_revenue()
    cat_rev_max      = max((c[1] for c in category_revenue), default=1)
    daily_revenue    = database.get_daily_revenue(7)
    daily_max        = max((d[1] for d in daily_revenue), default=0.01)
    low_stock        = [i for i in inventory if i[4] <= 5]
    last_tx_id       = transactions[0]['id'] if transactions else 0

    new_txs = [tx for tx in transactions if tx['id'] > since_tx]

    return jsonify({
        'last_tx_id':       last_tx_id,
        'new_transactions': [
            {'id': tx['id'], 'total': tx['total'],
             'items': [[it[0], it[1], it[2]] for it in tx['items']]}
            for tx in new_txs
        ],
        'transactions': [
            {'id': tx['id'], 'timestamp': tx['timestamp'], 'total': tx['total'],
             'items': [[it[0], it[1], it[2]] for it in tx['items']]}
            for tx in transactions
        ],
        'inventory':        [{'id': i[0], 'name': i[1], 'category': i[2],
                               'price': i[3], 'stock': i[4]} for i in inventory],
        'revenue':          revenue,
        'expenses_total':   expenses_total,
        'profit':           profit,
        'profit_margin':    profit_margin,
        'tx_count':         tx_count,
        'avg_order':        avg_order,
        'top_items':        [{'name': r[0], 'qty': r[1], 'rev': round(r[2], 2)} for r in top_items],
        'top_items_max':    top_items_max,
        'category_revenue': [{'cat': c[0], 'rev': round(c[1], 2)} for c in category_revenue],
        'cat_rev_max':      cat_rev_max,
        'daily_revenue':    [{'day': d[0], 'rev': d[1]} for d in daily_revenue],
        'daily_max':        daily_max,
        'low_stock':        [{'id': i[0], 'name': i[1], 'stock': i[4]} for i in low_stock],
    })


# ── Expense routes ────────────────────────────────────────────────────────────

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    date        = request.form.get('exp_date', '').strip()
    description = request.form.get('exp_description', '').strip()
    try:
        amount = float(request.form.get('exp_amount', ''))
        if not date or not description:
            raise ValueError('Date and description are required.')
        database.add_expense(date, description, amount)
        set_admin_alert(f'Expense of ${amount:.2f} logged.', 'success')
    except ValueError as exc:
        set_admin_alert(str(exc))
    return redirect('/?tab=analytics')


@app.route('/delete_expense', methods=['POST'])
@login_required
def delete_expense():
    exp_id = request.form.get('expense_id')
    if exp_id:
        database.delete_expense(int(exp_id))
        set_admin_alert('Expense removed.', 'warning')
    return redirect('/?tab=analytics')


# ── Kiosk API routes (no auth) ────────────────────────────────────────────────

@app.route('/kiosk')
def kiosk():
    return render_template('kiosk.html')


@app.route('/api/inventory')
def api_inventory():
    items = database.get_all_inventory()
    return jsonify([{'id': i[0], 'name': i[1], 'category': i[2],
                     'price': i[3], 'stock': i[4]} for i in items])


@app.route('/api/categories')
def api_categories():
    return jsonify(database.get_categories())


@app.route('/api/announcements')
def api_announcements():
    rows = database.get_announcements()
    return jsonify([{'date': r[0], 'message': r[1]} for r in rows])


@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    data  = request.get_json(force=True)
    cart  = data.get('cart', {})
    total = data.get('total', 0)
    try:
        database.log_transaction(cart, total)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/suggestion', methods=['POST'])
def api_suggestion():
    data = request.get_json(force=True)
    msg  = data.get('message', '')
    try:
        database.add_suggestion(msg)
        return jsonify({'success': True})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400


@app.route('/api/venmo_qr')
def venmo_qr():
    """Generate a Venmo payment QR code image (PNG → base64 data URL)."""
    import qrcode

    amount   = request.args.get('amount', '0.00')
    note     = request.args.get('note', 'Company Store Order')
    username = database.get_setting('venmo_username', VENMO_USERNAME)
    # quote(note, safe='') encodes spaces as %20 (never +), which Venmo decodes correctly
    url = f'https://venmo.com/{username}?txn=pay&amount={amount}&note={quote(note, safe="")}'

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=9,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    encoded = base64.b64encode(buf.getvalue()).decode()

    return jsonify({
        'qr':     f'data:image/png;base64,{encoded}',
        'url':    url,
        'amount': amount,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
