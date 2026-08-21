"""Flask routes for the kiosk and the admin panel.

Two audiences share one app:

- `/kiosk` and `/api/inventory`, `/api/categories`, `/api/announcements`,
  `/api/kiosk_poll`, `/api/checkout`, `/api/venmo_qr` — what the touchscreen
  calls.
- `/` and the rest — the admin panel, meant for a manager on the LAN,
  reachable from a laptop or phone on the same network.

There is no login. Every route is open to anyone who can reach the port, which
is a deliberate choice for a small hobby store on a trusted network: the panel
can change prices and delete inventory, so the network is the only boundary.
To limit it to the Pi itself, bind HOST to 127.0.0.1 in main.py.

Data access goes through database.py; this module holds request handling,
presentation helpers, and the analytics assembled for both the rendered page
and its polling endpoint.
"""
import os
import io
import base64
import datetime
from urllib.parse import quote

from flask import Flask, render_template, request, redirect, session, jsonify
import database

# Set VENMO_USERNAME env var before fielding on Pi
VENMO_USERNAME = os.environ.get('VENMO_USERNAME', 'YourVenmoHere')

_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(_BASE, 'templates'),
            static_folder=os.path.join(_BASE, 'static'))
# The admin panel has no login. The secret key now only signs the flash
# messages shown after an action ("Added X to inventory"), so its value is not
# security-sensitive — but Flask requires one for `session` to work at all.
app.secret_key = os.environ.get('STORE_ADMIN_SECRET_KEY', 'kiosk-flash-messages')

# ── Helpers ───────────────────────────────────────────────────────────────────

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


def stock_percent(stock, max_stock):
    if not max_stock:
        return 100
    return max(0, min(100, round((stock / max_stock) * 100)))


def stock_color(stock, max_stock):
    ratio = max(0, min(1, stock / max_stock)) if max_stock else 1
    hue = round(ratio * 120)
    return f'hsl({hue}, 75%, 45%)'


def stock_text_color(stock, max_stock):
    ratio = (stock / max_stock) if max_stock else 1
    return '#111111' if ratio >= 0.36 else '#ffffff'


# Fraction of an item's restock baseline at or below which it counts as low.
LOW_STOCK_RATIO = 0.25
# Fallback for items with no recorded restock baseline to take a fraction of.
LOW_STOCK_UNITS = 5


def is_low_stock(stock, max_stock):
    """Single source of truth for the low-stock list.

    The dashboard renders this server-side and /api/live_data recomputes it
    every 8 s; when the two used different rules the panel visibly changed
    contents moments after the page loaded. Items with no baseline (max_stock
    of 0, e.g. added at zero stock) fall back to a flat unit threshold.
    """
    if not max_stock:
        return stock <= LOW_STOCK_UNITS
    return stock <= max_stock * LOW_STOCK_RATIO


def _display_date(date_str):
    """YYYY-MM-DD as MM/DD/YYYY, passing anything unparseable through as-is."""
    try:
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%m/%d/%Y')
    except ValueError:
        return date_str


def build_restock_periods(restocks):
    """Turn restock dates into the spans between them, most recent first.

    Each restock opens a period that runs until the next one; the newest is
    still open, and displays as "Present". `restocks` arrives oldest-first as
    [(id, 'YYYY-MM-DD'), ...].
    """
    periods = []
    for index, (restock_id, start) in enumerate(restocks):
        is_last = index + 1 == len(restocks)
        end = None if is_last else restocks[index + 1][1]
        periods.append({
            'id':            restock_id,
            'start':         start,
            'end':           end or '',
            'display_start': _display_date(start),
            'display_end':   'Present' if end is None else _display_date(end),
            'is_current':    end is None,
        })
    periods.reverse()
    return periods


