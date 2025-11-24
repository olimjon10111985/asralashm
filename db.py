import aiosqlite
from typing import Optional, List, Dict, Any

from rag_client import chroma_upsert

DB_PATH = "database.db"


async def init_db(db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                name TEXT NOT NULL,
                surname TEXT NOT NULL,
                nick TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                text TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        await db.commit()


async def create_user(telegram_id: int, name: str, surname: str, nick: str, password_hash: str, db_path: str = DB_PATH) -> bool:
    # Nickni bazaga har doim kichik harflarda saqlaymiz
    norm_nick = nick.lower()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO users (telegram_id, name, surname, nick, password_hash) VALUES (?, ?, ?, ?, ?)",
                (telegram_id, name, surname, norm_nick, password_hash),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def get_user_by_nick(nick: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Nick bo'yicha userni topadi (case-insensitive)."""
    norm_nick = nick.lower()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE LOWER(nick) = ?", (norm_nick,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def count_today_entries(db_path: str = DB_PATH) -> int:
    """Bugungi kunda yozilgan jami yozuvlar soni (entries)."""
    async with aiosqlite.connect(db_path) as db:
        # SQLite-da CURRENT_DATE UTC bo'yicha, lekin biz created_at DEFAULT CURRENT_TIMESTAMP dan foydalanamiz.
        # Oddiylik uchun sananing YYYY-MM-DD qismiga qaraymiz.
        async with db.execute(
            "SELECT COUNT(*) FROM entries WHERE DATE(created_at) = DATE('now')"
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0


async def count_today_active_users(db_path: str = DB_PATH) -> int:
    """Bugun kamida bitta yozuv qoldirgan noyob foydalanuvchilar soni."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM entries WHERE DATE(created_at) = DATE('now')"
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0


async def get_user_by_id(user_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_entry(user_id: int, text: str, db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO entries (user_id, text) VALUES (?, ?)",
            (user_id, text),
        )
        await db.commit()

        # Chroma servisiga ham yuborib qo'yamiz (agar CHROMA_BASE_URL sozlangan bo'lsa)
        try:
            entry_id = cursor.lastrowid
        except Exception:
            entry_id = None

    # DB tranzaksiyasi tugagandan so'ng, Chroma'ga async tarzda sync qilamiz
    if text.strip():
        doc_id = f"user_{user_id}_{entry_id or 'unknown'}"
        await chroma_upsert(
            [
                {
                    "id": doc_id,
                    "user_id": user_id,
                    "text": text,
                    "created_at": None,
                }
            ]
        )


async def get_entries_for_user(user_id: int, limit: Optional[int] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Berilgan foydalanuvchining kundalik yozuvlarini qaytaradi.

    Hozircha LIMIT ishlatilmayapti, barcha yozuvlar olinadi.
    Agar keyin yana oxirgi 100 ta bilan cheklamoqchi bo'lsak, so'rovni
    `... ORDER BY created_at DESC LIMIT 100` shakliga qaytarish mumkin.
    """

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM entries WHERE user_id = ? ORDER BY created_at DESC"
        params: tuple[Any, ...] = (user_id,)
        # Agar kerak bo'lsa, limit parametri qayta yoqilishi mumkin:
        # if limit is not None:
        #     query += " LIMIT ?"
        #     params = (user_id, limit)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def search_users_by_name_or_nick(query: str, limit: int = 10, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Ism, familiya yoki nik bo'yicha qidirish (case-insensitive)."""
    norm = query.lower()
    like = f"%{norm}%"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(name) LIKE ? OR LOWER(surname) LIKE ? OR LOWER(nick) LIKE ? LIMIT ?",
            (like, like, like, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_entries_for_user(user_id: int, db_path: str = DB_PATH) -> None:
    """Berilgan foydalanuvchiga tegishli barcha kundalik yozuvlarini o'chiradi."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM entries WHERE user_id = ?", (user_id,))
        await db.commit()


async def delete_user_by_id(user_id: int, db_path: str = DB_PATH) -> None:
    """Foydalanuvchini va uning barcha yozuvlarini o'chiradi."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM entries WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()


async def count_users(db_path: str = DB_PATH) -> int:
    """Jami foydalanuvchilar sonini qaytaradi."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0


async def count_entries(db_path: str = DB_PATH) -> int:
    """Jami kundalik yozuvlari (entries) sonini qaytaradi."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM entries") as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0


async def get_last_entry_time(db_path: str = DB_PATH) -> Optional[str]:
    """Oxirgi yozuv yaratilgan vaqtni (TEXT ko'rinishida) qaytaradi."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT MAX(created_at) FROM entries") as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else None


async def get_avg_entries_per_user(db_path: str = DB_PATH) -> float:
    """Bitta foydalanuvchiga o'rtacha to'g'ri keladigan yozuvlar soni."""
    users = await count_users(db_path=db_path)
    entries = await count_entries(db_path=db_path)
    if users == 0:
        return 0.0
    return entries / users


async def get_last_user(db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Oxirgi ro'yxatdan o'tgan foydalanuvchini (id bo'yicha) qaytaradi."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_top_writer(db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Eng ko'p yozuv qoldirgan foydalanuvchini va uning yozuvlar sonini qaytaradi."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT u.*, COUNT(e.id) AS entry_count
            FROM users u
            LEFT JOIN entries e ON e.user_id = u.id
            GROUP BY u.id
            ORDER BY entry_count DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
