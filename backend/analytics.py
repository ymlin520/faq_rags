import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "analytics.db"

TAIPEI = timezone(timedelta(hours=8))
TIME_FIELDS = ("created_at", "updated_at", "resolved_at", "rated_at")
MIN_RATING_SAMPLE = 5   # 評分數少於這個值就不顯示平均評分
LOW_RATING = 2          # 1~2 星視為負評，會自動重啟提問單
OVERDUE_HOURS = 48      # 待處理超過這個時數標記為逾期
SLOW_HOURS = 12         # 平均解答時間超過這個時數標紅


def to_taipei(value: str | None) -> str | None:
    """SQLite 的 CURRENT_TIMESTAMP 存的是 UTC，對外一律轉成台灣時間顯示。"""
    if not value:
        return value
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return moment.replace(tzinfo=timezone.utc).astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")
    return value


def _local(row) -> dict:
    item = dict(row)
    for field in TIME_FIELDS:
        if field in item:
            item[field] = to_taipei(item[field])
    return item


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS queries (
          id INTEGER PRIMARY KEY, query TEXT NOT NULL, result_count INTEGER NOT NULL,
          top_score REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS feedback (
          id INTEGER PRIMARY KEY, query TEXT NOT NULL, source_question TEXT NOT NULL DEFAULT '',
          helpful INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tickets (
          id INTEGER PRIMARY KEY, ticket_no TEXT NOT NULL UNIQUE, query TEXT NOT NULL,
          subject TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
          office TEXT NOT NULL, requester_name TEXT NOT NULL, requester_contact TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT '待處理', assignee TEXT NOT NULL DEFAULT '',
          resolution TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT,
          access_key TEXT NOT NULL DEFAULT '', email_status TEXT NOT NULL DEFAULT 'pending',
          email_error TEXT NOT NULL DEFAULT '', rating INTEGER,
          rating_comment TEXT NOT NULL DEFAULT '', rated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ticket_events (
          id INTEGER PRIMARY KEY, ticket_no TEXT NOT NULL, event_type TEXT NOT NULL,
          actor TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', office TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
    if "access_key" not in columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN access_key TEXT NOT NULL DEFAULT ''")
    if "email_status" not in columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN email_status TEXT NOT NULL DEFAULT 'pending'")
    if "email_error" not in columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN email_error TEXT NOT NULL DEFAULT ''")
    if "rating" not in columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN rating INTEGER")
    if "rating_comment" not in columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN rating_comment TEXT NOT NULL DEFAULT ''")
    if "rated_at" not in columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN rated_at TEXT")
    return connection


def create_ticket(data: dict) -> dict:
    with _connect() as db:
        next_id = int(db.execute("SELECT COALESCE(MAX(id),0)+1 FROM tickets").fetchone()[0])
        ticket_no = f"T-{datetime.now(TAIPEI):%Y%m%d}-{next_id:04d}"
        access_key = secrets.token_urlsafe(24)
        db.execute(
            """INSERT INTO tickets(ticket_no,query,subject,description,category,office,
               requester_name,requester_contact,access_key) VALUES(?,?,?,?,?,?,?,?,?)""",
            (ticket_no, data["query"], data["subject"], data["description"], data["category"],
             data["office"], data["requester_name"], data["requester_contact"], access_key),
        )
        db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message,office) VALUES(?,?,?,?,?)",
                   (ticket_no, "created", "系統", "AI 查無足夠資料，建立服務需求單", data["office"]))
        row = db.execute("SELECT * FROM tickets WHERE ticket_no=?", (ticket_no,)).fetchone()
        return _local(row)


def list_tickets(status: str = "", office: str = "") -> list[dict]:
    sql, params = "SELECT * FROM tickets WHERE 1=1", []
    if status:
        sql += " AND status=?"; params.append(status)
    if office:
        sql += " AND office=?"; params.append(office)
    sql += " ORDER BY CASE status WHEN '待處理' THEN 0 WHEN '處理中' THEN 1 ELSE 2 END, id DESC"
    with _connect() as db:
        result = []
        for row in db.execute(sql, params).fetchall():
            item = _local(row); item.pop("access_key", None); result.append(item)
        return result


def ticket_detail(ticket_no: str) -> dict | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM tickets WHERE ticket_no=?", (ticket_no,)).fetchone()
        if not row: return None
        ticket = _local(row); ticket.pop("access_key", None)
        ticket["events"] = [_local(x) for x in db.execute("SELECT * FROM ticket_events WHERE ticket_no=? ORDER BY id", (ticket_no,)).fetchall()]
        return ticket


def update_ticket(ticket_no: str, data: dict) -> dict | None:
    resolved_at = "CURRENT_TIMESTAMP" if data["status"] == "已解決" else "NULL"
    with _connect() as db:
        current = db.execute("SELECT * FROM tickets WHERE ticket_no=?", (ticket_no,)).fetchone()
        if not current: return None
        office = data.get("office") or current["office"]
        db.execute(f"""UPDATE tickets SET status=?,assignee=?,resolution=?,office=?,updated_at=CURRENT_TIMESTAMP,
                resolved_at={resolved_at} WHERE ticket_no=?""",
            (data["status"], data.get("assignee", ""), data.get("resolution", ""), office, ticket_no))
        if office != current["office"]:
            db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message,office) VALUES(?,?,?,?,?)",
                       (ticket_no, "transfer", data.get("assignee") or "管理者", f"轉派至 {office}", office))
        if data["status"] != current["status"] or data.get("resolution", ""):
            db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message,office) VALUES(?,?,?,?,?)",
                       (ticket_no, "update", data.get("assignee") or "承辦單位", data.get("resolution") or data["status"], office))
        row = db.execute("SELECT * FROM tickets WHERE ticket_no=?", (ticket_no,)).fetchone()
        return _local(row) if row else None


