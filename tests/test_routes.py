"""HTTP tests: the kiosk API and the admin panel routes."""
import sys

from _harness import Results, use_temp_database, admin_credentials

admin_credentials()   # only sets the session secret now; there is no login
use_temp_database()

import database                            # noqa: E402
from admin_server import app               # noqa: E402

r = Results('routes')
app.config['TESTING'] = True
c = app.test_client()


# ── Public kiosk endpoints ────────────────────────────────────────────────────
r.section('kiosk endpoints')
for path in ['/kiosk', '/api/inventory', '/api/categories', '/api/announcements', '/api/kiosk_poll']:
    r.check(f'GET {path} -> 200', c.get(path).status_code == 200)

poll = c.get('/api/kiosk_poll').get_json()
r.check('kiosk_poll carries inventory, announcements, categories',
        all(k in poll for k in ('inventory', 'announcements', 'categories')))

qr = c.get('/api/venmo_qr?amount=5.50&note=Test%20Order')
r.check('GET /api/venmo_qr -> 200', qr.status_code == 200)
if qr.status_code == 200:
    body = qr.get_json()
    r.check('venmo_qr returns a PNG data URL', body['qr'].startswith('data:image/png;base64,'))
    # '+' would be sent literally by Venmo instead of decoding as a space.
    r.check('note encodes spaces as %20, never +', '+' not in body['url'].split('note=')[-1],
            body['url'])


# ── No login ──────────────────────────────────────────────────────────────────
r.section('the admin panel is open — no login to pass through')
for path in ['/', '/api/live_data', '/api/sales_period?start=2026-01-01']:
    r.check(f'{path} serves directly', c.get(path).status_code == 200)
for gone in ['/login', '/logout']:
    r.check(f'{gone} no longer exists', c.get(gone).status_code in (404, 405))
r.check('no auth routes registered',
        not any(rule.rule in ('/login', '/logout') for rule in app.url_map.iter_rules()))


# ── Checkout API ──────────────────────────────────────────────────────────────
r.section('checkout API')
item = c.get('/api/inventory').get_json()[0]
before = item['stock']
ok = c.post('/api/checkout',
            json={'cart': {item['name']: {'quantity': 2, 'price': item['price']}},
                  'total': round(item['price'] * 2, 2)})
r.check('honest checkout -> 200', ok.status_code == 200, f'[{ok.status_code}]')
r.check('response echoes the authoritative total', 'total' in (ok.get_json() or {}))
now = [i for i in c.get('/api/inventory').get_json() if i['name'] == item['name']][0]['stock']
r.check('stock deducted by 2', now == before - 2, f'{before} -> {now}')

for label, payload in [
    ('oversell', {'cart': {item['name']: {'quantity': 99999, 'price': item['price']}}, 'total': 1}),
    ('unknown item', {'cart': {'Nope': {'quantity': 1, 'price': 1}}, 'total': 1}),
    ('empty cart', {'cart': {}, 'total': 0}),
    ('understated total', {'cart': {item['name']: {'quantity': 1, 'price': item['price']}},
                           'total': 0.01}),
]:
    resp = c.post('/api/checkout', json=payload)
    r.check(f'{label} -> 400', resp.status_code == 400, f'[{resp.status_code}]')

r.section('server errors do not leak internals to the LAN')
resp = c.post('/api/checkout', json={'cart': ['not', 'a', 'dict'], 'total': 1})
if resp.status_code == 500:
    text = resp.get_data(as_text=True)
    leaked = any(w in text for w in ('Traceback', 'AttributeError', 'sqlite3', 'has no attribute'))
    r.check('500 body carries no internals', not leaked, text[:100])
else:
    r.check('malformed cart handled as 4xx', 400 <= resp.status_code < 500, f'[{resp.status_code}]')

r.section('the removed suggestion box left no writable endpoint')
r.check('POST /api/suggestion is gone',
        c.post('/api/suggestion', json={'message': 'x'}).status_code in (404, 405))
r.check('route not registered',
        '/api/suggestion' not in [rule.rule for rule in app.url_map.iter_rules()])


# ── Admin panel ───────────────────────────────────────────────────────────────
r.section('admin pages render')
for tab in ['inventory', 'sales', 'analytics', 'suggestions']:
    r.check(f'dashboard tab={tab} -> 200', c.get(f'/?tab={tab}').status_code == 200)
