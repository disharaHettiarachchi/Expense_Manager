import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import date, datetime, timedelta
from pathlib import Path
import base64
from zoneinfo import ZoneInfo 
from openai import OpenAI

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
        
#OpenAI Key
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = """
You are an assistant that extracts structured payment info
from user free-text. Output JSON with keys:
date (YYYY-MM-DD or empty), time (HH:MM or empty),
amount_lkr (number), category, source, notes.
"""

# ──────────────────  HELPERS  ──────────────────
def nlp_extract(text: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",   # or gpt-3.5-turbo
        temperature=0.0,
        messages=[
          {"role":"system", "content": SYSTEM_PROMPT},
          {"role":"user",   "content": text}
        ]
    )
    import json
    return json.loads(resp.choices[0].message.content)

def run(query, params=None, fetch=False):
    with engine.begin() as conn:
        res = conn.execute(text(query), params or {})
        return res.fetchall() if fetch else None

def load_table(tbl):
    return pd.read_sql(f"select * from {tbl}", engine)

def datetime_input(
        label: str,
        default_date: date,
        default_time = datetime.strptime("12:00", "%H:%M").time(),
        tz = ZoneInfo("Asia/Colombo")
) -> datetime:
    """Two widgets → one timezone-aware datetime."""
    c_date, c_time = st.columns([2, 1])

    d_val = c_date.date_input(
        f"{label} – date", value=default_date, key=f"d_{label}"
    )
    t_val = c_time.time_input(
        f"{label} – time", value=default_time, key=f"t_{label}"
    )

    # nudge if the user left the default noon value unchanged
    if t_val == default_time:
        c_time.warning("← set the time")

    # return aware datetime so Postgres stores the exact local wall-time
    return datetime.combine(d_val, t_val, tzinfo=tz)

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
    ("Dashboard", "Quick Add", "Add Income", "Add Expense", "Budgets",
      "Manage", "Pending") 
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
            
# ──────────────────  ADD Quick Add  ──────────────────
elif menu == "Quick Add":
    st.subheader("🤖 Quick Add (free-text)")

    raw = st.text_area(
        "Describe the transaction "
        "(e.g. “Paid photographer 75 000 yesterday 3 pm”)",
        height=120,
        key="qa_raw",
    )

    # keep parsed result across reruns
    if "qa_parsed" not in st.session_state:
        st.session_state.qa_parsed = None

    # 1️⃣ Parse
    if st.button("🔍 Parse") and raw.strip():
        with st.spinner("Let me think…"):
            st.session_state.qa_parsed = nlp_extract(raw)
        st.success("Parsed!  Review below & hit Save")

    # 2️⃣ Preview + confirm
    if st.session_state.qa_parsed:
        data = st.session_state.qa_parsed
        st.json(data, expanded=False)

        target = st.radio("Save as", ("expense", "income"), horizontal=True)

        if st.button("💾 Save to database"):

            # ── clean / validate ───────────────────────────
            #  ⬩ date fallback: if year < current → today
            dt_txt = data.get("date") or ""
            if len(dt_txt) == 10:        # YYYY-MM-DD
                yr = int(dt_txt[:4])
                if yr < date.today().year:
                    dt_txt = ""
            if not dt_txt:
                dt_txt = date.today().isoformat()

            #  ⬩ time fallback
            tm_txt = data.get("time") or "12:00"

            ts = datetime.fromisoformat(f"{dt_txt} {tm_txt}")

            amt = float(data.get("amount_lkr") or 0)
            cat = (data.get("category") or "Other").title()
            src = (data.get("source")   or "Other").title()

            #  ⬩ note = model note or full raw text
            note = data.get("notes") or raw

            # ── insert ─────────────────────────────────────
            if target == "income":
                run("""insert into income (date, amount_lkr, source, notes)
                       values (:d, :a, :s, :n)""",
                    dict(d=ts, a=amt, s=src, n=note))
            else:
                run("""insert into expense (date, amount_lkr, category, notes)
                       values (:d, :a, :c, :n)""",
                    dict(d=ts, a=amt, c=cat, n=note))

            st.success(f"Added {target}: LKR {amt:,.0f}")

            # housekeeping
            st.cache_data.clear()
            st.session_state.qa_parsed = None   # ← DO clear this
            # DO NOT reset qa_raw (widget key) → avoids StreamlitAPIException
            st.experimental_rerun()


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

