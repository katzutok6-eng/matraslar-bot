import logging
from typing import Optional
from models import OrderData
from parsers.regex_parser import parse_order_regex
from parsers.ai_parser import parse_order_gemini, parse_order_openai

logger = logging.getLogger(__name__)


async def parse_order(
    text: str,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> OrderData:
    """
    Универсальный парсер:
    1. Если указан GEMINI_API_KEY -> парсит через Gemini Flash.
    2. Иначе если указан OPENAI_API_KEY -> парсит через OpenAI.
    3. Если ключей нет или запрос завершился ошибкой -> надёжно парсит через regex_parser.
    """
    if gemini_api_key:
        try:
            logger.info("Попытка парсинга через Gemini...")
            ai_res = await parse_order_gemini(text, gemini_api_key)
            if ai_res:
                logger.info("Успешный парсинг через Gemini!")
                return ai_res
        except Exception as e:
            logger.warning(f"Ошибка Gemini, переключаемся на резервный парсер: {e}")

    if openai_api_key:
        try:
            logger.info("Попытка парсинга через OpenAI...")
            ai_res = await parse_order_openai(text, openai_api_key)
            if ai_res:
                logger.info("Успешный парсинг через OpenAI!")
                return ai_res
        except Exception as e:
            logger.warning(f"Ошибка OpenAI, переключаемся на резервный парсер: {e}")

    logger.info("Используется быстрый встроенный эвристический парсер (Regex).")
    return parse_order_regex(text)
