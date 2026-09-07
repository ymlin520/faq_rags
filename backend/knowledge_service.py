import csv
from pathlib import Path

from .config import PROJECT_ROOT
from .embedding import embed_text
from .qdrant_service import upsert_faqs

CSV_PATH = PROJECT_ROOT / "data" / "faq.csv"
FIELDS = ["id", "category", "question", "answer", "url", "keywords"]
FAQ_MARKER = "[列入知識庫整理候選]"


def _record(ticket: dict) -> dict[str, str]:
    answer = str(ticket.get("resolution") or "").replace(FAQ_MARKER, "").strip()
    question = str(ticket.get("query") or ticket.get("subject") or "").strip()
    if ticket.get("status") != "已解決" or not question or not answer:
        raise ValueError("只有包含完整問題與回答的已解決工單才能加入知識庫")
    office = str(ticket.get("office") or "承辦處室").strip()
    category = str(ticket.get("category") or "工單回覆").strip()
    return {
        "id": f"TICKET-{ticket['ticket_no']}", "category": category, "question": question,
        "answer": answer, "url": "", "keywords": f"{category} {office} 工單回覆 已解決",
    }


def _save_csv(record: dict[str, str]) -> None:
    rows: list[dict[str, str]] = []
    if CSV_PATH.exists():
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as source:
            rows = [{field: str(row.get(field) or "") for field in FIELDS} for row in csv.DictReader(source)]
    for index, row in enumerate(rows):
        if row["id"] == record["id"]:
            rows[index] = record
            break
    else:
        rows.append(record)
    temporary = Path(str(CSV_PATH) + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(CSV_PATH)


def sync_resolved_ticket(ticket: dict) -> dict[str, str]:
    record = _record(ticket)
    text = (f"分類：\n{record['category']}\n\n問題：\n{record['question']}\n\n"
            f"答案：\n{record['answer']}\n\n關鍵字：\n{record['keywords']}")
    upsert_faqs([record], [embed_text(text)])
    _save_csv(record)
    return record


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
        for group in _load_groups() if group["questions"]
    ]
