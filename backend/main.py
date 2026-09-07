import logging
import csv
import io
import json
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import COLLECTION_NAME, PROJECT_ROOT
from .embedding import embed_text
from .llm_service import answer_from_faq, ollama_status, route_ticket_office
from .knowledge_service import faq_categories, sync_resolved_ticket
from .analytics import add_ticket_reply, create_ticket, list_tickets, log_feedback, log_query, public_ticket, rate_ticket, record_knowledge_sync, record_student_email, record_ticket_email, stats, ticket_detail, update_ticket
from .mail_service import (mail_status, save_office_emails, save_password, save_settings,
                           send_student_resolution_email, send_test_email, send_ticket_email)
from .models import (AnswerResponse, FeedbackRequest, FeedbackResponse, MailSettingsRequest,
                     MailTestRequest, OfficeMailRequest, SearchRequest, SearchResponse, TicketCreateRequest,
                     TicketRateRequest, TicketReplyRequest, TicketUpdateRequest)
from .qdrant_service import check_connection, close_client, collection_info, search_faq
from . import theme_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("vector-faq")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("FAQ API 啟動")
    try:
        yield
    finally:
        close_client()


app = FastAPI(title="校務 FAQ 智慧搜尋", lifespan=lifespan)
frontend = PROJECT_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=frontend), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(frontend / "admin.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/office", include_in_schema=False)
def office_page() -> FileResponse:
    return FileResponse(frontend / "office.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/office/ticket/{ticket_no}", include_in_schema=False)
def office_ticket_page(ticket_no: str) -> FileResponse:
    return FileResponse(frontend / "office-ticket.html")


@app.get("/ticket/{ticket_no}", include_in_schema=False)
def ticket_page(ticket_no: str) -> FileResponse:
    return FileResponse(frontend / "ticket.html")


@app.get("/design", include_in_schema=False)
def design_page() -> FileResponse:
    """外觀 / 文案管理後台。"""
    return FileResponse(frontend / "design-admin.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/site-theme.css", include_in_schema=False)
