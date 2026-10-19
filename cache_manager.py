import sqlite3
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "deals_cache.db")

def init_cache_db():
    """Инициализирует SQLite таблицу для связки сообщений Telegram со сделками Битрикс24."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_deals (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    deal_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, message_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deal_id ON message_deals(deal_id)")
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации базы кеша сообщений: {e}")

def save_message_deal(chat_id: int, message_id: int, deal_id: int):
    """Сохраняет связку сообщения Telegram со сделкой Битрикс24."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO message_deals (chat_id, message_id, deal_id)
                VALUES (?, ?, ?)
            """, (chat_id, message_id, deal_id))
            conn.commit()
    except Exception as e:
        logger.warning(f"Ошибка сохранения сделки #{deal_id} для сообщения {chat_id}:{message_id}: {e}")

def get_deal_by_message(chat_id: int, message_id: int) -> Optional[int]:
    """Возвращает ID сделки по ID сообщения Telegram."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT deal_id FROM message_deals
                WHERE chat_id = ? AND message_id = ?
            """, (chat_id, message_id))
            row = cursor.fetchone()
            if row:
                return int(row[0])
    except Exception as e:
        logger.warning(f"Ошибка поиска сделки по сообщению {chat_id}:{message_id}: {e}")
    return None

# Автоматическая инициализация при импорте
init_cache_db()
