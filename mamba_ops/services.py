"""Business rules. Pages and the website API only call these functions.
Each function is ONE database transaction, so bookings, orders, KOTs, stock and
the guest folio can never get out of sync."""
from datetime import date, datetime
import db

STATIONS = ["Kitchen", "Bar"]
PAYMENT_METHODS = ["Cash", "Card", "Mobile money", "Room charge"]


def _now():
    return datetime.now().isoformat(timespec="seconds")


def nights(ci, co):
    return (date.fromisoformat(str(co)) - date.fromisoformat(str(ci))).days


# ---------------------------------------------------------------- booking / front desk
def available_rooms(pid, ci, co, conn=None):
    sql = """SELECT * FROM rooms r WHERE r.property_id=? AND r.status!='maintenance' AND NOT EXISTS (
               SELECT 1 FROM reservations x WHERE x.room_id=r.id AND x.status IN ('booked','in_house')
               AND x.check_in < ? AND x.check_out > ?) ORDER BY r.number"""
    p = (pid, str(co), str(ci))
    return db.qc(conn, sql, p) if conn else db.q(sql, p)


def create_reservation(pid, name, phone, email, ci, co, room_id, source="front_desk"):
    ci, co = str(ci), str(co)
    n = nights(ci, co)
    if n < 1:
        raise ValueError("Check-out must be after check-in.")
    if not name.strip():
        raise ValueError("Guest name is required.")
    with db.tx() as c:
        # re-check inside the transaction -> two people cannot book the same room
        if room_id not in [r["id"] for r in available_rooms(pid, ci, co, c)]:
            raise ValueError("Room is not available for those dates.")
        room = db.qc(c, "SELECT * FROM rooms WHERE id=?", (room_id,))[0]
        gid = c.execute("INSERT INTO guests(name,phone,email) VALUES(?,?,?)", (name.strip(), phone, email)).lastrowid
        rid = c.execute("INSERT INTO reservations(property_id,guest_id,room_id,check_in,check_out,source,created_at) "
                        "VALUES(?,?,?,?,?,?,?)", (pid, gid, room_id, ci, co, source, _now())).lastrowid
        c.execute("INSERT INTO folio_charges(reservation_id,category,description,amount,created_at) VALUES(?,?,?,?,?)",
                  (rid, "ROOM", f"Room {room['number']} x {n} night(s)", n * room["rate"], _now()))
        return rid


def reservations(pid, statuses):
    marks = ",".join("?" * len(statuses))
    return db.q(f"""SELECT r.*, g.name guest, g.phone, rm.number room_no, rm.type room_type
                    FROM reservations r JOIN guests g ON g.id=r.guest_id JOIN rooms rm ON rm.id=r.room_id
                    WHERE r.property_id=? AND r.status IN ({marks}) ORDER BY r.check_in""", (pid, *statuses))


def check_in(res_id):
    with db.tx() as c:
        r = db.qc(c, "SELECT * FROM reservations WHERE id=?", (res_id,))[0]
        if r["status"] != "booked":
            raise ValueError("Reservation is not in 'booked' status.")
        c.execute("UPDATE reservations SET status='in_house' WHERE id=?", (res_id,))
        c.execute("UPDATE rooms SET status='occupied' WHERE id=?", (r["room_id"],))


def folio(res_id):
    rows = db.q("SELECT * FROM folio_charges WHERE reservation_id=? ORDER BY id", (res_id,))
    return rows, sum(r["amount"] for r in rows)


def check_out(res_id):
    with db.tx() as c:
        r = db.qc(c, "SELECT * FROM reservations WHERE id=?", (res_id,))[0]
        if r["status"] != "in_house":
            raise ValueError("Guest is not in house.")
        total = db.qc(c, "SELECT COALESCE(SUM(amount),0) t FROM folio_charges WHERE reservation_id=?", (res_id,))[0]["t"]
        c.execute("UPDATE reservations SET status='checked_out' WHERE id=?", (res_id,))
        c.execute("UPDATE rooms SET status='dirty' WHERE id=?", (r["room_id"],))   # housekeeping is told automatically
        return total


