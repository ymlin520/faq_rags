"""前台外觀與文案設定：提供 site-config.json 讀寫與動態 CSS 產生。"""
import json
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from .config import PROJECT_ROOT

CONFIG_PATH = PROJECT_ROOT / "data" / "site-config.json"
TOKEN_PATH = PROJECT_ROOT / "theme-admin-token.txt"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
CSS_BACKUP_DIR = PROJECT_ROOT / "data" / "css-original"

# 可在後台直接編輯的原始 CSS 檔（白名單，其他檔案一律拒絕）
CSS_FILES = {
    "style.css": "學生前台主樣式（版面、側欄、對話框、輸入區）",
    "llm.css": "學生前台 AI 回答與對話紀錄樣式",
    "ticket.css": "學生前台需求單視窗與需求單提示樣式",
    "ticket-page.css": "學生查看需求單頁樣式",
    "office.css": "處室登入頁樣式",
    "office-ticket.css": "處室需求單處理頁樣式",
    "admin.css": "總管理員後台樣式",
}

DEFAULT_TEXT = {
    "page_title": "校務 FAQ 智慧問答",
    "brand_mark": "FAQ",
    "site_title": "校務 FAQ 智慧問答",
    "site_subtitle": "地端知識庫 × 地端 AI · 找不到答案可直接轉交承辦處室",
    "beta_label": "AI 版",
    "beta_small": "BETA",
    "new_chat": "＋ 新對話",
    "history_title": "之前的對話",
    "history_clear": "清除",
    "sidebar_mobile_title": "常見問題",
    "section_label": "常見問題分類",
    "section_hint": "點選分類，右側會列出該分類的常見問題",
    "sidebar_note": "找不到分類？直接輸入完整問題即可。",
    "welcome_title": "您好，我是校務 FAQ 助理",
    "welcome_text": "請選擇分類或直接輸入問題。如果知識庫無法解答，我可以協助建立需求單並轉交指定處室。",
    "newchat_welcome_text": "請輸入您的問題；知識庫沒有答案時，您可以確認提出需求單。",
    "composer_placeholder": "請輸入您的問題…",
    "submit_text": "送出 ↗",
    "disclaimer": "回答由地端 AI 依 FAQ 整理；重要規定仍請以校方最新公告為準。",
    "ticket_badge": "AI 自動分派",
    "ticket_title": "建立服務需求單",
    "ticket_intro": "請留下聯絡方式與問題內容，AI 會自動判斷並送至適合的承辦處室。",
    "ticket_subject_label": "需求單主旨",
    "ticket_desc_label": "問題說明",
    "ticket_name_label": "姓名",
    "ticket_contact_label": "電子郵件或電話",
    "ticket_cancel": "取消",
    "ticket_submit": "送出需求單",
}

DEFAULT_SUGGESTIONS = [
    {"label": "最低修課學分", "query": "最低修課學分是多少？"},
    {"label": "實習申請", "query": "如何申請實習？"},
    {"label": "宿舍申請", "query": "宿舍如何申請？"},
]

DEFAULT_CATEGORIES = [
    {"label": "選課相關", "query": "選課相關常見問題"},
    {"label": "實習相關", "query": "實習相關常見問題"},
    {"label": "畢業相關", "query": "畢業相關常見問題"},
    {"label": "成績與學籍", "query": "成績與學籍常見問題"},
    {"label": "獎助學金", "query": "獎助學金常見問題"},
    {"label": "宿舍住宿", "query": "宿舍住宿常見問題"},
    {"label": "教室與設備", "query": "教室與設備常見問題"},
    {"label": "資訊系統", "query": "資訊系統常見問題"},
    {"label": "海外學習", "query": "交換與海外學習常見問題"},
    {"label": "其他問題", "query": "其他常見問題"},
]

