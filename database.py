"""
database.py - SQLite 資料庫層
所有資料存在同目錄的 finance.db
"""
import sqlite3
import os
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finance.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── 初始化 ────────────────────────────────────────────────────────────────────

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # 帳戶（現金帳戶：銀行、證券交割帳等）
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        name     TEXT    NOT NULL,
        type     TEXT    NOT NULL DEFAULT 'bank',   -- bank / securities
        currency TEXT    NOT NULL DEFAULT 'TWD',
        balance  REAL    NOT NULL DEFAULT 0,
        notes    TEXT,
        active   INTEGER NOT NULL DEFAULT 1,
        created_at TEXT  DEFAULT CURRENT_TIMESTAMP
    )""")

    # 股票主檔
    c.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol     TEXT    NOT NULL,
        name       TEXT    NOT NULL,
        market     TEXT    NOT NULL,    -- TW / US
        currency   TEXT    NOT NULL,    -- TWD / USD
        account_id INTEGER,
        FOREIGN KEY (account_id) REFERENCES accounts(id)
    )""")

    # 持倉（由買賣紀錄彙總，另存快照方便查詢）
    c.execute("""
    CREATE TABLE IF NOT EXISTS holdings (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_id     INTEGER UNIQUE NOT NULL,
        shares       REAL    NOT NULL DEFAULT 0,
        avg_cost     REAL    NOT NULL DEFAULT 0,   -- 每股成本（含手續費攤算）
        last_price   REAL,
        last_updated TEXT,
        FOREIGN KEY (stock_id) REFERENCES stocks(id)
    )""")

    # 股票買賣紀錄
    c.execute("""
    CREATE TABLE IF NOT EXISTS stock_transactions (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_id INTEGER NOT NULL,
        type     TEXT    NOT NULL,   -- buy / sell
        shares   REAL    NOT NULL,
        price    REAL    NOT NULL,   -- 每股成交價
        fee      REAL    NOT NULL DEFAULT 0,
        date     TEXT    NOT NULL,
        notes    TEXT,
        created_at TEXT  DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (stock_id) REFERENCES stocks(id)
    )""")

    # 帳戶資金異動（轉帳 / 存提 / 調整）
    c.execute("""
    CREATE TABLE IF NOT EXISTS account_transactions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        type            TEXT    NOT NULL,   -- transfer / deposit / withdrawal / adjustment
        from_account_id INTEGER,
        to_account_id   INTEGER,
        amount          REAL    NOT NULL,
        currency        TEXT    NOT NULL DEFAULT 'TWD',
        exchange_rate   REAL    NOT NULL DEFAULT 1,   -- from → TWD 匯率（只在外幣時用）
        date            TEXT    NOT NULL,
        notes           TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (from_account_id) REFERENCES accounts(id),
        FOREIGN KEY (to_account_id)   REFERENCES accounts(id)
    )""")

    # 系統設定（匯率、偏好等）
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key        TEXT PRIMARY KEY,
        value      TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # 遷移：新增欄位（已存在則忽略）
    for migration in [
        "ALTER TABLE accounts ADD COLUMN twd_cost REAL",
        "ALTER TABLE stocks ADD COLUMN cash_account_id INTEGER",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except Exception:
            pass

    conn.commit()
    conn.close()


def seed_initial_data():
    """插入示範資料（只在首次執行時呼叫）"""
    conn = get_conn()
    c = conn.cursor()

    # 確認是否已有資料
    c.execute("SELECT COUNT(*) FROM accounts")
    if c.fetchone()[0] > 0:
        conn.close()
        return  # 已有資料，不重複插入

    today = date.today().isoformat()

    # ── 帳戶 ──────────────────────────────────────────────
    accounts = [
        ("示範銀行 台幣活存",   "bank",       "TWD", 100000),
        ("示範銀行 外幣活存",   "bank",       "USD", 1000),
        ("示範證券 台股帳",     "securities", "TWD", 0),
        ("示範證券 外幣帳",     "securities", "USD", 0),
    ]
    acc_ids = {}
    for name, atype, cur, bal in accounts:
        c.execute(
            "INSERT INTO accounts (name, type, currency, balance) VALUES (?,?,?,?)",
            (name, atype, cur, bal)
        )
        acc_ids[name] = c.lastrowid

    # ── 股票主檔 & 持倉 ───────────────────────────────────
    us_stocks = [
        ("AAPL", "Apple",     "US", "USD", acc_ids["示範證券 外幣帳"], 10, 180.00, 185.00),
        ("MSFT", "Microsoft", "US", "USD", acc_ids["示範證券 外幣帳"],  5, 380.00, 390.00),
    ]
    tw_stocks = [
        ("0050", "元大台灣50", "TW", "TWD", acc_ids["示範證券 台股帳"], 1000, 155.00, 160.00),
        ("2330", "台積電",     "TW", "TWD", acc_ids["示範證券 台股帳"],   10, 850.00, 900.00),
    ]

    for symbol, name, market, cur, acc_id, shares, avg_cost, last_price in (us_stocks + tw_stocks):
        c.execute(
            "INSERT INTO stocks (symbol, name, market, currency, account_id) VALUES (?,?,?,?,?)",
            (symbol, name, market, cur, acc_id)
        )
        stock_id = c.lastrowid

        c.execute("""
            INSERT INTO holdings (stock_id, shares, avg_cost, last_price, last_updated)
            VALUES (?,?,?,?,?)""",
            (stock_id, shares, avg_cost, last_price, today)
        )

        c.execute("""
            INSERT INTO stock_transactions (stock_id, type, shares, price, fee, date, notes)
            VALUES (?,?,?,?,?,?,?)""",
            (stock_id, "buy", shares, avg_cost, 0, today, "示範資料")
        )

    # 預設匯率
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('usd_twd_rate', '32.5')")
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('initialized', '1')")

    conn.commit()
    conn.close()


# ─── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
        (key, str(value), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


# ─── Accounts ──────────────────────────────────────────────────────────────────

def get_accounts(active_only=True):
    conn = get_conn()
    q = "SELECT * FROM accounts"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY currency, name"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_account(name, atype, currency, balance, notes=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO accounts (name, type, currency, balance, notes) VALUES (?,?,?,?,?)",
        (name, atype, currency, balance, notes)
    )
    conn.commit()
    conn.close()


def update_account_balance(account_id, new_balance):
    conn = get_conn()
    conn.execute("UPDATE accounts SET balance=? WHERE id=?", (new_balance, account_id))
    conn.commit()
    conn.close()


def update_account_twd_cost(account_id, twd_cost):
    conn = get_conn()
    conn.execute("UPDATE accounts SET twd_cost=? WHERE id=?", (twd_cost, account_id))
    conn.commit()
    conn.close()


def delete_account(account_id):
    conn = get_conn()
    conn.execute("UPDATE accounts SET active=0 WHERE id=?", (account_id,))
    conn.commit()
    conn.close()


# ─── Stocks & Holdings ─────────────────────────────────────────────────────────

def get_holdings():
    """取得所有持倉，含股票資訊"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT h.*, s.symbol, s.name, s.market, s.currency, s.account_id,
               a.name as account_name
        FROM holdings h
        JOIN stocks s ON h.stock_id = s.id
        JOIN accounts a ON s.account_id = a.id
        WHERE h.shares > 0 AND a.active = 1
        ORDER BY s.market, s.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stocks():
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.*, a.name as account_name
        FROM stocks s JOIN accounts a ON s.account_id = a.id
        WHERE a.active = 1
        ORDER BY s.market, s.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_stock(symbol, name, market, currency, account_id, cash_account_id=None):
    conn = get_conn()
    cid = cash_account_id if cash_account_id is not None else account_id
    cur = conn.execute(
        "INSERT INTO stocks (symbol, name, market, currency, account_id, cash_account_id) VALUES (?,?,?,?,?,?)",
        (symbol.upper(), name, market, currency, account_id, cid)
    )
    stock_id = cur.lastrowid
    conn.execute(
        "INSERT INTO holdings (stock_id, shares, avg_cost) VALUES (?,0,0)",
        (stock_id,)
    )
    conn.commit()
    conn.close()
    return stock_id


def update_last_price(stock_id, price):
    conn = get_conn()
    conn.execute(
        "UPDATE holdings SET last_price=?, last_updated=? WHERE stock_id=?",
        (price, date.today().isoformat(), stock_id)
    )
    conn.commit()
    conn.close()


def _recalc_holding(conn, stock_id):
    """根據買賣紀錄重新計算持倉均價與股數"""
    rows = conn.execute("""
        SELECT type, shares, price, fee FROM stock_transactions
        WHERE stock_id=? ORDER BY date, id
    """, (stock_id,)).fetchall()

    total_shares = 0.0
    total_cost = 0.0
    for r in rows:
        if r["type"] == "buy":
            total_cost += r["shares"] * r["price"] + r["fee"]
            total_shares += r["shares"]
        elif r["type"] == "sell":
            if total_shares > 0:
                # 賣出按比例減少成本
                ratio = r["shares"] / total_shares
                total_cost -= total_cost * ratio
            total_shares -= r["shares"]
            total_shares = max(total_shares, 0)

    avg_cost = (total_cost / total_shares) if total_shares > 0 else 0
    conn.execute(
        "UPDATE holdings SET shares=?, avg_cost=? WHERE stock_id=?",
        (round(total_shares, 4), round(avg_cost, 4), stock_id)
    )


# ─── Stock Transactions ────────────────────────────────────────────────────────

def _adjust_account_for_trade(conn, stock_id, tx_type, shares, price, fee, reverse=False):
    """Buy deducts from account; sell adds back. Also scales twd_cost proportionally on buy/unbuy."""
    stock = conn.execute("SELECT account_id, cash_account_id FROM stocks WHERE id=?", (stock_id,)).fetchone()
    if not stock:
        return
    acct_id = stock["cash_account_id"] or stock["account_id"]
    if not acct_id:
        return
    acct = conn.execute("SELECT balance, twd_cost FROM accounts WHERE id=?", (acct_id,)).fetchone()

    if tx_type == "buy" and not reverse:
        # Normal buy: deduct balance, scale twd_cost down proportionally
        amount = shares * price + fee
        new_balance = acct["balance"] - amount
        if acct["twd_cost"] is not None and acct["balance"] > 0:
            new_twd = round(acct["twd_cost"] * (new_balance / acct["balance"]), 2)
            conn.execute("UPDATE accounts SET balance=?, twd_cost=? WHERE id=?",
                         (new_balance, new_twd, acct_id))
        else:
            conn.execute("UPDATE accounts SET balance=? WHERE id=?", (new_balance, acct_id))
    elif tx_type == "buy" and reverse:
        # Undo a buy: add back to balance, scale twd_cost up proportionally
        amount = shares * price + fee
        new_balance = acct["balance"] + amount
        if acct["twd_cost"] is not None and acct["balance"] > 0:
            new_twd = round(acct["twd_cost"] * (new_balance / acct["balance"]), 2)
            conn.execute("UPDATE accounts SET balance=?, twd_cost=? WHERE id=?",
                         (new_balance, new_twd, acct_id))
        else:
            conn.execute("UPDATE accounts SET balance=? WHERE id=?", (new_balance, acct_id))
    elif tx_type == "sell" and not reverse:
        # Normal sell: add proceeds to balance, twd_cost unchanged
        conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?",
                     (shares * price - fee, acct_id))
    elif tx_type == "sell" and reverse:
        # Undo a sell: deduct from balance, twd_cost unchanged
        conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?",
                     (shares * price - fee, acct_id))


def record_stock_transaction(stock_id, tx_type, shares, price, fee, tx_date, notes=""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO stock_transactions (stock_id, type, shares, price, fee, date, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (stock_id, tx_type, shares, price, fee, tx_date, notes))
    _recalc_holding(conn, stock_id)
    _adjust_account_for_trade(conn, stock_id, tx_type, shares, price, fee)
    conn.commit()
    conn.close()


def delete_stock_transaction(tx_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT stock_id, type, shares, price, fee FROM stock_transactions WHERE id=?", (tx_id,)
    ).fetchone()
    if row:
        # Reverse the balance effect of the deleted transaction
        _adjust_account_for_trade(conn, row["stock_id"], row["type"], row["shares"], row["price"], row["fee"], reverse=True)
        conn.execute("DELETE FROM stock_transactions WHERE id=?", (tx_id,))
        _recalc_holding(conn, row["stock_id"])
        conn.commit()
    conn.close()


def get_stock_transactions(stock_id=None):
    conn = get_conn()
    q = """
        SELECT t.*, s.symbol, s.name, s.currency, s.market
        FROM stock_transactions t JOIN stocks s ON t.stock_id = s.id
    """
    if stock_id:
        q += " WHERE t.stock_id=?"
        rows = conn.execute(q + " ORDER BY t.date DESC, t.id DESC", (stock_id,)).fetchall()
    else:
        rows = conn.execute(q + " ORDER BY t.date DESC, t.id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Account Transactions ──────────────────────────────────────────────────────

def record_account_transaction(tx_type, amount, currency, tx_date,
                                from_id=None, to_id=None,
                                exchange_rate=1.0, notes=""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO account_transactions
            (type, from_account_id, to_account_id, amount, currency, exchange_rate, date, notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (tx_type, from_id, to_id, amount, currency, exchange_rate, tx_date, notes))

    from_acct = conn.execute("SELECT currency, balance, twd_cost FROM accounts WHERE id=?",
                             (from_id,)).fetchone() if from_id else None
    to_acct   = conn.execute("SELECT currency, balance, twd_cost FROM accounts WHERE id=?",
                             (to_id,)).fetchone()   if to_id   else None

    if tx_type in ("transfer", "withdrawal") and from_id:
        conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (amount, from_id))
        # 從外幣帳扣款時，按比例縮減 twd_cost
        if from_acct and from_acct["currency"] != "TWD" \
                and from_acct["twd_cost"] is not None and from_acct["balance"] > 0:
            new_bal = from_acct["balance"] - amount
            new_twd = round(from_acct["twd_cost"] * (new_bal / from_acct["balance"]), 2)
            conn.execute("UPDATE accounts SET twd_cost=? WHERE id=?", (new_twd, from_id))

    if tx_type in ("transfer", "deposit") and to_id:
        from_cur = from_acct["currency"] if from_acct else None
        to_cur   = to_acct["currency"]

        if from_cur is not None and from_cur != to_cur:
            if from_cur == "TWD" and to_cur == "USD":
                # 台幣換美金：存入 amount÷rate USD，twd_cost 記錄換匯成本
                deposited    = round(amount / exchange_rate, 6)
                existing_twd = to_acct["twd_cost"] if to_acct["twd_cost"] is not None else 0
                conn.execute("UPDATE accounts SET balance = balance + ?, twd_cost = ? WHERE id=?",
                             (deposited, existing_twd + amount, to_id))
            elif from_cur == "USD" and to_cur == "TWD":
                # 美金換台幣：存入 amount×rate TWD
                deposited = round(amount * exchange_rate, 2)
                conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (deposited, to_id))
            else:
                conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (amount, to_id))
        else:
            if from_cur is None:
                # 純存款：依 currency vs 帳戶幣別判斷
                if currency == to_cur:
                    # 同幣別存入（USD→USD 或 TWD→TWD）
                    conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (amount, to_id))
                    if to_cur == "USD" and to_acct and exchange_rate > 1:
                        # USD 存款：追蹤換匯成本
                        existing_twd = to_acct["twd_cost"] if to_acct["twd_cost"] is not None else 0
                        conn.execute("UPDATE accounts SET twd_cost = ? WHERE id=?",
                                     (existing_twd + round(amount * exchange_rate, 2), to_id))
                elif currency == "USD" and to_cur == "TWD":
                    conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?",
                                 (round(amount * exchange_rate, 2), to_id))
                elif currency == "TWD" and to_cur == "USD":
                    deposited = round(amount / exchange_rate, 6)
                    existing_twd = to_acct["twd_cost"] if to_acct["twd_cost"] is not None else 0
                    conn.execute("UPDATE accounts SET balance = balance + ?, twd_cost = ? WHERE id=?",
                                 (deposited, existing_twd + amount, to_id))
                else:
                    conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (amount, to_id))
            else:
                # 同幣別轉帳：直接加
                conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (amount, to_id))

    if tx_type == "adjustment" and to_id:
        conn.execute("UPDATE accounts SET balance = ? WHERE id=?", (amount, to_id))

    conn.commit()
    conn.close()


def delete_account_transaction(tx_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM account_transactions WHERE id=?", (tx_id,)).fetchone()
    if row:
        tx_type       = row["type"]
        amount        = row["amount"]
        currency      = row["currency"]
        exchange_rate = row["exchange_rate"]
        from_id       = row["from_account_id"]
        to_id         = row["to_account_id"]

        from_acct = conn.execute("SELECT currency, balance, twd_cost FROM accounts WHERE id=?",
                                 (from_id,)).fetchone() if from_id else None
        to_acct   = conn.execute("SELECT currency, balance, twd_cost FROM accounts WHERE id=?",
                                 (to_id,)).fetchone()   if to_id   else None

        if tx_type in ("transfer", "withdrawal") and from_id:
            conn.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (amount, from_id))
            if from_acct and from_acct["currency"] != "TWD" \
                    and from_acct["twd_cost"] is not None and from_acct["balance"] > 0:
                new_bal = from_acct["balance"] + amount
                new_twd = round(from_acct["twd_cost"] * (new_bal / from_acct["balance"]), 2)
                conn.execute("UPDATE accounts SET twd_cost=? WHERE id=?", (new_twd, from_id))

        if tx_type in ("transfer", "deposit") and to_id:
            from_cur = from_acct["currency"] if from_acct else None
            to_cur   = to_acct["currency"]

            if from_cur is not None and from_cur != to_cur:
                if from_cur == "TWD" and to_cur == "USD":
                    deposited    = round(amount / exchange_rate, 6)
                    existing_twd = to_acct["twd_cost"] if to_acct["twd_cost"] is not None else 0
                    conn.execute("UPDATE accounts SET balance = balance - ?, twd_cost = ? WHERE id=?",
                                 (deposited, max(0, existing_twd - amount), to_id))
                elif from_cur == "USD" and to_cur == "TWD":
                    deposited = round(amount * exchange_rate, 2)
                    conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (deposited, to_id))
                else:
                    conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (amount, to_id))
            else:
                if from_cur is None:
                    # 反轉純存款
                    if currency == to_cur:
                        conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (amount, to_id))
                        if to_cur == "USD" and to_acct and exchange_rate > 1:
                            existing_twd = to_acct["twd_cost"] if to_acct["twd_cost"] is not None else 0
                            conn.execute("UPDATE accounts SET twd_cost = ? WHERE id=?",
                                         (max(0, existing_twd - round(amount * exchange_rate, 2)), to_id))
                    elif currency == "USD" and to_cur == "TWD":
                        conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?",
                                     (round(amount * exchange_rate, 2), to_id))
                    elif currency == "TWD" and to_cur == "USD":
                        deposited = round(amount / exchange_rate, 6)
                        existing_twd = to_acct["twd_cost"] if to_acct["twd_cost"] is not None else 0
                        conn.execute("UPDATE accounts SET balance = balance - ?, twd_cost = ? WHERE id=?",
                                     (deposited, max(0, existing_twd - amount), to_id))
                    else:
                        conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (amount, to_id))
                else:
                    # 同幣別轉帳反轉
                    conn.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (amount, to_id))

        # adjustment 是直接 SET 餘額，無法安全反轉，僅刪除紀錄
        conn.execute("DELETE FROM account_transactions WHERE id=?", (tx_id,))
        conn.commit()
    conn.close()


def get_account_transactions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*,
               fa.name as from_name,
               ta.name as to_name
        FROM account_transactions t
        LEFT JOIN accounts fa ON t.from_account_id = fa.id
        LEFT JOIN accounts ta ON t.to_account_id   = ta.id
        ORDER BY t.date DESC, t.id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