def site_theme_css() -> Response:
    return Response(content=theme_service.build_css(), media_type="text/css",
                    headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/site-config")
def site_config_public():
    """前台載入用：只回傳文案與選單，不含設定介面資訊。"""
    cfg = theme_service.load_config()
    return {"text": cfg["text"], "suggestions": cfg["suggestions"],
            "categories": cfg["categories"], "updated_at": cfg["updated_at"]}


def require_design(token: str) -> None:
    if not theme_service.check_token(token):
        raise HTTPException(status_code=401, detail="外觀後台密碼不正確")


@app.post("/api/design/login")
def design_login(payload: dict = Body(default={})):
    token = str(payload.get("token", ""))
    require_design(token)
    return {"ok": True}


@app.get("/api/design/config")
def design_config_get(x_design_token: str = Header(default="")):
    require_design(x_design_token)
    cfg = theme_service.load_config()
    return {"config": cfg, "theme_fields": theme_service.theme_fields(),
            "text_fields": theme_service.text_fields()}


@app.put("/api/design/config")
def design_config_save(payload: dict = Body(default={}), x_design_token: str = Header(default="")):
    require_design(x_design_token)
    cfg = theme_service.save_config(payload)
    logger.info("更新前台外觀設定 updated_at=%s", cfg["updated_at"])
    return {"config": cfg}


@app.post("/api/design/preview.css")
def design_preview_css(payload: dict = Body(default={}), x_design_token: str = Header(default="")):
    """後台即時預覽用：依傳入的設定產生 CSS，但不寫入檔案。"""
    require_design(x_design_token)
    cfg = theme_service.load_config()
    if isinstance(payload.get("theme"), dict):
        cfg["theme"] = theme_service.clean_theme(payload["theme"])
    if "custom_css" in payload:
        cfg["custom_css"] = str(payload["custom_css"] or "")[:20000]
    return Response(content=theme_service.build_css(cfg), media_type="text/css")


@app.post("/api/design/reset")
def design_config_reset(x_design_token: str = Header(default="")):
    require_design(x_design_token)
    logger.info("前台外觀設定已還原為預設")
    return {"config": theme_service.reset_config()}


def require_admin(token: str) -> None:
    expected = os.getenv("FAQ_ADMIN_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="管理密碼不正確")


def require_office(token: str) -> str:
    path = PROJECT_ROOT / "office-tokens.json"
    if not path.exists(): raise HTTPException(status_code=503, detail="尚未設定處室帳號")
    tokens = json.loads(path.read_text(encoding="utf-8-sig"))
    for office, saved in tokens.items():
        if token and token == saved: return office
    raise HTTPException(status_code=401, detail="處室登入碼不正確")


@app.get("/health")
@app.get("/api/health")
def health():
    try:
        check_connection()
        info = collection_info()
        return {
            "status": "ok",
            "qdrant": "connected",
            "collection": COLLECTION_NAME,
            "points": info.points_count or 0,
            "llm": {key: value for key, value in ollama_status().items() if key != "model"},
        }
    except Exception as exc:
        logger.exception("健康檢查失敗")
        raise HTTPException(status_code=503, detail=f"Qdrant 或 Collection 無法使用：{exc}") from exc


@app.get("/api/categories")
def categories(limit: int = 8):
    """側欄分類與每類的代表問題，供前端點選分類後直接列出問題。"""
    try:
        return {"categories": faq_categories(max(1, min(limit, 20)))}
    except Exception as exc:
        logger.exception("讀取 FAQ 分類失敗")
        raise HTTPException(status_code=503, detail=f"無法讀取 FAQ 分類：{exc}") from exc


@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest):
    started = time.perf_counter()
    try:
        results = search_faq(embed_text(request.query), request.limit)
        logger.info("搜尋完成 query_length=%d results=%d duration_ms=%.1f", len(request.query), len(results), (time.perf_counter() - started) * 1000)
        return {"query": request.query, "results": results}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("搜尋失敗")
        raise HTTPException(status_code=503, detail=f"搜尋服務暫時無法使用：{exc}") from exc


@app.post("/api/ask", response_model=AnswerResponse)
def ask(request: SearchRequest):
    started = time.perf_counter()
    try:
        results = search_faq(embed_text(request.query), max(request.limit, 5))
        log_query(request.query, results)
        if not results:
            return {"query": request.query, "answer": "目前知識庫沒有足夠資訊，建議洽詢系辦公室確認。", "results": [], "generated": False, "model": "", "notice": "未找到相關 FAQ", "followups": [], "steps": []}
        try:
            answer = answer_from_faq(request.query, results[:5])
            generated, notice = True, ""
        except Exception as llm_exc:
            logger.warning("地端模型回答失敗，改用 FAQ 原文：%s", llm_exc)
            answer = results[0].get("answer", "目前無法產生回答。")
            generated, notice = False, "地端模型暫時無法使用，已顯示最相關的 FAQ 原文。"
        logger.info("問答完成 query_length=%d generated=%s duration_ms=%.1f", len(request.query), generated, (time.perf_counter() - started) * 1000)
        followups = []
        for item in results[1:]:
            question = str(item.get("question", "")).strip()
            if question and question != request.query and question not in followups:
                followups.append(question)
            if len(followups) == 3:
                break
        steps = [part.strip(" -•\t") for part in answer.splitlines() if part.strip()]
        if len(steps) < 2:
            steps = []
        return {"query": request.query, "answer": answer, "results": results[:3], "generated": generated, "model": "", "notice": notice, "followups": followups, "steps": steps[:6]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("問答失敗")
        raise HTTPException(status_code=503, detail=f"問答服務暫時無法使用：{exc}") from exc


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest):
    log_feedback(request.query.strip(), request.source_question.strip(), request.helpful)
    return {"saved": True}


def _notify_ticket(ticket: dict) -> None:
    sent, detail = send_ticket_email(ticket)
    record_ticket_email(ticket["ticket_no"], sent, detail)


def _notify_student_resolution(ticket: dict) -> None:
    sent, detail = send_student_resolution_email(ticket)
    record_student_email(ticket["ticket_no"], sent, detail)


def _sync_ticket_knowledge(ticket: dict) -> None:
    try:
        record = sync_resolved_ticket(ticket)
        record_knowledge_sync(ticket["ticket_no"], True, record["id"])
    except Exception as exc:
        logger.exception("工單寫入知識庫失敗 ticket=%s", ticket.get("ticket_no"))
        record_knowledge_sync(ticket["ticket_no"], False, f"{type(exc).__name__}: {exc}")


@app.get("/api/mail/status")
@app.get("/api/admin/mail/settings")
def email_status(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return mail_status()


@app.put("/api/admin/mail/settings")
def email_settings_save(request: MailSettingsRequest, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    data = request.model_dump()
    password = data.pop("password", "")
    offices = data.pop("offices", {})
    recipients = []
    for email in data.get("student_recipients", []):
        email = email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise HTTPException(status_code=422, detail=f"學生通知信箱格式不正確：{email or '空白'}")
        if email not in recipients:
            recipients.append(email)
    data["student_recipients"] = recipients or [mail_status()["default_email"]]
    save_settings(data)
    if password.strip():
        save_password(password)
    if offices:
        save_office_emails(offices)
    logger.info("更新工單通知信箱設定 offices=%d", len(offices))
    return mail_status()


@app.post("/api/admin/mail/test")
def email_test(request: MailTestRequest, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    sent, detail = send_test_email(request.to)
    if not sent:
        raise HTTPException(status_code=502, detail=f"測試信寄送失敗：{detail}")
    return {"sent": True, "to": detail}


@app.post("/api/admin/tickets/{ticket_no}/resend-mail")
def ticket_resend_mail(ticket_no: str, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    ticket = ticket_detail(ticket_no)
    if not ticket:
        raise HTTPException(status_code=404, detail="找不到工單")
    sent, detail = send_ticket_email(ticket)
    record_ticket_email(ticket_no, sent, detail)
    if not sent:
        raise HTTPException(status_code=502, detail=f"通知信寄送失敗：{detail}")
    return {"sent": True, "to": detail}


@app.post("/api/tickets", status_code=201)
def ticket_create(request: TicketCreateRequest, background_tasks: BackgroundTasks):
    data = request.model_dump()
    if not data["office"]:
        data["office"] = route_ticket_office(data["query"], data["description"])
    ticket = create_ticket(data)
    background_tasks.add_task(_notify_ticket, ticket)
    return ticket


@app.get("/api/tickets/{ticket_no}")
def ticket_public_get(ticket_no: str, key: str):
    ticket = public_ticket(ticket_no, key)
    if not ticket: raise HTTPException(status_code=404, detail="找不到工單或存取碼不正確")
    return ticket


@app.post("/api/tickets/{ticket_no}/replies")
def ticket_public_reply(ticket_no: str, request: TicketReplyRequest):
    ticket = add_ticket_reply(ticket_no, request.access_key, request.message, request.allow_faq)
    if not ticket: raise HTTPException(status_code=404, detail="找不到工單或存取碼不正確")
    return ticket


@app.post("/api/tickets/{ticket_no}/rating")
def ticket_public_rate(ticket_no: str, request: TicketRateRequest):
    try:
        ticket = rate_ticket(ticket_no, request.access_key, request.rating, request.comment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not ticket: raise HTTPException(status_code=404, detail="找不到工單或存取碼不正確")
    logger.info("提問單評分 ticket=%s rating=%d", ticket_no, request.rating)
    return ticket


@app.get("/api/admin/tickets")
def tickets_get(status: str = "", office: str = "", x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return {"tickets": list_tickets(status, office)}


@app.get("/api/office/tickets")
def office_tickets(status: str = "", x_office_token: str = Header(default="")):
    office = require_office(x_office_token)
    return {"office": office, "tickets": list_tickets(status, office)}


@app.get("/api/office/mail")
def office_mail_get(x_office_token: str = Header(default="")):
    office = require_office(x_office_token)
    info = mail_status()
    return {"office": office, "email": info["offices"].get(office, info["default_email"]),
            "default_email": info["default_email"], "mail_enabled": info["configured"]}


@app.put("/api/office/mail")
def office_mail_save(request: OfficeMailRequest, x_office_token: str = Header(default="")):
    office = require_office(x_office_token)
    email = request.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="請輸入有效的電子郵件地址")
    save_office_emails({office: email})
    logger.info("處室自行更新工單通知信箱 office=%s", office)
    return {"saved": True, "office": office, "email": email}


@app.get("/api/office/tickets/{ticket_no}")
def office_ticket_get(ticket_no: str, x_office_token: str = Header(default="")):
    office = require_office(x_office_token)
    rows = [x for x in list_tickets(office=office) if x["ticket_no"] == ticket_no]
    if not rows: raise HTTPException(status_code=404, detail="找不到分派給本處室的工單")
    return ticket_detail(ticket_no)


@app.patch("/api/office/tickets/{ticket_no}")
def office_ticket_update(ticket_no: str, request: TicketUpdateRequest, background_tasks: BackgroundTasks,
                         x_office_token: str = Header(default="")):
    office = require_office(x_office_token)
    rows = [x for x in list_tickets(office=office) if x["ticket_no"] == ticket_no]
    if not rows: raise HTTPException(status_code=404, detail="找不到分派給本處室的工單")
    previous_office = rows[0]["office"]
    data = request.model_dump()
    ticket = update_ticket(ticket_no, data)
    if ticket and ticket["office"] != previous_office:
        background_tasks.add_task(_notify_ticket, ticket)
    if ticket and ticket["status"] == "已解決" and rows[0]["status"] != "已解決":
        background_tasks.add_task(_notify_student_resolution, ticket)
        background_tasks.add_task(_sync_ticket_knowledge, ticket)
    return ticket


@app.patch("/api/admin/tickets/{ticket_no}")
def ticket_update(ticket_no: str, request: TicketUpdateRequest, background_tasks: BackgroundTasks,
                  x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    previous = ticket_detail(ticket_no)
    ticket = update_ticket(ticket_no, request.model_dump())
    if not ticket:
        raise HTTPException(status_code=404, detail="找不到工單")
    if previous and ticket["office"] != previous["office"]:
        background_tasks.add_task(_notify_ticket, ticket)
    if previous and ticket["status"] == "已解決" and previous["status"] != "已解決":
        background_tasks.add_task(_notify_student_resolution, ticket)
        background_tasks.add_task(_sync_ticket_knowledge, ticket)
    return ticket


@app.post("/api/admin/knowledge/sync-resolved")
def knowledge_sync_resolved(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    saved, failed = [], []
    for summary in list_tickets(status="已解決"):
        ticket = ticket_detail(summary["ticket_no"])
        try:
            record = sync_resolved_ticket(ticket)
            record_knowledge_sync(ticket["ticket_no"], True, record["id"])
            saved.append(ticket["ticket_no"])
        except Exception as exc:
            record_knowledge_sync(ticket["ticket_no"], False, f"{type(exc).__name__}: {exc}")
            failed.append({"ticket_no": ticket["ticket_no"], "error": str(exc)})
    return {"saved": saved, "failed": failed}


@app.get("/api/admin/tickets.csv")
def tickets_csv(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    rows = list_tickets()
    output = io.StringIO()
    fields = ["ticket_no","status","office","category","subject","description","requester_name","requester_contact","assignee","resolution","rating","rating_comment","rated_at","created_at","updated_at","resolved_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    data = "\ufeff" + output.getvalue()
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=tickets.csv"})


@app.get("/api/admin/stats")
def admin_stats(days: int = 7, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return stats(days)
