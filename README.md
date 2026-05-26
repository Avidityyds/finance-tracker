# 💰 個人資產追蹤工具

完全本機運行的資產管理工具，資料存在同目錄的 `finance.db`，不會上傳任何資訊。

---

## 🚀 安裝與啟動

### 首次安裝（只需執行一次）

#### 1. 建立虛擬環境
```bash
cd finance_tracker
python -m venv venv
source venv/bin/activate        # Mac/Linux
# 或 venv\Scripts\activate      # Windows
```

#### 2. 安裝套件
```bash
pip install -r requirements.txt
```

---

### 之後每次啟動

```bash
cd finance_tracker
source venv/bin/activate        # Mac/Linux
# 或 venv\Scripts\activate      # Windows
streamlit run app.py
```

瀏覽器會自動開啟 `http://localhost:8501`

---

## 📁 檔案結構
```
finance_tracker/
├── app.py          # 主程式（Streamlit UI）
├── database.py     # 資料庫操作（SQLite）
├── finance.db      # 資料庫（首次啟動自動建立）
├── requirements.txt
└── README.md
```

---

## 🗂️ 功能說明

| 頁面 | 功能 |
|------|------|
| 📊 總覽 | 資產加總、配置圓餅圖、帳戶餘額、各股損益橫條圖 |
| 🏦 帳戶管理 | 新增帳戶、調整餘額、記錄轉帳 / 存提，支援多幣別與換匯成本 |
| 📈 持股管理 | 查看持倉損益、手動或自動更新股價、新增股票 |
| 🔄 股票買賣 | 記錄買賣，自動扣款 / 回補帳戶餘額，重算均價與損益 |
| 💸 資金異動 | 查看所有帳戶資金異動歷史 |
| ⚙️ 設定 | 更新 USD/TWD 匯率（手動或自動抓取）、調整手續費設定、匯出 CSV 備份 |

---

## 💾 備份

- **完整備份**：直接複製 `finance.db` 即可
- **CSV 匯出**：至「設定」頁面，可個別匯出帳戶、持倉、股票主檔、股票交易記錄（UTF-8 with BOM，支援 Excel 直接開啟）

---

## ⚙️ 手續費設定

在設定頁面可自訂：

| 項目 | 預設值 |
|------|--------|
| 台股整張手續費率 | 0.1425%，最低 NT$20 |
| 台股零股手續費率 | 0.0855%，最低 NT$1 |
| 台股股票證交稅 | 0.3% |
| 台股 ETF 證交稅 | 0.1% |
| 美股手續費率 | 0.1%，最低 $1 USD |

---

## 💡 技術說明

- **前端**：Streamlit
- **資料庫**：SQLite（`finance.db`）
- **股價抓取**：yfinance（Yahoo Finance）
- **外幣換匯成本**：每個帳戶可鎖定換匯當時的台幣成本（`twd_cost`），不隨即時匯率浮動；買賣股票時自動按比例調整
