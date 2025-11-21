import asyncio
import logging
from typing import Dict, Any, Optional

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

from db import (
    init_db,
    create_user,
    get_user_by_nick,
    get_user_by_id,
    add_entry,
    get_entries_for_user,
    search_users_by_name_or_nick,
    delete_user_by_id,
    count_users,
    count_entries,
    get_last_entry_time,
    get_avg_entries_per_user,
    get_last_user,
    get_top_writer,
    count_today_entries,
    count_today_active_users,
)
from ai_service import generate_reply_stub

try:
    import config  # type: ignore
except ImportError:
    config = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Admin uchun Telegram ID (config faylidan olinadi)
# Iltimos config.py ichida: ADMIN_TELEGRAM_ID = 7718149728 kabi o'rnating
ADMIN_ID = getattr(config, "ADMIN_TELEGRAM_ID", None) if config is not None else None

# Conversation states
(
    MAIN_MENU,
    REG_NAME,
    REG_SURNAME,
    REG_NICK,
    REG_PASSWORD,
    LOGIN_NICK,
    LOGIN_PASSWORD,
    PROFILE_MENU,
    PROFILE_ADD_ENTRY,
    SEARCH_QUERY,
    CHAT_WITH_PROFILE,
    DELETE_ACCOUNT_PASSWORD,
) = range(12)


