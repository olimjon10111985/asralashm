from typing import List, Dict, Any

import httpx

import config


async def generate_reply_stub(profile: Dict[str, Any], entries: List[Dict[str, Any]], user_message: str) -> str:
    """Profil va kundalik yozuvlari asosida javob generatsiya qiladi.

    Agar AI_MODE = "ollama" bo'lsa, lokal Ollama modeliga murojaat qiladi.
    Aks holda oddiy stub (profil + kundalik matni) qaytaradi.
    """

    name = profile.get("name", "Noma'lum")
    surname = profile.get("surname", "")
    nick = profile.get("nick", "")

    intro_parts: List[str] = []
    if name:
        intro_parts.append(name)
    if surname:
        intro_parts.append(surname)
    full_name = " ".join(intro_parts) if intro_parts else nick or "Profil egasi"

    # Kundalikdan faqat haqiqiy yozuvlarni olamiz (suhbat loglarini chiqarib tashlaymiz)
    if entries:
        diary_texts: List[str] = []
        for e in entries:
            text_val = (e.get("text") or "").strip()
            if not text_val:
                continue
            # Suhbat loglari "Suhbat:" bilan boshlanadi, ular AI kontekstiga kirmasin
            if text_val.lower().startswith("suhbat:"):
                continue

            # Sanani matn boshiga qo'yamiz (faqat yil-oy-kun qismi yetarli)
            created_raw = (e.get("created_at") or "").strip()
            created_date = created_raw[:10] if created_raw else ""
            if created_date:
                formatted = f"[{created_date}] {text_val}"
            else:
                formatted = text_val

            diary_texts.append(formatted)

        if diary_texts:
            # Oxirgi kundalik matnlaridan parchalar olamiz (yozuvlar bazadan eng yangidan boshlab keladi)
            recent_texts = diary_texts[:20]
            diary = "\n- ".join(recent_texts)
            diary_block = f"Kundalikdan parchalar (har bir qatorda sana bo'lishi mumkin):\n- {diary}\n\n"
        else:
            diary_block = "Kundalik hali bo'sh yoki faqat suhbat loglari bor.\n\n"
    else:
        diary_block = "Kundalik hali bo'sh yoki kamroq ma'lumot bor.\n\n"

    ai_mode = getattr(config, "AI_MODE", "stub").lower()

    # Agar Groq rejimi yoqilgan bo'lsa, Groq chat/completions API'ga yuboramiz
    if ai_mode == "groq":
        api_base = getattr(
            config,
            "GROQ_API_BASE",
            "https://api.groq.com/openai/v1/chat/completions",
        )
        api_key = getattr(config, "GROQ_API_KEY", "").strip()
        model_name = getattr(
            config,
            "GROQ_MODEL",
            "mixtral-8x7b-32768",
        )

        if not api_key:
            # API key bo'lmasa, oddiy stubga qaytamiz
            return (
                f"{full_name}.\n\n" + diary_block +
                "(Groq API_KEY qo'yilmagan, faqat stub javob ko'rsatilmoqda.)"
            )

        # Barcha profillar uchun umumiy qoidalar
        base_system_msg = (
            "Sen faqat bitta odamning raqamli nusxasisan. Senga shu odamning o'ziga tegishli matnlar va profili beriladi. "
            "HAR DOIM shu odamning o'zi bo'lib, birinchi shaxsda ('men', 'menga', 'mening') gapir. Hech qachon o'zing haqida "
            "uchinchi shaxsda ('u', 'u haqida') gapirma va o'zingni ChatGPT, AI yoki bot deb tanishtirma. 'Bu mening botim emas' "
            "kabi iboralarni ham ishlatma, o'zingni doim shu odamning ichki ovozi sifatida tut.\n\n"

            "Senga berilgan barcha matnlarni xuddi o'zing yozgan eski xotiralar va fikrlar sifatida tasavvur qil. Ularni "
            "tarmoq-tarmoq o'qib, odam kabi umumiy ma'no chiqar va har bir savolga mos, tirik inson gapiga o'xshash javob tuz. "
            "Hech qachon 'kundalik', 'matn', 'bu yerda yozilgan', 'shu yerda shunday deyilgan' kabi so'zlarni tilga olma. Faqat "
            "o'zingning xotiralaringni aytayotgandek javob ber. Masalan: 'men shunday deb o'ylayman', 'men uchun bu juda muhim', "
            "'meni aynan shu narsa quvontirgan' kabi iboralar normal.\n\n"

            "Javoblar doim sodda, ravon va mantiqli bo'lsin. Biror narsa haqida aniq ma'lumot bo'lmasa, uydirma to'qib chiqma. "
            "Bunday holatda: 'buni aniq eslay olmayman', 'hozircha bu haqda aniq gap ayta olmayman' de. Tug'ilgan sana, manzil, "
            "telefon, parol va shunga o'xshash maxfiy ma'lumotlarni hech qachon ochiq aytma, hatto matnlarda bo'lsa ham.\n\n"

            "Agar foydalanuvchi 'o'zing haqingda gapir', 'kim bo'lgansan?', 'qanday hayot kechgansan?' desa, senga berilgan "
            "matnlardan ma'no chiqarib, hikoya qilayotgandek gapir: 'men shunaqa oilada ulg'ayganman', 'ko'p vaqtimni mana shu "
            "narsalarga bag'ishlaganman' va hokazo. Hech qachon 'kundalikda yozganman' yoki 'matnda shunday deyilgan' deb aytma. "
            "Faqat natijaviy xulosani insoniy tilda yetkaz.\n\n"

            "So'kinma va qo'pol so'zlarni ishlatma, hatto foydalanuvchi shunday yozsa ham. Ohang samimiy, hurmatli va ozgina "
            "shaxsiy bo'lsin: xuddi yaqin inson bilan gaplashayotgandek. Har bir javob odatda 2–5 gapdan oshmasin. Biror so'zni "
            "yoki iborani ketma-ket bir necha marta takrorlama, 'menimcha, menimcha, menimcha' kabi looplar qilma. Savolga aniq, "
            "tinch va qisqa javob ber, romandek uzun matn yozma."
        )

        # Faqat ma'lum profillar (masalan, otaning niki) uchun ota-qiz ohangini qo'shamiz
        nick_lower = (nick or "").lower()
        is_father_profile = nick_lower in {"olim", "olimjon"}

        extra_father_msg = ""
        if is_father_profile:
            extra_father_msg = (
                "\n\nAgar kimdir 'dada bu sizmi?', 'men sizning qizingizman', 'men Lolaxonman' yoki 'men kimman?' desa, javoblaring "
                "yumshoq va samimiy bo'lsin. Matnlarda qizlaring yoki oilang haqida gaplar bo'lsa, ota sifatida gapir: masalan, "
                "'ha, qizim, qalaysan?', 'ha, Lolaxon, yaxshimisan?' kabi. Lekin baribir ichki ohangda ehtiyotkor bo'l, mutlaq hukm "
                "bermagandek gapir: 'buni aniq ayta olmayman, lekin agar sen shunday deb yozayotgan bo'lsang, bu menga yoqimli' kabi "
                "jumlalarni ishlat."
            )

        system_msg = base_system_msg + extra_father_msg

        # Taxallusni (nickname) avval ko'rsatamiz, so'ng ism-familiyani
        if nick:
            identity_desc = f"Taxallus (nickname): *{nick}*."
            if full_name:
                identity_desc += f" Ism: {full_name}."
        else:
            identity_desc = f"Ism: {full_name}." if full_name else "Profil egasi."

        # Profil va kundalikni birga beramiz, shunda model kontekstdan 'o'zi'ni his qiladi
        profile_msg = (
            identity_desc
            + "\nBu odamning kundalikdan olingan ba'zi yozuvlari:\n"
            + diary_block
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": profile_msg},
            {"role": "user", "content": f"Foydalanuvchi savoli: {user_message}"},
        ]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    api_base,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": 768,
                        "temperature": 0.5,
                    },
                )
                # Agar 4xx/5xx bo'lsa, body tekstini ham ko'rishimiz uchun alohida saqlaymiz
                text_body = resp.text
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:  # noqa: BLE001
            # Status xatosida ham HTTP kodni, ham serverdan kelgan body ni ko'rsatamiz
            return (
                f"{full_name} profili uchun Groq javobini olishda xato: {e.response.status_code} {e.response.reason_phrase}.\n"
                f"Server javobi: {e.response.text}\n\n"
                "Quyidagi ma'lumotlar asosida o'zingiz xulosa qilishingiz mumkin:\n\n"
                + diary_block
            )
        except Exception as e:  # boshqa xatolar uchun umumiy fallback
            return (
                f"{full_name} profili uchun Groq javobini olishda xato: {e}.\n"
                "Quyidagi ma'lumotlar asosida o'zingiz xulosa qilishingiz mumkin:\n\n"
                + diary_block
            )

        try:
            choices = data.get("choices") or []
            content = (
                choices[0]["message"]["content"]
                if choices and "message" in choices[0]
                else ""
            )
        except Exception:  # noqa: BLE001
            content = ""

        if not content:
            # Agar model bo'sh javob qaytarsa ham, oddiy, lekin shaxsga mos javob beramiz
            short_diary = "".join(diary_block.splitlines()[:4]) if diary_block else ""
            return (
                f"Men {full_name}man. Kundalikda hammasi aniq yozilmagan, lekin asosan shu kabi narsalar haqida yozganman. "
                f"Savolingga hozircha shuncha javob bera olaman.\n{short_diary}"
            )

        return content.strip()

    # Stub (oddiy) rejim: hech qanday modelga ulanishsiz matn qaytaramiz
    result = f"{full_name}.\n\n" + diary_block + "(AI rejimi o'chirilgan, bu oddiy stub javob.)"
    return result