# key -> (型別, 預設值, 中文說明, 分組)
THEME_FIELDS = {
    "font_family":        ("font",  '"Segoe UI","Microsoft JhengHei",sans-serif', "全站字體", "字體"),
    "base_font_size":     ("num",   16, "內文基準字級 (px)", "字體"),
    "page_bg_from":       ("color", "#eeeae4", "頁面背景漸層（起）", "背景"),
    "page_bg_to":         ("color", "#ddd8d0", "頁面背景漸層（迄）", "背景"),
    "paper":              ("color", "#fbf8f3", "主面板底色", "背景"),
    "composer_bg":        ("color", "#f5f0e9", "輸入區底色", "背景"),
    "ink":                ("color", "#292724", "主要文字色", "文字"),
    "muted":              ("color", "#77716a", "次要文字色", "文字"),
    "line":               ("color", "#2d2a27", "外框線顏色", "外框"),
    "radius":             ("num",   18, "面板圓角 (px)", "外框"),
    "accent":             ("color", "#e6532d", "主題強調色", "主題色"),
    "accent_soft":        ("color", "#f7ddd1", "強調色（淡）", "主題色"),
    "title_color":        ("color", "#292724", "標題文字色", "標題"),
    "title_size":         ("num",   31, "標題字級 (px)", "標題"),
    "subtitle_color":     ("color", "#77716a", "副標文字色", "標題"),
    "subtitle_size":      ("num",   15, "副標字級 (px)", "標題"),
    "brand_color":        ("color", "#77716a", "左上角標記文字色", "標題"),
    "beta_color":         ("color", "#292724", "右上角標籤文字色", "標題"),
    "btn_bg":             ("color", "#e6532d", "送出鈕背景色", "按鈕"),
    "btn_text":           ("color", "#ffffff", "送出鈕文字色", "按鈕"),
    "btn_font_size":      ("num",   15, "送出鈕字級 (px)", "按鈕"),
    "btn_radius":         ("num",   11, "送出鈕圓角 (px)", "按鈕"),
    "newchat_bg":         ("color", "#e6532d", "新對話鈕背景色", "按鈕"),
    "newchat_text":       ("color", "#ffffff", "新對話鈕文字色", "按鈕"),
    "category_text":      ("color", "#292724", "分類鈕文字色", "分類鈕"),
    "category_bg":        ("color", "#fbf8f3", "分類鈕背景色", "分類鈕"),
    "category_font_size": ("num",   15, "分類鈕字級 (px)", "分類鈕"),
    "category_radius":    ("num",   12, "分類鈕圓角 (px)", "分類鈕"),
    "message_bg":         ("color", "#ffffff", "AI 對話框底色", "對話"),
    "message_text":       ("color", "#292724", "AI 對話框文字色", "對話"),
    "user_msg_bg":        ("color", "#f7ddd1", "使用者對話框底色", "對話"),
    "disclaimer_color":   ("color", "#888078", "底部免責文字色", "對話"),
}

DEFAULT_THEME = {key: spec[1] for key, spec in THEME_FIELDS.items()}

COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def default_config() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "text": dict(DEFAULT_TEXT),
        "suggestions": [dict(row) for row in DEFAULT_SUGGESTIONS],
        "categories": [dict(row) for row in DEFAULT_CATEGORIES],
        "theme": dict(DEFAULT_THEME),
        "custom_css": "",
    }


def load_config() -> dict:
    cfg = default_config()
    if not CONFIG_PATH.exists():
        return cfg
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return cfg
    if isinstance(saved.get("text"), dict):
        for key in DEFAULT_TEXT:
            value = saved["text"].get(key)
            if isinstance(value, str) and value.strip():
                cfg["text"][key] = value
    if isinstance(saved.get("theme"), dict):
        for key in DEFAULT_THEME:
            value = saved["theme"].get(key)
            if value not in (None, ""):
                cfg["theme"][key] = value
    for key in ("suggestions", "categories"):
        rows = saved.get(key)
        if isinstance(rows, list):
            cfg[key] = [{"label": str(row.get("label", "")).strip(),
                         "query": str(row.get("query", "")).strip()}
                        for row in rows
                        if isinstance(row, dict) and str(row.get("label", "")).strip()]
    if isinstance(saved.get("custom_css"), str):
        cfg["custom_css"] = saved["custom_css"]
    cfg["updated_at"] = str(saved.get("updated_at") or "")
    return cfg


