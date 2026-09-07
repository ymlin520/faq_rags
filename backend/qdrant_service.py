import uuid
from datetime import datetime
from collections.abc import Iterable
from typing import Any

from qdrant_client import QdrantClient, models

from .config import COLLECTION_NAME, PROJECT_ROOT, SCORE_THRESHOLD, VECTOR_SIZE

_CLIENT: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _CLIENT
    if _CLIENT is None:
        local_path = PROJECT_ROOT / "data" / "qdrant-local"
        local_path.mkdir(parents=True, exist_ok=True)
        _CLIENT = QdrantClient(path=str(local_path))
    return _CLIENT


def close_client() -> None:
    global _CLIENT
    if _CLIENT is not None:
        _CLIENT.close()
        _CLIENT = None


def check_connection() -> bool:
    get_client().get_collections()
    return True


def create_collection_if_needed() -> None:
    client = get_client()
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )


def recreate_collection() -> None:
    client = get_client()
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
    )


def point_id(raw_id: Any) -> int | str:
    value = str(raw_id).strip()
    try:
        return int(value)
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vector-faq:{value}"))


def upsert_faqs(records: Iterable[dict[str, Any]], vectors: list[list[float]]) -> None:
    rows = list(records)
    if len(rows) != len(vectors):
        raise ValueError("FAQ 筆數與向量筆數不一致")
    points = [
        models.PointStruct(id=point_id(row["id"]), vector=vector, payload=row)
        for row, vector in zip(rows, vectors, strict=True)
    ]
    if points:
        get_client().upsert(collection_name=COLLECTION_NAME, points=points, wait=True)


def delete_faqs(ids: Iterable[Any]) -> None:
    points = [point_id(raw_id) for raw_id in ids]
    if points:
        get_client().delete(collection_name=COLLECTION_NAME,
                            points_selector=models.PointIdsList(points=points), wait=True)


def search_faq(vector: list[float], limit: int) -> list[dict[str, Any]]:
    response = get_client().query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit,
        score_threshold=SCORE_THRESHOLD,
        with_payload=True,
    )
    fallback_date = datetime.fromtimestamp(__file_mtime()).strftime("%Y-%m-%d")
    results = []
    for item in response.points:
        payload = dict(item.payload or {})
        payload["updated_at"] = str(payload.get("updated_at") or payload.get("updated") or fallback_date)
        results.append({"score": float(item.score), **payload})
    return results


def __file_mtime() -> float:
    from .config import PROJECT_ROOT
    candidates = [PROJECT_ROOT / "data" / "faq_import.csv", PROJECT_ROOT.parent / "vector-faq" / "data" / "faq_import.csv"]
    existing = [path.stat().st_mtime for path in candidates if path.exists()]
    return max(existing) if existing else 0


def collection_info() -> Any:
    return get_client().get_collection(COLLECTION_NAME)
