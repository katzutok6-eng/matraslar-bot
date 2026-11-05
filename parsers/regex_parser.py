import re
from typing import List, Optional, Tuple, Dict
from models import OrderData

UZ_OPERATORS = r"(?:33|50|55|71|77|88|90|91|93|94|95|97|98|99)"


def normalize_amount(val_str: str) -> float:
    """Очищает строку суммы от точек, пробелов и запятых."""
    cleaned = re.sub(r"[^\d]", "", val_str)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def normalize_phone(phone_str: str) -> str:
    """Приводит номер телефона к международному формату +998XXXXXXXXX."""
    digits = re.sub(r"[^\d]", "", phone_str)
    if len(digits) == 9:
        return f"+998{digits}"
    elif len(digits) == 12 and digits.startswith("998"):
        return f"+{digits}"
    elif len(digits) > 9 and not digits.startswith("+"):
        return f"+{digits}"
    return phone_str.strip()


def extract_uz_phones(text: str) -> List[Tuple[str, str, str]]:
    """
    Извлекает телефоны Узбекистана и возможные примечания/имена.
    Возвращает список кортежей: (чистый_номер_+998, форматированный_номер, пометка_или_имя).
    Строго требует валидный код оператора (33, 50, 55, 71, 77, 88, 90, 91, 93, 94, 95, 97, 98, 99).
    Исключает математические формулы и даты.
    """
    results = []
    lines = text.splitlines()

    pattern = re.compile(
        rf"(?:(?:\+?998)[ \t-]*)?({UZ_OPERATORS})[ \t-]*(\d{{3}})[ \t-]*(\d{{2}})[ \t-]*(\d{{2}})\b|"
        rf"(?:(?:\+?998)[ \t-]*)?({UZ_OPERATORS})[ \t-]*(\d{{7}})\b",
        re.IGNORECASE
    )

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        lower = line_clean.lower()
        # Исключаем явные финансовые строки
        if any(w in lower for w in ["suma", "summa", "сумма", "сума", "olasila", "оласила", "olindi", "олинди", "$"]):
            if re.search(r"\d+\s*[-+]\s*\d+", line_clean) or "=" in line_clean:
                continue

        # Исключаем строки дат (например: 04.11.2026)
        if re.search(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$", line_clean):
            continue

        for m in pattern.finditer(line_clean):
            if m.group(1):
                op, p1, p2, p3 = m.group(1), m.group(2), m.group(3), m.group(4)
                full_num = f"+998{op}{p1}{p2}{p3}"
                formatted = f"+998 {op} {p1} {p2} {p3}"
            else:
                op, rest = m.group(5), m.group(6)
                full_num = f"+998{op}{rest}"
                formatted = f"+998 {op} {rest[:3]} {rest[3:5]} {rest[5:7]}"

            # Ищем имя/пометку в этой же строке
            note = line_clean[:m.start()] + " " + line_clean[m.end():]
            note = re.sub(r"[+:\-,()]+", " ", note).strip()
            # Фильтруем чистые цифры и слишком короткие слова
            clean_words = [w for w in note.split() if not w.isdigit() and len(w) > 1 and not w.startswith("#")]
            note_str = " ".join(clean_words)

            if full_num not in [r[0] for r in results]:
                results.append((full_num, formatted, note_str))

    return results


def extract_address(text: str, delivery_date: str = "") -> str:
    """
    Извлекает адрес доставки из текста заказа.
    Поддерживает ключевые слова, районы и эвристику.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1. Явный префикс адреса (Адрес: ..., Adres: ..., Dostavka: ...)
    for line in lines:
        m = re.match(r"^(?:адрес|adres|dostavka|доставка)\s*[:;=-]?\s*(.+)", line, re.IGNORECASE)
        if m:
            clean = m.group(1).strip()
            if len(clean) > 3:
                return clean

    # 2. Ключевые слова адреса / районов Ташкента и городов
    addr_keywords = [
        "ko'cha", "kucha", "куча", "ул.", "улица", "дом", "dom", "kvartira", "квартира",
        "etaj", "этаж", "massiv", "массив", "kvartal", "квартал", "mavze", "мавзе",
        "tuman", "туман", "rayon", "район", "shahar", "шахар", "город", "padez", "подъезд",
        "tower", "mo'ljal", "ориентир", "chapanata", "чапаната",
        "sergeli", "сергели", "yunusobod", "юнусобод", "chilonzor", "чилонзор",
        "yakkasaroy", "яккасарой", "mirobod", "миробод", "shayxontoxur", "шайхонтохур",
        "olmazor", "олмазор", "uchtepa", "учтепа", "yashnobod", "яшнобод", "bektemir", "бектемир",
        "samarqand", "самарканд", "buxoro", "бухара", "andijon", "андижан", "fargona", "фергана",
        "namangan", "наманган", "navoiy", "навои", "jizzax", "джизак"
    ]

    ignore_for_address = [
        "summa", "сумма", "suma", "сума", "olindi", "олинди", "olasila", "оласила",
        "narxi", "нархи", "narx", "нарх", "karta", "карта", "som", "сом", "$",
        "purjina", "пружина", "paralon", "паралон", "поролон", "plotns", "плотност",
        "kakos", "какос", "кокос", "qora", "кора", "tomoni", "томони", "qavat", "кават",
        "xb", "хб", "barxt", "бархат", "seriy", "серый", "palasa", "полоса", "admanka",
        "zet", "зет", "zich", "зич", "bort", "борт", "namatrasnik", "наматрасник", "chixol", "чехол",
        "garantya", "гарантия", "talon", "талон", "upakofka", "упаковка"
    ]

    for line in lines:
        lower = line.lower()
        if any(k in lower for k in addr_keywords):
            if not any(k in lower for k in ignore_for_address) and not re.search(r"\d+\s*[-+]\s*\d+", line):
                clean_addr = re.sub(r"^(?:адрес|adres|dostavka|доставка)\s*[:;=-]?\s*", "", line, flags=re.IGNORECASE).strip()
                if len(clean_addr) > 3:
                    return clean_addr

    # 3. Эвристика: строка перед датой доставки
    for i, line in enumerate(lines):
        if delivery_date and re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", line):
            if i > 0:
                candidate = lines[i-1].strip()
                cand_lower = candidate.lower()
                if (
                    not any(k in cand_lower for k in ignore_for_address)
                    and "=" not in candidate
                    and "$" not in candidate
                    and not re.search(r"^\d+\s*[-+]\s*\d+", candidate)
                    and not re.search(r"\b\d{2,3}\s*[/x*х]\s*\d{2,3}\b", candidate)
                ):
                    addr_candidate = re.sub(r"(?i)(ga|ka|ge|ke|га|ка|ге|ке)$", "", candidate).strip()
                    if len(addr_candidate) > 3:
                        return addr_candidate

    return ""


def parse_order_regex(text: str) -> OrderData:
    """
    Эвристический / RegEx парсер для заказов матрасов из Telegram.
    Поддерживает узбекский и русский языки (латиницу и кириллицу).
    """
    order = OrderData(raw_text=text.strip())
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    # 1. Извлечение хештегов (#10x10x59 #lz20)
    tags = re.findall(r"#[A-Za-z0-9_x-]+", text)
    order.order_tags = tags

    # 2. Извлечение номеров телефонов и пометок
    extracted_phones = extract_uz_phones(text)
    order.phones = [p[0] for p in extracted_phones]
    order.phone_notes = {p[0]: p[2] for p in extracted_phones if p[2]}

    # 3. Финансовый блок: Summa, Olindi, Olasila, Формулы, Валюта
    if "$" in text:
        order.currency = "USD"

    # Формула с равенством: например 430-100=330$
    math_with_eq = re.search(r"(\d[\d\s.,]*)\s*-\s*(\d[\d\s.,]*)\s*=\s*(\d[\d\s.,]*)\s*([$A-Za-z]+)?", text)
    if math_with_eq:
        tot = normalize_amount(math_with_eq.group(1))
        pre = normalize_amount(math_with_eq.group(2))
        bal = normalize_amount(math_with_eq.group(3))
        curr_sym = (math_with_eq.group(4) or "").strip()
        if "$" in curr_sym or "$" in text:
            order.currency = "USD"
        if tot > 0 and pre > 0:
            order.total_amount = tot
            order.prepayment_amount = pre
            order.balance_due = max(0.0, bal)

    # Формула после Suma / Summa: например Suma 1200000-200000 g karta
    if order.total_amount == 0:
        math_suma = re.search(r"(?:summa|suma|сумма|сума)\s*[:;=-]?[ \t]*(\d[\d\s.,]*)\s*-\s*(\d[\d\s.,]*)", text, re.IGNORECASE)
        if math_suma:
            tot = normalize_amount(math_suma.group(1))
            pre = normalize_amount(math_suma.group(2))
            if tot > 0 and pre > 0:
                order.total_amount = tot
                order.prepayment_amount = pre
                order.balance_due = max(0.0, tot - pre)

    # Одиночная сумма в долларах, например: 208$
    usd_single = re.search(r"(?:^|\s)(\d[\d\s.,]*)\s*\$", text)
    if usd_single and order.total_amount == 0:
        order.total_amount = normalize_amount(usd_single.group(1))
        order.balance_due = order.total_amount
        order.currency = "USD"

    # Summa (если не определена формулой)
    if order.total_amount == 0:
        summa_match = re.search(r"(?:summa|suma|сумма|сума|narxi|нархи|narx|нарх)\s*[:;=-]?[ \t]*(\d[\d\s.,]*)", text, re.IGNORECASE)
        if summa_match:
            order.total_amount = normalize_amount(summa_match.group(1))

    # Olindi (Предоплата / Оплачено)
    olindi_match = re.search(r"(?:olindi|олинди|avans|аванс|oplata|оплата|tolandi|туланди)\s*[:;=-]?[ \t]*(.+)", text, re.IGNORECASE)
    has_full_prepayment = False

    if olindi_match:
        olindi_val = olindi_match.group(1).splitlines()[0].strip()
        lower_olindi = olindi_val.lower()

        if "qr" in lower_olindi:
            order.prepayment_type = "QR"
        elif any(k in lower_olindi for k in ["karta", "карта", "kart", "карт", "card"]):
            order.prepayment_type = "Karta"
        elif any(k in lower_olindi for k in ["naqd", "накд", "нал", "nal"]):
            order.prepayment_type = "Naqd"
        elif "click" in lower_olindi:
            order.prepayment_type = "Click"
        elif "payme" in lower_olindi:
            order.prepayment_type = "Payme"

        if any(k in lower_olindi for k in ["hammasi", "хаммаси", "polnost", "полност", "barchasi", "барчаси", "to'liq", "тулик"]):
            order.prepayment_amount = order.total_amount
            order.balance_due = 0.0
            has_full_prepayment = True
        else:
            amount_match = re.search(r"(\d[\d\s.,]*)", olindi_val)
            if amount_match:
                order.prepayment_amount = normalize_amount(amount_match.group(1))

    # Предоплата на карту из строки Suma 1200000-200000 g karta
    if not order.prepayment_type and ("g karta" in text.lower() or "karta" in text.lower()):
        order.prepayment_type = "Karta"

    # Olasila (Остаток к получению)
    olasila_before = re.search(r"(\d[\d\s.,]*)\s*(?:som|сум|so'm)?\s*(?:olasila|оласила)", text, re.IGNORECASE)
    if olasila_before:
        order.balance_due = normalize_amount(olasila_before.group(1))
    else:
        olasila_after = re.search(r"(?:olasila|оласила|qoldiq|колдик|qoldi|колди|ostatok|остаток)\s*[:;=-]?[ \t]+(\d[\d\s.,]*)", text, re.IGNORECASE)
        if olasila_after:
            order.balance_due = normalize_amount(olasila_after.group(1))

    if order.balance_due == 0.0 and not has_full_prepayment and order.total_amount > 0:
        order.balance_due = max(0.0, order.total_amount - order.prepayment_amount)

    # 4. Дата доставки (DD.MM.YYYY или YYYY-MM-DD)
    date_matches = re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if date_matches:
        day, month, year = date_matches[-1]
        if len(year) == 2:
            year = f"20{year}"
        order.delivery_date = f"{year}-{int(month):02d}-{int(day):02d}"

    # 5. Размеры и количество
    size_pattern = re.compile(
        r"(\b\d{2,3}\s*[/x*х]\s*\d{2,3}\b)(?:[-–—\s(]*([0-9]+)\s*(?:ta|dona|шт|d)\)?)?",
        re.IGNORECASE
    )
    items = []
    for m in size_pattern.finditer(text):
        base_size = m.group(1).replace(" ", "")
        qty_str = m.group(2)
        qty = int(qty_str) if qty_str else 1
        items.append({"size": base_size, "qty": qty})

    order.items = items
    if items:
        size_strs = []
        for it in items:
            if it["qty"] > 1:
                size_strs.append(f"{it['size']} ({it['qty']} шт)")
            else:
                size_strs.append(it['size'])
        order.size = ", ".join(size_strs)

    # 6. Адрес доставки
    order.delivery_address = extract_address(text, delivery_date=order.delivery_date or "")

    # Заполняем имя клиента из пометок к телефону (например: Элла, Maniki)
    for p_num, p_note in order.phone_notes.items():
        if p_note and not order.customer_name:
            order.customer_name = p_note
            break

    # 7. Фильтрация строк для извлечения названия модели и характеристик
    content_lines: List[str] = []
    for line in lines:
        lower = line.lower()

        if line.startswith("#"):
            continue

        # Пропускаем строки с телефонами в первую очередь
        if extract_uz_phones(line):
            continue

        # Стоп на финансовом блоке или формуле расчета
        if (
            any(lower.startswith(k) for k in ["summa", "suma", "сумма", "сума", "narxi", "нархи", "narx", "нарх", "olindi", "олинди", "olasila", "оласила"])
            or re.search(r"\d+\s*-\s*\d+\s*=", line)
            or re.search(r"\d+\s*-\s*\d+.*(?:karta|карта|som|сум|\$)", lower)
            or line.strip().endswith("$")
        ):
            break

        # Пропускаем строки с датами
        if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", line):
            continue

        # Пропускаем строку адреса если она уже определена
        if order.delivery_address and (order.delivery_address in line or line in order.delivery_address):
            continue

        content_lines.append(line)

    explicit_model = None
    product_candidates = []
    spec_lines = []
    material_lines = []

    for line in content_lines:
        lower = line.lower()
        clean_decor = re.sub(r"[✨⭐💎👑🌟🔥🏷️]", "", line).strip()

        if any(k in lower for k in ["razmer", "размер"]) or re.search(r"\b\d{2,3}\s*[/x*х]\s*\d{2,3}\b", line):
            continue

        model_check = re.search(r"^(?:модель|модел|model|modeli)\s*[:;=-]?\s*(.+)", clean_decor, re.IGNORECASE)
        if model_check:
            raw_model = model_check.group(1).strip()
            clean_val = re.sub(r"[^\w\s\d/-]", "", raw_model).strip()
            explicit_model = f"Модель {clean_val}"
            continue

        if any(k in lower for k in ["material", "материал", "rangi", "ранги", "matosi", "матоси", "чехол", "chexol"]):
            clean_mat = re.sub(r"(?i)^(?:material|материал|rangi|ранги|matosi|матоси|чехол|chexol)\s*[:;=-]?\s*", "", clean_decor)
            material_lines.append(clean_mat.strip(";:, "))
            continue

        spec_keywords = [
            "purjina", "пружина", "независим", "nezavisim",
            "paralon", "паралон", "поролон", "plotns", "плотност",
            "kakos", "какос", "кокос", "qora", "кора", "черн",
            "tomoni", "томони", "qavat", "кават", "слой", "bambuk", "бамбук",
            "bezpurjniy", "безпружинный", "toper", "топер"
        ]
        if any(k in lower for k in spec_keywords):
            spec_lines.append(clean_decor)
            continue

        fabric_keywords = ["xb", "хб", "barxt", "бархат", "seriy", "серый", "naqwli", "накшли", "palasa", "полоса", "admanka", "stop", "sintetika", "синтетика"]
        if any(k in lower for k in fabric_keywords):
            material_lines.append(clean_decor)
            continue

        product_candidates.append(clean_decor)

    # Приоритет выбора названия товара:
    if explicit_model:
        order.product_name = explicit_model
        if product_candidates:
            spec_lines = product_candidates + spec_lines
    elif product_candidates:
        # Проверяем, не является ли кандидат слишком похожим на имя человека или мусор
        cand = product_candidates[0]
        if len(cand) > 1 and not cand.isdigit():
            order.product_name = cand
            if len(product_candidates) > 1:
                spec_lines.extend(product_candidates[1:])
    elif spec_lines:
        order.product_name = spec_lines[0]
        spec_lines = spec_lines[1:]
    else:
        order.product_name = "Матрас"

    if material_lines:
        order.material = ", ".join(material_lines)
    if spec_lines:
        order.details = "; ".join(spec_lines)

    return order
