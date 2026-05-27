"""
app.py - 個人資產追蹤系統
執行方式：streamlit run app.py
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import database as db

st.set_page_config(
    page_title="資產追蹤",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* 隱藏 Streamlit 預設 chrome */
#MainMenu, footer, header {visibility: hidden;}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: #0f172a;
    border-right: 1px solid #1e293b;
}
/* 縮減預設上下 padding，讓內容更緊湊 */
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem !important;
    padding-bottom: 1rem !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.1) !important;
    margin: 0.8rem 0 !important;
}
/* 標題 */
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {
    color: #f1f5f9;
    font-size: 1.3rem !important;
    font-weight: 700;
    letter-spacing: 0.03em;
    margin-bottom: 0.5rem !important;
}
/* Radio 導覽文字 */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] label p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label span {
    color: #f1f5f9 !important;
    font-size: 1.05rem !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: 8px 4px !important;
    line-height: 1.6 !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #38bdf8 !important;
    font-size: 1.35rem !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    color: #64748b !important;
}
section[data-testid="stSidebar"] .stCaption p {
    color: #475569 !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 14px 18px !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.45rem !important;
    font-weight: 700 !important;
}

/* ── Containers ── */
[data-testid="stVerticalBlockBorderWrapper"] > div:first-child {
    border-radius: 12px !important;
    border-color: #e2e8f0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── 初始化資料庫 ───────────────────────────────────────────────────────────────
db.init_db()
db.seed_initial_data()

# ── 工具函數 ───────────────────────────────────────────────────────────────────

def usd_rate() -> float:
    return float(db.get_setting("usd_twd_rate", "32.5"))

def to_twd(amount: float, currency: str) -> float:
    return amount * usd_rate() if currency == "USD" else amount

def fmt_twd(n: float) -> str:
    return f"NT$ {n:,.0f}"

def fmt_usd(n: float) -> str:
    return f"$ {n:,.2f}"

def pnl_color(val):
    if val > 0:   return "🔴"
    if val < 0:   return "🟢"
    return "⚪"

def fee_cfg() -> dict:
    """從 DB 讀取手續費設定，附預設值"""
    g = lambda k, d: float(db.get_setting(k, d))
    return {
        "tw_comm":      g("tw_commission_rate",     "0.001425"),
        "tw_lot_min":   g("tw_lot_min_fee",         "20"),
        "tw_odd_comm":  g("tw_odd_commission_rate", "0.000855"),
        "tw_odd_min":   g("tw_odd_min_fee",         "1"),
        "tw_stock_tax": g("tw_stock_tax_rate",       "0.003"),
        "tw_etf_tax":   g("tw_etf_tax_rate",         "0.001"),
        "us_comm":      g("us_commission_rate",      "0.001"),
        "us_min":       g("us_min_fee",              "1.0"),
    }

def est_sell_cost(market: str, symbol: str, shares: float, price: float) -> float:
    """估算若今天賣出的手續費＋證交稅（台股）/ 手續費（美股）"""
    fc = fee_cfg()
    amount = shares * price
    if market == "TW":
        is_lot = shares == int(shares) and int(shares) % 1000 == 0
        commission = max(round(amount * fc["tw_comm"]), int(fc["tw_lot_min"])) if is_lot \
                     else max(round(amount * fc["tw_odd_comm"]), int(fc["tw_odd_min"]))
        stt = round(amount * (fc["tw_etf_tax"] if symbol.startswith("00") else fc["tw_stock_tax"]))
        return float(commission + stt)
    elif market == "US":
        return float(max(round(amount * fc["us_comm"], 2), fc["us_min"]))
    return 0.0

def account_twd_value(a) -> float:
    """折台幣：優先使用手動設定的換匯成本，否則用即時匯率換算"""
    if a.get("twd_cost") is not None:
        return float(a["twd_cost"])
    return to_twd(a["balance"], a["currency"])

# ── 側邊欄 ────────────────────────────────────────────────────────────────────
_NAV = {
    ":material/dashboard: 總覽":           "overview",
    ":material/account_balance: 帳戶管理": "accounts",
    ":material/trending_up: 持股管理":     "holdings",
    ":material/swap_horiz: 股票買賣":      "trades",
    ":material/receipt_long: 資金異動":    "transactions",
    ":material/settings: 設定":            "settings",
}

with st.sidebar:
    st.markdown("## :material/account_balance_wallet: 資產追蹤")
    st.markdown("---")
    _nav_label = st.radio(
        "功能選單",
        list(_NAV.keys()),
        label_visibility="collapsed",
        key="nav_radio",
    )
    page = _NAV[_nav_label]
    st.markdown("---")
    rate = usd_rate()
    st.metric("USD / TWD 匯率", f"{rate:.2f}")
    st.caption(f"更新時間：{db.get_setting('rate_updated', '未設定')}")
    st.markdown("---")
    st.caption("Made by Avidityyds")

# ── 全域 toast 通知 ───────────────────────────────────────────────────────────
if _t := st.session_state.pop("_toast", None):
    st.toast(_t, icon="✅")

# ════════════════════════════════════════════════════════════════════════════════
# 總覽
# ════════════════════════════════════════════════════════════════════════════════
if page == "overview":
    st.title(":material/dashboard: 資產總覽")
    rate = usd_rate()

    accounts = db.get_accounts()
    holdings = db.get_holdings()

    # ── 計算各類資產 ───────────────────────────────────────
    cash_twd = sum(account_twd_value(a) for a in accounts)

    stock_value_twd   = 0.0
    stock_cost_twd    = 0.0
    stock_pnl_net_twd = 0.0
    for h in holdings:
        price     = h["last_price"] or h["avg_cost"]
        value     = h["shares"] * price
        cost      = h["shares"] * h["avg_cost"]
        sell_cost = est_sell_cost(h["market"], h["symbol"], h["shares"], price)
        stock_value_twd   += to_twd(value, h["currency"])
        stock_cost_twd    += to_twd(cost,  h["currency"])
        stock_pnl_net_twd += to_twd(value - cost - sell_cost, h["currency"])

    total_twd     = cash_twd + stock_value_twd
    total_pnl_twd = stock_pnl_net_twd

    # ── KPI 卡片 ────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總資產（折台幣）", fmt_twd(total_twd))
    c2.metric("現金部位",          fmt_twd(cash_twd))
    c3.metric("股票市值",          fmt_twd(stock_value_twd))
    pnl_pct = (total_pnl_twd / stock_cost_twd * 100) if stock_cost_twd else 0
    c4.metric(
        "股票損益",
        fmt_twd(total_pnl_twd),
        f"{pnl_pct:+.2f}%",
        delta_color="normal"
    )

    st.markdown("---")

    # ── 圖表區 ──────────────────────────────────────────────
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("資產配置")
        labels = ["現金", "台股", "美股"]
        tw_stock_val = sum(
            to_twd(h["shares"] * (h["last_price"] or h["avg_cost"]), h["currency"])
            for h in holdings if h["market"] == "TW"
        )
        us_stock_val = sum(
            to_twd(h["shares"] * (h["last_price"] or h["avg_cost"]), h["currency"])
            for h in holdings if h["market"] == "US"
        )
        values = [cash_twd, tw_stock_val, us_stock_val]
        fig_pie = px.pie(
            names=labels, values=values,
            color_discrete_sequence=["#3B82F6", "#10B981", "#F59E0B"],
            hole=0.45
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(
            showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=280
        )
        st.plotly_chart(fig_pie, width="stretch")

        # 帳戶清單
        st.subheader("帳戶餘額")
        for a in accounts:
            bal_str = fmt_usd(a["balance"]) if a["currency"] == "USD" else fmt_twd(a["balance"])
            twd_val = account_twd_value(a)
            with st.container(border=True):
                st.markdown(f"**{a['name']}**")
                cols = st.columns(2)
                cols[0].metric("餘額", bal_str)
                if a["currency"] == "USD":
                    lbl = "折台幣（手動）" if a.get("twd_cost") is not None else "折台幣"
                    cols[1].metric(lbl, fmt_twd(twd_val))

    with col_right:
        st.subheader("持倉損益")
        rows = []
        for h in holdings:
            price     = h["last_price"] or h["avg_cost"]
            value     = h["shares"] * price
            cost      = h["shares"] * h["avg_cost"]
            sell_cost = est_sell_cost(h["market"], h["symbol"], h["shares"], price)
            pnl       = value - cost - sell_cost
            pct       = (pnl / cost * 100) if cost else 0
            rows.append({
                "市場":   h["market"],
                "代號":   h["symbol"],
                "名稱":   h["name"],
                "股數":   h["shares"],
                "均價":   h["avg_cost"],
                "現價":   price,
                "市值":   value,
                "損益":   pnl,
                "報酬%":  pct,
                "幣別":   h["currency"],
                "更新日": h["last_updated"] or "—",
            })

        if rows:
            df = pd.DataFrame(rows)
            # 損益橫條圖
            df_sorted = df.sort_values("損益")
            bar_colors = ["#10B981" if v < 0 else "#EF4444" for v in df_sorted["損益"]]
            fig_bar = go.Figure(go.Bar(
                x=df_sorted["損益"],
                y=df_sorted["名稱"],
                orientation='h',
                marker_color=bar_colors,
                text=[f"{v:+.1f}%" for v in df_sorted["報酬%"]],
                textposition="outside"
            ))
            fig_bar.update_layout(
                xaxis_title="損益（原幣）", yaxis_title="",
                margin=dict(t=10, b=10, l=0, r=40), height=320,
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_bar, width="stretch")

            # 持倉表格（台股 / 美股分開顯示）
            def render_holdings_table(subset: pd.DataFrame):
                d = subset.copy()
                d["均價"] = d.apply(lambda r: fmt_usd(r["均價"]) if r["幣別"]=="USD" else f"{r['均價']:,.2f}", axis=1)
                d["現價"] = d.apply(lambda r: fmt_usd(r["現價"]) if r["幣別"]=="USD" else f"{r['現價']:,.2f}", axis=1)
                d["市值"] = d.apply(lambda r: fmt_usd(r["市值"]) if r["幣別"]=="USD" else fmt_twd(r["市值"]), axis=1)
                d["損益"] = d.apply(lambda r: f"{pnl_color(r['損益'])} {r['損益']:+,.2f}", axis=1)
                d["報酬%"] = d["報酬%"].map(lambda x: f"{x:+.2f}%")
                d["股數"]  = d["股數"].map(lambda x: f"{x:g}")
                st.dataframe(d[["代號","名稱","股數","均價","現價","市值","損益","報酬%","更新日"]],
                             width="stretch", hide_index=True)

            tw_df = df[df["市場"] == "TW"]
            us_df = df[df["市場"] == "US"]

            if not tw_df.empty:
                st.markdown(":material/flag: **台股**", help="Taiwan Stock Exchange / OTC")
                render_holdings_table(tw_df)

            if not tw_df.empty and not us_df.empty:
                st.markdown('<hr style="border:none;border-top:2px solid #cbd5e1;margin:6px 0 10px 0;">', unsafe_allow_html=True)

            if not us_df.empty:
                st.markdown(":material/public: **美股**", help="US Equities")
                render_holdings_table(us_df)
        else:
            st.info("尚無持倉資料")


# ════════════════════════════════════════════════════════════════════════════════
# 帳戶管理
# ════════════════════════════════════════════════════════════════════════════════
elif page == "accounts":
    st.title(":material/account_balance: 帳戶管理")

    accounts = db.get_accounts()
    rate = usd_rate()

    # ── 現有帳戶 ────────────────────────────────────────────
    st.subheader("現有帳戶")
    for a in accounts:
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 1, 1])
            cols[0].markdown(f"**{a['name']}**  \n`{a['type']} · {a['currency']}`")
            bal_str = fmt_usd(a["balance"]) if a["currency"] == "USD" else fmt_twd(a["balance"])
            twd_lbl = ("折台幣（手動）" if a.get("twd_cost") is not None else "折台幣") if a["currency"] == "USD" else "折台幣"
            cols[1].metric("餘額", bal_str)
            cols[2].metric(twd_lbl, fmt_twd(account_twd_value(a)))

            with cols[3]:
                if st.button("調整", key=f"adj_{a['id']}", icon=":material/edit:"):
                    st.session_state[f"editing_{a['id']}"] = True
                    st.session_state[f"deleting_{a['id']}"] = False

            with cols[4]:
                if st.button("刪除", key=f"del_{a['id']}", icon=":material/delete:", type="secondary"):
                    st.session_state[f"deleting_{a['id']}"] = True
                    st.session_state[f"editing_{a['id']}"] = False

            if st.session_state.get(f"deleting_{a['id']}"):
                st.warning(f"確定要刪除「{a['name']}」？此操作無法復原，相關異動紀錄也會一併刪除。")
                d1, d2 = st.columns(2)
                if d1.button("確認刪除", key=f"confirm_del_{a['id']}", icon=":material/delete:", type="primary"):
                    db.delete_account(a["id"])
                    st.session_state[f"deleting_{a['id']}"] = False
                    st.session_state["_toast"] = f"已刪除帳戶「{a['name']}」"
                    st.rerun()
                if d2.button("取消", key=f"cancel_del_{a['id']}"):
                    st.session_state[f"deleting_{a['id']}"] = False
                    st.rerun()

            if st.session_state.get(f"editing_{a['id']}"):
                with st.form(key=f"form_adj_{a['id']}"):
                    st.markdown(f"#### 調整「{a['name']}」餘額")
                    new_bal = st.number_input(
                        "新餘額", value=float(a["balance"]), step=100.0, format="%.2f"
                    )
                    new_twd_cost = None
                    if a["currency"] == "USD":
                        current_twd = float(a["twd_cost"]) if a.get("twd_cost") is not None else to_twd(a["balance"], "USD")
                        new_twd_cost = st.number_input(
                            "折台幣金額（換匯成本）",
                            value=current_twd, step=100.0, format="%.0f",
                            help="按換匯當時匯率計算的台幣等值，不隨即時匯率浮動。留空（設為 0）表示使用即時匯率換算。"
                        )
                    note = st.text_input("備註（選填）")
                    tx_date = st.date_input("日期", value=date.today())
                    s1, s2 = st.columns(2)
                    submitted = s1.form_submit_button("確認", icon=":material/check:")
                    cancel = s2.form_submit_button("取消")
                    if submitted:
                        db.record_account_transaction(
                            "adjustment", new_bal, a["currency"],
                            tx_date.isoformat(), to_id=a["id"], notes=note
                        )
                        if a["currency"] == "USD":
                            db.update_account_twd_cost(a["id"], new_twd_cost if new_twd_cost else None)
                        st.session_state[f"editing_{a['id']}"] = False
                        st.session_state["_toast"] = "餘額已更新"
                        st.rerun()
                    if cancel:
                        st.session_state[f"editing_{a['id']}"] = False
                        st.rerun()

    st.markdown("---")

    # ── 新增帳戶 ────────────────────────────────────────────
    with st.expander("新增帳戶"):
        with st.form("add_account"):
            c1, c2, c3 = st.columns(3)
            name     = c1.text_input("帳戶名稱", placeholder="e.g. 中信銀行活存")
            atype_label = c2.selectbox("類型", ["銀行", "證券"])
            atype = {"銀行": "bank", "證券": "securities"}[atype_label]
            currency = c3.selectbox("幣別", ["TWD", "USD"])
            balance  = st.number_input("初始餘額", value=0.0, step=100.0, format="%.2f")
            notes    = st.text_input("備註（選填）")
            if st.form_submit_button("新增帳戶", icon=":material/add:"):
                if name:
                    db.add_account(name, atype, currency, balance, notes)
                    st.session_state["_toast"] = f"已新增帳戶「{name}」"
                    st.rerun()
                else:
                    st.error("請填寫帳戶名稱")

    st.markdown("---")

    # ── 資金轉帳 ────────────────────────────────────────────
    st.subheader("記錄資金轉帳 / 存提")
    with st.form("transfer_form"):
        tx_type_label = st.selectbox("類型", ["轉帳", "存入", "提出"])
        tx_type = {"轉帳": "transfer", "存入": "deposit", "提出": "withdrawal"}[tx_type_label]
        c1, c2, c3 = st.columns(3)
        acc_names = {a["name"]: a["id"] for a in accounts}
        acc_list  = list(acc_names.keys())

        from_acc = c1.selectbox("從帳戶", ["（無）"] + acc_list, key="from_acc")
        to_acc   = c2.selectbox("到帳戶",  ["（無）"] + acc_list, key="to_acc")
        amount   = c3.number_input("金額（從帳戶扣除）", value=0.0, step=1000.0, format="%.2f")

        c4, c5, c6 = st.columns(3)
        currency = c4.selectbox("幣別", ["TWD", "USD"], help="轉帳時幣別由帳戶自動判斷，此欄僅在存入／提出時有效")
        exrate   = c5.number_input("USD/TWD 匯率", value=rate, step=0.1, format="%.4f",
                                   help="台幣→美金 ÷ 此值，美金→台幣 × 此值")
        tx_date  = c6.date_input("日期", value=date.today())
        notes    = st.text_input("備註")

        if st.form_submit_button("記錄", icon=":material/check:"):
            from_id = acc_names.get(from_acc) if from_acc != "（無）" else None
            to_id   = acc_names.get(to_acc)   if to_acc   != "（無）" else None
            if amount <= 0:
                st.error("金額必須大於 0")
            else:
                db.record_account_transaction(
                    tx_type, amount, currency, tx_date.isoformat(),
                    from_id=from_id, to_id=to_id,
                    exchange_rate=exrate, notes=notes
                )
                st.session_state["_toast"] = "已記錄資金異動"
                st.rerun()


# ════════════════════════════════════════════════════════════════════════════════
# 持股管理
# ════════════════════════════════════════════════════════════════════════════════
elif page == "holdings":
    st.title(":material/trending_up: 持股管理")
    rate = usd_rate()

    holdings = db.get_holdings()
    stocks   = db.get_stocks()
    accounts = db.get_accounts()

    # ── 更新股價 ────────────────────────────────────────────
    st.subheader("更新股價")

    col_auto, col_manual = st.columns(2)
    with col_auto:
        with st.container(border=True):
            st.markdown("**自動抓取（yfinance）**")
            if st.button("自動更新所有股價", icon=":material/sync:"):
                try:
                    import yfinance as yf
                    import io, contextlib
                    updated = []
                    for s in stocks:
                        if s["market"] != "TW":
                            candidates = [s["symbol"]]
                        else:
                            candidates = [s["symbol"] + ".TW", s["symbol"] + ".TWO"]
                        price = None
                        for ticker_sym in candidates:
                            try:
                                _buf = io.StringIO()
                                with contextlib.redirect_stderr(_buf):
                                    t = yf.Ticker(ticker_sym)
                                    p = t.fast_info.last_price
                                if p and p > 0:
                                    price = p
                                    break
                            except Exception:
                                pass
                        if price:
                            db.update_last_price(s["id"], round(price, 3))
                            updated.append(f"{s['name']}: {price:.2f}")
                        else:
                            st.warning(f"{s['name']} 抓取失敗")
                    db.set_setting("rate_updated", date.today().isoformat())
                    st.session_state["_toast"] = f"股價更新完成（{len(updated)} 檔）"
                    st.rerun()
                except ImportError:
                    st.error("請先安裝 yfinance：`pip install yfinance`")

    with col_manual:
        with st.container(border=True):
            st.markdown("**手動輸入現價**")
            with st.form("manual_price"):
                stock_opts = {f"{s['name']} ({s['symbol']})": s["id"] for s in stocks}
                chosen = st.selectbox("選擇股票", list(stock_opts.keys()))
                new_price = st.number_input("現價", value=0.0, step=0.01, format="%.3f")
                if st.form_submit_button("更新", icon=":material/check:"):
                    if new_price > 0:
                        db.update_last_price(stock_opts[chosen], new_price)
                        st.session_state["_toast"] = "股價已更新"
                        st.rerun()
                    else:
                        st.error("請輸入有效價格")

    st.markdown("---")

    # ── 持倉明細 ────────────────────────────────────────────
    st.subheader("持倉明細")
    st.caption("損益已扣除預估賣出手續費＋證交稅")

    for market_label, market_code in [("🇺🇸 美股", "US"), ("🇹🇼 台股", "TW")]:
        mkt_holdings = [h for h in holdings if h["market"] == market_code]
        if not mkt_holdings:
            continue
        st.markdown(f"#### {market_label}")
        rows = []
        total_pnl = 0.0
        for h in mkt_holdings:
            price     = h["last_price"] or h["avg_cost"]
            val       = h["shares"] * price
            cost      = h["shares"] * h["avg_cost"]
            sell_cost = est_sell_cost(h["market"], h["symbol"], h["shares"], price)
            pnl       = val - cost - sell_cost
            pct       = (pnl / cost * 100) if cost else 0
            total_pnl += pnl
            rows.append({
                "名稱":    h["name"],
                "代號":    h["symbol"],
                "股數":    h["shares"],
                "均價":    h["avg_cost"],
                "現價":    price,
                "市值":    val,
                "損益":    pnl,
                "報酬%":   pct,
                "幣別":    h["currency"],
                "更新日":  h["last_updated"] or "—",
                "帳戶":    h["account_name"],
            })

        df = pd.DataFrame(rows)
        cur = "USD" if market_code == "US" else "TWD"
        df_disp = df.copy()
        df_disp["均價"] = df["均價"].map(lambda x: f"{x:,.3f}" if market_code=="US" else f"{x:,.2f}")
        df_disp["現價"] = df["現價"].map(lambda x: f"{x:,.3f}" if market_code=="US" else f"{x:,.2f}")
        df_disp["市值"] = df["市值"].map(lambda x: fmt_usd(x) if cur=="USD" else fmt_twd(x))
        df_disp["損益"] = df.apply(lambda r: f"{pnl_color(r['損益'])} {r['損益']:+,.2f}", axis=1)
        df_disp["報酬%"] = df["報酬%"].map(lambda x: f"{x:+.2f}%")
        df_disp["股數"] = df["股數"].map(lambda x: f"{x:g}")

        st.dataframe(
            df_disp[["名稱","代號","股數","均價","現價","市值","損益","報酬%","帳戶","更新日"]],
            width="stretch", hide_index=True
        )
        st.caption(f"小計損益：{pnl_color(total_pnl)} {total_pnl:+,.2f} {cur}"
                   + (f"  ≈ {fmt_twd(to_twd(total_pnl,'USD'))}" if cur=="USD" else ""))

    # ── 尚無部位的股票 ─────────────────────────────────────
    holding_ids = {h["stock_id"] for h in holdings}
    zero_stocks = [s for s in stocks if s["id"] not in holding_ids]
    if zero_stocks:
        st.markdown("---")
        st.subheader("尚無部位")
        st.caption("已建立主檔但尚未記錄買入，請至「股票買賣」新增第一筆交易")
        zdf = pd.DataFrame([{
            "代號": s["symbol"], "名稱": s["name"],
            "市場": s["market"], "幣別": s["currency"], "帳戶": s["account_name"]
        } for s in zero_stocks])
        st.dataframe(zdf, width="stretch", hide_index=True)

    st.markdown("---")

    # ── 新增股票主檔 ────────────────────────────────────────
    with st.expander("新增股票（建立主檔）"):
        with st.form("add_stock"):
            acc_opts = {a["name"]: a["id"] for a in accounts}
            c1, c2, c3 = st.columns(3)
            symbol   = c1.text_input("代號", placeholder="e.g. AAPL / 2330")
            name     = c2.text_input("名稱", placeholder="e.g. 台積電")
            market   = c3.selectbox("市場", ["US", "TW"])
            c4, c5 = st.columns(2)
            currency = c4.selectbox("幣別", ["USD", "TWD"])
            account  = c5.selectbox("所屬帳戶", list(acc_opts.keys()))
            if st.form_submit_button("新增股票", icon=":material/add:"):
                if symbol and name:
                    db.add_stock(symbol, name, market, currency, acc_opts[account])
                    st.session_state["_toast"] = f"已新增 {symbol.upper()} {name}"
                    st.rerun()
                else:
                    st.error("請填寫代號與名稱")


# ════════════════════════════════════════════════════════════════════════════════
# 股票買賣
# ════════════════════════════════════════════════════════════════════════════════
elif page == "trades":
    st.title(":material/swap_horiz: 股票買賣紀錄")

    stocks   = db.get_stocks()
    rate     = usd_rate()
    stock_opts = {f"{s['name']} ({s['symbol']})": s for s in stocks}
    holdings_map = {h["stock_id"]: h["shares"] for h in db.get_holdings()}

    # ── 手續費計算 ──────────────────────────────────────────
    def calc_fee(market: str, shares: float, price: float) -> tuple[float, str]:
        """回傳 (計算後手續費, 說明文字)"""
        fc = fee_cfg()
        amount = shares * price
        if market == "TW":
            is_lot = (shares == int(shares) and int(shares) % 1000 == 0)
            if is_lot:
                fee = max(round(amount * fc["tw_comm"]), int(fc["tw_lot_min"]))
                note = f"整張 ×{fc['tw_comm']*100:.4f}%，最低 NT${int(fc['tw_lot_min'])}（= {amount * fc['tw_comm']:.1f}，取 {fee}）"
            else:
                fee = max(round(amount * fc["tw_odd_comm"]), int(fc["tw_odd_min"]))
                note = f"零股 ×{fc['tw_odd_comm']*100:.4f}%，最低 NT${int(fc['tw_odd_min'])}（= {amount * fc['tw_odd_comm']:.2f}，取 {fee}）"
        elif market == "US":
            fee = max(round(amount * fc["us_comm"], 2), fc["us_min"])
            note = f"美股 ×{fc['us_comm']*100:.3f}%，最低 ${fc['us_min']}（= {fee:.2f}）"
        else:
            fee = 0.0
            note = ""
        return fee, note

    # ── 新增買賣 ────────────────────────────────────────────
    with st.container(border=True):
        st.subheader("新增一筆買賣")

        c1, c2 = st.columns(2)
        chosen_label = c1.selectbox("股票", list(stock_opts.keys()), key="trade_stock")
        tx_type      = c2.selectbox("類型", ["buy", "sell"], key="trade_type",
                                    format_func=lambda x: "買入" if x == "buy" else "賣出")

        s = stock_opts[chosen_label]
        c3, c4, c5, c6 = st.columns(4)
        shares  = c3.number_input("股數",   min_value=0.0001, value=1.0,  step=1.0,  key="trade_shares")
        price   = c4.number_input("成交價", value=0.0,        step=0.01,  format="%.3f", key="trade_price")
        tx_date = c6.date_input("日期", value=date.today(), key="trade_date")

        # 自動計算手續費
        auto_fee, fee_note = (0.0, "") if (shares <= 0 or price <= 0) else calc_fee(s["market"], shares, price)
        fee = c5.number_input("手續費", value=float(auto_fee), min_value=0.0, step=1.0, format="%.2f")
        if fee_note:
            c5.caption(fee_note)

        notes = st.text_input("備註（選填）", key="trade_notes")

        if st.button("確認送出", icon=":material/check:", key="trade_submit"):
            current_shares = holdings_map.get(s["id"], 0)
            if price <= 0:
                st.error("請輸入成交價")
            elif shares <= 0:
                st.error("股數必須大於 0")
            elif tx_type == "sell" and shares > current_shares:
                st.error(f"賣出股數（{shares:g}）超過現有持倉（{current_shares:g} 股）")
            else:
                db.record_stock_transaction(
                    s["id"], tx_type, shares, price, fee,
                    tx_date.isoformat(), notes
                )
                amt = shares * price + (fee if tx_type == "buy" else -fee)
                st.session_state["_toast"] = (
                    f"{'買入' if tx_type=='buy' else '賣出'} {s['name']} "
                    f"{shares:g} 股 @ {price:.3f}，{amt:,.2f} {s['currency']}"
                )
                st.rerun()

    st.markdown("---")

    # ── 歷史紀錄 ────────────────────────────────────────────
    st.subheader("交易歷史")

    txs = db.get_stock_transactions()
    if txs:
        df = pd.DataFrame(txs)
        df["類型"]   = df["type"].map({"buy": "🟢 買入", "sell": "🔴 賣出"})
        df["總金額"] = (df["shares"] * df["price"] + df["fee"]).map(lambda x: f"{x:,.2f}")
        df["手續費"] = df["fee"].map(lambda x: f"{x:,.2f}")
        df["股數"]   = df["shares"].map(lambda x: f"{x:g}")
        df["成交價"] = df["price"].map(lambda x: f"{x:,.3f}")

        # 篩選器
        col_f1, col_f2 = st.columns(2)
        filter_stock = col_f1.selectbox(
            "篩選股票", ["全部"] + [f"{s['name']} ({s['symbol']})" for s in stocks]
        )
        filter_type = col_f2.selectbox("篩選類型", ["全部", "買入", "賣出"])

        df_show = df.copy()
        if filter_stock != "全部":
            sym = filter_stock.split("(")[-1].rstrip(")")
            df_show = df_show[df_show["symbol"] == sym]
        if filter_type == "買入":
            df_show = df_show[df_show["type"] == "buy"]
        elif filter_type == "賣出":
            df_show = df_show[df_show["type"] == "sell"]

        cols_show = ["date","類型","name","股數","成交價","手續費","總金額","currency","notes"]
        col_rename = {"date": "日期", "name": "名稱", "currency": "幣別", "notes": "備註"}

        tw_show = df_show[df_show["market"] == "TW"]
        us_show = df_show[df_show["market"] == "US"]

        if not tw_show.empty:
            st.markdown(":material/flag: **台股**")
            st.dataframe(tw_show[cols_show].rename(columns=col_rename),
                         width="stretch", hide_index=True)

        if not tw_show.empty and not us_show.empty:
            st.markdown('<hr style="border:none;border-top:2px solid #cbd5e1;margin:6px 0 10px 0;">',
                        unsafe_allow_html=True)

        if not us_show.empty:
            st.markdown(":material/public: **美股**")
            st.dataframe(us_show[cols_show].rename(columns=col_rename),
                         width="stretch", hide_index=True)

        # 刪除紀錄
        with st.expander("刪除紀錄（謹慎操作）"):
            tx_ids = df_show["id"].tolist()
            if tx_ids:
                del_id = st.selectbox(
                    "選擇要刪除的紀錄 ID",
                    tx_ids,
                    format_func=lambda i: " | ".join(
                        str(x) for x in df_show[df_show["id"]==i][["date","name","type","shares"]].values[0]
                    )
                )
                if st.button("刪除此筆", type="secondary", icon=":material/delete:"):
                    db.delete_stock_transaction(del_id)
                    st.session_state["_toast"] = "已刪除，持倉已重新計算"
                    st.rerun()
    else:
        st.info("尚無買賣紀錄")


# ════════════════════════════════════════════════════════════════════════════════
# 資金異動
# ════════════════════════════════════════════════════════════════════════════════
elif page == "transactions":
    st.title(":material/receipt_long: 資金異動紀錄")

    txs = db.get_account_transactions()
    if txs:
        df = pd.DataFrame(txs)
        type_map = {
            "transfer":   "↔ 轉帳",
            "deposit":    "↑ 存入",
            "withdrawal": "↓ 提出",
            "adjustment": "✎ 調整",
        }
        df["類型"]    = df["type"].map(lambda x: type_map.get(x, x))
        df["金額"]    = df["amount"].map(lambda x: f"{x:,.2f}")
        df["匯率"]    = df["exchange_rate"].map(lambda x: f"{x:.4f}" if x != 1 else "—")
        df["from_name"] = df["from_name"].fillna("—")
        df["to_name"]   = df["to_name"].fillna("—")
        df["notes"]     = df["notes"].fillna("")

        st.dataframe(
            df[["date","類型","from_name","to_name","金額","currency","匯率","notes"]].rename(columns={
                "date": "日期", "from_name": "從", "to_name": "到",
                "currency": "幣別", "notes": "備註"
            }),
            width="stretch", hide_index=True
        )

        with st.expander("刪除紀錄（謹慎操作）"):
            del_id = st.selectbox(
                "選擇要刪除的紀錄",
                df["id"].tolist(),
                format_func=lambda i: " | ".join(str(x) for x in
                    df[df["id"]==i][["date","類型","from_name","to_name","金額","currency"]].values[0]
                )
            )
            sel = df[df["id"] == del_id].iloc[0]
            if sel["type"] == "adjustment":
                st.warning("調整類型的紀錄刪除後**不會**自動回復帳戶餘額，請手動調整。")
            if st.button("刪除此筆", type="secondary", icon=":material/delete:", key="del_acc_tx"):
                db.delete_account_transaction(del_id)
                st.session_state["_toast"] = "已刪除" + ("，餘額已反轉" if sel["type"] != "adjustment" else "（請手動確認帳戶餘額）")
                st.rerun()
    else:
        st.info("尚無資金異動紀錄")


# ════════════════════════════════════════════════════════════════════════════════
# 設定
# ════════════════════════════════════════════════════════════════════════════════
elif page == "settings":
    st.title(":material/settings: 設定")

    # ── 匯率設定 ────────────────────────────────────────────
    with st.container(border=True):
        st.subheader("USD/TWD 匯率")
        current_rate = usd_rate()
        st.caption(f"目前匯率：{current_rate}")

        col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
        new_rate = col1.number_input("更新匯率", value=current_rate, step=0.01, format="%.4f")
        if col2.button("手動更新匯率", icon=":material/check:", use_container_width=True):
            db.set_setting("usd_twd_rate", new_rate)
            db.set_setting("rate_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
            st.session_state["_toast"] = f"匯率已更新為 {new_rate:.4f}"
            st.rerun()

        if st.button("自動抓取即時匯率", icon=":material/language:"):
            try:
                import yfinance as yf
                ticker = yf.Ticker("USDTWD=X")
                fetched = ticker.fast_info.last_price
                if fetched:
                    db.set_setting("usd_twd_rate", round(fetched, 4))
                    db.set_setting("rate_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
                    st.session_state["_toast"] = f"匯率已更新為 {fetched:.4f}"
                    st.rerun()
            except Exception as e:
                st.error(f"抓取失敗：{e}")

    st.markdown("---")

    # ── 手續費設定 ────────────────────────────────────────────
    with st.container(border=True):
        st.subheader("手續費設定")
        st.caption("調整後會立即影響損益計算與買賣記錄的手續費估算")
        fc = fee_cfg()

        with st.form("fee_settings"):
            st.markdown("**台股**")
            fc1, fc2, fc3, fc4 = st.columns(4)
            tw_comm     = fc1.number_input("手續費率 %",       value=fc["tw_comm"]     * 100, step=0.0001, format="%.4f", key="fc_tw_comm")
            tw_lot_min  = fc2.number_input("整張最低 NT$",     value=fc["tw_lot_min"],         step=1.0,    format="%.0f", key="fc_tw_lot_min")
            tw_odd_comm = fc3.number_input("零股手續費率 %",   value=fc["tw_odd_comm"] * 100, step=0.0001, format="%.4f", key="fc_tw_odd")
            tw_odd_min  = fc4.number_input("零股最低 NT$",     value=fc["tw_odd_min"],         step=1.0,    format="%.0f", key="fc_tw_odd_min")

            fc5, fc6, _, _ = st.columns(4)
            tw_stock_tax = fc5.number_input("股票證交稅 %",    value=fc["tw_stock_tax"] * 100, step=0.01,   format="%.3f", key="fc_tw_stax")
            tw_etf_tax   = fc6.number_input("ETF 證交稅 %",   value=fc["tw_etf_tax"]   * 100, step=0.01,   format="%.3f", key="fc_tw_etax")

            st.markdown("**美股**")
            fu1, fu2, _, _ = st.columns(4)
            us_comm = fu1.number_input("手續費率 %",           value=fc["us_comm"] * 100, step=0.001, format="%.4f", key="fc_us_comm")
            us_min  = fu2.number_input("最低手續費 USD",       value=fc["us_min"],        step=0.5,   format="%.2f", key="fc_us_min")

            if st.form_submit_button("儲存手續費設定", icon=":material/check:"):
                db.set_setting("tw_commission_rate",     tw_comm     / 100)
                db.set_setting("tw_lot_min_fee",         int(tw_lot_min))
                db.set_setting("tw_odd_commission_rate", tw_odd_comm / 100)
                db.set_setting("tw_odd_min_fee",         int(tw_odd_min))
                db.set_setting("tw_stock_tax_rate",      tw_stock_tax / 100)
                db.set_setting("tw_etf_tax_rate",        tw_etf_tax   / 100)
                db.set_setting("us_commission_rate",     us_comm     / 100)
                db.set_setting("us_min_fee",             us_min)
                st.session_state["_toast"] = "手續費設定已儲存"
                st.rerun()

    st.markdown("---")

    # ── 匯出備份 ────────────────────────────────────────────
    with st.container(border=True):
        st.subheader("匯出備份（CSV）")
        import io, csv as _csv

        def to_csv(rows):
            if not rows:
                return ""
            buf = io.StringIO()
            w = _csv.DictWriter(buf, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
            return buf.getvalue().encode("utf-8-sig")  # utf-8-sig 讓 Excel 正確顯示中文

        exports = {
            "帳戶":     lambda: db.get_accounts(),
            "持倉":     lambda: db.get_holdings(),
            "股票主檔": lambda: db.get_stocks(),
            "股票交易": lambda: db.get_stock_transactions(),
        }

        cols = st.columns(len(exports))
        for col, (label, fn) in zip(cols, exports.items()):
            data = fn()
            col.download_button(
                label=f"⬇ {label}",
                data=to_csv(data),
                file_name=f"finance_{label}.csv",
                mime="text/csv",
                use_container_width=True,
            )
