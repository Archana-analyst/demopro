from datetime import date, timedelta
import streamlit as st
import pandas as pd
import services as svc


def render():
    pid = st.session_state.property_id
    st.title("Front Desk")
    tab_new, tab_arr, tab_house, tab_rooms = st.tabs(["New reservation", "Arrivals", "In-house / Check-out", "Room board"])

    with tab_new:
        c1, c2 = st.columns(2)
        ci = c1.date_input("Check-in", date.today(), key="fd_ci")
        co = c2.date_input("Check-out", date.today() + timedelta(days=1), key="fd_co")
        rooms = svc.available_rooms(pid, ci, co) if co > ci else []
        if co <= ci:
            st.warning("Check-out must be after check-in.")
        elif not rooms:
            st.error("No rooms available for these dates.")
        else:
            with st.form("new_res", clear_on_submit=True):
                name = st.text_input("Guest name")
                p1, p2 = st.columns(2)
                phone, email = p1.text_input("Phone"), p2.text_input("Email")
                choice = st.selectbox("Room", rooms, format_func=lambda r: f"{r['number']} - {r['type']} (${r['rate']:.0f}/night)")
                if st.form_submit_button("Create reservation", type="primary"):
                    try:
                        rid = svc.create_reservation(pid, name, phone, email, ci, co, choice["id"])
                        st.success(f"Reservation #{rid} created. Room charge posted to the guest folio.")
                    except ValueError as e:
                        st.error(str(e))

    with tab_arr:
        rows = svc.reservations(pid, ["booked"])
        if not rows:
            st.info("No upcoming arrivals.")
        for r in rows:
            c = st.columns([3, 2, 2, 1, 1])
            c[0].write(f"**#{r['id']} {r['guest']}**  \n{r['phone'] or ''}")
            c[1].write(f"Room {r['room_no']} ({r['room_type']})")
            c[2].write(f"{r['check_in']} to {r['check_out']}  \nsource: {r['source']}")
            if c[3].button("Check in", key=f"ci{r['id']}"):
                svc.check_in(r["id"]); st.rerun()
            if c[4].button("Cancel", key=f"cx{r['id']}"):
                svc.cancel_reservation(r["id"]); st.rerun()

    with tab_house:
        rows = svc.reservations(pid, ["in_house"])
        if not rows:
            st.info("No guests in house.")
        for r in rows:
            items, total = svc.folio(r["id"])
            with st.expander(f"Room {r['room_no']} - {r['guest']}  |  folio ${total:,.2f}"):
                st.dataframe(pd.DataFrame(items)[["created_at", "category", "description", "amount"]],
                             hide_index=True, width="stretch")
                st.write(f"**Total due: ${total:,.2f}**")
                if st.button("Check out and close folio", key=f"co{r['id']}", type="primary"):
                    t = svc.check_out(r["id"])
                    st.success(f"Checked out. Invoice total ${t:,.2f}. Room set to 'dirty' for housekeeping.")
                    st.rerun()

    with tab_rooms:
        icons = {"clean": "🟢", "occupied": "🔴", "dirty": "🟡", "maintenance": "⚫"}
        for r in svc.rooms(pid):
            c = st.columns([1, 2, 2, 3])
            c[0].write(f"**{r['number']}**"); c[1].write(r["type"]); c[2].write(f"{icons[r['status']]} {r['status']}")
            if r["status"] in ("dirty", "maintenance"):
                if c[3].button("Mark clean", key=f"cl{r['id']}"):
                    svc.set_room_status(r["id"], "clean"); st.rerun()
