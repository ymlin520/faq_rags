# 校務 FAQ 智慧問答與工單系統

這是一套可在 Windows 電腦自行部署的校務 FAQ、地端 AI 與跨處室工單系統。系統先從本機 FAQ 知識庫搜尋相關內容，再由本機 Ollama 模型整理成繁體中文回答；若資料不足，學生可匿名建立工單，由 AI 自動判斷承辦處室。

處室回覆結案後，系統會寄送包含問題、回答及星級評分連結的通知信，並把有效 Q&A 自動寫回 FAQ CSV 與向量知識庫。

> 本專案是 Windows 單機／原型驗證版。正式上線前，建議串接學校會員系統、正式網域、權限控管、備份及資安機制。

## 目錄

- [功能總覽](#功能總覽)
- [系統架構](#系統架構)
- [使用技術](#使用技術)
- [系統需求](#系統需求)
- [快速開始](#快速開始)（安裝、啟動、密碼位置、停止）
- [FAQ CSV](#faq-csv)
- [工單流程](#工單流程)
- [Email 設定](#email-設定)
- [Cloudflare 臨時公開](#cloudflare-臨時公開)
- [資料位置與備份](#資料位置與備份)
- [專案結構](#專案結構)
- [API 摘要](#api-摘要)
- [健康檢查](#健康檢查)
- [常見問題](#常見問題)
- [安全注意事項](#安全注意事項)

### 三行版快速開始

```powershell
git clone https://github.com/yufan-code/rags.git
cd rags
Set-ExecutionPolicy -Scope Process Bypass; .\setup.ps1; .\start.ps1
```

需先安裝 Python 3.11+ 與 [Ollama for Windows](https://ollama.com/download/windows)。首次安裝需下載模型，約數分鐘。完成後瀏覽器會自動開啟 <http://127.0.0.1:8001>，管理員密碼寫在 `admin-token.txt`。

## 功能總覽

### 學生端

- 側欄分類直接讀取 `data/faq.csv` 的實際分類（`GET /api/categories`），點選分類後在對話區列出該類常見問題，不需自行輸入。
- 也可以直接用自然語句搜尋 FAQ。
- 本機 AI 只根據搜尋到的 FAQ 整理回答。
- 可查看來源 FAQ、相似度及官方連結。
- 知識庫沒有答案時，一鍵匿名建立工單，不需姓名或 Email。
- 可查看工單狀態、承辦處室及處理紀錄。
- 結案後可給 1～5 星評分及補充意見。
- 1～2 星會自動重新開啟工單，交回原處室確認。

### 處室端

- 每個處室使用不同的專屬密碼登入，只能查看自己的工單。
- 可依待處理、處理中及已解決篩選。
- 可輸入回答、結案或轉派其他處室。
- 只有實際轉派才計入轉單數；學生開單與 AI 初始分派不計入。
- 可自行修改本處室通知 Email，不能修改其他處室。
- 工單轉派後，新處室會收到包含工單連結及該處室密碼的通知信。

### 總管理員端

- 查看所有處室、所有狀態的工單。
- 查看提問數、實際轉單數、轉單率、結案數及平均處理時間。
- 查看各處室工單量、處理時間、評分及全校星級分布。
- 查看待處理、逾時及低分重新開啟的工單。
- 可修改工單狀態、回答、承辦人及承辦處室。
- 可設定各處室通知信箱，以及一個或多個學生回覆完成通知信箱。
- 可新增、移除學生通知收件人、測試寄信及匯出 CSV。

### Email 與知識庫成長

- 新工單自動寄至 AI 判斷的承辦處室。
- 處室信件包含問題、工單連結、後台連結及該處室專屬密碼。
- 結案後寄出 Q、A 及 1～5 星評分連結。
- 單機版預設將學生評分信寄到 `default-email.txt`，管理員可在後台新增或移除多個通知信箱。
- 已解決且有回答的工單會自動新增或更新 `data/faq.csv` 與向量庫。
- 同一工單使用固定 FAQ ID，重複同步不會建立重複資料。

## 系統架構

```text
學生／處室／管理員瀏覽器
            │
            ▼
FastAPI（127.0.0.1:8001）
    ├─ Sentence Transformers 多語言 Embedding
    ├─ Qdrant Local 本機向量庫
    ├─ Ollama qwen2.5:3b（回答與工單分派）
    ├─ SQLite（工單、事件、評分與統計）
    └─ Gmail OAuth／SMTP（通知信）
```

FAQ、工單及向量資料預設只存於執行系統的 Windows 電腦。不需要 Docker，也不需公開 Ollama 或資料庫連接埠。

## 使用技術

- Python 3.11+
- FastAPI / Uvicorn
- Sentence Transformers
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Qdrant Client Local Mode
- Ollama `qwen2.5:3b`
- SQLite
- Gmail API OAuth 2.0 或 SMTP
- HTML、CSS、Vanilla JavaScript
- 選用 Cloudflare Tunnel

## 系統需求

- Windows 10 或 Windows 11
- Python 3.11 以上，安裝時勾選 `Add Python to PATH`
- [Ollama for Windows](https://ollama.com/download/windows)
- 建議至少 8 GB RAM
- 第一次安裝需要網路下載 Python 套件、Embedding 模型及 Ollama 模型
- 約需數 GB 磁碟空間，實際大小取決於模型與 FAQ 數量

## 快速開始

### 1. 下載專案

```powershell
git clone https://github.com/yufan-code/rags.git
cd rags
```

也可以在 GitHub 選擇 `Code` → `Download ZIP`，解壓縮後在專案資料夾開啟 PowerShell。

### 2. 第一次安裝

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

安裝程式會自動：

1. 建立 `.venv` Python 虛擬環境。
2. 安裝 `backend/requirements.txt` 套件。
3. 產生管理員密碼及 10 個處室專屬密碼。
4. 建立本機 Email 設定範本。
5. 啟動 Ollama 並下載 `qwen2.5:3b`。
6. 下載多語言 Embedding 模型。
7. 將 `data/faq.csv` 匯入本機向量庫。

第一次執行可能需要數分鐘，請等待模型下載及 FAQ Embedding 完成。

### 3. 啟動

```powershell
.\start.ps1
```

| 入口 | 網址 | 用途 |
|---|---|---|
| 學生版 | <http://127.0.0.1:8001/?student=1> | FAQ、建立工單、查看結果 |
| 處室版 | <http://127.0.0.1:8001/office> | 處室回覆、結案及轉單 |
| 管理員版 | <http://127.0.0.1:8001/admin> | 全校工單、統計及設定 |
| 健康檢查 | <http://127.0.0.1:8001/api/health> | FAQ、向量庫與 Ollama 狀態 |
| API 文件 | <http://127.0.0.1:8001/docs> | FastAPI Swagger 文件 |

### 4. 密碼位置

- 管理員密碼：`admin-token.txt`
- 處室密碼清單：`office-login-codes.txt`
- 程式使用的處室密碼：`office-tokens.json`

這些檔案由安裝程式產生並已加入 `.gitignore`，不可上傳或公開。

### 5. 停止

```powershell
.\stop.ps1
```

停止服務不會刪除 FAQ、工單、評分或設定。

## FAQ CSV

FAQ 來源是 `data/faq.csv`，請使用 UTF-8 或 UTF-8 with BOM。

```csv
id,category,question,answer,url,keywords
Q001,選課相關,如何加退選課程？,請登入選課系統辦理加退選,https://example.edu.tw/course,加退選 選課 教務處
```

| 欄位 | 必填 | 說明 |
|---|---:|---|
| `id` | 是 | 唯一且固定的資料 ID |
| `category` | 否 | 前台分類及搜尋資訊 |
| `question` | 是 | FAQ 問題 |
| `answer` | 是 | 正式回答 |
| `url` | 否 | 官方公告或原始資料連結 |
| `keywords` | 否 | 處室、同義詞及補充關鍵字 |

修改後執行：

```powershell
.\stop.ps1
.\update_faq.ps1
.\start.ps1
```

這會重建 FAQ 向量資料，不會刪除工單 SQLite 資料。

## 工單流程

```text
學生提問
  ├─ 找到 FAQ → 顯示 AI 整理回答與來源
  └─ 找不到 FAQ → 匿名建立工單
                      │
                      ▼
                  AI 判斷處室
                      │
                      ▼
       寄信給處室（問題＋連結＋處室密碼）
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
      處室回覆結案           不屬於本處室
          │                       └─ 轉單並通知新處室
          ▼
寄出 Q&A 與評分連結 → 1～5 星評分
          │
          ├─ 3～5 星：保留結案
          └─ 1～2 星：自動重新開啟
          │
          ▼
Q&A 自動寫回 FAQ CSV 與向量知識庫
```

## Email 設定

未設定 Email 時，FAQ、AI 與工單仍可使用，但通知信會顯示寄送失敗。

### Gmail OAuth 2.0（建議）

1. 在 Google Cloud Console 建立專案。
2. 啟用 Gmail API。
3. 設定 OAuth 同意畫面。
4. 建立「桌面應用程式」OAuth 用戶端。
5. 將下載的 JSON 命名為 `gmail-oauth-client.json`，放在專案根目錄。
6. 執行：

```powershell
.\.venv\Scripts\python.exe .\authorize_gmail.py
```

7. 在瀏覽器完成授權，系統會建立 `gmail-oauth-token.json`。
8. 重新啟動 FAQ 系統。

OAuth 憑證與權杖已加入 `.gitignore`，不得提交 GitHub。

### SMTP

也可在管理員後台設定 SMTP 伺服器、連接埠、寄件帳號與應用程式密碼。Gmail 若使用 SMTP，通常需要先啟用兩步驟驗證並建立應用程式密碼。

### 收件地址

- 管理員可設定所有處室 Email。
- 處室登入後只能修改自己的通知地址。
- 管理員可在「學生回覆完成通知信箱」新增多個收件地址；處室結案時會同時寄送 Q、A 與評分連結。
- 初始範例是 `office-emails.example.json`。
- 實際設定寫入 `office-emails.json`，不會提交 GitHub。
- `default-email.txt` 是第一次啟動時的學生通知預設地址；之後可直接在管理員後台維護通知清單。
- 未來串接會員系統後，可改用會員資料中的學生 Email。

## Cloudflare 臨時公開

確認本機 `127.0.0.1:8001` 正常後，安裝 `cloudflared` 並執行：

```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```

終端機會顯示隨機 `https://*.trycloudflare.com` 網址。Quick Tunnel 只適合臨時展示：網址每次可能改變、關閉程式後失效，而且沒有正常運作時間保證。電腦、FastAPI、Ollama 及 Tunnel 都必須保持執行。

正式環境應使用自有網域、Cloudflare Named Tunnel、會員登入、速率限制及正式備份。不要公開 Ollama 或本機資料庫連接埠。

## 資料位置與備份

| 路徑 | 內容 | 提交 GitHub |
|---|---|---:|
| `data/faq.csv` | FAQ 原始資料 | 是 |
| `data/qdrant-local/` | FAQ 向量索引 | 否，可重建 |
| `data/analytics.db` | 工單、事件、評分及統計 | 否 |
| `admin-token.txt` | 管理員密碼 | 否 |
| `office-tokens.json` | 處室密碼 | 否 |
| `office-emails.json` | 實際通知信箱 | 否 |
| `gmail-oauth-client.json` | OAuth 用戶端憑證 | 否 |
| `gmail-oauth-token.json` | Gmail OAuth 權杖 | 否 |
| `default-email.txt` | 單機評分測試信箱 | 否 |
| `data/site-config.json` | 前台外觀與文案設定 | 否 |
| `theme-admin-token.txt` | 外觀設定頁密碼 | 否 |

建議停止服務後備份 `data/faq.csv`、`data/analytics.db`、Email 設定與必要憑證。`data/qdrant-local` 可不備份，因為能從 FAQ CSV 重新建立。

## 專案結構

```text
rags/
├─ backend/
│  ├─ main.py                 FastAPI 路由與權限
│  ├─ analytics.py            SQLite 工單、評分與統計
│  ├─ embedding.py            多語言 Embedding
│  ├─ qdrant_service.py       本機向量庫
│  ├─ llm_service.py          Ollama 回答與處室分派
│  ├─ mail_service.py         Gmail／SMTP 通知
│  ├─ knowledge_service.py    已解決工單回寫 FAQ 與分類清單
│  └─ theme_service.py        前台外觀與文案設定（開發中）
├─ frontend/                  學生、處室及管理員頁面
├─ scripts/                   匯入、搜尋及健康檢查
├─ data/faq.csv               FAQ 來源
├─ setup.ps1                  首次安裝
├─ start.ps1                  啟動
├─ stop.ps1                   停止
└─ update_faq.ps1             重建向量庫
```

## API 摘要

完整文件：<http://127.0.0.1:8001/docs>

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/health` | FAQ 數量、向量庫及 Ollama 狀態 |
| `GET` | `/api/categories` | 側欄分類與各類代表問題（參數 `limit`，1～20） |
| `POST` | `/api/search` | FAQ 語意搜尋 |
| `POST` | `/api/ask` | 搜尋後由 Ollama 整理回答 |
| `POST` | `/api/tickets` | 建立並分派工單 |
| `GET` | `/api/tickets/{ticket_no}` | 使用存取碼查看學生工單 |
| `POST` | `/api/tickets/{ticket_no}/rating` | 提交星級評分 |
| `GET` | `/api/office/tickets` | 處室工單清單 |
| `PATCH` | `/api/office/tickets/{ticket_no}` | 處室回覆、結案或轉派 |
| `GET` | `/api/admin/stats` | 管理統計 |
| `GET` | `/api/admin/tickets.csv` | 匯出工單 CSV |

## 健康檢查

先啟動系統，再執行：

```powershell
.\.venv\Scripts\python.exe .\scripts\health_check.py
.\.venv\Scripts\python.exe .\scripts\test_search.py
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

正常結果應包含 `status: ok`、FAQ `points` 大於 0，以及 `llm.connected`、`llm.available` 為 `true`。

## 常見問題

### PowerShell 禁止執行指令碼

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### 找不到 Python

重新安裝 Python 3.11 以上並勾選 `Add Python to PATH`，再重新開啟 PowerShell。

### Ollama 無法連線

```powershell
ollama serve
ollama pull qwen2.5:3b
```

### FAQ 數量為 0 或搜尋不到

```powershell
.\stop.ps1
.\update_faq.ps1
.\start.ps1
```

### 8001 連接埠被占用

```powershell
Get-NetTCPConnection -LocalPort 8001
```

關閉占用連接埠的舊程序後再執行 `start.ps1`。

### Gmail 沒收到信

- 確認 OAuth 或 SMTP 設定成功。
- 查看垃圾郵件與促銷分類。
- 確認處室 Email 不是範例地址。
- 確認 `default-email.txt` 已改成測試信箱。
- 在管理後台查看寄送狀態與錯誤。

### 結案後沒有進入知識庫

- 工單必須為「已解決」。
- 回覆不可空白。
- 工單事件應顯示「已將本工單 Q&A 寫入知識庫」。
- 確認 `data/faq.csv` 可寫入且磁碟空間足夠。

## 安全注意事項

- **服務預設只綁 `127.0.0.1`**，僅本機可連。若要讓同區網其他電腦連入，需自行把 `start.ps1` 的 `--host` 改為 `0.0.0.0`；但本系統沒有正式登入機制，開放前請先評估風險。
- 不要提交 `.gitignore` 已排除的密碼、OAuth、資料庫及 Email 設定。
- 不要把管理員或處室密碼提供給學生。
- 工單連結包含存取碼，不應公開分享。
- 正式環境應串接學校 SSO／會員系統及正式 RBAC 權限。
- 正式公開前應加入 HTTPS、速率限制、稽核紀錄、備份及弱點掃描。
- FAQ 與工單可能含個資，應遵守校方規範及相關法令。

## 後續可擴充

- 串接學校 SSO、LDAP 或會員系統。
- 自動取得學生 Email，取代固定測試信箱。
- 正式 RBAC 權限及處室帳號管理。
- PostgreSQL 或其他正式資料庫。
- 自有網域與 Cloudflare Named Tunnel。
- 附件、SLA、催辦與通知排程。
- FAQ 審核流程，避免未審核回答直接公開。

### 開發中

`backend/theme_service.py` 提供前台外觀（配色、字級、圓角）與所有介面文案的設定讀寫，後端 API 與 `/site-theme.css` 動態樣式已可運作，但對應的設定畫面尚未完成，因此這部分暫不列入正式功能。

## GitHub 上傳前檢查

```powershell
git status
git ls-files
```

確認沒有追蹤：`admin-token.txt`、`office-tokens.json`、`office-login-codes.txt`、`各處室與後台連結密碼.txt`、Gmail OAuth JSON、`data/analytics.db`、`data/qdrant-local/` 或 `public-url.txt`。以上皆已列入 `.gitignore`。

## 授權與資料權利

本專案尚未預設 LICENSE。若要讓其他人自由使用、修改或散布，請加入 MIT、Apache-2.0 或其他適合的授權。

`data/faq.csv` 可能包含學校規章、聯絡方式或其他校務資料。公開前請確認發布權限、內容正確性、個資規範及更新責任。
