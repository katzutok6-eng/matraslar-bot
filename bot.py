import asyncio
import logging
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

from config import settings
from bitrix_client import Bitrix24Client
from parsers.service import parse_order

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("telegram_bitrix_bot")

dp = Dispatcher()
bitrix_client = Bitrix24Client(
    webhook_url=settings.BITRIX_WEBHOOK_URL,
    custom_fields_map=settings.get_custom_fields_map()
)


def is_order_message(text: str) -> bool:
    """
    Проверяет, является ли сообщение заказом.
    Критерии:
    - Содержит хештег заказа (например: #10x10... #lz...)
    - ИЛИ содержит ключевые слова (Summa/Olindi/Razmer) и телефонные номера.
    """
    if not text:
        return False
    lower = text.lower()
    has_hashtags = bool(re.search(r"#[A-Za-z0-9_x-]+", text))
    has_keywords = any(k in lower for k in ["summa", "razmer", "olindi", "olasila", "toper", "matras"])
    has_phones = bool(re.search(r"\b[0-9]{9}\b", text))

    return (has_hashtags and (has_keywords or has_phones)) or (has_keywords and has_phones)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.reply(
        "👋 Привет! Я бот для автоматического создания сделок в Битрикс24 из заказов матрасов.\n\n"
        "Добавьте меня в рабочую Telegram-группу заказов и дайте права администратора (или отключите Group Privacy).\n"
        "Как только в группе появится заказ с деталями, я автоматически создам контакт и сделку в Битрикс24!"
    )


@dp.message(Command("test"))
async def cmd_test(message: Message):
    """Команда для быстрой проверки связи с Битрикс24."""
    try:
        # Проверяем доступность вебхука через простой запрос
        res = await bitrix_client._call("app.info")
        await message.reply(f" Связь с Битрикс24 активна!\nДомен: {bitrix_client.domain}")
    except Exception as e:
        await message.reply(f"⚠️ Ошибка связи с Битрикс24:\n`{e}`", parse_mode=ParseMode.MARKDOWN)


@dp.message(F.text)
async def handle_group_message(message: Message):
    text = message.text or ""

    # Проверка белого списка чатов (если задан)
    allowed_chats = settings.get_allowed_chats()
    if allowed_chats and message.chat.id not in allowed_chats:
        return

    # Фильтруем обычные сообщения/флуд
    if not is_order_message(text):
        return

    logger.info(f"Получен заказ в чате {message.chat.id} от @{message.from_user.username or message.from_user.id}")

    try:
        # 1. Интеллектуальный парсинг заказа (AI или быстрый Regex fallback)
        order = await parse_order(
            text=text,
            gemini_api_key=settings.GEMINI_API_KEY,
            openai_api_key=settings.OPENAI_API_KEY
        )

        logger.info(f"Распознан заказ: {order.summary_title()} | Сумма: {order.total_amount}")

        # 2. Поиск или создание контакта по телефону
        contact_id = None
        if order.phones:
            try:
                contact_id = await bitrix_client.find_or_create_contact(order.phones)
            except Exception as e:
                logger.warning(f"Не удалось связать контакт: {e}")

        # 3. Умное создание или обновление существующей сделки (например, из Instagram)
        deal_id, is_updated = await bitrix_client.create_or_update_deal(
            order,
            contact_id=contact_id,
            stage_id=settings.DEFAULT_STAGE_ID
        )
        deal_url = bitrix_client.get_deal_url(deal_id)

        # 4. Формирование красивого ответа в группу
        phone_items = []
        for p in order.phones:
            note = order.phone_notes.get(p)
            phone_items.append(f"{p} ({note})" if note else p)
        phones_text = ", ".join(phone_items) if phone_items else "не указан"

        prepay_info = f"{order.prepayment_amount:,.0f} сум".replace(",", " ")
        if order.prepayment_type:
            prepay_info += f" ({order.prepayment_type})"

        total_info = f"{order.total_amount:,.0f} сум".replace(",", " ")
        balance_info = f"{order.balance_due:,.0f} сум".replace(",", " ")

        if is_updated:
            header_text = f"🔄 <b>Сделка #{deal_id} из Instagram/CRM обновлена!</b>\n<i>Переведена на этап «Zakaz yaratildi»</i>"
        else:
            header_text = f"✅ <b>Создана новая сделка #{deal_id} в Битрикс24!</b>\n<i>Этап «Zakaz yaratildi»</i>"

        reply_text = (
            f"{header_text}\n\n"
            f"📦 <b>Модель:</b> {order.product_name}\n"
            f"📏 <b>Размер:</b> {order.size or 'не указан'}\n"
            f"💰 <b>Сумма:</b> {total_info}\n"
            f"💳 <b>Оплачено:</b> {prepay_info}\n"
            f"⏳ <b>К доплате:</b> {balance_info}\n"
            f"📞 <b>Телефон:</b> {phones_text}\n"
            f"📍 <b>Доставка:</b> {order.delivery_address or '—'} ({order.delivery_date or '—'})\n\n"
            f"🔗 <a href=\"{deal_url}\">Открыть сделку в Битрикс24</a>"
        )

        await message.reply(
            text=reply_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке заказа: {e}", exc_info=True)
        await message.reply(
            f"⚠️ <b>Не удалось создать сделку в Битрикс24:</b>\n<code>{e}</code>",
            parse_mode=ParseMode.HTML
        )


async def start_web_server():
    """Запускает простой HTTP-сервер для health check облачных платформ (Koyeb, Render)."""
    try:
        from aiohttp import web
        port = int(os.getenv("PORT", "8000"))
        app = web.Application()

        async def ping(request):
            return web.Response(text="Bot is running OK", status=200)

        app.router.add_get("/", ping)
        app.router.add_get("/health", ping)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Health check HTTP сервер запущен на порту {port}")
    except Exception as e:
        logger.warning(f"Не удалось запустить health check сервер (не критично): {e}")


async def main():
    if not settings.BOT_TOKEN or settings.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("\n[!] ОШИБКА: Задайте токен бота BOT_TOKEN в файле .env")
        return

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print(f"[*] Бот запущен. Интеграция с {bitrix_client.domain} готова к работе.")
    
    # Запускаем health check сервер в фоне для облака
    await start_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
