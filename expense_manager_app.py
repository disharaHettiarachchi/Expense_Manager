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
             url("data:image/jpg;base64,{img_b64}") center/cover no-repeat fixed;
        }}
        div[data-testid="stSidebar"] > div:first-child {{
           background: rgba(255,255,255,0.85); border-radius:12px;
        }}
        </style>""", unsafe_allow_html=True)
def fmt_rupees(n: float) -> str:
    """Compact rupee formatting: 400k / 1.2 M / 950."""
    if n >= 1_000_000:
        return f"LKR {n/1_000_000:.1f} M"
    if n >= 1_000:
        return f"LKR {n/1_000:.0f} k"
    return f"LKR {n:,.0f}"

@st.cache_resource
def get_engine():
    return create_engine(
        st.secrets["DATABASE_URL"],
        connect_args={"sslmode": "require"}
    )

engine = get_engine()   # use everywhere

@st.cache_data(ttl=30)   # auto-refresh every 30 s
def load_table(tbl):
    return pd.read_sql(f"select * from {tbl}", engine)

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
    ("Add Income", "Add Expense", "Budgets",
     "Dashboard", "Manage", "Pending") 
)


# ──────────────────  ADD INCOME  ──────────────────
if menu == "Add Income":
    with st.form(key="income_form"):
        st.subheader("➕ Add Income")
        ts     = datetime_input("Income", today)
        amount = st.number_input("Amount (LKR)", 0.0, step=1000.0, key="inc_amt")
        src    = st.selectbox("Source", ("Salary","Freelance","Gift","Other"), key="inc_src")
        notes  = st.text_input("Notes (optional)", key="inc_note")
        submitted = st.form_submit_button("Add Income")
        if submitted and amount > 0:
            run("insert into income (date, amount_lkr, source, notes) "
                "values (:d,:a,:s,:n)",
                dict(d=ts, a=amount, s=src, n=notes))
            st.success("Income added!")
            st.cache_data.clear()        # invalidate cached tables


# ──────────────────  ADD EXPENSE  ──────────────────
elif menu == "Add Expense":
    with st.form(key="expense_form"):
        st.subheader("➖ Add Expense")
        ts   = datetime_input("Expense", today)
        amt  = st.number_input("Amount (LKR)", 0.0, step=1000.0, key="exp_amt")
        cat  = st.text_input("Category (e.g., Groom Suit, Ring)", key="exp_cat")
        note = st.text_input("Notes (optional)", key="exp_note")
        submitted = st.form_submit_button("Add Expense")
        if submitted and amt > 0 and cat.strip():
            run("insert into expense (date, amount_lkr, category, notes) "
                "values (:d,:a,:c,:n)",
                dict(d=ts, a=amt, c=cat.strip(), n=note))
            st.success("Expense added!")
            st.cache_data.clear()


# ──────────────────  BUDGETS  ──────────────────
elif menu == "Budgets":
    st.subheader("📋 Category Budgets")
    df_bud = load_table("budget")
    st.dataframe(df_bud if not df_bud.empty else
                 pd.DataFrame(columns=["category", "limit_lkr"]))
    st.markdown("---")
    b_cat  = st.text_input("Category")
    b_lim  = st.number_input("Limit (LKR)", 0.0, step=10000.0)
    if st.button("Save / Update Budget") and b_cat.strip():
        run("insert into budget (category,limit_lkr) "
            "values (:c,:l) on conflict (category) do update set limit_lkr=:l",
            dict(c=b_cat.strip(), l=b_lim))
        st.success("Budget saved/updated!")

elif menu == "Pending":
    st.subheader("🕒 Add / Review Pending Income")
    with st.form("pending_form"):
        colD, colA = st.columns(2)
        p_date  = colD.date_input("Expected date", value=today + timedelta(days=7))
        p_amt   = colA.number_input("Amount (LKR)", 0.0, step=1000.0)
        p_src   = st.selectbox("Source", ("PayPal","Mom","Salary","Other"))
        p_note  = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Add pending")
        if submitted and p_amt > 0:
            run("insert into pending_income (expected_on, amount_lkr, source, notes) "
                "values (:d,:a,:s,:n)",
                dict(d=p_date, a=p_amt, s=p_src, n=p_note))
            st.success("Pending income added!")
            st.cache_data.clear()

    p_df = load_table("pending_income").sort_values(["cleared", "expected_on"])
    st.dataframe(p_df, hide_index=True, use_container_width=True)

    unclrd = p_df.loc[~p_df["cleared"], "id"]
    chosen = st.multiselect("Select IDs to move to Income", unclrd)
    if st.button("✅ Move to Income") and chosen:
        for pid in chosen:
            row = p_df.loc[p_df["id"] == pid].iloc[0]
            run("insert into income (date, amount_lkr, source, notes) "
                "values (now(), :a, :s, :n)",
                dict(a=row["amount_lkr"], s=row["source"], n=row["notes"]))
            run("update pending_income set cleared=true where id=:i", {"i": pid})
        st.success(f"{len(chosen)} item(s) cleared into Income.")


# ──────────────────  DASHBOARD  ──────────────────
elif menu == "Dashboard":
    st.subheader("📊 Dashboard")

    df_inc, df_exp, df_bud = load_table("income"), load_table("expense"), load_table("budget")
    tot_inc, tot_exp = df_inc["amount_lkr"].sum(), df_exp["amount_lkr"].sum()
    bal = tot_inc - tot_exp
    
    p_df       = load_table("pending_income")
    pending_li = p_df.loc[~p_df["cleared"], "amount_lkr"].sum()

    c1,c2,c3,c4 = st.columns([1.3,1.3,1.3,1.3])   # widen a bit
    c1.metric("Total Income",  fmt_rupees(tot_inc))
    c2.metric("Total Expense", fmt_rupees(tot_exp))
    c3.metric("Balance",       fmt_rupees(bal))
    c4.metric("Pending",       fmt_rupees(pending_li))


    total_budget = df_bud["limit_lkr"].sum()
    if total_budget > 0:
        remaining = max(total_budget - (bal + pending_li), 0)
        fig_stack = go.Figure()
        fig_stack.add_bar(name="Cash",    y=[bal])
        fig_stack.add_bar(name="Pending", y=[pending_li])
        fig_stack.add_bar(name="Remaining budget", y=[remaining])
        fig_stack.update_layout(barmode="stack",
                                title="Cash + Pending vs Budget",
                                showlegend=True,
                                xaxis_visible=False)
        st.plotly_chart(fig_stack, use_container_width=True)

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

    # ────────── Ledger + analytics (enhanced) ──────────
    if not df_inc.empty or not df_exp.empty:
        # --- Build ledger with true timestamps ---
        ledger = (pd.concat(
                     [df_inc.assign(delta=df_inc["amount_lkr"]),
                      df_exp.assign(delta=-df_exp["amount_lkr"])]
                  )
                  .sort_values("date", kind="stable")
                  .reset_index(drop=True))
        ledger["date"] = pd.to_datetime(ledger["date"]).dt.tz_localize(None)

        ledger["balance"] = ledger["delta"].cumsum()

        # ---------- 1. Burn-down gauge ----------
        total_budget = df_bud["limit_lkr"].sum() or 1   # avoid ÷0
        spent_pct    = min(ledger["balance"].iloc[-1] * -1 / total_budget * 100, 100)
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=spent_pct,
            number={"suffix":"%"},
            title={"text":"% of Budget Spent"},
            gauge={
                "axis":{"range":[0,100]},
                "bar":{"color":"red"},
                "steps":[
                    {"range":[0,80],"color":"lightgreen"},
                    {"range":[80,100],"color":"orange"}
                ]
            }
        ))
        st.plotly_chart(fig_g, use_container_width=True)

        # ---------- 2. Stair-step running balance ----------
        fig2 = go.Figure()
        fig2.add_scatter(x=ledger["date"], y=ledger["balance"],
                         mode="lines+markers", line_shape="hv",
                         name="Running balance")
        fig2.update_layout(title="Running Balance – every transaction",
                           xaxis_title="Date / Time", yaxis_title="LKR")
        st.plotly_chart(fig2, use_container_width=True)

        # ---------- 3. Daily cash-in / cash-out bars ----------
        daily = (ledger.groupby(ledger["date"].dt.date)["delta"]
                 .agg(received=lambda s: s[s>0].sum(),
                      spent   =lambda s: -s[s<0].sum())
                 .reset_index(names="day"))
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

        # ---------- 4. Calendar heat-map of spend ----------
        cal = daily.copy()
        cal["day"] = pd.to_datetime(cal["day"])
        heat = go.Figure(go.Heatmap(
                x=cal["day"],
                y=["Spent"]*len(cal),
                z=cal["spent"],
                colorscale="Reds",
                showscale=False))
        heat.update_layout(title="Spend intensity calendar",
                           xaxis_nticks=35, yaxis_visible=False)
        st.plotly_chart(heat, use_container_width=True)

        # ---------- 5. Budget-compliance pie ----------
        spent_by_cat = df_exp.groupby("category")["amount_lkr"].sum()
        merged = pd.concat([spent_by_cat,
                            df_bud.set_index("category")["limit_lkr"]],
                           axis=1, join="inner").fillna(0)
        def bucket(row):
            pct = row["amount_lkr"] / row["limit_lkr"] * 100 if row["limit_lkr"] else 0
            if pct < 80:      return "Under 80%"
            elif pct <=100:   return "80-100%"
            else:             return "Over"
        merged["buck"] = merged.apply(bucket, axis=1)
        pie_df = merged["buck"].value_counts()
        fig_p = go.Figure(data=[go.Pie(labels=pie_df.index, values=pie_df.values,
                                       hole=.4)])
        fig_p.update_layout(title="Budget compliance")
        st.plotly_chart(fig_p, use_container_width=True)

        # ---------- 6. Cash-flow forecast ----------
        horizon = datetime(2025,8,16)      # 7 days before wedding
        if len(ledger) >= 2:
            days = (ledger["date"] - ledger["date"].min()).dt.total_seconds()/86400
            coef = pd.Series(days).corr(ledger["balance"])   # simple slope sign
            slope = (ledger["balance"].iloc[-1]-
                     ledger["balance"].iloc[0]) / max(days.iloc[-1],1)
            future_days = (horizon - ledger["date"].iloc[-1].to_pydatetime()).days
            forecast    = ledger["balance"].iloc[-1] + slope*future_days
            fig_f = go.Figure()
            fig_f.add_scatter(x=ledger["date"], y=ledger["balance"],
                              mode="lines", name="Actual")
            fig_f.add_scatter(x=[ledger["date"].iloc[-1], horizon],
                              y=[ledger["balance"].iloc[-1], forecast],
                              mode="lines", name="Forecast",
                              line=dict(dash="dash"))
            fig_f.update_layout(title="Balance forecast (linear)",
                                xaxis_title="Date", yaxis_title="LKR")
            st.plotly_chart(fig_f, use_container_width=True)

        # ---------- 7. Top-5 expense table ----------
        top5 = (df_exp.sort_values("amount_lkr", ascending=False)
                 .head(5)[["id","date","category","amount_lkr","notes"]])
        st.subheader("💸 Top-5 expenses so far")
        st.dataframe(top5, hide_index=True, use_container_width=True)


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
        # pass the raw list; let psycopg2 adapt it to a Postgres array
        run(f"delete from {tbl} where id = any(:ids)", {"ids": del_ids})
        st.warning(f"Deleted {len(del_ids)} rows – refresh page to update.")


# ──────────────────  MOBILE-FRIENDLY SCROLLBAR  ──────────────────
st.markdown("""
<style>
/* thick scrollbar pinned left (webkit only) */
::-webkit-scrollbar { width: 14px; }
::-webkit-scrollbar-track { background: rgba(0,0,0,0.05); }
::-webkit-scrollbar-thumb { background: #c0c0c0; border-radius: 7px; }
html { direction: rtl; }       /* flip scroll bar to left */
body { direction: ltr; }       /* keep content LTR */
</style>""", unsafe_allow_html=True)


