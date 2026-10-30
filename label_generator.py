import re
from typing import List, Dict, Any, Optional

def extract_label_items(text: str, default_size: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Извлекает список позиций с указанием товара (Матрас / Наматрасник и т.д.) и размера.
    Пример:
    M3
    197/187 1ta
    78/178 2ta
    Namatrasnik chixol
    198/187 1ta
    78/178 2ta
    -> [
        {'product': 'Matras M3', 'size': '197/187', 'qty': 1},
        {'product': 'Matras M3', 'size': '78/178', 'qty': 2},
        {'product': 'Namatrasnik chixol', 'size': '198/187', 'qty': 1},
        {'product': 'Namatrasnik chixol', 'size': '78/178', 'qty': 2}
    ]
    """
    if not text:
        return [{"product": "Matras", "size": default_size or "Standart", "qty": 1}]

    size_pattern = re.compile(
        r"(\b\d{2,3}\s*[/x*хXХ]\s*\d{2,3}\b)(?:[-–—\s(]*([0-9]+)\s*(?:ta|dona|шт|d)\)?)?",
        re.IGNORECASE
    )

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    current_product = "Matras"
    items = []

    for line in lines:
        lower = line.lower()

        # Категории товаров
        if any(k in lower for k in ["namatrasnik", "наматрасник", "chixol", "чехол"]):
            current_product = "Namatrasnik chixol" if ("chixol" in lower or "чехол" in lower) else "Namatrasnik"
        elif any(k in lower for k in ["toper", "топер", "топпер"]):
            current_product = "Toper"
        elif any(k in lower for k in [
            "matras", "матрас", "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8",
            "orto", "artaped", "diamond", "zich", "lux", "prezident", "royal"
        ]):
            # Если в этой строке нет размера, значит это заголовок модели
            if not size_pattern.search(line):
                clean = line.strip(" :#-")
                if not clean.lower().startswith(("matras", "матрас", "toper", "топер")):
                    current_product = f"Matras {clean}"
                else:
                    current_product = clean

        # Поиск размеров в текущей строке
        matches = list(size_pattern.finditer(line))
        for m in matches:
            sz = m.group(1).replace(" ", "")
            qty = int(m.group(2)) if m.group(2) else 1
            items.append({
                "product": current_product,
                "size": sz,
                "qty": qty
            })

    if not items and default_size:
        items.append({"product": current_product, "size": default_size, "qty": 1})

    if not items:
        items.append({"product": "Matras", "size": "Standart", "qty": 1})

    return items


def extract_balance_from_text(text: str) -> tuple[Optional[float], Optional[str]]:
    """
    Извлекает остаток к оплате (qogan summa) и валюту напрямую из текста заказа,
    если они не переданы из Битрикс24.
    """
    if not text:
        return None, None

    # 1. Формула расчета: например, 430-100=330$ или 1200000-200000=1000000
    math_match = re.search(r"\d[\d\s.,]*\s*-\s*\d[\d\s.,]*\s*=\s*(\d[\d\s.,]*)\s*([$A-Za-z]+)?", text)
    if math_match:
        bal_str = re.sub(r"[^\d.]", "", math_match.group(1))
        curr_str = (math_match.group(2) or "").strip()
        try:
            bal = float(bal_str)
            curr = "USD" if ("$" in curr_str or "$" in text) else "UZS"
            return bal, curr
        except ValueError:
            pass

    # 2. Ключевые слова: olasila, qoldiq, qoldi, ostatok, qogan summa
    olasila_match = re.search(
        r"(?:olasila|оласила|qoldiq|колдик|qoldi|колди|ostatok|остаток|qogan\s*summa|коган\s*сумма)\s*[:;=-]?\s*([\d\s.,]+)\s*([$A-Za-z]+)?",
        text,
        re.IGNORECASE
    )
    if olasila_match:
        bal_str = re.sub(r"[^\d.]", "", olasila_match.group(1))
        curr_str = (olasila_match.group(2) or "").strip()
        try:
            bal = float(bal_str)
            curr = "USD" if ("$" in curr_str or "$" in text) else "UZS"
            return bal, curr
        except ValueError:
            pass

    return None, None


def format_currency(val: Any, currency: Optional[str] = None, text: str = "") -> str:
    """
    Форматирует остаток к оплате (Qogan summasi):
    - Если в тексте или сделке доллары ($ / USD) -> '330 $'
    - Если сумы -> '1 300 000 UZS'
    - Если val пустой или 0, пробуем надежно извлечь из text.
    """
    is_usd = False
    if currency and currency.upper() in ["USD", "$"]:
        is_usd = True
    elif text and "$" in text:
        is_usd = True

    num = 0.0
    has_num = False

    if val is not None and str(val).strip() != "" and str(val).strip() != "—":
        val_str = str(val).strip()
        if "$" in val_str:
            is_usd = True
        try:
            cleaned = re.sub(r"[^\d.]", "", val_str)
            if cleaned:
                num = float(cleaned)
                has_num = True
        except (ValueError, TypeError):
            pass

    # Если из val получили 0 или ничего, а в тексте есть расчет (например, 430-100=330$)
    if (not has_num or num <= 0) and text:
        text_bal, text_curr = extract_balance_from_text(text)
        if text_bal is not None and text_bal > 0:
            num = text_bal
            has_num = True
            if text_curr == "USD":
                is_usd = True

    if not has_num:
        return "—"

    if num <= 0:
        return "0 $" if is_usd else "0 UZS"

    if is_usd:
        if num.is_integer():
            return f"{num:,.0f} $".replace(",", " ")
        else:
            return f"{num:,.2f} $".replace(",", " ")
    else:
        return f"{num:,.0f} UZS".replace(",", " ")


def build_order_labels(
    code: str,
    phones: str,
    address: str,
    balance_due: Any,
    currency: Optional[str] = "UZS",
    text: str = "",
    default_size: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Формирует список этикеток для заказа:
    1. Каждому товару отдельная этикетка с нумерацией (1/N, 2/N...).
    2. Позиция (Матрас М3 / Наматрасник чехол) четко указывается рядом с размером.
    3. Поле Qogan summasi печатается ТОЛЬКО на 1-й этикетке с точной валютой, на остальных '—'.
    """
    items = extract_label_items(text, default_size=default_size)
    total_stickers = sum(it["qty"] for it in items)
    labels = []
    current_index = 1

    formatted_balance = format_currency(balance_due, currency=currency, text=text)

    for it in items:
        prod = it.get("product", "Matras")
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
                "product": prod,
                "size": size_display,
                "phone": phones or "—",
                "address": address or "—",
                "balance_due": balance_display
            })
            current_index += 1

    return labels
