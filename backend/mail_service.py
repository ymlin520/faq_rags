import json
import os
import smtplib
import base64
from html import escape
from email.message import EmailMessage
from pathlib import Path

from .config import PROJECT_ROOT

DEFAULT_EMAIL = os.getenv("FAQ_DEFAULT_EMAIL", "admin@example.edu.tw")
OFFICES = ["教務處註冊組", "教務處課務組", "學務處生活輔導組", "學務處住宿服務組", "國際處",
           "總務處", "資訊處", "圖資處", "系辦公室", "其他行政單位"]
DEFAULT_SETTINGS = {"server": "smtp.gmail.com", "port": 587, "username": "", "from_name": "校務AI系統",
                    "subject_tag": "校務AI系統",
                    "method": "", "use_tls": True, "require_auth": True,
                    "student_recipients": [DEFAULT_EMAIL]}
SETTINGS_FILE = PROJECT_ROOT / "mail-settings.json"
OFFICE_FILE = PROJECT_ROOT / "office-emails.json"
PASSWORD_FILE = PROJECT_ROOT / "mail-app-password.txt"
GOOGLE_CLIENT_FILE = PROJECT_ROOT / "gmail-oauth-client.json"
GOOGLE_TOKEN_FILE = PROJECT_ROOT / "gmail-oauth-token.json"
OFFICE_TOKENS_FILE = PROJECT_ROOT / "office-tokens.json"


def _json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_settings() -> dict:
    settings = {**DEFAULT_SETTINGS, **_json(SETTINGS_FILE, {})}
    saved = settings.get("student_recipients")
    if not isinstance(saved, list):
        saved = [saved] if saved else []
    settings["student_recipients"] = list(dict.fromkeys(
        str(address).strip().lower() for address in saved if str(address).strip()
    )) or [DEFAULT_EMAIL]
    return settings


def save_settings(data: dict) -> dict:
    settings = load_settings()
    settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS and v not in (None, "")})
    settings["port"] = int(settings.get("port") or 587)
    recipients = settings.get("student_recipients")
    if isinstance(recipients, list):
        settings["student_recipients"] = list(dict.fromkeys(
            str(address).strip().lower() for address in recipients if str(address).strip()
        )) or [DEFAULT_EMAIL]
    _write_json(SETTINGS_FILE, settings)
    return settings


def load_office_emails() -> dict:
    saved = _json(OFFICE_FILE, {})
    return {office: str(saved.get(office) or DEFAULT_EMAIL).strip() for office in OFFICES}


def save_office_emails(data: dict) -> dict:
    emails = load_office_emails()
    for office, address in (data or {}).items():
        if office in emails:
            emails[office] = str(address or DEFAULT_EMAIL).strip() or DEFAULT_EMAIL
    _write_json(OFFICE_FILE, emails)
    return emails


def _password() -> str:
    from_env = os.getenv("FAQ_SMTP_PASSWORD", "")
    if from_env:
        return from_env
    return PASSWORD_FILE.read_text(encoding="utf-8-sig").strip() if PASSWORD_FILE.exists() else ""


def save_password(password: str) -> None:
    PASSWORD_FILE.write_text(password.strip(), encoding="utf-8")


def office_email(office: str) -> str:
    return load_office_emails().get(office) or DEFAULT_EMAIL


def office_login_code(office: str) -> str:
    tokens = _json(OFFICE_TOKENS_FILE, {})
    return str(tokens.get(office) or "").strip()


def base_url() -> str:
    public_file = PROJECT_ROOT / "public-url.txt"
    if public_file.exists():
        url = public_file.read_text(encoding="utf-8-sig").strip().rstrip("/")
        if url:
            return url
    return "http://127.0.0.1:8001"


def _resolved_method(settings: dict) -> str:
    method = str(settings.get("method") or "").strip().lower()
    if method in ("smtp", "gmail_oauth"):
        return method
    return "gmail_oauth" if (GOOGLE_CLIENT_FILE.exists() and GOOGLE_TOKEN_FILE.exists()) else "smtp"


def _configured(settings: dict) -> bool:
    if _resolved_method(settings) == "gmail_oauth":
        return GOOGLE_CLIENT_FILE.exists() and GOOGLE_TOKEN_FILE.exists()
    if not settings.get("username"):
        return False
    if settings.get("require_auth", True):
        return bool(_password())
    return True


def mail_status() -> dict:
    settings = load_settings()
    return {
        "configured": _configured(settings),
        "method": _resolved_method(settings),
        "server": settings.get("server", "smtp.gmail.com"),
        "port": int(settings.get("port", 587)),
        "sender": settings.get("username", ""),
        "from_name": settings.get("from_name", DEFAULT_SETTINGS["from_name"]),
        "subject_tag": _subject_tag(settings),
        "use_tls": bool(settings.get("use_tls", True)),
        "require_auth": bool(settings.get("require_auth", True)),
        "password_set": bool(_password()),
        "default_email": DEFAULT_EMAIL,
        "student_recipients": settings.get("student_recipients", [DEFAULT_EMAIL]),
        "base_url": base_url(),
        "offices": load_office_emails(),
    }