# ──────────────────  PENDING  ──────────────────
elif menu == "Pending":
    st.subheader("🕒 Add / Review Pending Income")
    with st.form("pending_form"):
        colD, colA = st.columns(2)
        p_date  = colD.date_input("Expected date", value=today + timedelta(days=7))
        p_amt   = colA.number_input("Amount (LKR)", 0.0, step=1000.0)
        p_src   = st.selectbox("Source", ("PayPal","Gift","Salary","Other"))
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
        
            # ── clean every field ───────────────────────────
            amt  = 0.0 if pd.isna(row["amount_lkr"]) else float(row["amount_lkr"])
            src  = ""  if pd.isna(row["source"])     else str(row["source"])
            note = ""  if pd.isna(row["notes"])      else str(row["notes"])
        
            try:
                run(
                    "insert into income (date, amount_lkr, source, notes) "
                    "values (now(), :a, :s, :n)",
                    dict(a=amt, s=src, n=note)
                )
                run("update pending_income set cleared=true where id=:i", {"i": pid})
            except Exception as e:
                st.error(f"Couldn’t move ID {pid}: {e}")
                continue  # move on to next selection

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

        # ---------- Stair-step running balance ----------
        fig2 = go.Figure()
        fig2.add_scatter(x=ledger["date"], y=ledger["balance"],
                         mode="lines+markers", line_shape="hv",
                         name="Running balance")
        fig2.update_layout(title="Running Balance – every transaction",
                           xaxis_title="Date / Time", yaxis_title="LKR")
        st.plotly_chart(fig2, use_container_width=True)

        # ---------- Daily cash-in / cash-out bars ----------
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
        # ----------  Expense-breakdown donut ----------
        if not df_exp.empty:
            # 1) aggregate spend per category
            cat_tot = (df_exp.groupby("category")["amount_lkr"]
                               .sum()
                               .sort_values(ascending=False))

            # 2) merge very small slices into “Other”
            tail_threshold = 0.05 * cat_tot.sum()          # < 5 % of total
            small_sum      = cat_tot[cat_tot < tail_threshold].sum()
            cat_tot        = cat_tot[cat_tot >= tail_threshold]
            if small_sum > 0:
                cat_tot.loc["Other"] = small_sum

            # 3) colour palette – warm top-3, then blues/greens
            warm  = ["#ff7f0e", "#ff6361", "#ffa600"]
            cool  = ["#4e79a7", "#59a14f", "#8cd17d",
                     "#76b7b2", "#9c755f", "#e15759"]
            colors = (warm + cool)[: len(cat_tot)]

            # 4) draw donut
            fig_donut = go.Figure(go.Pie(
                labels       = cat_tot.index,
                values       = cat_tot.values,
                hole         = .45,
                marker_color = colors,
                sort         = False,                     # keep our order
                textinfo     = "label+percent",
                texttemplate = "%{label}<br>%{percent:.1%}"
                               "<br>(LKR %{value:,.0f})",
            ))
            fig_donut.update_layout(title="Expense breakdown by category")
            st.plotly_chart(fig_donut, use_container_width=True)


# ──────────────────  MANAGE (edit / delete)  ──────────────────
else:   # menu == "Manage"
    st.subheader("🛠 Manage Entries (edit / delete)")

    tbl = st.selectbox("Choose table", ("income", "expense", "budget"))

    df  = load_table(tbl)
    df  = df.sort_values(df.columns[0], ascending=False).reset_index(drop=True)

    # column rules per table
    if tbl == "budget":
        disabled_cols = ["category"]          # keep category immutable
    else:
        disabled_cols = ["id", "date", "source", "category"]

    edited = st.data_editor(
        df,
        disabled=disabled_cols,
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )

    if st.button("💾 Save changes"):
        diff = edited.compare(df)
        for idx in diff.index.unique(level=0):
            row = edited.loc[idx]
            if tbl == "budget":
                run("update budget set limit_lkr=:l where category=:c",
                    dict(l=row["limit_lkr"], c=row["category"]))
            else:
                run(f"update {tbl} set amount_lkr=:a, notes=:n where id=:i",
                    dict(a=row["amount_lkr"], n=row["notes"], i=row["id"]))
        st.success("Rows updated!")
        st.cache_data.clear()

    del_key  = "category" if tbl == "budget" else "id"
    del_vals = st.multiselect(f"Select {del_key}(s) to delete", df[del_key])

    if st.button("🗑 Delete selected") and del_vals:
        run(f"delete from {tbl} where {del_key} = any(:vals)", {"vals": del_vals})
        st.warning(f"Deleted {len(del_vals)} row(s).")
        st.cache_data.clear()
        st.experimental_rerun()


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
