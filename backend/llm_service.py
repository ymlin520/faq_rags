import os

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OFFICES = ["教務處註冊組", "教務處課務組", "學務處生活輔導組", "學務處住宿服務組", "國際處", "總務處", "資訊處", "圖資處", "系辦公室", "其他行政單位"]


def _fallback_office(text: str) -> str:
    rules = [
        ("學務處住宿服務組", ["宿舍", "住宿", "床位", "退宿"]),
        ("教務處註冊組", ["學籍", "成績", "畢業證書", "休學", "復學", "轉學", "註冊", "抵免"]),
        ("教務處課務組", ["選課", "課程", "學分", "加退選", "停修", "教室", "排課"]),
        ("學務處生活輔導組", ["獎學金", "助學金", "請假", "兵役", "操行", "急難", "學生申訴"]),
        ("國際處", ["交換", "海外", "外籍", "國際學生", "留學"]),
        ("資訊處", ["帳號", "密碼", "系統", "網路", "wifi", "登入", "校務系統"]),
        ("圖資處", ["圖書館", "借書", "電子資源", "資料庫", "閱覽"]),
        ("總務處", ["停車", "場地", "修繕", "繳費", "收據", "門禁"]),
        ("系辦公室", ["實習", "系所", "專題", "導師", "系辦"]),
    ]
    lowered = text.lower()
    for office, words in rules:
        if any(word.lower() in lowered for word in words): return office
    return "其他行政單位"


def route_ticket_office(query: str, description: str = "") -> str:
    text = f"{query}\n{description}".strip()
    keyword_choice = _fallback_office(text)
    if keyword_choice != "其他行政單位":
        return keyword_choice
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "stream": False, "messages": [
                {"role": "system", "content": "你是校務需求單分流器。只能從指定處室名稱中選一個，僅輸出處室名稱，不要解釋。"},
                {"role": "user", "content": f"處室：{'、'.join(OFFICES)}\n問題：{text}"}],
                "options": {"temperature": 0, "num_predict": 30}, "keep_alive": "10m"}, timeout=30)
        response.raise_for_status()
        choice = response.json().get("message", {}).get("content", "").strip()
        for office in OFFICES:
            if office in choice: return office
    except (requests.RequestException, ValueError):
        pass
    return keyword_choice


def ollama_status() -> dict[str, str | bool]:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
        available = OLLAMA_MODEL in names or any(name.startswith(f"{OLLAMA_MODEL}:") for name in names)
        return {"connected": True, "model": OLLAMA_MODEL, "available": available}
    except requests.RequestException:
        return {"connected": False, "model": OLLAMA_MODEL, "available": False}


def answer_from_faq(query: str, results: list[dict]) -> str:
    context_blocks = []
    for index, item in enumerate(results, start=1):
        context_blocks.append(
            f"[來源 {index}]\n分類：{item.get('category', '一般問題')}\n"
            f"問題：{item.get('question', '')}\n答案：{item.get('answer', '')}\n"
            f"網址：{item.get('url', '') or '無'}"
        )
    context = "\n\n".join(context_blocks)
    system = (
        "你是系辦公室 FAQ 助理。請使用繁體中文，以親切、清楚、自然的語氣回答。"
        "只能根據提供的 FAQ 內容作答，不得加入常識推測、虛構規定、日期、流程或聯絡方式。"
        "若資料不足，請明確說『目前知識庫沒有足夠資訊，建議洽詢系辦公室確認』。"
        "整合重複內容，保留重要條件與例外；回答控制在 2 到 5 個短段落。"
        "不要聲稱自己看過未提供的文件。只輸出可以直接呈現給使用者的最終答案，"
        "不要描述你的任務、分析步驟、來源篩選過程或思考過程。"
    )
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"使用者問題：{query}\n\n可用 FAQ：\n{context}\n\n請直接輸出最終回答。"},
            ],
            "options": {"temperature": 0.1, "num_predict": 300},
            "keep_alive": "10m",
        },
        timeout=180,
    )
    response.raise_for_status()
    answer = response.json().get("message", {}).get("content", "").strip()
    if not answer:
        raise RuntimeError("地端模型未回傳回答")
    return answer
