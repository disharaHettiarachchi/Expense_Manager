import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from dateutil.relativedelta import relativedelta
from datetime import date, datetime

# ---------- DB Connection ----------
engine = create_engine(
    st.secrets["DATABASE_URL"],
    connect_args={"sslmode": "require"}   # harmless even if already in URL
)

import psycopg2
import streamlit as st

try:
    psycopg2.connect(st.secrets["DATABASE_URL"])
    st.success("Wedding of Himashi & Dishara!")
except Exception as e:
    st.error(e)

    
# ---------- Helpers ----------
def run(query, params=None, fetch=False):
    with engine.begin() as conn:
        res = conn.execute(text(query), params or {})
        return res.fetchall() if fetch else None

def load_table(table):
    return pd.read_sql(f"select * from {table}", engine)

# ---------- UI ----------
st.set_page_config(page_title="Wedding Expense Tracker", layout="centered")
st.title("💍 Wedding Expense & Income Tracker")

#Background
import streamlit as st
import base64
from pathlib import Path

def add_scrolling_bg(image_path: str,
                     veil_opacity: float = 0.35,
                     veil_rgb: tuple[int, int, int] = (255, 255, 255)):
    """
    Adds a scrolling background image with a built-in translucent veil.
    
    Parameters
    ----------
    image_path   : str   Path to local JPG/PNG inside the repo, e.g. 'assets/wedding_bg.jpg'.
    veil_opacity : float 0 (transparent) … 1 (solid).  0.35-0.45 keeps text readable.
    veil_rgb     : tuple Veil colour as (R, G, B).  Use (0,0,0) for a dark tint.
    """
    # base-64-encode the local file
    img_data = Path(image_path).read_bytes()
    img_b64  = base64.b64encode(img_data).decode()

    r, g, b  = veil_rgb
    veil_rgba = f"rgba({r},{g},{b},{veil_opacity})"

    st.markdown(
        f"""
        <style>
        /* Root element for every page in Streamlit */
        .stApp {{
            /* ① dimming veil, ② actual photo */
            background:
                linear-gradient({veil_rgba}, {veil_rgba}),
                url("data:image/jpg;base64,{img_b64}") center/cover no-repeat scroll;
        }}
        /* Optional glassy sidebar */
        div[data-testid="stSidebar"] > div:first-child {{
            background: rgba(255,255,255,0.85);
            border-radius: 12px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# --------- call once near the top of your app ----------
add_scrolling_bg("assets/wedding_bg.jpg",
                 veil_opacity=0.05,   # 35 % white veil
                 veil_rgb=(255, 255, 255))


# Date Countdown
today        = date.today()
wedding_day  = date(2025, 8, 23)   # YYYY, M, D

raw_gap      = (wedding_day - today).days   # difference in days
days_left    = max(raw_gap - 1, 0)          # exclude the wedding day itself

st.metric("⏳ Days until wedding", f"{days_left} days")

# Side Menu
menu = st.sidebar.radio(
    "Menu",
    ("Add Income", "Add Expense", "Budgets", "Dashboard"),
)

# ---------- Add Income ----------
if menu == "Add Income":
    st.subheader("➕ Add Income")
    in_date = st.date_input("Date", value=today)
    in_amount = st.number_input("Amount (LKR)", min_value=0.0, step=1000.0)
    in_source = st.selectbox("Source", ("Salary", "Freelance", "Gift", "Other"))
    in_notes = st.text_input("Notes (optional)")
    if st.button("Add Income") and in_amount > 0:
        run(
            "insert into income (date, amount_lkr, source, notes) "
            "values (:d, :a, :s, :n)",
            dict(d=in_date, a=in_amount, s=in_source, n=in_notes),
        )
        st.success("Income added!")

# ---------- Add Expense ----------
elif menu == "Add Expense":
    st.subheader("➖ Add Expense")
    ex_date = st.date_input("Date", value=today, key="ex_date")
    ex_amount = st.number_input("Amount (LKR)", min_value=0.0, step=1000.0, key="ex_amt")
    ex_cat = st.text_input("Category (e.g., Groom Suit, Ring, Vehicle Rent)")
    ex_notes = st.text_input("Notes (optional)", key="ex_notes")
    if st.button("Add Expense") and ex_amount > 0 and ex_cat.strip():
        run(
            "insert into expense (date, amount_lkr, category, notes) "
            "values (:d, :a, :c, :n)",
            dict(d=ex_date, a=ex_amount, c=ex_cat.strip(), n=ex_notes),
        )
        st.success("Expense added!")

# ---------- Budgets ----------
elif menu == "Budgets":
    st.subheader("📋 Category Budgets")
    df_bud = load_table("budget")
    st.dataframe(df_bud if not df_bud.empty else pd.DataFrame(columns=["category", "limit_lkr"]))
    st.markdown("---")
    b_cat = st.text_input("Category")
    b_limit = st.number_input("Limit (LKR)", min_value=0.0, step=10000.0)
    if st.button("Save / Update Budget") and b_cat.strip():
        run(
            "insert into budget (category, limit_lkr) "
            "values (:c, :l) on conflict (category) do update set limit_lkr = :l",
            dict(c=b_cat.strip(), l=b_limit),
        )
        st.success("Budget saved/updated!")

# ---------- Dashboard ----------
# ---------- Dashboard ----------
else:
    st.subheader("📊 Dashboard")

    df_inc = load_table("income")
    df_exp = load_table("expense")
    df_bud = load_table("budget")

    total_income  = df_inc["amount_lkr"].sum() if not df_inc.empty else 0
    total_expense = df_exp["amount_lkr"].sum() if not df_exp.empty else 0
    balance       = total_income - total_expense

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Income",  f"LKR {total_income:,.0f}")
    col2.metric("Total Expense", f"LKR {total_expense:,.0f}")
    col3.metric("Balance",       f"LKR {balance:,.0f}")

    # ────────── Spent vs Budget bar chart ──────────
    if not df_exp.empty:
        spent = df_exp.groupby("category")["amount_lkr"].sum()
        limit = (
            df_bud.set_index("category")["limit_lkr"]
            if not df_bud.empty else pd.Series(dtype=float)
        )
        bar_df = pd.concat([spent, limit], axis=1).fillna(0).reset_index()
        bar_df.columns = ["Category", "Spent", "Budget"]

        fig1 = go.Figure()
        fig1.add_bar(x=bar_df["Category"], y=bar_df["Spent"],  name="Spent")
        fig1.add_bar(x=bar_df["Category"], y=bar_df["Budget"], name="Budget")
        fig1.update_layout(barmode="group",
                           title="Spent vs Budget by Category")
        st.plotly_chart(fig1, use_container_width=True)

    # ────────── Ledger + analytics ──────────
    if not df_inc.empty or not df_exp.empty:
        # 1️⃣ combine tables into a time-ordered ledger
        ledger = (
            pd.concat(
                [df_inc.assign(delta=df_inc["amount_lkr"]),
                 df_exp.assign(delta=-df_exp["amount_lkr"])],
                ignore_index=True
            )
            .sort_values("date", kind="stable")
            .reset_index(drop=True)
        )

        ledger["date"] = pd.to_datetime(ledger["date"])  # ensure datetime dtype
        # synthetic +1s offset for duplicates within the same day
        ledger["date"] += pd.to_timedelta(
            ledger.groupby(ledger["date"].dt.date).cumcount(), unit="s"
        )
        ledger["balance"] = ledger["delta"].cumsum()

        # 2️⃣ staircase running-balance plot
        fig2 = go.Figure()
        fig2.add_scatter(x=ledger["date"],
                         y=ledger["balance"],
                         mode="lines+markers",
                         line_shape="hv",
                         name="Running balance")
        fig2.update_layout(title="Running Balance – every transaction",
                           xaxis_title="Date / Time",
                           yaxis_title="LKR")
        st.plotly_chart(fig2, use_container_width=True)

        # 3️⃣ daily in/out bars
        daily = (
            ledger
            .groupby(ledger["date"].dt.date)["delta"]
            .agg(received=lambda s: s[s > 0].sum(),
                 spent   =lambda s: -s[s < 0].sum())
            .reset_index(names="day")
        )
        if not daily.empty:
            fig3 = go.Figure()
            fig3.add_bar(x=daily["day"], y=daily["received"],
                         name="Received", marker_color="green")
            fig3.add_bar(x=daily["day"], y=daily["spent"],
                         name="Spent",    marker_color="red")
            fig3.update_layout(barmode="group",
                               title="Daily cash-in / cash-out",
                               xaxis_title="Day", yaxis_title="LKR")
            st.plotly_chart(fig3, use_container_width=True)
