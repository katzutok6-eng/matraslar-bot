import json
import logging
from typing import Optional
import httpx
from models import OrderData

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты — специализированный парсер заказов матрасов и спальных принадлежностей из Telegram-групп фабрики в Узбекистане.
Твоя задача — извлечь детали заказа из неструктурированного текста на узбекском/русском языках в строгий JSON.

ПРАВИЛА ИЗВЛЕЧЕНИЯ:
1. order_tags: список хештегов (например: ["#10x10x59", "#lz20"]).
2. phones: список номеров телефонов клиента. Обязательно приведи к формату +998XXXXXXXXX (если 9 цифр, например 998680205 -> +998998680205).
3. product_name: название модели или изделия (например: 'Toper 10 sm', 'Mayami kaprz').
4. size: размер матраса (например: '200/175', '200/180', '200x160').
5. material: ткань чехла, цвет, боковины (например: 'oq xb yoni jigaren barxt orqasi stop').
6. details: наполнение, пружинный блок, слои поролона, кокос, плотность (например: 'Nezavisniy purjina, 2 tomoni qora, 1 tomoni kakos, 2 tomoni 4 li 28plotnsli paralon').
7. total_amount: общая сумма заказа числом в сумах (Summa). Точки и пробелы удали. (1.580.000 -> 1580000).
8. prepayment_amount: сумма предоплаты числом в сумах (Olindi). Если написано 'hammasi' / 'barchasi' / 'QR' без суммы — значит оплачено полностью, ставь total_amount.
9. prepayment_type: способ предоплаты ('Karta', 'QR', 'Naqd', 'Click', 'Payme' и т.д.).
10. balance_due: остаток к получению числом (Olasila). Если предоплата 100%, ставь 0.
11. delivery_address: адрес или район доставки (например 'Limanariya', 'Sergili'). Убирай грамматический аффикс -ga/-ka ('Limanariyaga' -> 'Limanariya').
12. delivery_date: дата доставки в формате YYYY-MM-DD.

Отвечай ТОЛЬКО валидным JSON объектом без лишнего текста и markdown кавычек.
"""


async def parse_order_gemini(text: str, api_key: str, model: str = "gemini-2.0-flash") -> Optional[OrderData]:
    """Парсинг через Google Gemini REST API с гарантированной структурой."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT},
                    {"text": f"Текст заказа из Telegram:\n\"\"\"\n{text}\n\"\"\""}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_json = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed_dict = json.loads(raw_json)
            parsed_dict["raw_text"] = text
            return OrderData(**parsed_dict)
    except Exception as e:
        logger.error(f"Ошибка вызова Gemini API: {e}", exc_info=True)
        return None


async def parse_order_openai(text: str, api_key: str, model: str = "gpt-4o-mini") -> Optional[OrderData]:
    """Парсинг через OpenAI REST API."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Текст заказа:\n{text}"}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed_dict = json.loads(content)
            parsed_dict["raw_text"] = text
            return OrderData(**parsed_dict)
    except Exception as e:
        logger.error(f"Ошибка вызова OpenAI API: {e}", exc_info=True)
        return None
