import os


# Asosiy sozlamalar: barcha maxfiy ma'lumotlar environment orqali beriladi.

# Telegram bot tokeni (Railway/GitHub secrets, lokal muhitda ham env orqali beriladi)
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Admin Telegram ID (butun son sifatida), masalan: 7718149728
_admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID", "0").strip() or "0"
try:
    ADMIN_TELEGRAM_ID: int = int(_admin_id_raw)
except ValueError:
    ADMIN_TELEGRAM_ID = 0

# Kanal majburiy obuna uchun ID yoki @username, masalan: "@asralashm" yoki "-100..."
REQUIRED_CHANNEL_ID: str = os.getenv("REQUIRED_CHANNEL_ID", "@asralashm")

# AI rejimi: "stub" yoki "groq" (default: groq)
AI_MODE: str = os.getenv("AI_MODE", "groq")

# Mahalliy SQLite bazasi yo'li
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "database.db")

# Groq API sozlamalari (OpenAI chat/completions formatida)
GROQ_API_BASE: str = os.getenv(
    "GROQ_API_BASE", "https://api.groq.com/openai/v1/chat/completions"
)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
