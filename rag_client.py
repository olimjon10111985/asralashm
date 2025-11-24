import os
from typing import List, Dict, Any

import httpx

CHROMA_BASE_URL = os.getenv("CHROMA_BASE_URL", "").rstrip("/")


async def chroma_upsert(entries: List[Dict[str, Any]]) -> None:
    """Chroma servisiga yozuvlar ro'yxatini yuboradi.

    entries elementlari: {"id": str, "user_id": int, "text": str, "created_at": str | None}
    """
    if not CHROMA_BASE_URL or not entries:
        return

    url = f"{CHROMA_BASE_URL}/upsert_entries"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await client.post(url, json={"entries": entries})
        except Exception:
            # Chroma bo'lmasa yoki xato bo'lsa, asosiy logika buzilmasligi uchun jim o'tkazib yuboramiz
            return


async def chroma_query(user_id: int, question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Chroma servisidan berilgan foydalanuvchi va savol uchun eng mos bo'laklarni so'raydi."""
    if not CHROMA_BASE_URL or not question.strip():
        return []

    url = f"{CHROMA_BASE_URL}/query"
    payload = {"user_id": user_id, "question": question, "top_k": top_k}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

    hits = data.get("hits") or []
    # Har bir hit: {"text": str, "metadata": {...}}
    return hits
