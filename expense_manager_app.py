import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path, PurePosixPath
import base64
from openai import OpenAI
import psycopg2, warnings

# ─────────────────────────  PROFILE PICKER  ─────────────────────────
if "profile" not in st.session_state:
    st.set_page_config("Wedding Expense Tracker", layout="centered")
    st.title("Select Bride Or Groom")

    c1, c2 = st.columns(2)
    if c1.button("🤵 Groom", use_container_width=True):
        st.session_state.profile = "groom"
        st.experimental_rerun()
    if c2.button("👰 Bride", use_container_width=True):
        st.session_state.profile = "bride"
        st.experimental_rerun()

    # big buttons
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] > button{
            width:100%;height:72px;font-size:1.4rem;font-weight:600;
            border-radius:12px;padding:.3rem 0;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    st.stop()

# --------------------------------------------------------------------
profile = st.session_state.profile           # "bride" or "groom"
TBL      = lambda name: f"{profile}_{name}"  # convenience helper

# ─────────────────────────  DB & OPENAI  ────────────────────────────
engine = create_engine(
    st.secrets["DATABASE_URL"],
    connect_args={"sslmode": "require"},
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        psycopg2.connect(st.secrets["DATABASE_URL"])
    except Exception as e:
        st.error(e)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = """
You are an assistant that extracts structured payment info
from user free-text.  Output JSON with keys:
date (YYYY-MM-DD or empty), time (HH:MM or empty),
amount_lkr (number), category, source, notes.
"""

def nlp_extract(text: str) -> dict:
    import json, re
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
    )
    return json.loads(resp.choices[0].message.content)

def run(sql: str, params: dict | None = None, fetch: bool = False):
    with engine.begin() as conn:
        res = conn.execute(text(sql), params or {})
        return res.fetchall() if fetch else None

@st.cache_data(ttl=30)
def load_table(name: str) -> pd.DataFrame:
    """Read the whole *profile* table into a DataFrame"""
    return pd.read_sql(f"select * from {TBL(name)}", engine)

# ────────────────────────────  UI HELPERS  ──────────────────────────
def fmt_rupees(n: float) -> str:
    if n >= 1_000_000:
        return f"LKR {n/1_000_000:.1f} M"
    if n >= 1_000:
        return f"LKR {n/1_000:.0f} k"
    return f"LKR {n:,.0f}"

def datetime_input(label: str,
                   default_date: date,
                   default_time=datetime.strptime("12:00", "%H:%M").time(),
                   tz=ZoneInfo("Asia/Colombo")) -> datetime:
    cd, ct = st.columns([2, 1])
    d_val  = cd.date_input(f"{label} – date",  value=default_date)
    t_val  = ct.time_input(f"{label} – time",  value=default_time)
    if t_val == default_time:
        ct.warning("← set the time")
    return datetime.combine(d_val, t_val, tzinfo=tz)

def add_bg(image: str, veil_opacity=.15, veil_rgb=(255,255,255)):
    img_b64 = base64.b64encode(Path(image).read_bytes()).decode()
    r,g,b   = veil_rgb
    st.markdown(f"""
    <style>
    .stApp {{
        background:linear-gradient(rgba({r},{g},{b},{veil_opacity}),
                                   rgba({r},{g},{b},{veil_opacity})),
                   url("data:image/jpg;base64,{img_b64}") center/cover fixed;
    }}
    div[data-testid="stSidebar"]>div:first-child{{
        background:rgba(255,255,255,0.85);border-radius:12px;
    }}
    </style>""", unsafe_allow_html=True)

# ────────────────────────────  PAGE SET-UP  ─────────────────────────
st.set_page_config("Wedding Expense Tracker", layout="centered")
add_bg("assets/wedding_bg.jpg")

st.title("💍 Wedding Expense & Income Tracker")
today, wedding_day = date.today(), date(2025, 8, 23)
st.metric("⏳ Days until wedding", f"{max((wedding_day - today).days - 1, 0)} days")

# side-bar
menu = st.sidebar.radio(
    "Menu",
    ("Dashboard", "Quick Add", "Add Income", "Add Expense",
     "Budgets", "Manage", "Pending"),
)
st.sidebar.markdown(f"**Profile:** `{profile}`")
if st.sidebar.button("Switch profile"):
    del st.session_state.profile
    st.experimental_rerun()

# ────────────────────────────  ADD INCOME  ──────────────────────────
if menu == "Add Income":
    with st.form("inc_form"):
        st.subheader("➕ Add Income")
        ts     = datetime_input("Income", today)
        amount = st.number_input("Amount (LKR)", 0.0, step=1000.0)
        src    = st.selectbox("Source", ("Salary", "Freelance", "Gift", "Other"))
        note   = st.text_input("Notes (optional)")
        if st.form_submit_button("Add Income") and amount > 0:
            run(f"insert into {TBL('income')} (date, amount_lkr, source, notes)"
                " values (:d,:a,:s,:n)", dict(d=ts, a=amount, s=src, n=note))
            st.success("Income added!")
            st.cache_data.clear()

# ───────────────────────────  ADD EXPENSE  ──────────────────────────
elif menu == "Add Expense":
    with st.form("exp_form"):
        st.subheader("➖ Add Expense")
        ts  = datetime_input("Expense", today)
        amt = st.number_input("Amount (LKR)", 0.0, step=1000.0)
        cat = st.text_input("Category (e.g. Dress, Décor)")
        note= st.text_input("Notes (optional)")
        if st.form_submit_button("Add Expense") and amt > 0 and cat.strip():
            run(f"insert into {TBL('expense')}"
                " (date, amount_lkr, category, notes)"
                " values (:d,:a,:c,:n)",
                dict(d=ts, a=amt, c=cat.strip(), n=note))
            st.success("Expense added!")
            st.cache_data.clear()

# ────────────────────────────  QUICK ADD  ───────────────────────────
elif menu == "Quick Add":
    st.subheader("🤖 Quick Add (free-text)")
    raw = st.text_area("Describe the transaction", height=120, key="qa_raw")

    if "qa_data" not in st.session_state:
        st.session_state.qa_data = None

    if st.button("Parse") and raw.strip():
        with st.spinner("Let me think…"):
            st.session_state.qa_data = nlp_extract(raw)
        st.success("Parsed! Review & Save.")

    if st.session_state.qa_data:
        data = st.session_state.qa_data
        st.json(data, expanded=False)
        target = st.radio("Save as", ("expense", "income"), horizontal=True)

        if st.button("Save"):
            dt_txt = data.get("date") or today.isoformat()
            tm_txt = data.get("time") or "12:00"
            ts     = datetime.fromisoformat(f"{dt_txt} {tm_txt}")
            amt    = float(data.get("amount_lkr") or 0)
            cat    = (data.get("category") or "Other").title()
            src    = (data.get("source")   or "Other").title()
            note   = data.get("notes") or raw

            if target == "income":
                run(f"insert into {TBL('income')}"
                    " (date, amount_lkr, source, notes)"
                    " values (:d,:a,:s,:n)",
                    dict(d=ts, a=amt, s=src, n=note))
            else:
                run(f"insert into {TBL('expense')}"
                    " (date, amount_lkr, category, notes)"
                    " values (:d,:a,:c,:n)",
                    dict(d=ts, a=amt, c=cat, n=note))

            st.success("Saved!")
            st.cache_data.clear()
            st.session_state.qa_data = None
            st.experimental_rerun()

# ────────────────────────────  BUDGETS  ────────────────────────────
elif menu == "Budgets":
    st.subheader("📋 Category Budgets")
    df_bud = load_table("budget")
    st.dataframe(df_bud if not df_bud.empty else
                 pd.DataFrame(columns=["category", "limit_lkr"]))
    st.markdown("---")
    b_cat = st.text_input("Category")
    b_lim = st.number_input("Limit (LKR)", 0.0, step=10000.0)
    if st.button("Save / Update Budget") and b_cat.strip():
        run(f"""insert into {TBL('budget')} (category, limit_lkr)
                values (:c,:l)
                on conflict (category) do update set limit_lkr=:l""",
            dict(c=b_cat.strip(), l=b_lim))
        st.success("Budget saved/updated!")
        st.cache_data.clear()

# ─────────────────────────── PENDING  ───────────────────────────────
elif menu == "Pending":
    st.subheader("🕒 Pending Income")
    with st.form("pend_form"):
        d  = st.date_input("Expected date", today + timedelta(days=7))
        a  = st.number_input("Amount (LKR)", 0.0, step=1000.0)
        s  = st.selectbox("Source", ("PayPal", "Gift", "Salary", "Other"))
        nt = st.text_input("Notes (optional)")
        if st.form_submit_button("Add pending") and a > 0:
            run(f"""insert into {TBL('pending_income')}
                    (expected_on, amount_lkr, source, notes)
                    values (:d,:a,:s,:n)""",
                dict(d=d, a=a, s=s, n=nt))
            st.success("Pending added!")
            st.cache_data.clear()

    pend_df = load_table("pending_income").sort_values(
                  ["cleared", "expected_on"])
    st.dataframe(pend_df, hide_index=True, use_container_width=True)

# ─────────────────────────── DASHBOARD  ─────────────────────────────
elif menu == "Dashboard":
    st.subheader("📊 Dashboard")

    df_inc  = load_table("income")
    df_exp  = load_table("expense")
    df_bud  = load_table("budget")
    df_pend = load_table("pending_income")

    tot_inc = df_inc["amount_lkr"].sum()
    tot_exp = df_exp["amount_lkr"].sum()
    bal     = tot_inc - tot_exp
    pend    = df_pend.loc[~df_pend["cleared"], "amount_lkr"].sum()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Income",  fmt_rupees(tot_inc))
    c2.metric("Total Expense", fmt_rupees(tot_exp))
    c3.metric("Balance",       fmt_rupees(bal))
    c4.metric("Pending",       fmt_rupees(pend))

    # spent vs budget
    if not df_exp.empty:
        spent = df_exp.groupby("category")["amount_lkr"].sum()
        lim   = df_bud.set_index("category")["limit_lkr"] if not df_bud.empty else pd.Series(dtype=float)
        cmp   = pd.concat([spent, lim], axis=1).fillna(0).reset_index()
        cmp.columns = ["Category","Spent","Budget"]
        fig = go.Figure()
        fig.add_bar(x=cmp["Category"], y=cmp["Spent"],  name="Spent")
        fig.add_bar(x=cmp["Category"], y=cmp["Budget"], name="Budget")
        fig.update_layout(barmode="group", title="Spent vs Budget")
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────── MANAGE  ───────────────────────────────
else:   # menu == "Manage"
    st.subheader("🛠 Manage Entries")
    tbl_name = st.selectbox("Table", ("income", "expense", "budget"))
    df       = load_table(tbl_name).sort_values(df.columns[0], ascending=False)
    disable  = ["category"] if tbl_name=="budget" else ["id","date","source","category"]
    edited   = st.data_editor(df, disabled=disable, use_container_width=True)

    if st.button("Save changes"):
        diff = edited.compare(df)
        for i in diff.index.unique(level=0):
            row = edited.loc[i]
            if tbl_name == "budget":
                run(f"update {TBL('budget')} set limit_lkr=:l where category=:c",
                    dict(l=row["limit_lkr"], c=row["category"]))
            else:
                run(f"update {TBL(tbl_name)} set amount_lkr=:a, notes=:n where id=:i",
                    dict(a=row["amount_lkr"], n=row["notes"], i=row["id"]))
        st.success("Updated!")
        st.cache_data.clear()

    del_key = "category" if tbl_name=="budget" else "id"
    del_ids = st.multiselect("Delete", df[del_key])
    if st.button("Delete selected") and del_ids:
        run(f"delete from {TBL(tbl_name)} where {del_key}=any(:x)", {"x": del_ids})
        st.cache_data.clear()
        st.success("Deleted!")

# ───────────────────────── SCROLLBAR  ───────────────────────────────
st.markdown("""
<style>
::-webkit-scrollbar{width:14px;}
::-webkit-scrollbar-track{background:rgba(0,0,0,.05);}
::-webkit-scrollbar-thumb{background:#c0c0c0;border-radius:7px;}
html{direction:rtl;} body{direction:ltr;}
</style>""", unsafe_allow_html=True)