def _send(message: EmailMessage) -> None:
    settings = load_settings()
    if _resolved_method(settings) == "gmail_oauth":
        if not (GOOGLE_CLIENT_FILE.exists() and GOOGLE_TOKEN_FILE.exists()):
            raise RuntimeError("寄件方式設為 Gmail OAuth，但找不到授權檔，請重新授權或改用 SMTP")
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        credentials = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), scopes)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            GOOGLE_TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise RuntimeError("Gmail OAuth 授權已失效，請重新授權")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        build("gmail", "v1", credentials=credentials, cache_discovery=False).users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return
    server, port = settings.get("server", "smtp.gmail.com"), int(settings.get("port", 587))
    use_tls = bool(settings.get("use_tls", True))
    require_auth = bool(settings.get("require_auth", True))
    if port == 465:
        with smtplib.SMTP_SSL(server, port, timeout=30) as smtp:
            if require_auth:
                smtp.login(settings["username"], _password())
            smtp.send_message(message)
        return
    with smtplib.SMTP(server, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if require_auth:
            smtp.login(settings["username"], _password())
        smtp.send_message(message)


def _subject_tag(settings: dict) -> str:
    """後台可自訂的信件主旨標題；未填寫時沿用寄件人顯示名稱。"""
    return (str(settings.get("subject_tag") or "").strip()
            or str(settings.get("from_name") or "").strip()
            or DEFAULT_SETTINGS["subject_tag"])


def _from_header(settings: dict) -> str:
    return f"{settings.get('from_name') or DEFAULT_SETTINGS['from_name']} <{settings['username']}>"


def send_ticket_email(ticket: dict) -> tuple[bool, str]:
    settings = load_settings()
    if not _configured(settings):
        return False, "尚未設定寄件帳號或應用程式密碼"
    recipient = office_email(ticket["office"])
    office_link = f"{base_url()}/office/ticket/{ticket['ticket_no']}"
    office_home = f"{base_url()}/office"
    login_code = office_login_code(ticket["office"])
    message = EmailMessage()
    message["Subject"] = f"[{_subject_tag(settings)} {ticket['ticket_no']}] {ticket['subject']}"
    message["From"] = _from_header(settings)
    message["To"] = recipient
    message["Reply-To"] = settings["username"]
    message.set_content(
        f"您好：\n\nAI 已將下列需求單分派至「{ticket['office']}」，請協助回覆。\n\n"
        f"需求單編號：{ticket['ticket_no']}\n"
        f"建立時間：{ticket.get('created_at', '')}\n"
        f"分類：{ticket.get('category', '')}\n"
        f"申請人：{ticket.get('requester_name', '')}（{ticket.get('requester_contact', '')}）\n\n"
        f"── 問題 ──\n{ticket['query']}\n\n"
        f"── 問題說明 ──\n{ticket['description']}\n\n"
        f"── 需求單連結 ──\n{office_link}\n\n"
        f"── 處室後台 ──\n{office_home}\n"
        f"該處室專屬密碼：{login_code or '請洽系統管理者'}\n\n"
        f"登入後即可查看及回覆需求單；回覆內容會直接顯示給提問學生。\n"
    )
    safe_office = escape(str(ticket["office"]))
    safe_ticket_no = escape(str(ticket["ticket_no"]))
    safe_subject = escape(str(ticket["subject"]))
    safe_query = escape(str(ticket["query"]))
    safe_description = escape(str(ticket["description"])).replace(chr(10), "<br>")
    safe_login_code = escape(login_code or "請洽系統管理者")
    message.add_alternative(
        "<div style=\"font-family:'Noto Sans TC',Arial,sans-serif;font-size:15px;color:#1f2933;line-height:1.7\">"
        f"<p>您好：</p><p>AI 已將下列需求單分派至「<strong>{safe_office}</strong>」，請協助回覆。</p>"
        "<table style=\"border-collapse:collapse;margin:16px 0\">"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">需求單編號</td><td><strong>{safe_ticket_no}</strong></td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">建立時間</td><td>{ticket.get('created_at', '')}</td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">分類</td><td>{ticket.get('category', '')}</td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">申請人</td><td>{ticket.get('requester_name', '')}（{ticket.get('requester_contact', '')}）</td></tr>"
        "</table>"
        f"<h3 style=\"margin:20px 0 6px\">問題</h3><p>{safe_query}</p>"
        f"<h3 style=\"margin:20px 0 6px\">問題說明</h3><p>{safe_description}</p>"
        f"<p style=\"margin:24px 0\"><a href=\"{office_link}\" style=\"background:#2563eb;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none\">開啟需求單並回覆 →</a></p>"
        f"<div style=\"border:1px solid #d7dce2;background:#f5f7fa;border-radius:10px;padding:14px 16px;margin:18px 0\"><strong>處室登入資訊</strong><p style=\"margin:8px 0 0\">後台連結：<a href=\"{office_home}\">{office_home}</a><br>該處室專屬密碼：<code style=\"font-size:15px;font-weight:700\">{safe_login_code}</code></p></div>"
        f"<p style=\"color:#6b7280;font-size:13px\">若按鈕無法開啟，請複製此連結：<br>{office_link}<br>登入後即可查看及回覆需求單；回覆內容會直接顯示給提問學生。</p></div>",
        subtype="html",
    )
    try:
        _send(message)
        return True, recipient
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def send_student_resolution_email(ticket: dict) -> tuple[bool, str]:
    settings = load_settings()
    if not _configured(settings):
        return False, "尚未設定寄件帳號或應用程式密碼"
    # 單機測試版寄至管理後台設定的通知清單；未來串接會員系統後再改用學生帳號信箱。
    recipients = settings.get("student_recipients") or [DEFAULT_EMAIL]
    recipient = ", ".join(recipients)
    access_key = str(ticket.get("access_key") or "").strip()
    if not access_key:
        return False, "需求單缺少學生存取碼"
    ticket_link = f"{base_url()}/ticket/{ticket['ticket_no']}?key={access_key}"
    question = str(ticket.get("query") or ticket.get("subject") or "")
    answer = str(ticket.get("resolution") or "")
    message = EmailMessage()
    message["Subject"] = f"[{_subject_tag(settings)} {ticket['ticket_no']}] 處室已回覆，請為服務評分"
    message["From"] = _from_header(settings)
    message["To"] = recipient
    message["Reply-To"] = settings["username"]
    message.set_content(
        f"您好：\n\n您的需求單已由「{ticket['office']}」回覆並結案。\n\n"
        f"需求單編號：{ticket['ticket_no']}\n\n【Q 問題】\n{question}\n\n【A 處室回覆】\n{answer}\n\n"
        f"請開啟下列連結查看 Q&A 並評分 1～5 顆星：\n{ticket_link}#rate-card\n"
    )
    safe_office = escape(str(ticket["office"]))
    safe_no = escape(str(ticket["ticket_no"]))
    safe_q = escape(question).replace(chr(10), "<br>")
    safe_a = escape(answer).replace(chr(10), "<br>")
    star_links = " ".join(
        f'<a href="{ticket_link}&rating={n}#rate-card" style="font-size:28px;color:#e6532d;text-decoration:none" title="評分 {n} 顆星">{chr(9733)}</a>'
        for n in range(1, 6)
    )
    message.add_alternative(
        "<div style=\"font-family:'Noto Sans TC',Arial,sans-serif;font-size:15px;color:#1f2933;line-height:1.7;max-width:680px\">"
        f"<p>您好：</p><p>您的需求單 <strong>{safe_no}</strong> 已由「<strong>{safe_office}</strong>」回覆並結案。</p>"
        f"<div style=\"border:1px solid #ddd;border-radius:10px;padding:16px;margin:18px 0\"><strong>Q．問題</strong><p>{safe_q}</p><hr style=\"border:0;border-top:1px solid #eee\"><strong>A．處室回覆</strong><p>{safe_a}</p></div>"
        f"<p><strong>請為本次服務評分：</strong></p><div>{star_links}</div>"
        f"<p style=\"margin:24px 0\"><a href=\"{ticket_link}#rate-card\" style=\"background:#e6532d;color:#fff;padding:11px 18px;border-radius:8px;text-decoration:none\">開啟需求單、查看 Q&A 並評分 →</a></p>"
        f"<p style=\"color:#6b7280;font-size:13px\">若按鈕無法開啟，請複製此連結：<br>{ticket_link}</p></div>",
        subtype="html",
    )
    try:
        _send(message)
        return True, recipient
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def send_test_email(recipient: str) -> tuple[bool, str]:
    settings = load_settings()
    if not _configured(settings):
        return False, "尚未設定寄件帳號或應用程式密碼"
    recipient = (recipient or DEFAULT_EMAIL).strip()
    message = EmailMessage()
    message["Subject"] = f"[{_subject_tag(settings)}] 測試信"
    message["From"] = _from_header(settings)
    message["To"] = recipient
    message.set_content(
        f"這是{_subject_tag(settings)}的寄信測試。\n\n"
        f"收到本信表示 SMTP 設定正確，之後學生送出的需求單會自動寄到各處室設定的信箱。\n"
        f"系統網址：{base_url()}\n"
    )
    try:
        _send(message)
        return True, recipient
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
