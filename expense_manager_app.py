import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import date, datetime, timedelta
from pathlib import Path
import base64

# ──────────────────  DB CONNECTION  ──────────────────
engine = create_engine(
    st.secrets["DATABASE_URL"],
    connect_args={"sslmode": "require"}
)

# quick connectivity check (remove if you like)
import psycopg2, warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        psycopg2.connect(st.secrets["DATABASE_URL"])
        st.success("Wedding of Himashi & Dishara!")
    except Exception as e:
        st.error(e)

# ──────────────────  HELPERS  ──────────────────
def run(query, params=None, fetch=False):
    with engine.begin() as conn:
        res = conn.execute(text(query), params or {})
        return res.fetchall() if fetch else None

def load_table(tbl):
    return pd.read_sql(f"select * from {tbl}", engine)

def datetime_input(label, default_date):
    """Returns a combined datetime from two widgets."""
    c1, c2 = st.columns([2, 1])
    d_val = c1.date_input(f"{label} – date", value=default_date, key=f"d_{label}")
    t_val = c2.time_input(f"{label} – time", value=datetime.now().time(), key=f"t_{label}")
    return datetime.combine(d_val, t_val)

def add_scrolling_bg(image_path, veil_opacity=.35, veil_rgb=(255,255,255)):
    img_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    r,g,b   = veil_rgb
    veil    = f"rgba({r},{g},{b},{veil_opacity})"
    st.markdown(f"""
        <style>
        .stApp {{
           background:
             linear-gradient({veil},{veil}),
             url("data:image/jpg;base64,{img_b64}") center/cover no-repeat scroll;
        }}
        div[data-testid="stSidebar"] > div:first-child {{
           background: rgba(255,255,255,0.85); border-radius:12px;
        }}
        </style>""", unsafe_allow_html=True)

# ──────────────────  PAGE CONFIG  ──────────────────
st.set_page_config("Wedding Expense Tracker", layout="centered")
add_scrolling_bg("assets/wedding_bg.jpg", veil_opacity=.05)

st.title("💍 Wedding Expense & Income Tracker")

# countdown
today, wedding_day = date.today(), date(2025,8,23)
st.metric("⏳ Days until wedding", f"{max((wedding_day-today).days-1,0)} days")

# ──────────────────  MENU  ──────────────────
menu = st.sidebar.radio(
    "Menu",
    ("Add Income", "Add Expense", "Budgets", "Dashboard", "Manage")
)

# ──────────────────  ADD INCOME  ──────────────────
if menu == "Add Income":
    st.subheader("➕ Add Income")
    ts        = datetime_input("Income", today)
    amount    = st.number_input("Amount (LKR)", 0.0, step=1000.0)
    src       = st.selectbox("Source", ("Salary","Freelance","Gift","Other"))
    notes     = st.text_input("Notes (optional)")
    if st.button("Add Income") and amount > 0:
        run("insert into income (date, amount_lkr, source, notes) "
            "values (:d,:a,:s,:n)",
            dict(d=ts, a=amount, s=src, n=notes))
        st.success("Income added!")

# ──────────────────  ADD EXPENSE  ──────────────────
elif menu == "Add Expense":
    st.subheader("➖ Add Expense")
    ts        = datetime_input("Expense", today)
    amt       = st.number_input("Amount (LKR)", 0.0, step=1000.0, key="ex_amt")
    cat       = st.text_input("Category (e.g., Groom Suit, Ring)")
    notes     = st.text_input("Notes (optional)", key="ex_notes")
    if st.button("Add Expense") and amt > 0 and cat.strip():
        run("insert into expense (date, amount_lkr, category, notes) "
            "values (:d,:a,:c,:n)",
            dict(d=ts, a=amt, c=cat.strip(), n=notes))
        st.success("Expense added!")

# ──────────────────  BUDGETS  ──────────────────
elif menu == "Budgets":
    st.subheader("📋 Category Budgets")
    df_bud = load_table("budget")
    st.dataframe(df_bud if not df_bud.empty else
                 pd.DataFrame(columns=["category","limit_lkr"]))
    st.markdown("---")
    b_cat = st.text_input("Category")
    b_lim = st.number_input("Limit (LKR)", 0.0, step=10000.0)
    if st.button("Save / Update Budget") and b_cat.strip():
        run("insert into budget (category,limit_lkr) "
            "values (:c,:l) on conflict (category) "
            "do update set limit_lkr=:l",
            dict(c=b_cat.strip(), l=b_lim))
        st.success("Budget saved/updated!")