def is_back_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"ortga", "⬅️ ortga", "⬅️< ortga >"}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🧠< Sun'iy ong odamlarini qidirish >")],
        [
            KeyboardButton("/start"),
            KeyboardButton("🆕< Hisob yaratish >"),
            KeyboardButton("🔐< Hisobga kirish >"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def chat_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("/start"), KeyboardButton("⬅️< Ortga >")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def profile_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📝< Yangi ma'lumot yozish >")],
        [KeyboardButton("🗑< Hisobni o'chirish >")],
        [KeyboardButton("/start")],
        [KeyboardButton("⬅️< Ortga >")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def back_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("/start"), KeyboardButton("⬅️< Ortga >")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def reg_start_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🆕< Hisobim yo'q >")],
        [KeyboardButton("/start"), KeyboardButton("⬅️< Ortga >")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def ensure_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi kanalga obuna bo'lganmi-yo'qligini tekshiradi.

    config.REQUIRED_CHANNEL_ID da ko'rsatilgan kanalga obuna bo'lmagan
    bo'lsa, obuna bo'lish uchun linkni yuboradi va False qaytaradi.
    """

    channel_id = getattr(config, "REQUIRED_CHANNEL_ID", None) if config is not None else None
    if not channel_id:
        # Kanal talabi o'rnatilmagan bo'lsa, hammani o'tkazamiz
        return True

    user = update.effective_user
    if not user:
        return False

    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user.id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception as e:
        logger.warning("Obuna tekshiruvda xato: %s", e)
        # Agar xatolik bo'lsa, foydalanuvchini to'sib qo'ymaslik uchun ruxsat beramiz
        return True

    # Obuna bo'lmagan foydalanuvchiga kanalga obuna bo'lishni so'raymiz
    channel_username = str(channel_id)
    join_link = f"https://t.me/{channel_username.lstrip('@')}"

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    inline_keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔔 Kanalga obuna bo'lish", url=join_link)],
        ]
    )

    # Foydalanuvchiga ko'rinadigan /start tugmasi bo'lsin
    start_keyboard = ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)

    if update.message:
        await update.message.reply_text(
            "Botdan foydalanish uchun avval kanalimizga obuna bo'ling:\n\n"
            f"Kanal: {join_link}\n\n"
            "Obuna bo'lgach, pastdagi /start tugmasini bosib davom eting.",
            reply_markup=start_keyboard,
        )
        # Inline tugmani alohida xabar sifatida yuboramiz
        await update.message.reply_text(
            "Quyidagi tugma orqali ham kanalga o'tishingiz mumkin:",
            reply_markup=inline_keyboard,
        )

    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Avval kanalga obuna bo'lganini tekshiramiz
    if not await ensure_subscribed(update, context):
        # Obuna bo'lmasa, asosiy menyu holatida qolamiz, lekin menyuni ko'rsatmaymiz
        return MAIN_MENU

    user = update.effective_user
    await update.message.reply_text(
        f"Salom, {user.first_name}! Bu bot sizning ongingizni raqamlash va shaxsiy sunʼiy ong yaratish uchun.\n" \
        "Miyangizda bor fikrlar, xotiralar va tasavvurlaringizni yozing – shular asosida sizga o‘xshash raqamli ong shakllanadi.\n" \
        "Quyidagi tugmalardan birini tanlab boshlang:",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Bu bot inson ongini raqamlash g‘oyasiga xizmat qiladi. Siz bu yerda o‘zingiz haqingizda fikrlaringizni, "
        "xotiralar, rejalar va hayotga qarashlaringizni matn ko‘rinishida yozib borasiz. Bu yozuvlar oddiy kundalik "
        "emas — ular sizning shaxsiy sunʼiy ongingiz uchun xomashyo hisoblanadi.\n\n"
        "Vaqt o‘tib, boshqa odamlar sizning nickingizni topib, savollar berishi mumkin. AI esa aynan shu yerda "
        "qoldirgan matnlaringizga tayanib, sizning ovozingizda javob berishga harakat qiladi: siz qanday o‘ylagan "
        "bo‘lsangiz, shunga yaqin ohangda. Maqsad — bugungi ongingizni raqamli xotira sifatida kelajak avlodlar va "
        "yaqinlaringiz uchun saqlab qolish."
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Faqat admin uchun statistik ma'lumotlar."""
    user = update.effective_user
    user_id = user.id if user else None

    # Admin ID sozlanmagan bo'lsa
    if not ADMIN_ID:
        await update.message.reply_text(
            "Admin ID sozlanmagan. Iltimos config.py ichida ADMIN_TELEGRAM_ID ni o'rnating.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Faqat bitta aniq admin uchun ruxsat beramiz
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "Bu buyruq faqat admin uchun.", reply_markup=main_menu_keyboard()
        )
        return

    total_users = await count_users()
    total_entries = await count_entries()
    last_entry_time = await get_last_entry_time()
    avg_entries = await get_avg_entries_per_user()

    last_user = await get_last_user()
    top_writer = await get_top_writer()

    today_entries = await count_today_entries()
    today_active_users = await count_today_active_users()

    # Vaqt bo'sh bo'lsa, foydalanuvchi hali yozuv kiritmagan bo'lishi mumkin
    last_entry_text = last_entry_time if last_entry_time else "hali yozuvlar yo'q"

    last_user_text = "yo'q"
    if last_user is not None:
        last_user_text = f"*{last_user['nick']}* ({last_user['name']} {last_user['surname']})"

    top_writer_text = "yo'q"
    if top_writer is not None:
        count = top_writer.get("entry_count", 0)
        top_writer_text = f"*{top_writer['nick']}* ({top_writer['name']} {top_writer['surname']}) — {count} ta yozuv"

    text = (
        "📊 Statistika:\n"
        f"- Foydalanuvchilar soni: {total_users}\n"
        f"- Kundalik yozuvlari soni: {total_entries}\n"
        f"- Oxirgi yozuv vaqti: {last_entry_text}\n"
        f"- O'rtacha yozuvlar soni / foydalanuvchi: {avg_entries:.1f}\n"
        f"- Bugungi yozuvlar soni: {today_entries}\n"
        f"- Bugun faol bo'lgan foydalanuvchilar: {today_active_users}\n"
        f"- Oxirgi qo'shilgan foydalanuvchi: {last_user_text}\n"
        f"- Eng ko'p yozgan foydalanuvchi: {top_writer_text}"
    )

    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text_raw = (update.message.text or "").strip()
    text = text_raw.lower()

    # Har safar asosiy menyuga kelganda obunani tekshiramiz
    if not await ensure_subscribed(update, context):
        return MAIN_MENU

    if is_back_command(text):
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    if text == "🆕< hisobim yo'q >" or text == "hisobim yo'q":
        await update.message.reply_text(
            "Ismingizni kiriting:", reply_markup=back_keyboard()
        )
        return REG_NAME

    if text == "🆕< hisob yaratish >" or text == "hisob yaratish":
        await update.message.reply_text(
            "Agar ilgari hisob ochgan bo'lsangiz, qayta hisob yaratmang. Taxallus (nickname) va parolingiz bilan 'Hisobga kirish' tugmasi orqali kirishingiz mumkin.\n\nAgar hali hisobingiz bo'lmasa, 'Hisobim yo'q' tugmasini bosing.",
            reply_markup=reg_start_keyboard()
        )
        return MAIN_MENU
    if text == "🔐< hisobga kirish >" or text == "hisobga kirish":
        await update.message.reply_text(
            "Taxallus (nickname) kiriting:", reply_markup=back_keyboard()
        )
        return LOGIN_NICK
    # "🧠 Sun'iy ong odamlarini qidirish" tugmasi uchun
    if text == "🧠< sun'iy ong odamlarini qidirish >" or text == "sun'iy ong odamlarini qidirish":
        # Qidiruv rejimiga o'tganda asosiy menyu tugmalarini yashirib, faqat "Ortga" tugmasini ko'rsatamiz
        await update.message.reply_text(
            "Qidirish uchun ism, familiya yoki taxallus (nickname) kiriting:",
            reply_markup=back_keyboard(),
        )
        return SEARCH_QUERY

    await update.message.reply_text(
        "Iltimos menyudagi tugmalardan foydalaning.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


# --- Registration flow ---


async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if is_back_command(text):
        # Registratsiya boshlanishidan oldingi holat: asosiy menyuga qaytamiz
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    context.user_data["reg_name"] = text
    await update.message.reply_text(
        "Familiyangizni kiriting:", reply_markup=back_keyboard()
    )
    return REG_SURNAME


async def reg_surname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if is_back_command(text):
        # Bir qadam ortga: ism so'rash bosqichiga qaytamiz
        await update.message.reply_text(
            "Ismingizni kiriting:", reply_markup=back_keyboard()
        )
        return REG_NAME

    context.user_data["reg_surname"] = text
    await update.message.reply_text(
        "O'zingiz uchun yagona taxallus (nickname) tanlang:", reply_markup=back_keyboard()
    )
    return REG_NICK


async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Nickni darhol kichik harflarga o'tkazib saqlaymiz
    text = (update.message.text or "").strip()
    if is_back_command(text):
        # Bir qadam ortga: familiya so'rash bosqichiga qaytamiz
        await update.message.reply_text(
            "Familiyangizni kiriting:", reply_markup=back_keyboard()
        )
        return REG_SURNAME

    context.user_data["reg_nick"] = text.lower()
    await update.message.reply_text(
        "Parol kiriting (minimal 4 belgi):", reply_markup=back_keyboard()
    )
    return REG_PASSWORD


async def reg_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import bcrypt

    text = (update.message.text or "").strip()
    if "ortga" in text.lower():
        # Bir qadam ortga: taxallus so'rash bosqichiga qaytamiz
        await update.message.reply_text(
            "O'zingiz uchun yagona taxallus (nickname) tanlang:", reply_markup=back_keyboard()
        )
        return REG_NICK

    password = text
    if len(password) < 4:
        await update.message.reply_text("Parol juda qisqa, kamida 4 belgi bo'lsin. Qayta kiriting:")
        return REG_PASSWORD

    name = context.user_data.get("reg_name")
    surname = context.user_data.get("reg_surname")
    nick = context.user_data.get("reg_nick")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    created = await create_user(
        telegram_id=update.effective_user.id,
        name=name,
        surname=surname,
        nick=nick,
        password_hash=password_hash,
    )

    if not created:
        await update.message.reply_text(
            "Bu taxallus (nickname) allaqachon band. Iltimos boshqa taxallus tanlang.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    await update.message.reply_text(
        "Hisob muvaffaqiyatli yaratildi! Taxallus (nickname) va parolingizni eslab qoling. Endi hisobga kira olasiz. Hisobga kirish tugmasini bosing",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


# --- Login & profile ---


async def login_nick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Login paytida ham nickni kichik harflarga o'tkazamiz
    text = (update.message.text or "").strip()
    if "ortga" in text.lower():
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    context.user_data["login_nick"] = text.lower()
    await update.message.reply_text(
        "Parolingizni kiriting:", reply_markup=back_keyboard()
    )
    return LOGIN_PASSWORD


async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import bcrypt

    text = (update.message.text or "").strip()
    if "ortga" in text.lower():
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    nick = context.user_data.get("login_nick")
    password = text

    user = await get_user_by_nick(nick)
    if not user:
        await update.message.reply_text("Bunday nik topilmadi.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    stored_hash = user.get("password_hash", "")
    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        valid = False

    if not valid:
        await update.message.reply_text("Parol noto'g'ri.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    context.user_data["profile_user_id"] = user["id"]
    await update.message.reply_text(
        "Hisobga muvaffaqiyatli kirdingiz. Profil menyusidan tugmani tanlang:",
        reply_markup=profile_menu_keyboard(),
    )
    return PROFILE_MENU


async def delete_account_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import bcrypt

    text = (update.message.text or "").strip()
    if "ortga" in text.lower():
        # Bir qadam ortga: profil menyusiga qaytamiz
        await update.message.reply_text(
            "Profil menyusidan tanlang:", reply_markup=profile_menu_keyboard()
        )
        return PROFILE_MENU

    if "asosiy menyu" in text.lower():
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    user_id = context.user_data.get("profile_user_id")
    if not user_id:
        await update.message.reply_text(
            "Hisob topilmadi. /start ni bosib qayta urinib ko'ring.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    user = await get_user_by_id(user_id)
    if not user:
        await update.message.reply_text(
            "Hisob topilmadi.", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    stored_hash = user.get("password_hash", "")
    try:
        valid = bcrypt.checkpw(text.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        valid = False

    if not valid:
        await update.message.reply_text(
            "Parol noto'g'ri. Agar fikringiz o'zgargan bo'lsa, 'Ortga' tugmasini bosishingiz yoki /start ni bosib menyuga qaytishingiz mumkin.",
            reply_markup=back_keyboard(),
        )
        return DELETE_ACCOUNT_PASSWORD

    await delete_user_by_id(user_id)
    context.user_data.pop("profile_user_id", None)
    await update.message.reply_text(
        "Hisobingiz va barcha kundalik yozuvlaringiz o'chirildi.",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip().lower()

    if is_back_command(text):
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    if "yangi ma'lumot yozish" in text:
        await update.message.reply_text(
            "Endi o'zingiz haqingizda matn yozing: kundalik fikrlaringiz, xotiralaringiz, rejalar yoki hayotingizga oid istalgan gaplarni yozib qoldirishingiz mumkin.",
            reply_markup=chat_menu_keyboard(),
        )
        return PROFILE_ADD_ENTRY

    if "hisobni o'chirish" in text:
        await update.message.reply_text(
            "Hisobni va barcha yozuvlarni o'chirmoqchimisiz? Iltimos tasdiqlash uchun parolingizni kiriting.",
            reply_markup=back_keyboard(),
        )
        return DELETE_ACCOUNT_PASSWORD

    if text == "asosiy menyu":
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    await update.message.reply_text(
        "Iltimos profil menyusidagi tugmalardan foydalaning.",
        reply_markup=profile_menu_keyboard(),
    )
    return PROFILE_MENU


async def profile_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = context.user_data.get("profile_user_id")
    if not user_id:
        await update.message.reply_text(
            "Hisob topilmadi. /start ni bosib qayta urinib ko'ring.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    text = (update.message.text or "").strip()

    # Agar foydalanuvchi yozishni to'xtatib, ortga qaytmoqchi bo'lsa
    if is_back_command(text):
        # Bir qadam ortga: profil menyusiga qaytamiz
        await update.message.reply_text(
            "Profil menyusidan tanlang:", reply_markup=profile_menu_keyboard()
        )
        return PROFILE_MENU

    # To'g'ridan-to'g'ri asosiy menyuga qaytish
    if "asosiy menyu" in text.lower():
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    # Har bir yuborilgan matn alohida kundalik yozuvi sifatida saqlanadi
    await add_entry(user_id=user_id, text=text)
    await update.message.reply_text(
        "Yozuvingiz saqlandi. Yana yozishingiz mumkin yoki 'Ortga' tugmasini bosib menyuga qaytishingiz mumkin.",
        reply_markup=chat_menu_keyboard(),
    )
    # Holat o'sha PROFILE_ADD_ENTRY da qoladi, foydalanuvchi ketma-ket yozishi mumkin
    return PROFILE_ADD_ENTRY


# --- Search & chat ---


async def search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()

    # Agar foydalanuvchi qidiruv oynasida "Ortga" tugmasini bossa, asosiy menyuga qaytamiz
    if is_back_command(text):
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    query = text
    results = await search_users_by_name_or_nick(query)

    if not results:
        await update.message.reply_text(
            "Hech narsa topilmadi.", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    # Inline tugmalar bilan natijalarni chiqaramiz (avval taxallus, keyin ism-familiya)
    buttons = []
    for u in results:
        label = f"*{u['nick']}* ({u['name']} {u['surname']})"
        buttons.append(
            [
                InlineKeyboardButton(
                    label, callback_data=f"choose_profile:{u['id']}"
                )
            ]
        )

    await update.message.reply_text("Topilgan profillarni tanlang:")
    await update.message.reply_text(
        "Quyidagi tugmalardan birini tanlang — shu odamning sunʼiy ongi bilan gaplashasiz.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return SEARCH_QUERY


async def chat_with_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Profil tanlangan, endi har bir xabarni AI ga yuboramiz
    profile = context.user_data.get("chat_profile")
    if not profile:
        await update.message.reply_text(
            "Profil topilmadi. /start bilan qaytadan boshlang.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    entries = await get_entries_for_user(profile["id"], limit=100)
    user_message = (update.message.text or "").strip()

    lower_msg = user_message.lower()
    if lower_msg == "asosiy menyu" or is_back_command(user_message):
        await update.message.reply_text(
            "Asosiy menyu:", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

    reply = await generate_reply_stub(profile, entries, user_message)

    await update.message.reply_text(reply, reply_markup=chat_menu_keyboard())

    # Suhbatdan ham ozgina "xotira" sifatida foydalanish uchun savol+javobni ham saqlab qo'yamiz
    try:
        log_text = f"Suhbat: foydalanuvchi savoli: {user_message}\nMening javobim: {reply}"
        await add_entry(user_id=profile["id"], text=log_text)
    except Exception:
        # Agar yozib bo'lmasa, butun chatni to'xtatmaymiz
        pass
    return CHAT_WITH_PROFILE


async def choose_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if not data.startswith("choose_profile:"):
        return ConversationHandler.END

    try:
        user_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.message.reply_text(
            "Profilni aniqlab bo'lmadi. /start bilan qaytadan urinib ko'ring.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    profile = await get_user_by_id(user_id)
    if not profile:
        await query.message.reply_text(
            "Profil topilmadi. /start bilan qaytadan urinib ko'ring.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    context.user_data["chat_profile"] = profile

    await query.message.reply_text(
        f"Endi siz *{profile['nick']}* ({profile['name']} {profile['surname']}) bilan gaplashyapsiz. Savolingizni yozing.",
        reply_markup=chat_menu_keyboard(),
    )

    return CHAT_WITH_PROFILE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Bekor qilindi.", reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU


async def non_text_warning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Har qanday no-matn xabarlar (rasm, video, audio, hujjat, stiker va hokazo) uchun ogohlantirish
    if update.effective_message:
        await update.effective_message.reply_text(
            "Iltimos, faqat matnli xabar yuboring. Rasm, ovozli xabar, video yoki boshqa fayllarni qabul qilmayman.",
            reply_markup=main_menu_keyboard(),
        )


async def post_init(application: Application) -> None:
    await init_db()


def build_application(token: str) -> Application:
    """Barcha handlerlar ulangan Application obyektini qaytaradi.

    Bu funksiya ham lokal polling rejimi, ham webhook (Deta Space) rejimi uchun
    qayta ishlatiladi.
    """

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_surname)],
            REG_NICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_nick)],
            REG_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_password)],
            LOGIN_NICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_nick)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
            PROFILE_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_menu)],
            PROFILE_ADD_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_add_entry)],
            DELETE_ACCOUNT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_account_password)],
            SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_query),
                CallbackQueryHandler(choose_profile_callback, pattern=r"^choose_profile:"),
            ],
            CHAT_WITH_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_profile)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("stats", stats))
    # Matn bo'lmagan barcha xabarlar uchun umumiy ogohlantirish handleri
    application.add_handler(MessageHandler(~filters.TEXT, non_text_warning))

    return application


def main() -> None:
    if config is None or not getattr(config, "TELEGRAM_BOT_TOKEN", None):
        raise RuntimeError(
            "config.py faylini yaratib, TELEGRAM_BOT_TOKEN ni to'ldiring (config_example.py ni nusxa oling)."
        )

    application = build_application(config.TELEGRAM_BOT_TOKEN)

    logger.info("Bot ishga tushyapti (polling rejimi)...")
    application.run_polling()


if __name__ == "__main__":
    main()
