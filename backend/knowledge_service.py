import csv
import re

from .faq_service import CSV_PATH, save_faq

# 側邊欄不顯示的分類（去掉「一、二、…」等序號後比對）；資料仍保留、搜尋與 AI 仍可命中。
HIDDEN_SIDEBAR_CATEGORIES = {"其他常見問題", "其他問題", "其他"}


def _base_category_name(name: str) -> str:
    return re.sub(r"^[一二三四五六七八九十百]+、", "", str(name)).strip()

FAQ_MARKER = "[列入知識庫整理候選]"


def _record(ticket: dict) -> dict[str, str]:
    answer = str(ticket.get("resolution") or "").replace(FAQ_MARKER, "").strip()
    question = str(ticket.get("query") or ticket.get("subject") or "").strip()
    if ticket.get("status") != "已解決" or not question or not answer:
        raise ValueError("只有包含完整問題與回答的已解決需求單才能加入知識庫")
    office = str(ticket.get("office") or "承辦處室").strip()
    category = str(ticket.get("category") or "需求單回覆").strip()
    return {
        "id": f"TICKET-{ticket['ticket_no']}", "category": category, "question": question,
        "answer": answer, "url": "", "keywords": f"{category} {office} 需求單回覆 已解決",
        "office": office, "email": "",
    }


def sync_resolved_ticket(ticket: dict) -> dict[str, str]:
    record = _record(ticket)
    return save_faq(record, original_id=record["id"])


_CATEGORY_CACHE: dict = {"mtime": None, "groups": []}


def _load_groups() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    mtime = CSV_PATH.stat().st_mtime
    if _CATEGORY_CACHE["mtime"] != mtime:
        groups: dict[str, list[dict[str, str]]] = {}
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                question = str(row.get("question") or "").strip()
                if not question:
                    continue
                category = str(row.get("category") or "").strip() or "其他"
                items = groups.setdefault(category, [])
                if not any(item["question"] == question for item in items):
                    items.append({"id": str(row.get("id") or ""), "question": question})
        _CATEGORY_CACHE["groups"] = [{"category": name, "questions": items} for name, items in groups.items()]
        _CATEGORY_CACHE["mtime"] = mtime
    return _CATEGORY_CACHE["groups"]


def faq_categories(limit: int = 8) -> list[dict]:
    """依 faq.csv 的分類回傳每類的代表問題，供前端側欄快速選單使用。"""
    return [
        {"category": group["category"], "total": len(group["questions"]),
         "questions": [item["question"] for item in group["questions"][:limit]]}
        for group in _load_groups()
        if group["questions"]
        and _base_category_name(group["category"]) not in HIDDEN_SIDEBAR_CATEGORIES
    ]