def public_ticket(ticket_no: str, access_key: str) -> dict | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM tickets WHERE ticket_no=? AND access_key=?", (ticket_no, access_key)).fetchone()
        if not row: return None
        ticket = _local(row); ticket.pop("access_key", None)
        ticket["events"] = [_local(x) for x in db.execute("SELECT * FROM ticket_events WHERE ticket_no=? ORDER BY id", (ticket_no,)).fetchall()]
        return ticket


def add_ticket_reply(ticket_no: str, access_key: str, message: str, allow_faq: bool) -> dict | None:
    with _connect() as db:
        row = db.execute("SELECT office FROM tickets WHERE ticket_no=? AND access_key=?", (ticket_no, access_key)).fetchone()
        if not row: return None
        note = message + ("\n[同意納入知識庫候選]" if allow_faq else "")
        db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message,office) VALUES(?,?,?,?,?)",
                   (ticket_no, "reply", "提問者", note, row["office"]))
        db.execute("UPDATE tickets SET updated_at=CURRENT_TIMESTAMP WHERE ticket_no=?", (ticket_no,))
    return public_ticket(ticket_no, access_key)


def record_ticket_email(ticket_no: str, sent: bool, detail: str) -> None:
    with _connect() as db:
        db.execute("UPDATE tickets SET email_status=?,email_error=? WHERE ticket_no=?",
                   ("sent" if sent else "failed", "" if sent else detail[:500], ticket_no))
        db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message) VALUES(?,?,?,?)",
                   (ticket_no, "email", "系統", f"通知信已寄至 {detail}" if sent else f"通知信寄送失敗：{detail[:300]}"))


def record_student_email(ticket_no: str, sent: bool, detail: str) -> None:
    with _connect() as db:
        message = f"已寄送回覆與評分連結至學生信箱 {detail}" if sent else f"學生回覆通知寄送失敗：{detail[:300]}"
        db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message) VALUES(?,?,?,?)",
                   (ticket_no, "email", "系統", message))


def record_knowledge_sync(ticket_no: str, saved: bool, detail: str) -> None:
    with _connect() as db:
        message = f"已將本需求單 Q&A 寫入知識庫（{detail}）" if saved else f"知識庫寫入失敗：{detail[:300]}"
        db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message) VALUES(?,?,?,?)",
                   (ticket_no, "knowledge", "系統", message))


