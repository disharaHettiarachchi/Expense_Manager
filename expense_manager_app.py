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

today = date.today()
wedding_day = date(2025, 8, 23)
days_left = (wedding_day - today).days
st.metric("⏳ Days until wedding", f"{days_left} days")

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
else:
    st.subheader("📊 Dashboard")

    df_inc = load_table("income")
    df_exp = load_table("expense")
    df_bud = load_table("budget")

    total_income = df_inc["amount_lkr"].sum() if not df_inc.empty else 0
    total_expense = df_exp["amount_lkr"].sum() if not df_exp.empty else 0
    balance = total_income - total_expense

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Income", f"LKR {total_income:,.0f}")
    col2.metric("Total Expense", f"LKR {total_expense:,.0f}")
    col3.metric("Balance", f"LKR {balance:,.0f}")

    # Spent vs Budget bar chart
    if not df_exp.empty:
        spent = df_exp.groupby("category")["amount_lkr"].sum()
        limit = df_bud.set_index("category")["limit_lkr"] if not df_bud.empty else pd.Series(dtype=float)
        bar_df = pd.concat([spent, limit], axis=1).fillna(0).reset_index()
        bar_df.columns = ["Category", "Spent", "Budget"]

        fig1 = go.Figure()
        fig1.add_bar(x=bar_df["Category"], y=bar_df["Spent"], name="Spent")
        fig1.add_bar(x=bar_df["Category"], y=bar_df["Budget"], name="Budget")
        fig1.update_layout(barmode="group", title="Spent vs Budget by Category")
        st.plotly_chart(fig1, use_container_width=True)

    # Cash-flow line chart
    if not df_inc.empty or not df_exp.empty:
        cf = (
            pd.concat(
                [
                    df_inc[["date", "amount_lkr"]].assign(type="inc"),
                    df_exp[["date", "amount_lkr"]].assign(amount_lkr=lambda d: -d["amount_lkr"], type="exp"),
                ]
            )
            .sort_values("date")
            .reset_index(drop=True)
        )
        cf["cumulative"] = cf["amount_lkr"].cumsum()
        fig2 = go.Figure()
        fig2.add_scatter(x=cf["date"], y=cf["cumulative"], mode="lines+markers", name="Balance")
        fig2.update_layout(title="Running Balance Over Time", xaxis_title="Date", yaxis_title="LKR")
        st.plotly_chart(fig2, use_container_width=True)