def build_analytics(inventory):
    """Every figure the analytics panel shows, computed in one place.

    The dashboard renders these into the page and /api/live_data returns the
    same numbers as JSON. They used to be computed separately in each, and the
    two copies drifted — which is how the low-stock list ended up disagreeing
    with itself between page load and the first poll.

    `inventory` is passed in rather than fetched here because both callers
    already need it for their own purposes.
    """
    revenue          = database.get_total_revenue()
    expenses_total   = database.get_total_expenses()
    profit           = revenue - expenses_total
    tx_count         = database.get_transaction_count()
    top_items        = database.get_top_items()
    category_revenue = database.get_category_revenue()
    daily_revenue    = database.get_daily_revenue()

    return {
        'revenue':          revenue,
        'expenses_total':   expenses_total,
        'profit':           profit,
        'profit_margin':    round(profit / revenue * 100, 1) if revenue > 0 else 0.0,
        'tx_count':         tx_count,
        'avg_order':        round(revenue / tx_count, 2) if tx_count > 0 else 0.0,
        'top_items':        top_items,
        # Chart bars are drawn as a fraction of the largest value, so these
        # divisors must never be zero. `default=` only covers the empty case:
        # a single $0.00-priced item makes the real maximum 0 and took the
        # whole dashboard down with a ZeroDivisionError. `or` catches 0 and
        # None as well, which is what the template actually needs.
        'top_items_max':    max((i[1] for i in top_items), default=1) or 1,
        'category_revenue': category_revenue,
        'cat_rev_max':      max((c[1] for c in category_revenue), default=1) or 1,
        'daily_revenue':    daily_revenue,
        'daily_max':        max((d[1] for d in daily_revenue), default=0.01) or 0.01,
        'low_stock':        [i for i in inventory if is_low_stock(i[4], i[5])],
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    inventory    = database.get_all_inventory()
    categories   = database.get_categories()
    transactions = database.get_recent_transactions()
    suggestions  = database.get_suggestions()
    last_tx_id   = transactions[0]['id'] if transactions else 0
    admin_alert  = session.pop('admin_alert', None)
    active_tab   = request.args.get('tab', 'inventory')

    return render_template(
        'admin.html',
        inventory=inventory,
        categories=categories,
        transactions=transactions,
        suggestions=suggestions,
        admin_alert=admin_alert,
        active_tab=active_tab,
        expense_log=database.get_expense_log(),
        venmo_username=database.get_setting('venmo_username', VENMO_USERNAME),
        restock_periods=build_restock_periods(database.get_restocks()),
        today=datetime.date.today().strftime('%Y-%m-%d'),
        last_tx_id=last_tx_id,
        # Formatting helpers the stock bars call per row.
        stock_color=stock_color,
        stock_percent=stock_percent,
        stock_text_color=stock_text_color,
        # revenue, profit, top_items, low_stock, ... — the same figures
        # /api/live_data serves, so the page and the poll cannot disagree.
        **build_analytics(inventory),
    )


# ── Inventory routes ──────────────────────────────────────────────────────────

@app.route('/add', methods=['POST'])
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
def delete_item():
    name = request.form.get('name', '').strip()
    if name:
        database.delete_inventory_item(name)
        set_admin_alert(f'Deleted "{name}".', 'warning')
    return redirect('/?tab=inventory')


@app.route('/add_category', methods=['POST'])
def create_category():
    new_cat = request.form.get('new_category', '').strip()
    if new_cat:
        database.add_category(new_cat)
        set_admin_alert(f'Category "{new_cat}" added.', 'success')
    return redirect('/?tab=inventory')


@app.route('/post_news', methods=['POST'])
def post_news():
    message = request.form.get('message', '').strip()
    if message:
        database.add_announcement(message)
        set_admin_alert('Announcement pushed to kiosk.', 'success')
    return redirect('/?tab=inventory')


@app.route('/update_venmo', methods=['POST'])
def update_venmo():
    username = request.form.get('venmo_username', '').strip().lstrip('@')
    if username:
        database.set_setting('venmo_username', username)
        set_admin_alert(f'Venmo username updated to @{username}.', 'success')
    return redirect('/?tab=inventory')


# ── Restock / Sales routes ────────────────────────────────────────────────────

@app.route('/add_restock', methods=['POST'])
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
def delete_restock():
    restock_id = request.form.get('restock_id')
    if restock_id:
        database.delete_restock(int(restock_id))
        set_admin_alert('Restock date removed.', 'warning')
    return redirect('/?tab=sales')


@app.route('/api/sales_period')
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
def api_live_data():
    """Single endpoint polled every 8 s by the admin page for live updates."""
    since_tx = request.args.get('since_tx', 0, type=int)

    inventory    = database.get_all_inventory()
    transactions = database.get_recent_transactions()
    stats        = build_analytics(inventory)
    last_tx_id   = transactions[0]['id'] if transactions else 0

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
                               'price': i[3], 'stock': i[4], 'max_stock': i[5]} for i in inventory],
        'revenue':          stats['revenue'],
        'expenses_total':   stats['expenses_total'],
        'profit':           stats['profit'],
        'profit_margin':    stats['profit_margin'],
        'tx_count':         stats['tx_count'],
        'avg_order':        stats['avg_order'],
        'top_items':        [{'name': r[0], 'qty': r[1], 'rev': round(r[2], 2)}
                             for r in stats['top_items']],
        'top_items_max':    stats['top_items_max'],
        'category_revenue': [{'cat': c[0], 'rev': round(c[1], 2)}
                             for c in stats['category_revenue']],
        'cat_rev_max':      stats['cat_rev_max'],
        'daily_revenue':    [{'day': d[0], 'rev': d[1]} for d in stats['daily_revenue']],
        'daily_max':        stats['daily_max'],
        'low_stock':        [{'id': i[0], 'name': i[1], 'stock': i[4], 'max_stock': i[5]}
                             for i in stats['low_stock']],
    })


# ── Expense routes ────────────────────────────────────────────────────────────

@app.route('/add_expense', methods=['POST'])
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


@app.route('/api/kiosk_poll')
def api_kiosk_poll():
    """Single no-auth endpoint polled every 20 s by the kiosk for live inventory + announcement updates."""
    items = database.get_all_inventory()
    rows  = database.get_announcements()
    cats  = database.get_categories()
    return jsonify({
        'inventory':     [{'id': i[0], 'name': i[1], 'category': i[2],
                           'price': i[3], 'stock': i[4]} for i in items],
        'announcements': [{'date': r[0], 'message': r[1]} for r in rows],
        'categories':    cats,
    })


@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    data  = request.get_json(force=True)
    cart  = data.get('cart', {})
    total = data.get('total', 0)
    try:
        # The stored total is recomputed server-side; echo it back so the kiosk
        # can never display an amount the store did not actually record.
        server_total = database.log_transaction(cart, total)
        return jsonify({'success': True, 'total': server_total})
    except ValueError as exc:
        # ValueError messages are written for the customer ("Only 2 left").
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception:
        # Anything else is a bug. Log it server-side; don't echo internals to
        # an unauthenticated caller on the LAN.
        app.logger.exception('checkout failed')
        return jsonify({'success': False,
                        'error': 'Checkout failed — please see a manager.'}), 500


# The kiosk's suggestion box was removed, so nothing posts suggestions any
# more. The route is gone with it rather than left as an unauthenticated,
# unbounded write endpoint on a LAN-facing port. Existing suggestions are
# retained and still readable in the admin panel.


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
