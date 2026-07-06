# bot.py — Video/Audio yuklab beruvchi bot
# Link tashlang -> video keladi -> "🎵 MP3" tugmasi bilan audio ham olasiz.
import asyncio
import logging
import os
import re
import shutil
import tempfile
import uuid

import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MAX_SIZE_MB = 48  # Telegram bot limiti 50 MB — ozgina zaxira qoldiramiz
URL_RE = re.compile(r"https?://\S+")

dp = Dispatcher()
links: dict[str, str] = {}  # qisqa id -> url (MP3 tugmasi uchun)


def human_error(e: Exception) -> str:
    text = str(e)
    if "Unsupported URL" in text:
        return "Bu sayt qo'llab-quvvatlanmaydi 😕"
    if "Private" in text or "login" in text.lower():
        return "Bu video yopiq (private) — yuklab bo'lmaydi 🔒"
    return "Yuklab bo'lmadi. Linkni tekshirib, qayta urinib ko'ring 😕"


def download(url: str, folder: str, audio: bool = False) -> str:
    """Videoni (yoki MP3 audioni) yuklab, fayl yo'lini qaytaradi."""
    opts = {
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "max_filesize": MAX_SIZE_MB * 1024 * 1024,
        # YouTube blokidan o'tishga yordam beradi: o'zini Android ilova kabi tanitadi
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    if audio:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        opts["format"] = (
            f"best[filesize<{MAX_SIZE_MB}M][ext=mp4]/"
            f"best[filesize<{MAX_SIZE_MB}M]/best"
        )
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    files = [os.path.join(folder, f) for f in os.listdir(folder)]
    if not files:
        raise RuntimeError("Fayl yuklanmadi")
    return max(files, key=os.path.getsize)


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "📥 <b>Video yuklab beruvchi bot</b>\n"
        "───────────────\n"
        "Menga video linkini tashlang:\n"
        "▫️ Instagram (reels, post)\n"
        "▫️ TikTok\n"
        "▫️ YouTube (Shorts)\n"
        "▫️ Pinterest va boshqalar\n\n"
        "Videoni yuboraman, xohlasangiz 🎵 MP3 ham beraman!"
    )


@dp.message(F.text.regexp(r"https?://"))
async def handle_link(message: Message) -> None:
    url = URL_RE.search(message.text).group(0)
    status = await message.answer("⏳ Yuklanmoqda, kuting...")
    folder = tempfile.mkdtemp()
    try:
        path = await asyncio.to_thread(download, url, folder)
        await status.edit_text("📤 Yuborilmoqda...")
        link_id = uuid.uuid4().hex[:10]
        links[link_id] = url
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎵 MP3 qilib ber", callback_data=f"mp3:{link_id}")
        ]])
        await message.answer_video(
            FSInputFile(path),
            caption="📥 Marhamat! Audio kerakmi? 👇",
            reply_markup=kb,
        )
        await status.delete()
    except Exception as e:
        logging.exception("Yuklashda xato")
        await status.edit_text(f"❌ {human_error(e)}")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@dp.callback_query(F.data.startswith("mp3:"))
async def handle_mp3(call: CallbackQuery) -> None:
    url = links.get(call.data.split(":", 1)[1])
    if not url:
        await call.answer("Link eskirgan. Qaytadan yuboring", show_alert=True)
        return
    await call.answer("🎵 Audio tayyorlanmoqda...")
    status = await call.message.answer("⏳ MP3 tayyorlanmoqda...")
    folder = tempfile.mkdtemp()
    try:
        path = await asyncio.to_thread(download, url, folder, audio=True)
        await status.edit_text("📤 Yuborilmoqda...")
        await call.message.answer_audio(FSInputFile(path), caption="🎵 Marhamat!")
        await status.delete()
    except Exception as e:
        logging.exception("Audio xatosi")
        await status.edit_text(f"❌ {human_error(e)}")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@dp.message()
async def fallback(message: Message) -> None:
    await message.answer("🔗 Menga video <b>linkini</b> yuboring (https:// bilan boshlanadi)")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment o'zgaruvchisi topilmadi!")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
