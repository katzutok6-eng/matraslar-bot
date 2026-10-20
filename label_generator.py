import re
from typing import List, Dict, Any, Optional

def extract_label_items(text: str, default_size: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Извлекает список позиций и количество из текста заказа.
    Пример:
    179х73-1шт
    199х88-1шт
    179х88-1шт
    -> [{'size': '179х73', 'qty': 1}, ...]
    """
    size_pattern = re.compile(
        r"(\b\d{2,3}\s*[/x*х]\s*\d{2,3}\b)(?:[-–—\s(]*([0-9]+)\s*(?:ta|dona|шт|d)\)?)?",
        re.IGNORECASE
    )
    items = []
    if text:
        for m in size_pattern.finditer(text):
            sz = m.group(1).replace(" ", "")
            qty = int(m.group(2)) if m.group(2) else 1
            items.append({"size": sz, "qty": qty})

    if not items and default_size:
        # Fallback на размер из сделки
        items.append({"size": default_size, "qty": 1})

    if not items:
        items.append({"size": "Стандарт", "qty": 1})

    return items


def format_currency(val: Any) -> str:
    """Форматирует сумму в красивый вид (например: 1 300 000 UZS)."""
    try:
        num = float(val)
        if num <= 0:
            return "0 UZS"
        return f"{num:,.0f} UZS".replace(",", " ")
    except (ValueError, TypeError):
        return str(val) if val else "—"


def build_order_labels(
    code: str,
    phones: str,
    address: str,
    balance_due: Any,
    text: str = "",
    default_size: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Формирует список этикеток для заказа строго по правилам:
    1. Если товаров несколько: каждому товару отдельная этикетка с нумерацией (1/N, 2/N...).
    2. Поле Qogan summasi печатается ТОЛЬКО на 1-й этикетке (Вариант 2), на остальных ставится '—'.
    """
    items = extract_label_items(text, default_size=default_size)
    total_stickers = sum(it["qty"] for it in items)
    labels = []
    current_index = 1

    formatted_balance = format_currency(balance_due)

    for it in items:
        sz = it["size"]
        for _ in range(it["qty"]):
            # Нумерация размера (1/3, 2/3...) если больше 1 товара
            size_display = f"{sz} ({current_index}/{total_stickers})" if total_stickers > 1 else sz
            
            # Сумма только на 1-й наклейке
            balance_display = formatted_balance if current_index == 1 else "—"

            labels.append({
                "index": current_index,
                "total": total_stickers,
                "code": code or "—",
                "size": size_display,
                "phone": phones or "—",
                "address": address or "—",
                "balance_due": balance_display
            })
            current_index += 1

    return labels
