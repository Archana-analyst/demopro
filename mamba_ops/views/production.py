import streamlit as st
import pandas as pd
import services as svc


def render():
    pid = st.session_state.property_id
    st.title("Production")
    prods = svc.production_products(pid)
    prod = st.selectbox("Product", prods, format_func=lambda p: f"{p['name']} (1 batch = {p['batch_yield']:g} {p['unit']})")
    recipe = svc.production_recipe(prod["id"])
    bal = {b["id"]: b["balance"] for b in svc.stock_balance(pid)}
    batches = st.number_input("Number of batches", min_value=1.0, value=1.0, step=1.0)

    st.write("**Ingredients needed**")
    st.dataframe(pd.DataFrame([{"ingredient": r["name"], "needed": r["qty_per_batch"] * batches, "unit": r["unit"],
                                "in stock": bal.get(r["id"], 0)} for r in recipe]), hide_index=True, width="stretch")
    st.write(f"Will produce **{prod['batch_yield'] * batches:g} {prod['unit']}** of {prod['name']}.")
    if st.button("Run production", type="primary"):
        try:
            qty, cost = svc.run_production(pid, prod["id"], batches, st.session_state.user["username"])
            st.success(f"Produced {qty:g} {prod['unit']} at cost ${cost:.3f} each. Raw materials deducted from store.")
        except ValueError as e:
            st.error(str(e))
    st.divider()
    st.subheader("Recent production")
    st.dataframe(pd.DataFrame(svc.production_history(pid)), hide_index=True, width="stretch")
