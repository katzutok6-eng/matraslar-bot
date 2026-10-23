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
from cache_manager import save_message_deal, get_deal_by_message, add_print_job, get_pending_print_jobs, mark_print_job_done
from label_generator import build_order_labels

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
    - Содержит хештег заказа (#...) + (размер, ключевые слова матраса, телефон или дату)
    - ИЛИ содержит ключевые слова матраса и (телефон или размер).
    """
    if not text:
        return False
    lower = text.lower()
    has_hashtags = bool(re.search(r"#[A-Za-z0-9_x-]+", text))
    has_size = bool(re.search(r"\b\d{2,3}\s*[/x*х]\s*\d{2,3}\b", text))
    has_phones = bool(re.search(r"\b[0-9]{9}\b", text))
    has_keywords = any(k in lower for k in [
        "summa", "сумма", "razmer", "размер", "olindi", "олинди",
        "olasila", "оласила", "toper", "топер", "matras", "матрас",
        "paralon", "паралон", "поролон", "purjina", "пружина",
        "qavat", "кават", "tomoni", "томони", "barxt", "бархат",
        "namatrasnik", "наматрасник", "dona", "ta", "zet", "зет",
        "kakos", "кокос"
    ])

    if has_hashtags and (has_size or has_keywords or has_phones):
        return True

    if has_keywords and (has_phones or has_size):
        return True

    return False


RE_TAYYOR = re.compile(r"\b(tayyor|tayor|тай[её]р|тайор)\b", re.IGNORECASE)
RE_PRINT = re.compile(r"\b(pechat|печать|print|chop|chop\s*etish)\b", re.IGNORECASE)

COURIER_RULES = [
    ("Orif", 45, re.compile(r"\b(orif|ориф|arif|ариф)(?:ga)?\b", re.IGNORECASE)),
    ("Bilol", 47, re.compile(r"\b(bilol|билол|belol|белол)(?:ga)?\b", re.IGNORECASE)),
    ("Zohit", 49, re.compile(r"\b(zohi[td]|зохи[тд]|zoxi[td])(?:ga)?\b", re.IGNORECASE)),
]


def parse_action_from_message(text: str):
    """Определяет, является ли сообщение командой изменения стадии (tayyor, печать или имя доставщика)."""
    if not text:
        return None

    # 1. Проверяем доставщиков (Orif, Bilol, Zohit)
    for name, cid, pat in COURIER_RULES:
        if pat.search(text):
            return {"type": "delivery", "courier_name": name, "courier_id": cid}

    # 2. Проверяем статус готовности (tayyor)
    if RE_TAYYOR.search(text):
        return {"type": "ready"}

    # 3. Проверяем команду печати (pechat)
    if RE_PRINT.search(text):
        return {"type": "print"}

    return None


async def queue_deal_print_labels(deal_id: int, fallback_text: str = "") -> int:
    """Извлекает данные сделки, формирует этикетки 58x100 мм и ставит их в очередь печати."""
    try:
        deal_info = await bitrix_client.find_deal_by_id(deal_id)
        order_text = fallback_text or ""
        if not order_text and deal_info:
            order_text = deal_info.get("COMMENTS") or ""

        # Код заказа (#19x10x108 #radal7)
        code_val = deal_info.get("UF_CRM_TAGS") if deal_info else ""
        if not code_val and order_text:
            tags = re.findall(r"#[A-Za-z0-9_x-]+", order_text)
            code_val = " ".join(tags)
        if not code_val and deal_info:
            code_val = deal_info.get("TITLE") or f"Сделка #{deal_id}"

        # Телефоны
        phones_val = ""
        if deal_info and deal_info.get("CONTACT_ID"):
            try:
                c_data = await bitrix_client._call("crm.contact.get", {"id": deal_info["CONTACT_ID"]})
                c_phones = c_data.get("result", {}).get("PHONE", [])
                phones_val = ", ".join(p.get("VALUE") for p in c_phones if p.get("VALUE"))
            except Exception:
                pass
        if not phones_val and order_text:
            p_list = re.findall(r"(?:\+?998)?[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}", order_text)
            phones_val = ", ".join(set(p_list))

        addr_val = deal_info.get("UF_CRM_DELIVERY_ADDR") if deal_info else ""
        balance_val = deal_info.get("UF_CRM_BALANCE") or deal_info.get("OPPORTUNITY") or 0
        def_size = deal_info.get("UF_CRM_MATTRESS_SIZE") if deal_info else None

        labels = build_order_labels(
            code=code_val,
            phones=phones_val,
            address=addr_val,
            balance_due=balance_val,
            text=order_text,
            default_size=def_size
        )

        job_id = add_print_job(deal_id, labels)
        logger.info(f"Задание на печать #{job_id} ({len(labels)} этикеток) добавлено в очередь для сделки #{deal_id}")
        return job_id
    except Exception as e:
        logger.error(f"Ошибка при постановке на печать для сделки #{deal_id}: {e}", exc_info=True)
        return 0


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

    # -------------------------------------------------------------
    # 1. Проверяем, является ли сообщение действием (tayyor / доставщик)
    # -------------------------------------------------------------
    action_info = parse_action_from_message(text)
    if action_info:
        deal_id = None

        # А. Если ответили (reply) на сообщение заказа
        if message.reply_to_message:
            replied_msg = message.reply_to_message
            deal_id = get_deal_by_message(replied_msg.chat.id, replied_msg.message_id)

            if not deal_id:
                replied_text = replied_msg.text or replied_msg.caption or ""
                deal_data = await bitrix_client.find_deal_from_text(replied_text)
                if deal_data:
                    deal_id = int(deal_data["ID"])
                    save_message_deal(replied_msg.chat.id, replied_msg.message_id, deal_id)

        # Б. Если указали тег или номер заказа в самом сообщении (например: "tayyor #19x10x108")
        if not deal_id:
            deal_data = await bitrix_client.find_deal_from_text(text)
            if deal_data:
                deal_id = int(deal_data["ID"])

        if deal_id:
            deal_url = bitrix_client.get_deal_url(deal_id)

            # Перевод на этап "Zakaz yaratildi" + печать (без ответа в чат по запросу)
            if action_info["type"] == "ready":
                ok = await bitrix_client.update_deal_stage_and_courier(
                    deal_id=deal_id,
                    stage_id=settings.ZAKAZ_YARATILDI_STAGE_ID
                )
                if ok:
                    logger.info(f"Сделка #{deal_id} успешно переведена на этап Zakaz yaratildi")
                else:
                    logger.warning(f"Ошибка обновления этапа для сделки #{deal_id}")

                # Ставим наклейки в очередь печати на ноутбук в цеху
                replied_text = ""
                if message.reply_to_message:
                    replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
                if getattr(settings, "AUTO_PRINT_ON_READY", False):
                    await queue_deal_print_labels(deal_id, fallback_text=replied_text)
                else:
                    logger.info(f"Печать для сделки #{deal_id} пропущена (AUTO_PRINT_ON_READY=False)")
                return

            # Ручная печать наклеек по команде pechat / print
            elif action_info["type"] == "print":
                replied_text = ""
                if message.reply_to_message:
                    replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
                job_id = await queue_deal_print_labels(deal_id, fallback_text=replied_text)
                if job_id:
                    await message.reply(
                        f"🖨 Заказ отправлен на печать на ноутбук в цеху (<a href=\"{deal_url}\">Сделка #{deal_id}</a>)",
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                else:
                    await message.reply("⚠️ Не удалось поставить заказ в очередь печати.")
                return

            # Перевод на этап "Dostavka" + выбор доставщика
            elif action_info["type"] == "delivery":
                courier_name = action_info["courier_name"]
                courier_id = action_info["courier_id"]
                ok = await bitrix_client.update_deal_stage_and_courier(
                    deal_id=deal_id,
                    stage_id=settings.DOSTAVKA_STAGE_ID,
                    courier_id=courier_id
                )
                if ok:
                    await message.reply(
                        f"✅ <a href=\"{deal_url}\">Сделка #{deal_id}</a> переведена на этап <b>Dostavka</b>!\n"
                        f"🚚 Доставщик: <b>{courier_name}</b>",
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                else:
                    await message.reply("⚠️ Ошибка при назначении доставщика в Битрикс24.")
                return

        # По поводу tayyor ничего не пишем в чат; оповещаем только если не удалось найти сделку для доставщика
        if action_info["type"] != "ready":
            if message.reply_to_message or len(text.strip().split()) <= 3:
                await message.reply(
                    "⚠️ Не удалось найти сделку в Битрикс24 по этому заказу.\n"
                    "Убедитесь, что вы отвечаете (reply) на сообщение с заказом, где есть хештег (#...) или номер телефона.",
                    parse_mode=ParseMode.HTML
                )
        return

    # -------------------------------------------------------------
    # 2. Обработка входящего заказа
    # -------------------------------------------------------------
    if not is_order_message(text):
        return

    logger.info(f"Получен заказ в чате {message.chat.id} от @{message.from_user.username or message.from_user.id}")

    try:
        # Проверяем, не существует ли уже сделка для этого заказа (например, отправлена из 1-й группы и теперь скопирована во 2-ю группу доставки)
        tags = re.findall(r"#[A-Za-z0-9_x-]+", text)
        existing_deal = await bitrix_client.find_deal_by_tags(tags) if tags else None
        if existing_deal:
            deal_id = int(existing_deal["ID"])
            logger.info(f"Заказ с тегами {tags} уже существует в Битрикс24: Сделка #{deal_id}. Связываем сообщение {message.message_id} в чате {message.chat.id}")
            save_message_deal(message.chat.id, message.message_id, deal_id)
            # Не создаем дубликат и не спамим повторными оповещениями в группе доставки
            return

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

        # 3. Умное создание или обновление существующей сделки
        initial_stage = settings.READY_DATE_STAGE_ID if order.delivery_date else settings.DEFAULT_STAGE_ID
        deal_id, is_updated = await bitrix_client.create_or_update_deal(
            order,
            contact_id=contact_id,
            stage_id=initial_stage
        )

        # Сохраняем связку сообщения Telegram со сделкой в кеш
        save_message_deal(message.chat.id, message.message_id, deal_id)

        deal_url = bitrix_client.get_deal_url(deal_id)

        # 4. Лаконичный ответ в группу: галочка, статус и ссылка на сделку
        if is_updated:
            reply_text = f"✅ Заказ обновлён в Битрикс24: <a href=\"{deal_url}\">Сделка #{deal_id}</a>"
        else:
            reply_text = f"✅ Заказ создан в Битрикс24: <a href=\"{deal_url}\">Сделка #{deal_id}</a>"

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

        async def get_print_queue(request):
            token = request.query.get("token")
            if token != settings.PRINT_SECRET_TOKEN:
                return web.json_response({"error": "Unauthorized"}, status=401)
            jobs = get_pending_print_jobs()
            return web.json_response({"status": "ok", "jobs": jobs})

        async def ack_print_job(request):
            token = request.query.get("token")
            if token != settings.PRINT_SECRET_TOKEN:
                return web.json_response({"error": "Unauthorized"}, status=401)
            try:
                data = await request.json()
                job_id = data.get("job_id")
                if job_id:
                    mark_print_job_done(int(job_id))
                    return web.json_response({"status": "ok", "job_id": job_id})
            except Exception as e:
                return web.json_response({"error": str(e)}, status=400)
            return web.json_response({"error": "Missing job_id"}, status=400)

        app.router.add_get("/", ping)
        app.router.add_get("/health", ping)
        app.router.add_get("/api/print-queue", get_print_queue)
        app.router.add_post("/api/print-ack", ack_print_job)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Health check HTTP сервер запущен на порту {port}")
    except Exception as e:
        logger.warning(f"Не удалось запустить health check сервер (не критично): {e}")


async def schedule_daily_stage_checker():
    """Периодически проверяет даты заказов и переводит их в 'Zakaz tayyor bolish kuni' за 1 день до срока."""
    await asyncio.sleep(5)
    while True:
        try:
            logger.info("Проверка дат заказов для перевода в 'Zakaz tayyor bolish kuni'...")
            updated = await bitrix_client.move_upcoming_deals_to_ready_stage(
                from_stages=[settings.DEFAULT_STAGE_ID, "UC_MG82DT"],
                to_stage=settings.READY_DATE_STAGE_ID,
                days_before=1
            )
            if updated:
                logger.info(f"Автоматически переведены на этап 'Zakaz tayyor bolish kuni': {updated}")
        except Exception as e:
            logger.error(f"Ошибка в фоновом чезере стадий: {e}")

        # Проверяем каждые 30 минут
        await asyncio.sleep(1800)


async def main():
    if not settings.BOT_TOKEN or settings.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("\n[!] ОШИБКА: Задайте токен бота BOT_TOKEN в файле .env")
        return

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print(f"[*] Бот запущен. Интеграция с {bitrix_client.domain} готова к работе.")
    
    # Запускаем health check сервер в фоне для облака
    await start_web_server()
    # Запускаем автоматический перевод стадий за 1 день до даты готовности
    asyncio.create_task(schedule_daily_stage_checker())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