def rate_ticket(ticket_no: str, access_key: str, rating: int, comment: str = "") -> dict | None:
    """提問者為已解決的提問單評分；1~2 星會自動重啟提問單交回承辦單位。"""
    rating = int(rating)
    if rating < 1 or rating > 5:
        raise ValueError("評分必須是 1 到 5 顆星")
    comment = (comment or "").strip()[:1000]
    with _connect() as db:
        row = db.execute("SELECT status,office FROM tickets WHERE ticket_no=? AND access_key=?",
                         (ticket_no, access_key)).fetchone()
        if not row: return None
        if row["status"] != "已解決":
            raise ValueError("提問單處理完成後才能評分")
        db.execute("""UPDATE tickets SET rating=?,rating_comment=?,rated_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE ticket_no=?""", (rating, comment, ticket_no))
        db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message,office) VALUES(?,?,?,?,?)",
                   (ticket_no, "rating", "提問者",
                    f"給予 {rating} 星評價" + (f"：{comment}" if comment else ""), row["office"]))
        if rating <= LOW_RATING:
            db.execute("UPDATE tickets SET status='處理中',resolved_at=NULL WHERE ticket_no=?", (ticket_no,))
            db.execute("INSERT INTO ticket_events(ticket_no,event_type,actor,message,office) VALUES(?,?,?,?,?)",
                       (ticket_no, "reopen", "系統",
                        f"評分 {rating} 星低於 3 星，提問單自動重啟，請承辦單位再次確認", row["office"]))
    return public_ticket(ticket_no, access_key)


def log_query(query: str, results: list[dict]) -> None:
    with _connect() as db:
        db.execute(
            "INSERT INTO queries(query,result_count,top_score) VALUES(?,?,?)",
            (query, len(results), float(results[0].get("score", 0)) if results else 0),
        )


def log_feedback(query: str, source_question: str, helpful: bool) -> None:
    with _connect() as db:
        db.execute(
            "INSERT INTO feedback(query,source_question,helpful) VALUES(?,?,?)",
            (query, source_question, int(helpful)),
        )


