import asyncio
import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from telegram import Update
from telegram.ext import Application

import config
from bot import build_application as build_bot_application, main as local_main

logger = logging.getLogger(__name__)

app = FastAPI()

telegram_app: Application | None = None


async def build_application() -> Application:
    """Webhook rejimi uchun Application ni bot.py dagi build_application yordamida yaratadi.

    Shu tariqa lokal polling va webhook rejimlari bir xil handlerlar to'plamidan
    foydalanadi.
    """

    if not getattr(config, "TELEGRAM_BOT_TOKEN", None):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN config.py ichida o'rnatilmagan."
        )

    application = build_bot_application(config.TELEGRAM_BOT_TOKEN)
    await application.initialize()
    await application.start()
    return application


@app.on_event("startup")
async def on_startup() -> None:
    global telegram_app
    telegram_app = await build_application()
    logger.info("Telegram application started inside FastAPI (Deta Space mode)")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global telegram_app
    if telegram_app is not None:
        await telegram_app.stop()
        await telegram_app.shutdown()
        telegram_app = None


@app.post("/")
async def telegram_webhook(request: Request):
    """Asosiy webhook endpoint. Telegram barcha update'larni shu yerga yuboradi."""
    global telegram_app
    if telegram_app is None:
        # Agar nimadir sababli app hali ishga tushmagan bo'lsa
        telegram_app = await build_application()

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


@app.get("/download-db")
async def download_db():
    """SQLite bazasini fayl sifatida yuklab beruvchi endpoint.

    Eslatma: Bu endpointni faqat vaqtincha backup olish uchun ishlating va
    keyinchalik xavfsizlik uchun olib tashlang yoki cheklang.
    """

    db_path = config.DATABASE_PATH

    # Agar asosiy yo'l bo'yicha fayl topilmasa, eski nisbiy yo'lni ham tekshirib ko'ramiz.
    if not os.path.exists(db_path):
        fallback_path = "database.db"
        if os.path.exists(fallback_path):
            db_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail="Database file not found")

    return FileResponse(
        path=db_path,
        filename="database.db",
        media_type="application/octet-stream",
    )


# Lokal test uchun: agar bu faylni bevosita ishga tushirsak, eski polling rejimidan foydalanamiz.
if __name__ == "__main__":
    local_main()
