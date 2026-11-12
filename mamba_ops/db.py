"""Database layer. SQLite for the demo (zero setup).
For production, swap this file for PostgreSQL (psycopg / SQLAlchemy) - the
services and pages only call q(), one(), run() and tx(), so nothing else changes.
"""
import sqlite3, hashlib
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "hotel.db"


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def tx():
    """One transaction = all-or-nothing. Writers are serialised (no double booking)."""
    conn = _connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def q(sql, params=()):
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def one(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def run(sql, params=()):
    with tx() as c:
        return c.execute(sql, params).lastrowid


def qc(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def hash_pw(pw):
    # Demo only. Use bcrypt/argon2 or st.login (OIDC) in production.
    return hashlib.sha256(("mph-salt:" + pw).encode()).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (id INTEGER PRIMARY KEY, name TEXT, country TEXT, currency TEXT);
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT);

CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, property_id INT, number TEXT, type TEXT, rate REAL,
    status TEXT DEFAULT 'clean');                          -- clean | dirty | occupied | maintenance
CREATE TABLE IF NOT EXISTS guests (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS reservations (id INTEGER PRIMARY KEY, property_id INT, guest_id INT, room_id INT,
    check_in TEXT, check_out TEXT, status TEXT DEFAULT 'booked',   -- booked | in_house | checked_out | cancelled
    source TEXT DEFAULT 'front_desk', created_at TEXT);
CREATE TABLE IF NOT EXISTS folio_charges (id INTEGER PRIMARY KEY, reservation_id INT, category TEXT,
    description TEXT, amount REAL, created_at TEXT);

CREATE TABLE IF NOT EXISTS stock_items (id INTEGER PRIMARY KEY, property_id INT, name TEXT, unit TEXT,
    reorder_level REAL DEFAULT 0, cost REAL DEFAULT 0, kind TEXT DEFAULT 'raw');   -- raw | produced | resale
CREATE TABLE IF NOT EXISTS stock_ledger (id INTEGER PRIMARY KEY, item_id INT, qty REAL, unit_cost REAL,
    ref_type TEXT, ref_id INT, note TEXT, created_by TEXT, created_at TEXT);       -- + in, - out. NEVER edit, only add.

CREATE TABLE IF NOT EXISTS menu_items (id INTEGER PRIMARY KEY, property_id INT, name TEXT, category TEXT,
    price REAL, station TEXT, active INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS recipes (menu_item_id INT, stock_item_id INT, qty REAL);   -- ingredients per 1 portion

CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, property_id INT, table_no TEXT, status TEXT DEFAULT 'open',
    total REAL DEFAULT 0, payment_method TEXT, reservation_id INT, created_by TEXT, created_at TEXT, paid_at TEXT);
CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INT, menu_item_id INT, qty INT,
    price REAL, note TEXT);
CREATE TABLE IF NOT EXISTS kots (id INTEGER PRIMARY KEY, order_id INT, station TEXT,
    status TEXT DEFAULT 'new', created_at TEXT, updated_at TEXT);             -- new | preparing | ready | served | cancelled
CREATE TABLE IF NOT EXISTS kot_items (id INTEGER PRIMARY KEY, kot_id INT, menu_item_id INT, qty INT, note TEXT);

CREATE TABLE IF NOT EXISTS production_recipes (product_item_id INT, ingredient_item_id INT, qty_per_batch REAL);
CREATE TABLE IF NOT EXISTS production_products (product_item_id INTEGER PRIMARY KEY, batch_yield REAL);
CREATE TABLE IF NOT EXISTS production_orders (id INTEGER PRIMARY KEY, property_id INT, product_item_id INT,
    batches REAL, produced_qty REAL, cost_per_unit REAL, created_by TEXT, created_at TEXT);