def cancel_reservation(res_id):
    db.run("UPDATE reservations SET status='cancelled' WHERE id=? AND status='booked'", (res_id,))


def set_room_status(room_id, status):
    db.run("UPDATE rooms SET status=? WHERE id=?", (status, room_id))


def rooms(pid):
    return db.q("SELECT * FROM rooms WHERE property_id=? ORDER BY number", (pid,))


# ---------------------------------------------------------------- restaurant POS + KOT
def menu(pid):
    return db.q("SELECT * FROM menu_items WHERE property_id=? AND active=1 ORDER BY category,name", (pid,))


def place_order(pid, table_no, lines, user="", ):
    """lines = [{'menu_item_id':1,'qty':2,'note':''}] -> order + one KOT per station."""
    if not lines:
        raise ValueError("Cart is empty.")
    with db.tx() as c:
        total, by_station = 0, {}
        oid = c.execute("INSERT INTO orders(property_id,table_no,created_by,created_at) VALUES(?,?,?,?)",
                        (pid, table_no, user, _now())).lastrowid
        for ln in lines:
            m = db.qc(c, "SELECT * FROM menu_items WHERE id=?", (ln["menu_item_id"],))[0]
            total += m["price"] * ln["qty"]
            c.execute("INSERT INTO order_items(order_id,menu_item_id,qty,price,note) VALUES(?,?,?,?,?)",
                      (oid, m["id"], ln["qty"], m["price"], ln.get("note", "")))
            by_station.setdefault(m["station"], []).append((m["id"], ln["qty"], ln.get("note", "")))
        c.execute("UPDATE orders SET total=? WHERE id=?", (total, oid))
        for station, items in by_station.items():           # KOTs go to each station automatically
            kid = c.execute("INSERT INTO kots(order_id,station,created_at,updated_at) VALUES(?,?,?,?)",
                            (oid, station, _now(), _now())).lastrowid
            for mid, qty, note in items:
                c.execute("INSERT INTO kot_items(kot_id,menu_item_id,qty,note) VALUES(?,?,?,?)", (kid, mid, qty, note))
        return oid


