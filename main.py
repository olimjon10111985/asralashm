import asyncio
import logging

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

import config
from bot import post_init, main as local_main

logger = logging.getLogger(__name__)

app = FastAPI()

telegram_app: Application | None = None


async def build_application() -> Application:
    if not getattr(config, "TELEGRAM_BOT_TOKEN", None):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN config.py ichida o'rnatilmagan."
        )

    application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
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


# Lokal test uchun: agar bu faylni bevosita ishga tushirsak, eski polling rejimidan foydalanamiz.
if __name__ == "__main__":
    local_main()