"""


def init_db():
    conn = _connect()
    conn.executescript(SCHEMA)
    seeded = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    conn.close()
    if not seeded:
        _seed()


def _seed():
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    with tx() as c:
        for u, p, r, n in [("admin", "admin123", "admin", "General Manager"),
                           ("reception", "rec123", "reception", "Front Desk"),
                           ("waiter", "wait123", "waiter", "Waiter"),
                           ("chef", "chef123", "chef", "Head Chef"),
                           ("store", "store123", "storekeeper", "Storekeeper")]:
            c.execute("INSERT INTO users(username,password,role,full_name) VALUES(?,?,?,?)", (u, hash_pw(p), r, n))

        for name, country, cur in [("Mamba Point Hotel - Monrovia", "Liberia", "USD"),
                                   ("Mamba Point Hotel - Freetown", "Sierra Leone", "USD")]:
            pid = c.execute("INSERT INTO properties(name,country,currency) VALUES(?,?,?)", (name, country, cur)).lastrowid

            for num, typ, rate in [("101", "Standard", 80), ("102", "Standard", 80), ("201", "Deluxe", 120),
                                   ("202", "Deluxe", 120), ("301", "Suite", 200)]:
                c.execute("INSERT INTO rooms(property_id,number,type,rate) VALUES(?,?,?,?)", (pid, num, typ, rate))

            ids = {}
            for nm, unit, rl, cost, kind in [
                ("Rice", "kg", 10, 1.2, "raw"), ("Chicken", "kg", 8, 4.5, "raw"), ("Cooking oil", "L", 5, 2.0, "raw"),
                ("Flour", "kg", 10, 0.9, "raw"), ("Tomatoes", "kg", 6, 1.5, "raw"),
                ("Tomato sauce", "kg", 3, 0, "produced"), ("Bread bun", "pcs", 20, 0, "produced"),
                ("Cola (bottle)", "pcs", 24, 0.6, "resale"), ("Beer (bottle)", "pcs", 24, 1.1, "resale"),
                ("Water (bottle)", "pcs", 24, 0.3, "resale")]:
                ids[nm] = c.execute("INSERT INTO stock_items(property_id,name,unit,reorder_level,cost,kind) VALUES(?,?,?,?,?,?)",
                                    (pid, nm, unit, rl, cost, kind)).lastrowid
            for nm, qty in [("Rice", 50), ("Chicken", 30), ("Cooking oil", 20), ("Flour", 40), ("Tomatoes", 25),
                            ("Cola (bottle)", 60), ("Beer (bottle)", 60), ("Water (bottle)", 80)]:
                c.execute("INSERT INTO stock_ledger(item_id,qty,unit_cost,ref_type,ref_id,note,created_by,created_at) "
                          "VALUES(?,?,?,?,?,?,?,?)", (ids[nm], qty, 0, "OPENING", 0, "Opening stock", "system", now))

            # production: bread (1 kg flour -> 12 buns), tomato sauce (2 kg tomatoes + 0.1 L oil -> 1.6 kg)
            for prod, yld, ings in [("Bread bun", 12, {"Flour": 1.0}),
                                    ("Tomato sauce", 1.6, {"Tomatoes": 2.0, "Cooking oil": 0.1})]:
                c.execute("INSERT INTO production_products VALUES(?,?)", (ids[prod], yld))
                for ing, qty in ings.items():
                    c.execute("INSERT INTO production_recipes VALUES(?,?,?)", (ids[prod], ids[ing], qty))

            menu = [("Jollof Rice & Chicken", "Mains", 12, "Kitchen", {"Rice": .25, "Chicken": .3, "Cooking oil": .02, "Tomato sauce": .1}),
                    ("Chicken Burger", "Mains", 10, "Kitchen", {"Bread bun": 1, "Chicken": .2, "Tomato sauce": .03}),
                    ("Fried Rice", "Mains", 9, "Kitchen", {"Rice": .25, "Cooking oil": .03}),
                    ("Cola", "Drinks", 2, "Bar", {"Cola (bottle)": 1}),
                    ("Beer", "Drinks", 3, "Bar", {"Beer (bottle)": 1}),
                    ("Water", "Drinks", 1, "Bar", {"Water (bottle)": 1})]
            for nm, cat, price, station, rec in menu:
                mid = c.execute("INSERT INTO menu_items(property_id,name,category,price,station) VALUES(?,?,?,?,?)",
                                (pid, nm, cat, price, station)).lastrowid
                for ing, qty in rec.items():
                    c.execute("INSERT INTO recipes VALUES(?,?,?)", (mid, ids[ing], qty))
