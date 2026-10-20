import sqlite3
import os
import json
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "deals_cache.db")

def init_cache_db():
    """Инициализирует SQLite таблицы для связки сообщений и очереди печати."""
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

            # Таблица очереди печати для ноутбука в цеху
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS print_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_id INTEGER NOT NULL,
                    labels_json TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    printed_at TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_print_status ON print_jobs(status)")
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации базы кеша/печати: {e}")

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

def add_print_job(deal_id: int, labels: List[Dict[str, Any]]) -> int:
    """Добавляет задание на печать этикеток в очередь на сервере."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO print_jobs (deal_id, labels_json, status)
                VALUES (?, ?, 'pending')
            """, (deal_id, json.dumps(labels, ensure_ascii=False)))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка добавления в очередь печати сделки #{deal_id}: {e}")
        return 0

def get_pending_print_jobs() -> List[Dict[str, Any]]:
    """Возвращает все ожидающие задания на печать."""
    jobs = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, deal_id, labels_json, created_at
                FROM print_jobs
                WHERE status = 'pending'
                ORDER BY id ASC
            """)
            rows = cursor.fetchall()
            for r in rows:
                jobs.append({
                    "id": r[0],
                    "deal_id": r[1],
                    "labels": json.loads(r[2]),
                    "created_at": r[3]
                })
    except Exception as e:
        logger.error(f"Ошибка получения заданий печати: {e}")
    return jobs

def mark_print_job_done(job_id: int):
    """Помечает задание на печать как выполненное."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE print_jobs
                SET status = 'printed', printed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (job_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления статуса задания #{job_id}: {e}")

# Автоматическая инициализация при импорте
init_cache_db()