def open_kots(pid, station):
    ks = db.q("""SELECT k.*, o.table_no FROM kots k JOIN orders o ON o.id=k.order_id
                 WHERE o.property_id=? AND k.station=? AND k.status IN ('new','preparing','ready')
                 ORDER BY k.id""", (pid, station))
    for k in ks:
        k["items"] = db.q("SELECT ki.*, m.name FROM kot_items ki JOIN menu_items m ON m.id=ki.menu_item_id WHERE kot_id=?",
                          (k["id"],))
        k["minutes"] = int((datetime.now() - datetime.fromisoformat(k["created_at"])).total_seconds() // 60)
    return ks


def set_kot_status(kot_id, status):
    db.run("UPDATE kots SET status=?, updated_at=? WHERE id=?", (status, _now(), kot_id))


def open_orders(pid):
    os_ = db.q("SELECT * FROM orders WHERE property_id=? AND status='open' ORDER BY id", (pid,))
    for o in os_:
        o["items"] = db.q("SELECT oi.*, m.name FROM order_items oi JOIN menu_items m ON m.id=oi.menu_item_id WHERE order_id=?",
                          (o["id"],))
        o["kots"] = db.q("SELECT station,status FROM kots WHERE order_id=?", (o["id"],))
    return os_


def void_order(order_id):
    with db.tx() as c:
        c.execute("UPDATE orders SET status='void' WHERE id=? AND status='open'", (order_id,))
        c.execute("UPDATE kots SET status='cancelled' WHERE order_id=?", (order_id,))


def settle_order(order_id, method, reservation_id=None, user=""):
    """Pay the bill -> posts payment / room charge -> deducts stock using recipes. One transaction."""
    with db.tx() as c:
        o = db.qc(c, "SELECT * FROM orders WHERE id=?", (order_id,))[0]
        if o["status"] != "open":
            raise ValueError("Order is already closed.")
        if method == "Room charge":
            r = db.qc(c, "SELECT * FROM reservations WHERE id=?", (reservation_id,))
            if not r or r[0]["status"] != "in_house" or r[0]["property_id"] != o["property_id"]:
                raise ValueError("Pick a guest who is currently checked in.")
            c.execute("INSERT INTO folio_charges(reservation_id,category,description,amount,created_at) VALUES(?,?,?,?,?)",
                      (reservation_id, "POS", f"Restaurant order #{order_id} (table {o['table_no']})", o["total"], _now()))
        for it in db.qc(c, "SELECT * FROM order_items WHERE order_id=?", (order_id,)):
            for rc in db.qc(c, "SELECT * FROM recipes WHERE menu_item_id=?", (it["menu_item_id"],)):
                cost = db.qc(c, "SELECT cost FROM stock_items WHERE id=?", (rc["stock_item_id"],))[0]["cost"]
                c.execute("INSERT INTO stock_ledger(item_id,qty,unit_cost,ref_type,ref_id,created_by,created_at) "
                          "VALUES(?,?,?,?,?,?,?)", (rc["stock_item_id"], -rc["qty"] * it["qty"], cost, "SALE", order_id, user, _now()))
        c.execute("UPDATE orders SET status='paid', payment_method=?, reservation_id=?, paid_at=? WHERE id=?",
                  (method, reservation_id, _now(), order_id))


# ---------------------------------------------------------------- store / inventory
def stock_balance(pid):
    return db.q("""SELECT s.id, s.name, s.unit, s.kind, s.cost, s.reorder_level,
                          ROUND(COALESCE(SUM(l.qty),0),3) balance
                   FROM stock_items s LEFT JOIN stock_ledger l ON l.item_id=s.id
                   WHERE s.property_id=? GROUP BY s.id ORDER BY s.kind, s.name""", (pid,))


def receive_stock(item_id, qty, unit_cost, supplier="", user=""):
    """Goods received note. Updates weighted-average cost."""
    if qty <= 0:
        raise ValueError("Quantity must be positive.")
    with db.tx() as c:
        bal = db.qc(c, "SELECT COALESCE(SUM(qty),0) b FROM stock_ledger WHERE item_id=?", (item_id,))[0]["b"]
        cost = db.qc(c, "SELECT cost FROM stock_items WHERE id=?", (item_id,))[0]["cost"]
        new_cost = ((max(bal, 0) * cost) + qty * unit_cost) / (max(bal, 0) + qty)
        c.execute("UPDATE stock_items SET cost=? WHERE id=?", (new_cost, item_id))
        c.execute("INSERT INTO stock_ledger(item_id,qty,unit_cost,ref_type,ref_id,note,created_by,created_at) "
                  "VALUES(?,?,?,?,?,?,?,?)", (item_id, qty, unit_cost, "GRN", 0, supplier, user, _now()))


def adjust_stock(item_id, qty, ref_type, note="", user=""):
    """WASTE (negative) or ADJUST (+/-). Always a new ledger row, never an edit."""
    if ref_type == "WASTE":
        qty = -abs(qty)
    db.run("INSERT INTO stock_ledger(item_id,qty,ref_type,ref_id,note,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
           (item_id, qty, ref_type, 0, note, user, _now()))


def ledger(pid, limit=200):
    return db.q("""SELECT l.created_at, s.name item, l.qty, l.ref_type, l.ref_id, l.note, l.created_by
                   FROM stock_ledger l JOIN stock_items s ON s.id=l.item_id
                   WHERE s.property_id=? ORDER BY l.id DESC LIMIT ?""", (pid, limit))


# ---------------------------------------------------------------- production
def production_products(pid):
    return db.q("""SELECT p.product_item_id id, s.name, s.unit, p.batch_yield FROM production_products p
                   JOIN stock_items s ON s.id=p.product_item_id WHERE s.property_id=?""", (pid,))


def production_recipe(product_id):
    return db.q("""SELECT r.ingredient_item_id id, s.name, s.unit, r.qty_per_batch FROM production_recipes r
                   JOIN stock_items s ON s.id=r.ingredient_item_id WHERE r.product_item_id=?""", (product_id,))


def run_production(pid, product_id, batches, user=""):
    """Consume raw materials from store, add finished goods, work out cost per unit."""
    if batches <= 0:
        raise ValueError("Batches must be positive.")
    with db.tx() as c:
        yield_qty = db.qc(c, "SELECT batch_yield y FROM production_products WHERE product_item_id=?", (product_id,))[0]["y"]
        total_cost, lines = 0, []
        for ing in db.qc(c, "SELECT * FROM production_recipes WHERE product_item_id=?", (product_id,)):
            need = ing["qty_per_batch"] * batches
            si = db.qc(c, "SELECT * FROM stock_items WHERE id=?", (ing["ingredient_item_id"],))[0]
            bal = db.qc(c, "SELECT COALESCE(SUM(qty),0) b FROM stock_ledger WHERE item_id=?", (si["id"],))[0]["b"]
            if bal < need:
                raise ValueError(f"Not enough {si['name']}: need {need:g} {si['unit']}, have {bal:g}.")
            total_cost += need * si["cost"]
            lines.append((si["id"], need, si["cost"]))
        produced = yield_qty * batches
        unit_cost = total_cost / produced
        poid = c.execute("INSERT INTO production_orders(property_id,product_item_id,batches,produced_qty,cost_per_unit,created_by,created_at) "
                         "VALUES(?,?,?,?,?,?,?)", (pid, product_id, batches, produced, unit_cost, user, _now())).lastrowid
        for item_id, need, cost in lines:
            c.execute("INSERT INTO stock_ledger(item_id,qty,unit_cost,ref_type,ref_id,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                      (item_id, -need, cost, "PRODUCTION_USE", poid, user, _now()))
        bal = db.qc(c, "SELECT COALESCE(SUM(qty),0) b FROM stock_ledger WHERE item_id=?", (product_id,))[0]["b"]
        old = db.qc(c, "SELECT cost FROM stock_items WHERE id=?", (product_id,))[0]["cost"]
        c.execute("UPDATE stock_items SET cost=? WHERE id=?",
                  ((max(bal, 0) * old + produced * unit_cost) / (max(bal, 0) + produced), product_id))
        c.execute("INSERT INTO stock_ledger(item_id,qty,unit_cost,ref_type,ref_id,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                  (product_id, produced, unit_cost, "PRODUCTION", poid, user, _now()))
        return produced, unit_cost


def production_history(pid):
    return db.q("""SELECT p.created_at, s.name product, p.batches, p.produced_qty, ROUND(p.cost_per_unit,3) cost_per_unit, p.created_by
                   FROM production_orders p JOIN stock_items s ON s.id=p.product_item_id
                   WHERE p.property_id=? ORDER BY p.id DESC LIMIT 50""", (pid,))


# ---------------------------------------------------------------- reports
def dashboard(pid, day=None):
    day = day or date.today().isoformat()
    sales = db.one("SELECT COALESCE(SUM(total),0) t, COUNT(*) n FROM orders WHERE property_id=? AND status='paid' AND substr(paid_at,1,10)=?", (pid, day))
    by_method = db.q("SELECT payment_method method, ROUND(SUM(total),2) amount FROM orders WHERE property_id=? AND status='paid' AND substr(paid_at,1,10)=? GROUP BY 1", (pid, day))
    total_rooms = db.one("SELECT COUNT(*) n FROM rooms WHERE property_id=?", (pid,))["n"]
    occupied = db.one("SELECT COUNT(*) n FROM reservations WHERE property_id=? AND status='in_house'", (pid,))["n"]
    top = db.q("""SELECT m.name, SUM(oi.qty) qty, ROUND(SUM(oi.qty*oi.price),2) revenue FROM order_items oi
                  JOIN orders o ON o.id=oi.order_id JOIN menu_items m ON m.id=oi.menu_item_id
                  WHERE o.property_id=? AND o.status='paid' GROUP BY m.id ORDER BY qty DESC""", (pid,))
    room_rev = db.one("""SELECT COALESCE(SUM(f.amount),0) t FROM folio_charges f JOIN reservations r ON r.id=f.reservation_id
                         WHERE r.property_id=? AND f.category='ROOM' AND r.status!='cancelled'""", (pid,))["t"]
    return dict(sales=sales["t"], orders=sales["n"], by_method=by_method, total_rooms=total_rooms,
                occupied=occupied, top=top, room_revenue=room_rev)
