# POP3 Forwarder

定期輪詢多個 POP3 信箱帳號，將新信件（含附件）轉寄到指定的目標信箱，轉寄成功後從原信箱刪除該封信。

## 檔案說明

- `main.py`：主程式邏輯。
- `config.json`：設定檔（POP3 帳號清單、SMTP 轉寄設定、輪詢間隔）。密碼**不**存在此檔案中。
- `docker-compose.yml`：使用 Docker Compose 啟動服務。
- `.env.example`：密碼環境變數範本。
- `.env`：實際密碼檔（已建立、已加入 `.gitignore`，不會進版控）。
- `Dockerfile`：建置 image 用。

## 設定步驟

### 1. 準備密碼環境變數

複製範本並填入真實密碼：

```
cp .env.example .env
```

編輯 `.env`：

```
SMTP_PASSWORD=你的Gmail應用程式密碼
ACCOUNT1_PASSWORD=帳號1的POP3密碼
ACCOUNT2_PASSWORD=帳號2的POP3密碼
```

> `.env` 已加入 `.gitignore`，不會被提交進版控。

### 2. 編輯 `config.json`

```json
{
  "check_interval_seconds": 300,
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "user": "your_gmail@gmail.com",
    "password_env": "SMTP_PASSWORD",
    "to_email": "target_receiver@gmail.com"
  },
  "accounts": [
    {
      "name": "帳號顯示名稱",
      "pop3_host": "pop3.example.com",
      "pop3_port": 995,
      "use_ssl": true,
      "user": "account1@example.com",
      "password_env": "ACCOUNT1_PASSWORD"
    }
  ]
}
```

欄位說明：

| 欄位 | 說明 |
| --- | --- |
| `check_interval_seconds` | 每次輪詢間隔秒數 |
| `smtp.host` / `smtp.port` | 轉寄用 SMTP 伺服器（預設 Gmail，587 + STARTTLS） |
| `smtp.user` | SMTP 登入帳號，同時作為轉寄信件的 `From` |
| `smtp.password_env` | 存放 SMTP 密碼的環境變數名稱，對應 `.env` 中的變數 |
| `smtp.to_email` | 轉寄目標信箱 |
| `accounts[].name` | 帳號顯示名稱（會出現在轉寄信主旨前綴） |
| `accounts[].pop3_host` / `pop3_port` | POP3 伺服器位址與埠號 |
| `accounts[].use_ssl` | 是否使用 POP3 over SSL（995 埠通常為 true） |
| `accounts[].user` | POP3 登入帳號（即信箱地址） |
| `accounts[].password_env` | 存放該帳號密碼的環境變數名稱 |

如果 Gmail 需要應用程式密碼，請至 Google 帳戶設定產生「應用程式專用密碼」，不要用一般登入密碼。

### 3. 新增/刪除信箱帳號

在 `config.json` 的 `accounts` 陣列中新增或移除物件即可，並記得在 `.env` 中補上對應的 `password_env` 變數，以及在 `docker-compose.yml` 的 `environment` 區塊加入該變數名稱。

## 啟動服務

### 方式一：Docker Compose（建議）

```
docker compose up -d --build
```

查看即時 log：

```
docker compose logs -f
```

修改 `config.json` 後（因為是 bind mount）不需要重新 build，直接重啟容器即可套用：

```
docker compose restart
```

停止服務：

```
docker compose down
```

### 方式二：直接用 Python 執行（本機測試用）

```
pip install --upgrade pip
set SMTP_PASSWORD=你的密碼
set ACCOUNT1_PASSWORD=帳號1密碼
set ACCOUNT2_PASSWORD=帳號2密碼
python main.py
```

（PowerShell 請改用 `$env:SMTP_PASSWORD = "..."` 設定環境變數）

## 行為說明

- 每輪會抓取信箱中**所有**未刪除信件並逐封轉寄，成功轉寄一封就立即從原信箱刪除該封，避免重複轉寄。
- 若某封信轉寄失敗（例如格式異常），該封信會保留在信箱中，下一輪會重試，不影響其他信件的轉寄。
- 轉寄信件會保留原始附件；主旨、寄件人、附件檔名即使是舊式郵件系統未做 RFC2047 編碼的 Big5 中文，也會嘗試正確解碼，避免亂碼或轉寄失敗。
