# bot.py — v2: Sifat tanlash (480p/720p/1080p/2160p) + 🎵 MP3
# Link tashlang -> sifatni tanlang -> video shu sifatda keladi.
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
    if "ffmpeg" in text.lower() or "ffprobe" in text.lower():
        return "Serverda ffmpeg yo'q — repo'da nixpacks.toml borligini tekshiring ⚙️"
    if "Fayl yuklanmadi" in text:
        return "Video 50 MB ga sig'madi — pastroq sifatni tanlang 📉"
    if "Unsupported URL" in text:
        return "Bu sayt qo'llab-quvvatlanmaydi 😕"
    if "Private" in text or "login" in text.lower():
        return "Bu video yopiq (private) — yuklab bo'lmaydi 🔒"
    return "Yuklab bo'lmadi. Linkni tekshirib, qayta urinib ko'ring 😕"


def download(url: str, folder: str, quality: str = "720", audio: bool = False) -> str:
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
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}]/best"
        )
        opts["merge_output_format"] = "mp4"
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
    link_id = uuid.uuid4().hex[:10]
    links[link_id] = url
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📺 480p", callback_data=f"q:{link_id}:480"),
                InlineKeyboardButton(text="📺 720p", callback_data=f"q:{link_id}:720"),
            ],
            [
                InlineKeyboardButton(text="🎬 1080p", callback_data=f"q:{link_id}:1080"),
                InlineKeyboardButton(text="🎬 2160p (4K)", callback_data=f"q:{link_id}:2160"),
            ],
            [InlineKeyboardButton(text="🎵 Faqat MP3 (audio)", callback_data=f"mp3:{link_id}")],
        ]
    )
    await message.answer(
        "🎚 <b>Qaysi sifatda yuboray?</b>\n"
        "<i>Eslatma: video 50 MB dan katta chiqsa yuborilmaydi — unda pastroq sifat tanlang</i>",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("q:"))
async def handle_quality(call: CallbackQuery) -> None:
    _, link_id, quality = call.data.split(":")
    url = links.get(link_id)
    if not url:
        await call.answer("Link eskirgan. Qaytadan yuboring", show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(f"⏳ {quality}p yuklanmoqda, kuting...")
    folder = tempfile.mkdtemp()
    try:
        path = await asyncio.to_thread(download, url, folder, quality=quality)
        await call.message.edit_text("📤 Yuborilmoqda...")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎵 MP3 qilib ber", callback_data=f"mp3:{link_id}")
        ]])
        await call.message.answer_video(
            FSInputFile(path),
            caption=f"📥 {quality}p — marhamat! Audio kerakmi? 👇",
            reply_markup=kb,
        )
        await call.message.delete()
    except Exception as e:
        logging.exception("Yuklashda xato")
        await call.message.edit_text(f"❌ {human_error(e)}")
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