def _clean_theme(raw: dict) -> dict:
    theme = dict(DEFAULT_THEME)
    for key, (kind, default, _label, _group) in THEME_FIELDS.items():
        if key not in raw:
            continue
        value = raw[key]
        if kind == "color":
            value = str(value).strip()
            theme[key] = value if COLOR_RE.match(value) else default
        elif kind == "num":
            try:
                theme[key] = max(0, min(200, int(float(value))))
            except (TypeError, ValueError):
                theme[key] = default
        else:
            value = str(value).strip()
            # 字體名稱只允許安全字元，避免被塞進其他 CSS 宣告
            theme[key] = value if value and not re.search(r"[{}<>;@]", value) else default
    return theme


def clean_theme(raw: dict) -> dict:
    return _clean_theme(raw if isinstance(raw, dict) else {})


def _clean_css(raw) -> str:
    css = str(raw or "")[:20000]
    css = re.sub(r"@import[^;]*;?", "", css, flags=re.I)
    css = re.sub(r"</\s*style", "", css, flags=re.I)
    return css.strip()


def _clean_rows(rows) -> list:
    clean = []
    for row in list(rows)[:40]:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", "")).strip()[:60]
        query = str(row.get("query", "")).strip()[:200] or label
        if label:
            clean.append({"label": label, "query": query})
    return clean