def stats(days: int = 7) -> dict:
    days = max(1, min(int(days or 7), 3650))
    since = f"-{days} days"
    with _connect() as db:
        summary = db.execute(
            """SELECT COUNT(*) total_queries,
               SUM(CASE WHEN result_count=0 OR top_score<0.55 THEN 1 ELSE 0 END) low_confidence
               FROM queries WHERE created_at >= datetime('now', ?)""", (since,)
        ).fetchone()
        feedback = db.execute(
            "SELECT COUNT(*) total, SUM(helpful) helpful FROM feedback WHERE created_at >= datetime('now', ?)", (since,)
        ).fetchone()
        popular = db.execute(
            "SELECT query, COUNT(*) count FROM queries WHERE created_at >= datetime('now', ?) GROUP BY query ORDER BY count DESC, MAX(id) DESC LIMIT 8", (since,)
        ).fetchall()
        unresolved = db.execute(
            """SELECT query, top_score, created_at FROM queries
               WHERE created_at >= datetime('now', ?) AND (result_count=0 OR top_score<0.55) ORDER BY id DESC LIMIT 10""", (since,)
        ).fetchall()
        ticket_summary = db.execute(
            """SELECT COUNT(*) total,
               SUM(status='待處理') pending, SUM(status='處理中') processing,
               SUM(status='已解決') resolved,
               AVG(CASE WHEN resolved_at IS NOT NULL THEN (julianday(resolved_at)-julianday(created_at))*24 END) avg_hours,
               AVG(rating) rating_avg, COUNT(rating) rating_count
               FROM tickets WHERE created_at >= datetime('now', ?)""", (since,)
        ).fetchone()
        transfer_summary = db.execute(
            """SELECT COUNT(*) transfer_count, COUNT(DISTINCT ticket_no) transferred_tickets
               FROM ticket_events WHERE event_type='transfer' AND created_at >= datetime('now', ?)""", (since,)
        ).fetchone()
        by_office = db.execute(
            """SELECT office, COUNT(*) total, SUM(status='已解決') resolved,
               AVG(CASE WHEN resolved_at IS NOT NULL THEN (julianday(resolved_at)-julianday(created_at))*24 END) avg_hours,
               AVG(rating) rating_avg, COUNT(rating) rating_count
               FROM tickets WHERE created_at >= datetime('now', ?)
               GROUP BY office ORDER BY total DESC, office""", (since,)
        ).fetchall()
        rating_rows = db.execute(
            """SELECT rating, COUNT(*) count FROM tickets
               WHERE created_at >= datetime('now', ?) AND rating IS NOT NULL GROUP BY rating""", (since,)
        ).fetchall()
        pending_tickets = db.execute(
            """SELECT ticket_no,category,subject,office,status,created_at,
               ROUND((julianday('now')-julianday(created_at))*24,1) waiting_hours
               FROM tickets WHERE created_at >= datetime('now', ?) AND status!='已解決'
               ORDER BY waiting_hours DESC, id DESC LIMIT 8""", (since,)
        ).fetchall()
    total_feedback = int(feedback["total"] or 0)
    helpful = int(feedback["helpful"] or 0)
    rating_count = int(ticket_summary["rating_count"] or 0)
    counts = {int(row["rating"]): int(row["count"]) for row in rating_rows}

    def office_row(row) -> dict:
        n = int(row["rating_count"] or 0)
        return {
            "office": row["office"],
            "total": int(row["total"] or 0),
            "resolved": int(row["resolved"] or 0),
            "avg_hours": round(float(row["avg_hours"] or 0), 1),
            "rating_count": n,
            "rating_avg": round(float(row["rating_avg"]), 1) if n >= MIN_RATING_SAMPLE else None,
        }

    def pending_row(row) -> dict:
        item = _local(row)
        hours = float(row["waiting_hours"] or 0)
        item["waiting_hours"] = hours
        item["overdue"] = hours >= OVERDUE_HOURS
        return item

    return {
        "days": days,
        "generated_at": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M"),
        "timezone": "Asia/Taipei (UTC+8)",
        "total_queries": int(summary["total_queries"] or 0),
        "low_confidence": int(summary["low_confidence"] or 0),
        "feedback_total": total_feedback,
        "helpful_rate": round(helpful / total_feedback * 100) if total_feedback else None,
        "popular": [dict(row) for row in popular],
        "unresolved": [_local(row) for row in unresolved],
        "ticket_total": int(ticket_summary["total"] or 0),
        "ticket_pending": int(ticket_summary["pending"] or 0),
        "ticket_processing": int(ticket_summary["processing"] or 0),
        "ticket_resolved": int(ticket_summary["resolved"] or 0),
        "transfer_count": int(transfer_summary["transfer_count"] or 0),
        "transferred_tickets": int(transfer_summary["transferred_tickets"] or 0),
        "transfer_rate": round(int(transfer_summary["transferred_tickets"] or 0) / int(ticket_summary["total"] or 1) * 100, 1),
        "avg_resolution_hours": round(float(ticket_summary["avg_hours"] or 0), 1),
        "rating_avg": round(float(ticket_summary["rating_avg"]), 1) if rating_count else None,
        "rating_count": rating_count,
        "rating_distribution": [{"stars": n, "count": counts.get(n, 0)} for n in (5, 4, 3, 2, 1)],
        "low_rating_count": counts.get(1, 0) + counts.get(2, 0),
        "min_rating_sample": MIN_RATING_SAMPLE,
        "low_rating_max": LOW_RATING,
        "overdue_hours": OVERDUE_HOURS,
        "slow_hours": SLOW_HOURS,
        "feedback_distribution": {"helpful": helpful, "unhelpful": max(total_feedback - helpful, 0)},
        "tickets_by_office": [office_row(row) for row in by_office],
        "pending_tickets": [pending_row(row) for row in pending_tickets],
    }
