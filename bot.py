# bot.py — v3: Chiroyli xabarlar + 🎟 stiker + 💎 4K fayl sifatida (siqilmaydi)
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
STICKER_ID = os.getenv("STICKER_ID", "")  # "yuklanmoqda" stikeri — sozlash: 🎟 bo'limda
MAX_SIZE_MB = 48  # Telegram bot limiti 50 MB — ozgina zaxira qoldiramiz
URL_RE = re.compile(r"https?://\S+")
LINE = "━━━━━━━━━━━━━"

dp = Dispatcher()
links: dict[str, str] = {}  # qisqa id -> url (tugmalar uchun)


def human_error(e: Exception) -> str:
    text = str(e)
    if "ffmpeg" in text.lower() or "ffprobe" in text.lower():
        return "Serverda ffmpeg yo'q — Dockerfile yoki nixpacks.toml ni tekshiring ⚙️"
    if "Fayl yuklanmadi" in text:
        return "Video 50 MB ga sig'madi — pastroq sifatni tanlang 📉"
    if "Unsupported URL" in text:
        return "Bu sayt qo'llab-quvvatlanmaydi 😕"
    if "Private" in text or "login" in text.lower():
        return "Bu video yopiq (private) — yuklab bo'lmaydi 🔒"
    return "Yuklab bo'lmadi. Linkni tekshirib, qayta urinib ko'ring 😕"


def download(url: str, folder: str, quality: str = "720", audio: bool = False):
    """Yuklab: (fayl yo'li, sarlavha, haqiqiy sifat) qaytaradi."""
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
        info = ydl.extract_info(url, download=True) or {}
    files = [os.path.join(folder, f) for f in os.listdir(folder)]
    if not files:
        raise RuntimeError("Fayl yuklanmadi")
    path = max(files, key=os.path.getsize)
    return path, info.get("title", "Video"), info.get("height")


async def send_status(message: Message) -> Message:
    """Yuklash paytida stiker (yoki STICKER_ID bo'lmasa ⏳) ko'rsatadi."""
    if STICKER_ID:
        try:
            return await message.answer_sticker(STICKER_ID)
        except Exception:
            logging.warning("STICKER_ID noto'g'ri — oddiy ⏳ ko'rsatildi")
    return await message.answer("⏳")


async def delete_silently(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Salom! Men video yuklab beruvchi botman</b> 📥\n"
        f"{LINE}\n"
        "🔗 Menga shunchaki <b>link</b> tashlang:\n\n"
        "   📸 Instagram — reels, post\n"
        "   🎵 TikTok\n"
        "   ▶️ YouTube — Shorts, video\n"
        "   📌 Pinterest va boshqalar\n"
        f"{LINE}\n"
        "🎚 Sifatni o'zingiz tanlaysiz: 480p dan 💎 4K gacha\n"
        "🎧 Xohlasangiz MP3 audio ham beraman!"
    )


@dp.message(F.sticker)
async def sticker_id(message: Message) -> None:
    await message.answer(
        "🆔 Bu stikerning ID'si — Railway'da <b>STICKER_ID</b> o'zgaruvchisiga qo'ying:\n\n"
        f"<code>{message.sticker.file_id}</code>"
    )


@dp.message(F.text.regexp(r"https?://"))
async def handle_link(message: Message) -> None:
    url = URL_RE.search(message.text).group(0)
    link_id = uuid.uuid4().hex[:10]
    links[link_id] = url
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 480p", callback_data=f"q:{link_id}:480"),
                InlineKeyboardButton(text="📺 720p", callback_data=f"q:{link_id}:720"),
            ],
            [
                InlineKeyboardButton(text="🎬 1080p", callback_data=f"q:{link_id}:1080"),
                InlineKeyboardButton(text="💎 4K", callback_data=f"q:{link_id}:2160"),
            ],
            [InlineKeyboardButton(text="🎧 Faqat MP3 (audio)", callback_data=f"mp3:{link_id}")],
        ]
    )
    await message.answer(
        "🎚 <b>Qaysi sifatda yuboray?</b>\n"
        f"{LINE}\n"
        "📱 480p / 📺 720p — tez, video ko'rinishida\n"
        "🎬 1080p / 💎 4K — <b>fayl</b> ko'rinishida (Telegram siqmaydi!)\n\n"
        "<i>⚠️ 50 MB dan katta chiqsa yuborilmaydi — pastroq sifat tanlang</i>",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("q:"))
async def handle_quality(call: CallbackQuery) -> None:
    _, link_id, quality = call.data.split(":")
    url = links.get(link_id)
    if not url:
        await call.answer("Link eskirgan. Linkni qaytadan yuboring 🔄", show_alert=True)
        return
    await call.answer("⏳ Tayyorlanmoqda...")
    await delete_silently(call.message)
    status = await send_status(call.message)
    folder = tempfile.mkdtemp()
    try:
        path, title, height = await asyncio.to_thread(download, url, folder, quality=quality)
        real = f"{height}p" if height else f"{quality}p"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎧 MP3 qilib ber", callback_data=f"mp3:{link_id}")
        ]])
        caption = (
            f"✅ <b>{title}</b>\n"
            f"{LINE}\n"
            f"🎞 Sifat: <b>{real}</b>  •  📥 Marhamat!\n"
            "🎧 Audio kerak bo'lsa — tugmani bosing 👇"
        )
        if quality in ("1080", "2160"):
            # Fayl (hujjat) sifatida — Telegram siqmaydi, asl sifat saqlanadi!
            await call.message.answer_document(FSInputFile(path), caption=caption, reply_markup=kb)
        else:
            await call.message.answer_video(FSInputFile(path), caption=caption, reply_markup=kb)
    except Exception as e:
        logging.exception("Yuklashda xato")
        await call.message.answer(f"❌ {human_error(e)}")
    finally:
        await delete_silently(status)
        shutil.rmtree(folder, ignore_errors=True)


@dp.callback_query(F.data.startswith("mp3:"))
async def handle_mp3(call: CallbackQuery) -> None:
    url = links.get(call.data.split(":", 1)[1])
    if not url:
        await call.answer("Link eskirgan. Linkni qaytadan yuboring 🔄", show_alert=True)
        return
    await call.answer("🎧 Audio tayyorlanmoqda...")
    status = await send_status(call.message)
    folder = tempfile.mkdtemp()
    try:
        path, title, _ = await asyncio.to_thread(download, url, folder, audio=True)
        await call.message.answer_audio(
            FSInputFile(path),
            caption=f"🎧 <b>{title}</b>\n{LINE}\n✨ Marhamat! Yana link tashlang 😉",
        )
    except Exception as e:
        logging.exception("Audio xatosi")
        await call.message.answer(f"❌ {human_error(e)}")
    finally:
        await delete_silently(status)
        shutil.rmtree(folder, ignore_errors=True)


@dp.message()
async def fallback(message: Message) -> None:
    await message.answer("🔗 Menga video <b>linkini</b> yuboring (https:// bilan boshlanadi) 😊")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment o'zgaruvchisi topilmadi!")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
