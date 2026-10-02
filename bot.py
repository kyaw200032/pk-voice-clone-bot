"""
PK Voice Clone - Telegram bot.

Send Burmese text -> get it back as a voice message in a cloned voice.
Default voice: bundled sample. /myvoice lets each user clone their OWN voice
by sending a voice message.

Needs env: TELEGRAM_BOT_TOKEN
Optional:  VOXCPM_API_BASE (defaults to the public VoxCPM2 demo API)
"""

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from voxcpm_api import generate_cloned_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pk-voice-clone")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VOICE = os.path.join(BASE_DIR, "assets", "default_voice.mp3")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

MAX_TEXT = 500  # keep generations fast on the free shared API

TXT_START = (
    "မင်ဂလာပါ! 🎙️\n"
    "PK Voice Clone မှ ကြိုဆိုပါတယ်။\n\n"
    "မြန်မာစာ ပို့လိုက်ပါ — အသံဖိုင်အနေနဲ့ ပြန်ပို့ပေးမယ်။\n\n"
    "📌 အမိန့်များ:\n"
    "/myvoice - ကိုယ့်အသံနဲ့ clone ချင်ရင် voice message ပို့ပါ\n"
    "/resetvoice - မူလအသံ (ကျော်ကြီးအသံ) ပြန်သုံးမယ်\n"
    "/help - အကူအညီ"
)
TXT_HELP = (
    "🎙️ PK Voice Clone အသုံးပြုနည်း:\n\n"
    "1️⃣ မြန်မာစာ ရိုက်ပို့ပါ → အသံထွက်လာမယ်\n"
    "2️⃣ ကိုယ့်အသံနဲ့ လိုချင်ရင် voice message ပို့ပါ (စက္ကန့် 10-30 လောက်)\n"
    "3️⃣ /resetvoice နဲ့ မူလအသံ ပြန်ပြောင်းလို့ရတယ်\n\n"
    "⚠️ အသံထုတ်တာ 1-3 မိနစ်လောက် ကြာနိုင်တယ်။"
)
TXT_WAIT = "⏳ အသံထုတ်နေတယ်၊ ခဏစောင့်ပေး..."
TXT_DONE = "✅ ရပြီ! နားထောင်ကြည့် 👇"
TXT_ERR = "❌ အမှားတစ်ခု ဖြစ်သွားတယ်။ နောက်မှ ပြန်စမ်းကြည့်ပေး။"
TXT_VOICE_SAVED = (
    "✅ မှတ်ထားပြီ! နောက်စာတွေကို ဒီအသံနဲ့ ပြောပေးမယ် 🎙️\n"
    "မူလအသံ ပြန်သုံးချင်ရင် /resetvoice"
)
TXT_VOICE_RESET = "🔄 မူလအသံ ပြန်ပြောင်းပြီးပြီ။"
TXT_TOO_LONG = f"⚠️ စာက ရှည်လွန်းတယ်။ စာလုံး {MAX_TEXT} ထက် မကျော်စေနဲ့။"
TXT_EMPTY = "ℹ️ စာပို့ပေးပါ — အသံထုတ်ပေးမယ်။"


def user_voice_path(user_id: int) -> str:
    return os.path.join(DATA_DIR, f"{user_id}.mp3")


def ref_voice_for(user_id: int) -> str:
    p = user_voice_path(user_id)
    return p if os.path.exists(p) else DEFAULT_VOICE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_START)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_HELP)


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
    ref = ref_voice_for(user_id)
    status = await update.message.reply_text(TXT_WAIT)
    try:
        out_path = await asyncio.to_thread(generate_cloned_audio, text, ref)
        with open(out_path, "rb") as audio:
            await update.message.reply_audio(
                audio=audio, title="PK Voice Clone", caption=TXT_DONE
            )
        os.remove(out_path)
    except Exception as e:  # noqa: BLE001
        log.exception("generation failed for user %s", user_id)
        await status.edit_text(TXT_ERR + f"\n({type(e).__name__})")
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
    app.add_handler(CommandHandler("myvoice", myvoice))
    app.add_handler(CommandHandler("resetvoice", resetvoice))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("PK Voice Clone bot starting (long polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
