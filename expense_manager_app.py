# expense_manager_app.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import date, datetime, timedelta
from pathlib import Path
import base64
from zoneinfo import ZoneInfo
from openai import OpenAI
import warnings, psycopg2

# ──────────────────────────────────────────────────────────────
#  0.  PROFILE PICKER  (Bride  /  Groom)
# ──────────────────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.title("Select Bride Or Groom")
    colG, colB = st.columns(2)

    if colG.button("🤵 Groom", use_container_width=True):
        st.session_state.profile = "groom"
        st.experimental_rerun()

    if colB.button("👰 Bride", use_container_width=True):
        st.session_state.profile = "bride"
        st.experimental_rerun()

    # enlarge the two buttons
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] > button {
            width: 100%; height: 72px;
            font-size: 1.4rem; font-weight: 600;
            border-radius: 12px; padding: .25rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.stop()  # wait until a choice is made

profile = st.session_state.profile            # "groom" | "bride"

# ──────────────────────────────────────────────────────────────
#  1.  DATABASE & GENERAL HELPERS
# ──────────────────────────────────────────────────────────────
def get_engine():
    return create_engine(
        st.secrets["DATABASE_URL"],
        connect_args={"sslmode": "require"},
    )

@st.cache_resource
def _engine():  # cached wrapper
    return get_engine()

engine = _engine()

# quick connectivity banner (optional)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        psycopg2.connect(st.secrets["DATABASE_URL"])
        st.success("Wedding of Himashi & Dishara – connected!")
    except Exception as e:
        st.error(e)

# add table-prefix helper  →  groom_income, bride_expense, …
TBL = lambda name: f"{profile}_{name}"

def run(sql: str, params: dict | None = None, fetch: bool = False):
    with engine.begin() as conn:
        res = conn.execute(text(sql), params or {})
        return res.fetchall() if fetch else None

@st.cache_data(ttl=30)
def load_table(name: str) -> pd.DataFrame:
    """Read `{profile}_{name}` fully into a DataFrame."""
    return pd.read_sql(f"select * from {TBL(name)}", engine)

# ───── UI helpers ─────────────────────────────────────────────
def datetime_input(
    label: str,
    default_date: date,
    default_time=datetime.strptime("12:00", "%H:%M").time(),
    tz=ZoneInfo("Asia/Colombo"),
) -> datetime:
    cd, ct = st.columns([2, 1])
    d_val = cd.date_input(f"{label} – date", value=default_date, key=f"d_{label}")
    t_val = ct.time_input(f"{label} – time", value=default_time, key=f"t_{label}")
    if t_val == default_time:
        ct.warning("← set the time")
    return datetime.combine(d_val, t_val, tzinfo=tz)

def add_background(image_path: str, veil_opacity=.15, veil_rgb=(255,255,255)):
    img_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    r, g, b = veil_rgb
    veil = f"rgba({r},{g},{b},{veil_opacity})"
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
              linear-gradient({veil},{veil}),
              url("data:image/jpg;base64,{img_b64}") center/cover no-repeat fixed;
        }}
        div[data-testid="stSidebar"] > div:first-child {{
            background: rgba(255,255,255,.85); border-radius:12px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def fmt_rupees(n: float) -> str:
    if n >= 1_000_000:  return f"LKR {n/1_000_000:.1f} M"
    if n >= 1_000:      return f"LKR {n/1_000:.0f} k"
    return f"LKR {n:,.0f}"

# ──────────────────────────────────────────────────────────────
#  2.  PAGE CONFIG & DECOR
# ──────────────────────────────────────────────────────────────
st.set_page_config("Wedding Expense Tracker", layout="centered")
add_background("assets/wedding_bg.jpg", veil_opacity=.15)

st.title("💍 Wedding Expense & Income Tracker")
today, wedding_day = date.today(), date(2025, 8, 23)
st.metric("⏳ Days until wedding", f"{max((wedding_day-today).days-1,0)} days")

# sidebar meta
menu = st.sidebar.radio(
    "Menu",
    ("Dashboard", "Quick Add", "Add Income", "Add Expense",
     "Budgets", "Pending", "Manage"),
)
st.sidebar.markdown(f"**Profile:** `{profile}`")
if st.sidebar.button("Switch profile"):
    st.session_state.pop("profile", None)
    st.experimental_rerun()

# ──────────────────────────────────────────────────────────────
#  3.  OPEN-AI free-text extractor (unchanged)
# ──────────────────────────────────────────────────────────────
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
SYSTEM_PROMPT = """
You are an assistant that extracts structured payment info
from user free-text. Output JSON with keys:
date (YYYY-MM-DD or empty), time (HH:MM or empty),
amount_lkr (number), category, source, notes.
"""
def nlp_extract(text: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
    )
    import json
    return json.loads(resp.choices[0].message.content)

# ──────────────────────────────────────────────────────────────
#  4.  INDIVIDUAL PAGES
# ──────────────────────────────────────────────────────────────
# --------------------  ADD INCOME  ---------------------------
if menu == "Add Income":
    with st.form(key="income_form"):
        st.subheader("➕ Add Income")
        ts     = datetime_input("Income", today)
        amount = st.number_input("Amount (LKR)", 0.0, step=1000.0)
        src    = st.selectbox("Source", ("Salary","Freelance","Gift","Other"))
        notes  = st.text_input("Notes (optional)")
        if st.form_submit_button("Add Income") and amount > 0:
            run(
                f"insert into {TBL('income')} (date, amount_lkr, source, notes) "
                "values (:d,:a,:s,:n)",
                dict(d=ts, a=amount, s=src, n=notes),
            )
            st.success("Income added!")
            st.cache_data.clear()

# --------------------  ADD EXPENSE ---------------------------
elif menu == "Add Expense":
    with st.form(key="expense_form"):
        st.subheader("➖ Add Expense")
        ts  = datetime_input("Expense", today)
        amt = st.number_input("Amount (LKR)", 0.0, step=1000.0)
        cat = st.text_input("Category (e.g., Suit, Venue)")
        note= st.text_input("Notes (optional)")
        if st.form_submit_button("Add Expense") and amt > 0 and cat.strip():
            run(
                f"insert into {TBL('expense')} (date, amount_lkr, category, notes) "
                "values (:d,:a,:c,:n)",
                dict(d=ts, a=amt, c=cat.strip(), n=note),
            )
            st.success("Expense added!")
            st.cache_data.clear()

# --------------------  QUICK ADD (LLM) -----------------------
elif menu == "Quick Add":
    st.subheader("🤖 Quick Add (free-text)")
    raw = st.text_area("Describe the transaction", height=120)
    if "qa_parsed" not in st.session_state:
        st.session_state.qa_parsed = None

    if st.button("🔍 Parse") and raw.strip():
        with st.spinner("Let me think…"):
            st.session_state.qa_parsed = nlp_extract(raw)
        st.success("Parsed!  Review below & hit Save")

    if st.session_state.qa_parsed:
        data = st.session_state.qa_parsed
        st.json(data, expanded=False)
        target = st.radio("Save as", ("expense", "income"), horizontal=True)

        if st.button("💾 Save to database"):
            dt = data.get("date") or date.today().isoformat()
            tm = data.get("time") or "12:00"
            ts = datetime.fromisoformat(f"{dt} {tm}")

            amt = float(data.get("amount_lkr") or 0)
            cat = (data.get("category") or "Other").title()
            src = (data.get("source")   or "Other").title()
            note= data.get("notes") or raw

            if target == "income":
                run(
                    f"insert into {TBL('income')} (date, amount_lkr, source, notes) "
                    "values (:d,:a,:s,:n)",
                    dict(d=ts, a=amt, s=src, n=note),
                )
            else:
                run(
                    f"insert into {TBL('expense')} (date, amount_lkr, category, notes) "
                    "values (:d,:a,:c,:n)",
                    dict(d=ts, a=amt, c=cat, n=note),
                )
            st.success(f"Saved {target}: LKR {amt:,.0f}")
            st.cache_data.clear()
            st.session_state.qa_parsed = None
            st.experimental_rerun()

# --------------------  BUDGETS  ------------------------------
elif menu == "Budgets":
    st.subheader("📋 Category Budgets")
    df_bud = load_table("budget")
    st.dataframe(df_bud if not df_bud.empty else pd.DataFrame(columns=["category","limit_lkr"]))
    st.markdown("---")
    b_cat = st.text_input("Category")
    b_lim = st.number_input("Limit (LKR)", 0.0, step=10_000.0)
    if st.button("Save / Update Budget") and b_cat.strip():
        run(
            f"""
            insert into {TBL('budget')} (category, limit_lkr)
            values (:c,:l)
            on conflict (category) do update set limit_lkr = :l
            """,
            dict(c=b_cat.strip(), l=b_lim),
        )
        st.success("Budget saved / updated!")
        st.cache_data.clear()

# --------------------  PENDING INCOME ------------------------
elif menu == "Pending":
    st.subheader("🕒 Pending Income")
    with st.form("pending_form"):
        c1,c2 = st.columns(2)
        p_date = c1.date_input("Expected on", value=today + timedelta(days=7))
        p_amt  = c2.number_input("Amount (LKR)", 0.0, step=1000.0)
        p_src  = st.selectbox("Source", ("PayPal","Gift","Salary","Other"))
        p_note = st.text_input("Notes (optional)")
        if st.form_submit_button("Add pending") and p_amt > 0:
            run(
                f"insert into {TBL('pending_income')} "
                "(expected_on, amount_lkr, source, notes, cleared) "
                "values (:d,:a,:s,:n,false)",
                dict(d=p_date, a=p_amt, s=p_src, n=p_note),
            )
            st.success("Pending income added!")
            st.cache_data.clear()

    p_df = load_table("pending_income").sort_values(["cleared","expected_on"])
    st.dataframe(p_df, hide_index=True)

    to_clear = st.multiselect("Select IDs to clear into Income",
                              p_df.loc[~p_df["cleared"], "id"])
    if st.button("✅ Move to Income") and to_clear:
        for pid in to_clear:
            row = p_df.loc[p_df["id"] == pid].iloc[0]
            run(
                f"insert into {TBL('income')} (date, amount_lkr, source, notes) "
                "values (now(), :a, :s, :n)",
                dict(a=float(row["amount_lkr"]), s=row["source"], n=row["notes"]),
            )
            run(f"update {TBL('pending_income')} set cleared=true where id=:i",
                {"i": pid})
        st.success(f"Cleared {len(to_clear)} item(s)")
        st.cache_data.clear()
        st.experimental_rerun()

# --------------------  DASHBOARD  ----------------------------
elif menu == "Dashboard":
    st.subheader("📊 Dashboard")

    df_inc  = load_table("income")
    df_exp  = load_table("expense")
    df_bud  = load_table("budget")
    df_pend = load_table("pending_income")

    tot_inc = df_inc["amount_lkr"].sum()
    tot_exp = df_exp["amount_lkr"].sum()
    bal     = tot_inc - tot_exp
    pending = df_pend.loc[~df_pend["cleared"], "amount_lkr"].sum()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Income",  fmt_rupees(tot_inc))
    c2.metric("Total Expense", fmt_rupees(tot_exp))
    c3.metric("Balance",       fmt_rupees(bal))
    c4.metric("Pending",       fmt_rupees(pending))

    # spent vs budget bar
    if not df_exp.empty:
        spent = df_exp.groupby("category")["amount_lkr"].sum()
        limit = df_bud.set_index("category")["limit_lkr"] if not df_bud.empty else pd.Series(dtype=float)
        bar_df = pd.concat([spent, limit], axis=1).fillna(0).reset_index()
        bar_df.columns = ["Category","Spent","Budget"]
        fig = go.Figure()
        fig.add_bar(x=bar_df["Category"], y=bar_df["Spent"],  name="Spent")
        fig.add_bar(x=bar_df["Category"], y=bar_df["Budget"], name="Budget")
        fig.update_layout(barmode="group", title="Spent vs Budget by Category")
        st.plotly_chart(fig, use_container_width=True)

    # ledger & daily charts (as before) …
    # ── keep the rest of your analytics code unchanged ──

# --------------------  MANAGE (edit / delete) ----------------
elif menu == "Manage":
    st.subheader("🛠 Manage Entries")
    tbl_choice = st.selectbox("Table", ("income","expense","budget","pending_income"))
    df = load_table(tbl_choice).sort_values(df.columns[0], ascending=False).reset_index(drop=True)

    disabled = ["category"] if tbl_choice == "budget" else ["id","date","source","category"]
    edited = st.data_editor(df, disabled=disabled, num_rows="dynamic", key="editor")

    if st.button("💾 Save changes"):
        diff = edited.compare(df)
        for idx in diff.index.unique(level=0):
            row = edited.loc[idx]
            if tbl_choice == "budget":
                run(
                    f"update {TBL('budget')} set limit_lkr=:l where category=:c",
                    dict(l=row["limit_lkr"], c=row["category"]),
                )
            else:
                run(
                    f"update {TBL(tbl_choice)} set amount_lkr=:a, notes=:n where id=:i",
                    dict(a=row["amount_lkr"], n=row.get("notes",""), i=row["id"]),
                )
        st.success("Updates saved!")
        st.cache_data.clear()

    del_key = "category" if tbl_choice == "budget" else "id"
    del_vals = st.multiselect(f"Select {del_key}(s) to delete", df[del_key])
    if st.button("🗑 Delete selected") and del_vals:
        run(
            f"delete from {TBL(tbl_choice)} where {del_key} = any(:vals)",
            {"vals": del_vals},
        )
        st.warning(f"Deleted {len(del_vals)} row(s)")
        st.cache_data.clear()
        st.experimental_rerun()

# ──────────────────────────────────────────────────────────────
#  5.  MOBILE-FRIENDLY LEFT SCROLLBAR
# ──────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    ::-webkit-scrollbar { width: 14px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,.05); }
    ::-webkit-scrollbar-thumb { background:#c0c0c0; border-radius:7px; }
    html{direction:rtl;} body{direction:ltr;}
    </style>
    """,
    unsafe_allow_html=True,
)
