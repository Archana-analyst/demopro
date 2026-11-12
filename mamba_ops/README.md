# Mamba Point Hotel - Integrated Operations System (Streamlit prototype)

One database, one set of business rules, six staff screens, and a small API for the website.

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py            # staff app  -> http://localhost:8501
uvicorn api:app --port 8000     # website API -> http://localhost:8000/docs   (optional)
```
First run creates `hotel.db` with demo data for two properties (Monrovia, Freetown).

Demo logins: admin/admin123, reception/rec123, waiter/wait123, chef/chef123, store/store123
(each role sees only its own pages).

## How the modules stay synchronised
| Action | What happens automatically (one DB transaction) |
|---|---|
| Web or desk booking | Room availability re-checked inside the transaction (no double booking); room charge posted to folio |
| Check-in / check-out | Room status changes (occupied / dirty); folio closes with total |
| POS order sent | Order saved; one KOT per station (Kitchen, Bar) appears on that station screen |
| KOT marked Ready | Waiter sees status on the open-orders list |
| Order settled | Payment or ROOM CHARGE posted to guest folio; stock deducted from recipes |
| Production run | Raw materials issued, finished goods added, cost per unit calculated |
| GRN / wastage | Stock ledger row added; weighted-average cost updated |

## Files
- `db.py` - schema, seed data, transaction helper. **Swap this file for PostgreSQL in production.**
- `services.py` - ALL business rules (reuse from pages and API; unit-test these)
- `views/` - one Streamlit page per module
- `app.py` - login, property selector, role-based navigation
- `api.py` - FastAPI endpoints for WordPress: `GET /availability`, `POST /book`

## Connect the WordPress website
1. Host `api.py` (e.g. `api.mambapointhotel.com`) over HTTPS.
2. On the website, a booking form calls `/availability`, shows rooms, then `POST /book`.
   Keep the API key on the server side (a small WordPress plugin or PHP proxy), not in browser JavaScript.
3. The booking appears at the Front Desk page immediately, with source = website.

Example call from a WordPress PHP proxy:
```php
$res = wp_remote_post('https://api.mambapointhotel.com/book', [
  'headers' => ['Content-Type'=>'application/json','x-api-key'=>MPH_API_KEY],
  'body'    => json_encode(['property_id'=>1,'room_id'=>$room,'check_in'=>$ci,'check_out'=>$co,'name'=>$name,'email'=>$email]),
]);
```

## Before going live (not in the prototype)
- Move to PostgreSQL; change `?` placeholders to `%s` (or use SQLAlchemy) and `BEGIN IMMEDIATE` to normal transactions + row locks.
- Replace demo login with `st.login` (OIDC) or bcrypt/argon2 + HTTPS; remove demo users.
- Taxes, service charge, currencies, discounts and manager approval for voids.
- Online payment gateway, confirmation emails, thermal printer agent for KOT/receipts.
- Backups, audit log table, automated tests for `services.py`, night audit/day close.
