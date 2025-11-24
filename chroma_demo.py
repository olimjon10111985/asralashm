import os
import sqlite3

from typing import List, Tuple

# Bu demo uchun: `pip install chromadb` kerak bo'ladi.
try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    raise SystemExit("chromadb o'rnatilmagan. Avval: pip install chromadb deb o'rnating.")


def load_entries(db_path: str) -> List[Tuple[int, str, str, int]]:
    """SQLite DB dan foydalanuvchi yozuvlarini yuklaydi.

    Qaytaradi: (id, content, created_at, user_id)
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB topilmadi: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # entries jadvali: id, user_id, text, created_at (db.py dagi sxemaga mos)
    cur.execute(
        """
        SELECT id, user_id, text, created_at
        FROM entries
        WHERE text IS NOT NULL AND TRIM(text) != ''
        ORDER BY created_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    return [
        (
            row["id"],
            str(row["text"]),
            str(row["created_at"] or ""),
            int(row["user_id"]),
        )
        for row in rows
    ]


def build_chroma_collection(entries: List[Tuple[int, str, str, int]]):
    """Chroma in-memory collection yaratadi va barcha yozuvlarni yuklaydi."""
    client = chromadb.Client()  # default in-memory client

    collection = client.get_or_create_collection(name="diary_entries")

    if not entries:
        print("Hech qanday yozuv topilmadi.")
        return collection

    ids: List[str] = []
    texts: List[str] = []
    metadatas: List[dict] = []

    for entry_id, content, created_at, user_id in entries:
        ids.append(str(entry_id))
        # Kichik format: [sana][user] content
        prefix = f"[{created_at[:10]}][user:{user_id}] " if created_at else f"[user:{user_id}] "
        texts.append(prefix + content.strip())
        metadatas.append({
            "user_id": str(user_id),
            "created_at": created_at,
        })

    # Kichik partiyalarga bo'lib qo'shamiz, chunki juda katta ro'yxat bo'lishi mumkin
    batch_size = 256
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_texts = texts[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        collection.add(ids=batch_ids, documents=batch_texts, metadatas=batch_meta)

    print(f"Chroma collection ga jami {len(ids)} ta yozuv qo'shildi.")
    return collection


def chroma_query_loop(collection):
    """Terminalda savol berib, eng mos bo'laklarni chiqarish."""
    print("\nChroma RAG DEMO: savol kiriting (chiqish uchun bo'sh enter)")

    while True:
        query = input("\nSavolingiz: ").strip()
        if not query:
            print("Chiqildi.")
            break

        # Eng mos 5 ta bo'lakni so'raymiz
        result = collection.query(query_texts=[query], n_results=5)

        docs = result.get("documents") or []
        metadatas = result.get("metadatas") or []

        if not docs or not docs[0]:
            print("Hech narsa topilmadi.")
            continue

        print("\nEng mos bo'laklar:")
        for idx, (doc, meta) in enumerate(zip(docs[0], metadatas[0]), start=1):
            print(f"\n[{idx}]")
            print(doc)
            if meta:
                print("meta:", meta)


def main():
    # DATABASE_PATH ni mavjud config.py dan olishga harakat qilamiz
    db_path = os.getenv("DATABASE_PATH") or "database.db"
    print(f"SQLite DB: {db_path}")

    entries = load_entries(db_path)
    print(f"Jami {len(entries)} ta kundalik yozuvi topildi.")

    collection = build_chroma_collection(entries)
    chroma_query_loop(collection)


if __name__ == "__main__":
    main()