def _write(cfg: dict) -> dict:
    cfg["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def save_config(payload: dict) -> dict:
    cfg = load_config()
    if isinstance(payload.get("text"), dict):
        for key in DEFAULT_TEXT:
            if key in payload["text"]:
                value = str(payload["text"][key]).strip()
                cfg["text"][key] = value or DEFAULT_TEXT[key]
    if isinstance(payload.get("theme"), dict):
        cfg["theme"] = _clean_theme(payload["theme"])
    for key in ("suggestions", "categories"):
        if isinstance(payload.get(key), list):
            cfg[key] = _clean_rows(payload[key])
    if "custom_css" in payload:
        cfg["custom_css"] = _clean_css(payload["custom_css"])
    return _write(cfg)


def reset_config() -> dict:
    return _write(default_config())


def build_css(cfg: dict = None) -> str:
    cfg = cfg or load_config()
    t = dict(DEFAULT_THEME)
    t.update(cfg.get("theme") or {})
    custom = cfg.get("custom_css") or ""
    return "\n".join([
        ":root{",
        "  --paper:%s;" % t["paper"],
        "  --ink:%s;" % t["ink"],
        "  --muted:%s;" % t["muted"],
        "  --line:%s;" % t["line"],
        "  --accent:%s;" % t["accent"],
        "  --accent-soft:%s;" % t["accent_soft"],
        "  font-family:%s;" % t["font_family"],
        "  color:%s;" % t["ink"],
        "  font-size:%spx;" % t["base_font_size"],
        "}",
        "body{background:linear-gradient(135deg,%s,%s);}" % (t["page_bg_from"], t["page_bg_to"]),
        ".app-shell{background:%s;border-radius:%spx;border-color:%s;}" % (t["paper"], t["radius"], t["line"]),
        ".topbar{border-bottom-color:%s;}" % t["line"],
        ".brand-mark{color:%s;border-color:%s;}" % (t["brand_color"], t["line"]),
        ".brand-copy h1{color:%s;font-size:%spx;}" % (t["title_color"], t["title_size"]),
        ".brand-copy p{color:%s;font-size:%spx;}" % (t["subtitle_color"], t["subtitle_size"]),
        ".beta{color:%s;border-color:%s;}" % (t["beta_color"], t["line"]),
        ".sidebar{border-right-color:%s;}" % t["line"],
        ".category{color:%s;background:%s;font-size:%spx;border-radius:%spx;border-color:%s;}"
        % (t["category_text"], t["category_bg"], t["category_font_size"], t["category_radius"], t["line"]),
        ".category:hover,.category:focus-visible{border-color:%s;}" % t["accent"],
        ".category.active{border-color:%s;background:%s;color:%s;}" % (t["accent"], t["accent_soft"], t["accent"]),
        ".message,.answer-card{background:%s;color:%s;border-color:%s;}" % (t["message_bg"], t["message_text"], t["line"]),
        ".user-message{background:%s;border-color:%s;}" % (t["user_msg_bg"], t["accent"]),
        ".user-avatar{background:%s;border-color:%s;}" % (t["accent"], t["accent"]),
        ".avatar{background:%s;border-color:%s;}" % (t["paper"], t["line"]),
        ".ai-answer{background:%s;border-color:%s;}" % (t["message_bg"], t["accent"]),
        ".answer-topline{color:%s;}" % t["accent"],
        ".composer-wrap{background:%s;}" % t["composer_bg"],
        ".composer{border-color:%s;}" % t["line"],
        ".composer button{background:%s;color:%s;font-size:%spx;border-radius:%spx;}"
        % (t["btn_bg"], t["btn_text"], t["btn_font_size"], t["btn_radius"]),
        ".new-chat{background:%s;color:%s;border-color:%s;}" % (t["newchat_bg"], t["newchat_text"], t["newchat_bg"]),
        ".new-chat:hover,.new-chat:focus-visible{background:%s;border-color:%s;filter:brightness(.92);}"
        % (t["newchat_bg"], t["newchat_bg"]),
        ".mobile-new-chat{background:%s;color:%s;}" % (t["btn_bg"], t["btn_text"]),
        "#status{color:%s;}" % t["accent"],
        ".disclaimer{color:%s;}" % t["disclaimer_color"],
        ".ticket-dialog .primary{background:%s;color:%s;}" % (t["btn_bg"], t["btn_text"]),
        "/* ==== 自訂 CSS ==== */",
        custom,
        "",
    ])


def css_path(name: str) -> Path:
    """把檔名對應到 frontend 下的實體檔案，只允許白名單內的名稱。"""
    if name not in CSS_FILES:
        raise ValueError("不允許編輯這個檔案")
    path = (FRONTEND_DIR / name).resolve()
    if path.parent != FRONTEND_DIR.resolve():
        raise ValueError("路徑不合法")
    return path


def _backup_path(name: str) -> Path:
    return CSS_BACKUP_DIR / name


def ensure_css_backup(name: str) -> bool:
    """第一次修改前先把原始檔留一份，之後才能還原。"""
    source = css_path(name)
    target = _backup_path(name)
    if target.exists() or not source.exists():
        return target.exists()
    CSS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def read_css_file(name: str) -> dict:
    path = css_path(name)
    content = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    backup = _backup_path(name)
    return {
        "name": name,
        "label": CSS_FILES[name],
        "content": content,
        "bytes": len(content.encode("utf-8")),
        "exists": path.exists(),
        "modified": backup.exists() and backup.read_text(encoding="utf-8-sig") != content,
        "has_backup": backup.exists(),
    }


def list_css_files() -> list:
    rows = []
    for name in CSS_FILES:
        try:
            info = read_css_file(name)
        except Exception:
            continue
        info.pop("content", None)
        rows.append(info)
    return rows


_VERSION_RE_CACHE = {}


def _bump_cache_version(name: str) -> None:
    """改完 CSS 之後更新 HTML/JS 裡的 ?v= 版本號，避免瀏覽器讀到舊的快取。"""
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    pattern = _VERSION_RE_CACHE.get(name)
    if pattern is None:
        pattern = re.compile(r"(?<![\w-])" + re.escape(name) + r"\?v=[^\"'\s]*")
        _VERSION_RE_CACHE[name] = pattern
    for path in list(FRONTEND_DIR.glob("*.html")) + list(FRONTEND_DIR.glob("*.js")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        updated = pattern.sub(name + "?v=" + stamp, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def write_css_file(name: str, content: str) -> dict:
    path = css_path(name)
    ensure_css_backup(name)
    text = str(content or "")
    if len(text.encode("utf-8")) > 400000:
        raise ValueError("檔案內容過大")
    path.write_text(text, encoding="utf-8")
    _bump_cache_version(name)
    return read_css_file(name)


def restore_css_file(name: str) -> dict:
    path = css_path(name)
    backup = _backup_path(name)
    if not backup.exists():
        raise ValueError("這個檔案沒有原始備份，可能還沒被修改過")
    shutil.copy2(backup, path)
    _bump_cache_version(name)
    return read_css_file(name)


def ensure_token() -> str:
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8-sig").strip()
        if token:
            return token
    token = secrets.token_urlsafe(18)
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    return token


def check_token(token: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    if secrets.compare_digest(token, ensure_token()):
        return True
    import os
    admin = os.getenv("FAQ_ADMIN_TOKEN", "")
    return bool(admin) and secrets.compare_digest(token, admin)


def theme_fields() -> list:
    return [{"key": key, "kind": spec[0], "default": spec[1], "label": spec[2], "group": spec[3]}
            for key, spec in THEME_FIELDS.items()]


def text_fields() -> list:
    labels = {
        "page_title": "瀏覽器分頁標題",
        "brand_mark": "左上角方塊標記",
        "site_title": "網站主標題",
        "site_subtitle": "網站副標題",
        "beta_label": "右上角標籤",
        "beta_small": "右上角小字",
        "new_chat": "新對話按鈕文字",
        "history_title": "對話紀錄區標題",
        "history_clear": "清除紀錄按鈕",
        "sidebar_mobile_title": "手機側欄標題",
        "section_label": "分類區標題",
        "section_hint": "分類區說明",
        "sidebar_note": "側欄底部提示",
        "welcome_title": "歡迎訊息標題",
        "welcome_text": "歡迎訊息內容",
        "newchat_welcome_text": "新對話歡迎訊息",
        "composer_placeholder": "輸入框提示文字",
        "submit_text": "送出按鈕文字",
        "disclaimer": "底部免責聲明",
        "ticket_badge": "需求單視窗小標",
        "ticket_title": "需求單視窗標題",
        "ticket_intro": "需求單視窗說明",
        "ticket_subject_label": "需求單：主旨欄位",
        "ticket_desc_label": "需求單：說明欄位",
        "ticket_name_label": "需求單：姓名欄位",
        "ticket_contact_label": "需求單：聯絡方式欄位",
        "ticket_cancel": "需求單：取消按鈕",
        "ticket_submit": "需求單：送出按鈕",
    }
    groups = {
        "頁首與品牌": ["page_title", "brand_mark", "site_title", "site_subtitle", "beta_label", "beta_small"],
        "側欄": ["new_chat", "history_title", "history_clear", "sidebar_mobile_title",
                 "section_label", "section_hint", "sidebar_note"],
        "對話區": ["welcome_title", "welcome_text", "newchat_welcome_text",
                   "composer_placeholder", "submit_text", "disclaimer"],
        "需求單視窗": ["ticket_badge", "ticket_title", "ticket_intro", "ticket_subject_label",
                     "ticket_desc_label", "ticket_name_label", "ticket_contact_label",
                     "ticket_cancel", "ticket_submit"],
    }
    long_fields = {"site_subtitle", "sidebar_note", "welcome_text", "newchat_welcome_text",
                   "disclaimer", "ticket_intro"}
    out = []
    for group, keys in groups.items():
        for key in keys:
            out.append({"key": key, "label": labels[key], "group": group,
                        "default": DEFAULT_TEXT[key], "long": key in long_fields})
    return out
