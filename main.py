import os
import re
import sys
import time
import json
import poplib
import smtplib
from email import message_from_bytes, encoders
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

sys.stdout.reconfigure(errors="replace")

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def resolve_password(cfg):
    env_name = cfg.get("password_env")
    if env_name:
        value = os.environ.get(env_name)
        if value:
            return value
    return cfg.get("password", "")

def decode_mime_header(value):
    """解碼信件標頭（主旨/寄件人/檔名）。除了處理標準 RFC2047 編碼，
    也處理舊式郵件系統直接塞入未編碼 Big5 位元組的情況，避免例外中斷轉寄。"""
    if not value:
        return ""
    try:
        chunks = decode_header(value)
    except (UnicodeDecodeError, LookupError):
        return str(value)

    parts = []
    for chunk, charset in chunks:
        if not isinstance(chunk, bytes):
            parts.append(chunk)
            continue
        candidates = [c for c in [charset if charset != "unknown-8bit" else None, "big5", "utf-8", "gb18030"] if c]
        for enc in candidates:
            try:
                parts.append(chunk.decode(enc))
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            parts.append(chunk.decode("utf-8", errors="replace"))
    return "".join(parts)

def get_attachment_filename(part):
    """取得附件檔名。part.get_filename() 在標頭是舊式未編碼 8-bit 字元（如 Big5）時，
    Python 內部會將其轉成無法復原的 U+FFFD 替代字元，因此改直接解析原始標頭字串。"""
    filename = part.get_filename()
    if filename and "�" not in filename:
        return decode_mime_header(filename)
    for header_name in ("Content-Disposition", "Content-Type"):
        raw_header = part.get(header_name)
        if raw_header is None:
            continue
        decoded = decode_mime_header(raw_header)
        match = re.search(r'name\*?=\s*"?([^";]+)', decoded, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return filename

def decode_payload(payload_bytes, charset):
    if payload_bytes is None:
        return ""
    for enc in filter(None, [charset, "utf-8"]):
        try:
            return payload_bytes.decode(enc, errors="ignore")
        except LookupError:
            continue
    return payload_bytes.decode("utf-8", errors="ignore")

def forward_message(pop, msg_num, account, smtp_cfg, server):
    _, lines, _ = pop.retr(msg_num)
    raw_bytes = b"\r\n".join(lines)
    msg = message_from_bytes(raw_bytes)

    orig_subject = decode_mime_header(msg.get("Subject", "No Subject"))
    orig_from = decode_mime_header(msg.get("From", "Unknown"))

    # 組合新信件內容
    forward_msg = MIMEMultipart()
    forward_msg["From"] = smtp_cfg["user"]
    forward_msg["To"] = smtp_cfg["to_email"]
    forward_msg["Subject"] = f"[{account['name']}] 轉寄: {orig_subject}"

    body_text = f"--- 這是一封自動轉寄信件 ---\n原始發件人: {orig_from}\n帳號: {account['user']}\n----------------------------\n\n"
    attachment_count = 0

    # 取得內文與附件
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue

            filename = get_attachment_filename(part)

            if part.get_content_type() == "text/plain" and not filename:
                body_text += decode_payload(part.get_payload(decode=True), part.get_content_charset())
            elif filename:
                attachment = MIMEBase(part.get_content_maintype(), part.get_content_subtype())
                attachment.set_payload(part.get_payload(decode=True))
                encoders.encode_base64(attachment)
                attachment.add_header("Content-Disposition", "attachment", filename=filename)
                forward_msg.attach(attachment)
                attachment_count += 1
    else:
        body_text += decode_payload(msg.get_payload(decode=True), msg.get_content_charset())

    forward_msg.attach(MIMEText(body_text, "plain", "utf-8"))

    server.send_message(forward_msg)
    log(f"Successfully forwarded email: {orig_subject} (attachments: {attachment_count})")

def fetch_and_forward(account, smtp_cfg):
    log(f"Checking account: {account['name']} ({account['user']})")
    try:
        if account.get("use_ssl", True):
            pop = poplib.POP3_SSL(account["pop3_host"], account["pop3_port"])
        else:
            pop = poplib.POP3(account["pop3_host"], account["pop3_port"])

        pop.user(account["user"])
        pop.pass_(resolve_password(account))

        num_messages = len(pop.list()[1])
        log(f"Total messages in mailbox: {num_messages}")

        if num_messages == 0:
            pop.quit()
            return

        # 逐封處理信箱中的所有信件，轉寄成功後即從伺服器刪除，避免重複轉寄
        with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"]) as server:
            server.starttls()
            server.login(smtp_cfg["user"], resolve_password(smtp_cfg))

            for i in range(1, num_messages + 1):
                try:
                    forward_message(pop, i, account, smtp_cfg, server)
                    pop.dele(i)
                except Exception as e:
                    log(f"Error forwarding message {i} for {account['name']}: {e}")

        pop.quit()

    except Exception as e:
        log(f"Error checking {account['name']}: {e}")

def main():
    while True:
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)

            for acc in config["accounts"]:
                fetch_and_forward(acc, config["smtp"])

            interval = config.get("check_interval_seconds", 300)
            time.sleep(interval)
        except Exception as e:
            log(f"Main loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()