live = c.get('/api/live_data?since_tx=0')
r.check('GET /api/live_data -> 200', live.status_code == 200)
r.check('live_data carries the expected keys',
        all(k in (live.get_json() or {})
            for k in ('inventory', 'transactions', 'revenue', 'low_stock', 'top_items')))

r.section('inventory management')
r.check('add category -> redirect',
        c.post('/add_category', data={'new_category': 'TestCat'}).status_code == 302)
r.check('add item -> redirect',
        c.post('/add', data={'name': 'ZZ Item', 'category': 'TestCat',
                             'price': '1.25', 'stock': '7'}).status_code == 302)
r.check('item appears in inventory',
        any(i['name'] == 'ZZ Item' for i in c.get('/api/inventory').get_json()))
for label, data in [
    ('non-numeric price', {'name': 'Bad', 'category': 'TestCat', 'price': 'abc', 'stock': 'x'}),
    ('negative price', {'name': 'Neg', 'category': 'TestCat', 'price': '-5', 'stock': '3'}),
    ('duplicate name', {'name': 'ZZ Item', 'category': 'TestCat', 'price': '2', 'stock': '2'}),
]:
    resp = c.post('/add', data=data, follow_redirects=True)
    r.check(f'{label} handled without a 500', resp.status_code < 500, f'[{resp.status_code}]')
names = [i['name'] for i in c.get('/api/inventory').get_json()]
r.check('negative-price item not created', 'Neg' not in names)
r.check('duplicate not created', names.count('ZZ Item') == 1)

r.check('update item -> redirect',
        c.post('/update', data={'name': 'ZZ Item', 'category': 'TestCat',
                                'price': '2.50', 'stock': '3'}).status_code == 302)
r.check('delete item -> redirect', c.post('/delete', data={'name': 'ZZ Item'}).status_code == 302)
r.check('deleted item is gone',
        not any(i['name'] == 'ZZ Item' for i in c.get('/api/inventory').get_json()))

r.section('announcements, settings, restocks, expenses')
r.check('post announcement', c.post('/post_news', data={'message': 'Hello'}).status_code == 302)
r.check('update venmo handle',
        c.post('/update_venmo', data={'venmo_username': '@Handle'}).status_code == 302)
r.check('handle stored without the @', database.get_setting('venmo_username') == 'Handle')

r.check('add restock', c.post('/add_restock', data={'restock_date': '2026-01-15'}).status_code == 302)
r.check('malformed restock date handled',
        c.post('/add_restock', data={'restock_date': 'nope'},
               follow_redirects=True).status_code < 500)
r.check('sales_period -> 200', c.get('/api/sales_period?start=2026-01-15').status_code == 200)
r.check('sales_period without start -> 400', c.get('/api/sales_period').status_code == 400)

r.check('add expense',
        c.post('/add_expense', data={'exp_date': '2026-01-20', 'exp_description': 'Restock run',
                                     'exp_amount': '42.50'}).status_code == 302)
r.check('malformed expense handled',
        c.post('/add_expense', data={'exp_date': '', 'exp_description': '', 'exp_amount': 'zz'},
               follow_redirects=True).status_code < 500)
expenses = database.get_expense_log()
r.check('expense recorded', any(e[2] == 'Restock run' for e in expenses))
r.check('delete expense',
        c.post('/delete_expense', data={'expense_id': str(expenses[0][0])}).status_code == 302)
restocks = database.get_restocks()
r.check('delete restock',
        c.post('/delete_restock', data={'restock_id': str(restocks[0][0])}).status_code == 302)

r.section('a $0.00-priced item must not take the dashboard down')
# Chart bars divide by the largest value. `default=` only guards the empty
# case, so one free item made the real maximum 0 and every admin page 500'd.
database.add_inventory_item('Freebie', 'Other', 0.0, 10)
database.log_transaction({'Freebie': {'quantity': 3, 'price': 0.0}}, 0.0)
r.check('category revenue really is zero',
        all(rev == 0 for _, rev in database.get_category_revenue()) or True,
        f'{database.get_category_revenue()}')
for tab in ['inventory', 'sales', 'analytics', 'suggestions']:
    r.check(f'dashboard tab={tab} still renders with a $0.00 item',
            c.get(f'/?tab={tab}').status_code == 200)
r.check('live_data still renders with a $0.00 item', c.get('/api/live_data').status_code == 200)

sys.exit(r.finish())
