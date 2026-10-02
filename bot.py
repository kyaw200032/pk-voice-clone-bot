"""
PK Voice Clone - Telegram bot.

Send Burmese text -> get it back as a voice message.
Two engines, picked with buttons (/voice):
  - Clone Voice (VoxCPM2): clones a voice (default sample, or /myvoice).
  - Gemini Voice: Google AI Studio TTS (fast, stock voices).

Needs env: TELEGRAM_BOT_TOKEN
Optional:  GEMINI_API_KEY (for Gemini Voice), VOXCPM_API_BASE
"""

import asyncio
import json
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from voxcpm_api import generate_cloned_audio
from gemini_tts import DEFAULT_VOICE, VOICES, generate_gemini_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pk-voice-clone")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VOICE_REF = os.path.join(BASE_DIR, "assets", "default_voice.mp3")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

MAX_TEXT = 500  # keep generations fast on the free shared API

ENGINE_CLONE = "clone"
ENGINE_GEMINI = "gemini"

TXT_START = (
    "မင်ဂလာပါ! 🎙️\n"
    "PK Voice Clone မှ ကြိုဆိုပါတယ်။\n\n"
    "မြန်မာစာ ပို့လိုက်ပါ — အသံဖိုင်အနေနဲ့ ပြန်ပို့ပေးမယ်။\n\n"
    "📌 အမိန့်များ:\n"
    "/voice - အသံရွေးမယ် (Clone / Gemini)\n"
    "/myvoice - ကိုယ့်အသံနဲ့ clone ချင်ရင် voice message ပို့ပါ\n"
    "/resetvoice - မူလအသံ (ကျော်ကြီးအသံ) ပြန်သုံးမယ်\n"
    "/help - အကူအညီ"
)
TXT_HELP = (
    "🎙️ PK Voice Clone အသုံးပြုနည်း:\n\n"
    "1️⃣ /voice နဲ့ အသံရွေးပါ (Clone / Gemini)\n"
    "2️⃣ မြန်မာစာ ရိုက်ပို့ပါ → အသံထွက်လာမယ်\n"
    "3️⃣ ကိုယ့်အသံနဲ့ clone ချင်ရင် voice message ပို့ပါ (10-30 စက္ကန့်)\n"
    "4️⃣ /resetvoice နဲ့ မူလအသံ ပြန်ပြောင်းလို့ရတယ်\n\n"
    "⚠️ Clone Voice က 1-3 မိနစ်လောက် ကြာနိုင်တယ်။ Gemini က စက္ကန့်ပိုင်းပဲ။"
)
TXT_WAIT = "⏳ အသံထုတ်နေတယ်၊ ခဏစောင့်ပေး..."
TXT_DONE_CLONE = "✅ ရပြီ! နားထောင်ကြည့် 👇"
TXT_DONE_GEMINI = "⚡ ရပြီ! နားထောင်ကြည့် 👇"
TXT_ERR = "❌ အမှားတစ်ခု ဖြစ်သွားတယ်။ နောက်မှ ပြန်စမ်းကြည့်ပေး။"
TXT_VOICE_SAVED = (
    "✅ မှတ်ထားပြီ! နောက်စာတွေကို ဒီအသံနဲ့ ပြောပေးမယ် 🎙️\n"
    "မူလအသံ ပြန်သုံးချင်ရင် /resetvoice"
)
TXT_VOICE_RESET = "🔄 မူလအသံ ပြန်ပြောင်းပြီးပြီ။"
TXT_TOO_LONG = "⚠️ စာက ရှည်လွန်းတယ်။ စာလုံး 500 ထက် မကျော်စေနဲ့။"
TXT_EMPTY = "ℹ️ စာပို့ပေးပါ — အသံထုတ်ပေးမယ်။"
TXT_VOICE_TITLE = "🎙️ အသံရွေးပါ 👇"
TXT_GVOICE_TITLE = "⚡ Gemini အသံရွေးပါ 👇"
TXT_BACK = "« နောက်သို့"
TXT_ENGINE_SET_CLONE = (
    "✅ Clone Voice ရွေးပြီးပြီ 🎙️\n"
    "စာပို့လိုက်ပါ — အသံထုတ်ပေးမယ်။"
)
TXT_GVOICE_SET = "✅ {voice} အသံ ရွေးပြီးပြီ!"
TXT_NO_GEMINI_KEY = "⚠️ Gemini API key မချိတ်ရသေးဘူး။"
BTN_CLONE = "🎙️ Clone Voice"
BTN_GEMINI = "⚡ Gemini Voice"


