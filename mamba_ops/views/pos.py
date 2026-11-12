import streamlit as st
import services as svc


def render():
    pid = st.session_state.property_id
    st.title("Restaurant POS")
    st.session_state.setdefault("cart", {})
    menu = svc.menu(pid)
    by_id = {m["id"]: m for m in menu}

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Menu")
        cats = sorted({m["category"] for m in menu})
        for tab, cat in zip(st.tabs(cats), cats):
            with tab:
                items = [m for m in menu if m["category"] == cat]
                cols = st.columns(3)
                for i, m in enumerate(items):
                    if cols[i % 3].button(f"{m['name']}\n${m['price']:.2f}", key=f"add{m['id']}", width="stretch"):
                        st.session_state.cart[m["id"]] = st.session_state.cart.get(m["id"], 0) + 1

    with right:
        st.subheader("Current order")
        table_no = st.text_input("Table / Bar", value="1")
        total = 0
        for mid, qty in list(st.session_state.cart.items()):
            m = by_id.get(mid)
            if not m:
                continue
            c = st.columns([4, 1, 1])
            c[0].write(f"{qty} x {m['name']}  (${m['price'] * qty:.2f})")
            if c[1].button("-", key=f"m{mid}"):
                st.session_state.cart[mid] -= 1
                if st.session_state.cart[mid] <= 0:
                    del st.session_state.cart[mid]
                st.rerun()
            if c[2].button("+", key=f"p{mid}"):
                st.session_state.cart[mid] += 1; st.rerun()
            total += m["price"] * qty
        st.markdown(f"### Total: ${total:,.2f}")
        note = st.text_input("Note for kitchen (optional)", placeholder="no onion, well done...")
        b1, b2 = st.columns(2)
        if b1.button("Send to kitchen / bar", type="primary", disabled=not st.session_state.cart):
            lines = [{"menu_item_id": k, "qty": v, "note": note} for k, v in st.session_state.cart.items()]
            oid = svc.place_order(pid, table_no, lines, st.session_state.user["username"])
            st.session_state.cart = {}
            st.success(f"Order #{oid} sent. KOTs created per station.")
            st.rerun()
        if b2.button("Clear"):
            st.session_state.cart = {}; st.rerun()

    st.divider()
    st.subheader("Open orders - serve and pay")
    orders = svc.open_orders(pid)
    if not orders:
        st.info("No open orders.")
    in_house = svc.reservations(pid, ["in_house"])
    for o in orders:
        status = " | ".join(f"{k['station']}: {k['status']}" for k in o["kots"])
        with st.expander(f"Order #{o['id']} - Table {o['table_no']} - ${o['total']:.2f}   [{status}]"):
            for it in o["items"]:
                st.write(f"{it['qty']} x {it['name']}" + (f"  _({it['note']})_" if it["note"] else ""))
            c = st.columns([2, 3, 1, 1])
            method = c[0].selectbox("Payment", svc.PAYMENT_METHODS, key=f"pm{o['id']}")
            res_id = None
            if method == "Room charge":
                if in_house:
                    g = c[1].selectbox("Guest", in_house, key=f"g{o['id']}",
                                       format_func=lambda r: f"Room {r['room_no']} - {r['guest']}")
                    res_id = g["id"]
                else:
                    c[1].warning("No guests in house.")
            if c[2].button("Settle", key=f"s{o['id']}", type="primary"):
                try:
                    svc.settle_order(o["id"], method, res_id, st.session_state.user["username"])
                    st.success("Paid. Stock deducted automatically."); st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if c[3].button("Void", key=f"v{o['id']}"):
                svc.void_order(o["id"]); st.rerun()
