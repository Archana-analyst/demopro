import streamlit as st
import pandas as pd
import services as svc


def render():
    pid = st.session_state.property_id
    st.title("Dashboard")
    d = svc.dashboard(pid)
    c = st.columns(4)
    c[0].metric("Restaurant sales today", f"${d['sales']:,.2f}")
    c[1].metric("Paid orders today", d["orders"])
    c[2].metric("Occupancy", f"{d['occupied']}/{d['total_rooms']}",
                f"{(d['occupied'] / d['total_rooms'] * 100 if d['total_rooms'] else 0):.0f}%")
    c[3].metric("Room revenue booked", f"${d['room_revenue']:,.2f}")

    a, b = st.columns(2)
    with a:
        st.subheader("Sales by payment method (today)")
        if d["by_method"]:
            st.bar_chart(pd.DataFrame(d["by_method"]).set_index("method"))
        else:
            st.info("No paid orders yet today.")
    with b:
        st.subheader("Best sellers")
        if d["top"]:
            st.dataframe(pd.DataFrame(d["top"]), hide_index=True, width="stretch")
        else:
            st.info("No sales yet.")

    st.subheader("Low stock alerts")
    low = [s for s in svc.stock_balance(pid) if s["balance"] <= s["reorder_level"]]
    st.dataframe(pd.DataFrame(low)[["name", "unit", "balance", "reorder_level"]], hide_index=True, width="stretch") \
        if low else st.success("All stock above reorder levels.")
