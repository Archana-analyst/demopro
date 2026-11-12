import streamlit as st
import pandas as pd
import services as svc


def render():
    pid = st.session_state.property_id
    user = st.session_state.user["username"]
    st.title("Store / Inventory")
    t1, t2, t3, t4 = st.tabs(["Stock balance", "Receive stock (GRN)", "Wastage / adjustment", "Ledger"])
    items = svc.stock_balance(pid)

    with t1:
        df = pd.DataFrame(items)
        df["status"] = df.apply(lambda r: "NEGATIVE" if r.balance < 0 else ("LOW" if r.balance <= r.reorder_level else "ok"), axis=1)
        df["value"] = (df.balance.clip(lower=0) * df.cost).round(2)
        low = df[df.status != "ok"]
        if len(low):
            st.warning(f"{len(low)} item(s) at or below reorder level: " + ", ".join(low.name))
        st.dataframe(df[["name", "kind", "unit", "balance", "reorder_level", "cost", "value", "status"]],
                     hide_index=True, width="stretch")
        st.metric("Total stock value", f"${df.value.sum():,.2f}")

    with t2:
        with st.form("grn", clear_on_submit=True):
            it = st.selectbox("Item", items, format_func=lambda i: f"{i['name']} ({i['unit']})")
            c = st.columns(3)
            qty = c[0].number_input("Quantity received", min_value=0.0, step=1.0)
            cost = c[1].number_input("Unit cost", min_value=0.0, step=0.1)
            sup = c[2].text_input("Supplier / invoice no.")
            if st.form_submit_button("Post goods received", type="primary"):
                try:
                    svc.receive_stock(it["id"], qty, cost, sup, user); st.success("Stock updated."); 
                except ValueError as e:
                    st.error(str(e))

    with t3:
        with st.form("adj", clear_on_submit=True):
            it = st.selectbox("Item", items, format_func=lambda i: f"{i['name']} ({i['unit']})", key="adj_item")
            kind = st.radio("Type", ["WASTE", "ADJUST"], horizontal=True,
                            help="WASTE always reduces stock. ADJUST can be + or - (stock-take correction).")
            qty = st.number_input("Quantity (use negative for ADJUST decrease)", step=1.0, value=1.0)
            note = st.text_input("Reason")
            if st.form_submit_button("Post"):
                svc.adjust_stock(it["id"], qty, kind, note, user); st.success("Recorded in the ledger.")

    with t4:
        st.caption("Every stock movement from every module, newest first. Nothing is ever edited or deleted.")
        st.dataframe(pd.DataFrame(svc.ledger(pid)), hide_index=True, width="stretch")
