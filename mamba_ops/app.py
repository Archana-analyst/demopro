"""Mamba Point Hotel - integrated operations system (prototype).
Run:  streamlit run app.py
"""
import streamlit as st
import db
from views import frontdesk, pos, kds, store, production, reports

st.set_page_config(page_title="Mamba Point Hotel Ops", page_icon="🏨", layout="wide")
db.init_db()

# ------------------------------------------------------------------ login (demo)
if "user" not in st.session_state:
    st.session_state.user = None
# if st.session_state.user is None:

    st.title("🏨 Mamba Point Hotel - Staff Login")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            row = db.one("SELECT * FROM users WHERE username=? AND password=?", (u.strip(), db.hash_pw(p)))
            if row:
                st.session_state.user = row
                st.rerun()
            else:
                st.error("Wrong username or password.")
    st.caption("Demo users: admin/admin123, reception/rec123, waiter/wait123, chef/chef123, store/store123")
    st.stop()

user = st.session_state.user
props = db.q("SELECT * FROM properties")

# ------------------------------------------------------------------ sidebar: property + user
prop = st.sidebar.selectbox("Property", props, format_func=lambda p: p["name"])
st.session_state.property_id = prop["id"]

st.sidebar.caption(f"Logged in: {user['full_name']} ({user['role']})")
if st.sidebar.button("Log out"):
    del st.session_state["user"]
    st.rerun()

# ------------------------------------------------------------------ role-based menu
ALL = {
    "Dashboard":  (reports.render,    "📊", {"admin"}),
    "Front Desk": (frontdesk.render,  "🛎️", {"admin", "reception"}),
    "POS":        (pos.render,        "🍽️", {"admin", "waiter", "reception"}),
    "Kitchen":    (kds.render,        "👨‍🍳", {"admin", "chef", "waiter"}),
    "Production": (production.render, "🏭", {"admin", "chef", "storekeeper"}),
    "Store":      (store.render,      "📦", {"admin", "storekeeper", "chef"}),
}
pages = [st.Page(fn, title=name, icon=icon, url_path=name.lower().replace(" ", "-"))
         for name, (fn, icon, roles) in ALL.items() if user["role"] in roles]
st.navigation(pages).run()