# ──────────────────  DASHBOARD  ──────────────────
elif menu == "Dashboard":
    st.subheader("📊 Dashboard")

    df_inc, df_exp, df_bud = load_table("income"), load_table("expense"), load_table("budget")
    tot_inc, tot_exp = df_inc["amount_lkr"].sum(), df_exp["amount_lkr"].sum()
    bal = tot_inc - tot_exp

    c1,c2,c3 = st.columns(3)
    c1.metric("Total Income",  f"LKR {tot_inc:,.0f}")
    c2.metric("Total Expense", f"LKR {tot_exp:,.0f}")
    c3.metric("Balance",       f"LKR {bal:,.0f}")

    # spent vs budget
    if not df_exp.empty:
        spent = df_exp.groupby("category")["amount_lkr"].sum()
        limit = df_bud.set_index("category")["limit_lkr"] if not df_bud.empty else pd.Series(dtype=float)
        bar_df = pd.concat([spent, limit], axis=1).fillna(0).reset_index()
        bar_df.columns = ["Category","Spent","Budget"]
        fig1 = go.Figure()
        fig1.add_bar(x=bar_df["Category"], y=bar_df["Spent"],  name="Spent")
        fig1.add_bar(x=bar_df["Category"], y=bar_df["Budget"], name="Budget")
        fig1.update_layout(barmode="group", title="Spent vs Budget by Category")
        st.plotly_chart(fig1, use_container_width=True)

    # ledger analytics
    if not df_inc.empty or not df_exp.empty:
        ledger = (pd.concat([df_inc.assign(delta=df_inc["amount_lkr"]),
                             df_exp.assign(delta=-df_exp["amount_lkr"])])
                  .sort_values("date", kind="stable")
                  .reset_index(drop=True))
        ledger["date"] = pd.to_datetime(ledger["date"])
        ledger["balance"] = ledger["delta"].cumsum()

        # running balance
        fig2 = go.Figure()
        fig2.add_scatter(x=ledger["date"], y=ledger["balance"],
                         mode="lines+markers", line_shape="hv",
                         name="Running balance")
        fig2.update_layout(title="Running Balance – every transaction",
                           xaxis_title="Date / Time", yaxis_title="LKR")
        st.plotly_chart(fig2, use_container_width=True)

        # daily cash-in / cash-out
        daily = (ledger.groupby(ledger["date"].dt.date)["delta"]
                 .agg(received=lambda s: s[s>0].sum(),
                      spent   =lambda s: -s[s<0].sum())
                 .reset_index(names="day"))
        if not daily.empty:
            fig3 = go.Figure()
            fig3.add_bar(x=daily["day"], y=daily["received"], name="Received", marker_color="green")
            fig3.add_bar(x=daily["day"], y=daily["spent"],    name="Spent",    marker_color="red")
            fig3.update_layout(barmode="group", title="Daily cash-in / cash-out",
                               xaxis_title="Day", yaxis_title="LKR")
            st.plotly_chart(fig3, use_container_width=True)

# ──────────────────  MANAGE (edit / delete)  ──────────────────
else:
    st.subheader("🛠 Manage Entries (edit / delete)")
    tbl = st.selectbox("Choose table", ("income","expense"))
    df  = load_table(tbl).sort_values("date", ascending=False).reset_index(drop=True)

    # Allow editing of amount & notes
    edited = st.data_editor(
        df,
        column_config={"amount_lkr":"numeric","notes":"text"},
        disabled=["id","date","source","category"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )

    if st.button("💾 Save changes"):
        diff = edited.compare(df)
        for idx in diff.index.unique(level=0):
            row = edited.loc[idx]
            run(f"update {tbl} set amount_lkr=:a, notes=:n where id=:i",
                dict(a=row["amount_lkr"], n=row["notes"], i=row["id"]))
        st.success("Rows updated!  Reload Dashboard to see effect.")

    del_ids = st.multiselect("Select IDs to delete", df["id"])
    if st.button("🗑 Delete selected") and del_ids:
        run(f"delete from {tbl} where id = any(:ids)", dict(ids=tuple(del_ids)))
        st.warning(f"Deleted {len(del_ids)} rows – refresh page to update.")
