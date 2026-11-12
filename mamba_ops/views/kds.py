import streamlit as st
import services as svc


@st.fragment(run_every=5)     # only this block re-queries every 5 seconds - the kitchen screen stays live
def board(pid, station):
    tickets = svc.open_kots(pid, station)
    if not tickets:
        st.success("No open tickets.")
        return
    cols = st.columns(4)
    for i, k in enumerate(tickets):
        colour = "🟢" if k["minutes"] < 10 else ("🟠" if k["minutes"] < 20 else "🔴")
        with cols[i % 4].container(border=True):
            st.markdown(f"**{colour} KOT #{k['id']} | Table {k['table_no']}**  \n{k['minutes']} min | _{k['status']}_")
            for it in k["items"]:
                st.write(f"**{it['qty']} x** {it['name']}" + (f"  \n_{it['note']}_" if it["note"] else ""))
            if k["status"] == "new":
                if st.button("Start", key=f"st{k['id']}", width="stretch"):
                    svc.set_kot_status(k["id"], "preparing"); st.rerun(scope="fragment")
            elif k["status"] == "preparing":
                if st.button("Ready", key=f"rd{k['id']}", type="primary", width="stretch"):
                    svc.set_kot_status(k["id"], "ready"); st.rerun(scope="fragment")
            else:
                if st.button("Served", key=f"sv{k['id']}", width="stretch"):
                    svc.set_kot_status(k["id"], "served"); st.rerun(scope="fragment")


def render():
    st.title("Kitchen / Bar Display")
    station = st.radio("Station", svc.STATIONS, horizontal=True)
    board(st.session_state.property_id, station)