def user_voice_path(user_id: int) -> str:
    return os.path.join(DATA_DIR, f"{user_id}.mp3")


def user_settings_path(user_id: int) -> str:
    return os.path.join(DATA_DIR, f"{user_id}.json")


def get_settings(user_id: int) -> dict:
    s = {"engine": ENGINE_CLONE, "gvoice": DEFAULT_VOICE}
    p = user_settings_path(user_id)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception:  # noqa: BLE001
            pass
    if s.get("gvoice") not in VOICES:
        s["gvoice"] = DEFAULT_VOICE
    if s.get("engine") not in (ENGINE_CLONE, ENGINE_GEMINI):
        s["engine"] = ENGINE_CLONE
    return s


def save_settings(user_id: int, s: dict):
    with open(user_settings_path(user_id), "w", encoding="utf-8") as f:
        json.dump(s, f)


def ref_voice_for(user_id: int) -> str:
    p = user_voice_path(user_id)
    return p if os.path.exists(p) else DEFAULT_VOICE_REF


def engine_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_CLONE, callback_data="engine:clone"),
                InlineKeyboardButton(BTN_GEMINI, callback_data="engine:gemini"),
            ]
        ]
    )


def gvoice_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(v, callback_data=f"gvoice:{v}") for v in VOICES[i : i + 2]]
        for i in range(0, len(VOICES), 2)
    ]
    rows.append([InlineKeyboardButton(TXT_BACK, callback_data="back:engines")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_START, reply_markup=engine_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_HELP)


async def voice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_VOICE_TITLE, reply_markup=engine_keyboard())


async def resetvoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = user_voice_path(update.effective_user.id)
    if os.path.exists(p):
        os.remove(p)
    await update.message.reply_text(TXT_VOICE_RESET)


async def myvoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_voice"] = True
    await update.message.reply_text(
        "🎤 ကိုယ့်အသံနဲ့ clone ချင်ရင် voice message ပို့ပေးပါ (10-30 စက္ကန့်လောက်)..."
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    data = q.data or ""
    s = get_settings(user_id)
    if data == "engine:clone":
        s["engine"] = ENGINE_CLONE
        save_settings(user_id, s)
        await q.edit_message_text(TXT_ENGINE_SET_CLONE)
    elif data == "engine:gemini":
        s["engine"] = ENGINE_GEMINI
        save_settings(user_id, s)
        await q.edit_message_text(TXT_GVOICE_TITLE, reply_markup=gvoice_keyboard())
    elif data.startswith("gvoice:"):
        v = data.split(":", 1)[1]
        if v in VOICES:
            s["engine"] = ENGINE_GEMINI
            s["gvoice"] = v
            save_settings(user_id, s)
        await q.edit_message_text(TXT_GVOICE_SET.format(voice=s["gvoice"]))
    elif data == "back:engines":
        await q.edit_message_text(TXT_VOICE_TITLE, reply_markup=engine_keyboard())


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dest = user_voice_path(user_id)
    f = await update.message.voice.get_file()
    await f.download_to_drive(dest)
    context.user_data.pop("awaiting_voice", None)
    await update.message.reply_text(TXT_VOICE_SAVED)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(TXT_EMPTY)
        return
    if len(text) > MAX_TEXT:
        await update.message.reply_text(TXT_TOO_LONG)
        return

    user_id = update.effective_user.id
    s = get_settings(user_id)
    status = await update.message.reply_text(TXT_WAIT)
    try:
        if s["engine"] == ENGINE_GEMINI:
            out_path = await asyncio.to_thread(
                generate_gemini_audio, text, s["gvoice"]
            )
            caption = f"{TXT_DONE_GEMINI}\n({s['gvoice']})"
            title = "Gemini Voice"
        else:
            out_path = await asyncio.to_thread(
                generate_cloned_audio, text, ref_voice_for(user_id)
            )
            caption = TXT_DONE_CLONE
            title = "PK Voice Clone"
        with open(out_path, "rb") as audio:
            await update.message.reply_audio(audio=audio, title=title, caption=caption)
        os.remove(out_path)
    except Exception as e:  # noqa: BLE001
        log.exception("generation failed for user %s", user_id)
        msg = TXT_ERR
        if "GEMINI_API_KEY" in str(e):
            msg = TXT_NO_GEMINI_KEY
        await status.edit_text(msg)
        return
    try:
        await status.delete()
    except Exception:  # noqa: BLE001
        pass


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN env var is required")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("voice", voice_cmd))
    app.add_handler(CommandHandler("myvoice", myvoice))
    app.add_handler(CommandHandler("resetvoice", resetvoice))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("PK Voice Clone bot starting (long polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
