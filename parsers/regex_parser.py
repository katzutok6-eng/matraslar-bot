import re
from typing import List, Optional
from models import OrderData


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

    # 2. Извлечение номеров телефонов и пометок (например: 881978909 Maniki)
    # Узбекские 9-значные (например: 998680205, 881978909, 974493645) или с кодом +998
    phone_matches = re.finditer(r"(?:(?:\+?998)|(?:\b))([0-9]{2}[0-9]{7})\b([^\n]*)", text)
    extracted_phones = []
    phone_notes = {}
    for m in phone_matches:
        raw_p = m.group(1)
        normalized = normalize_phone(raw_p)
        note = m.group(2).strip()
        # Чистим пометку от знаков препинания и дефисов
        clean_note = re.sub(r"^[-–—:;,()\s]+|[-–—:;,()\s]+$", "", note).strip()
        
        if normalized not in extracted_phones:
            extracted_phones.append(normalized)
            if clean_note:
                phone_notes[normalized] = clean_note

    order.phones = extracted_phones
    order.phone_notes = phone_notes

    # 3. Финансовый блок: Summa, Olindi, Olasila
    # Summa (Сумма)
    summa_match = re.search(r"(?:summa|сумма|narxi|нархи|narx|нарх)\s*[:;=-]?\s*([\d\s.,]+)", text, re.IGNORECASE)
    if summa_match:
        order.total_amount = normalize_amount(summa_match.group(1))

    # Olindi (Предоплата / Оплачено)
    olindi_match = re.search(r"(?:olindi|олинди|avans|аванс|oplata|оплата|tolandi|туланди)\s*[:;=-]?\s*(.+)", text, re.IGNORECASE)
    has_full_prepayment = False

    if olindi_match:
        olindi_val = olindi_match.group(1).strip()
        lower_olindi = olindi_val.lower()

        # Способ оплаты
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

        # Сумма оплаты
        if any(k in lower_olindi for k in ["hammasi", "хаммаси", "polnost", "полност", "barchasi", "барчаси", "to'liq", "тулик"]):
            order.prepayment_amount = order.total_amount
            order.balance_due = 0.0
            has_full_prepayment = True
        else:
            amount_match = re.search(r"([\d\s.,]+)", olindi_val)
            if amount_match:
                order.prepayment_amount = normalize_amount(amount_match.group(1))

    # Olasila (Остаток к оплате / К доплате)
    olasila_match = re.search(r"(?:olasila|оласила|qoldiq|колдик|qoldi|колди|ostatok|остаток)\s*[:;=-]?\s*([\d\s.,]+)", text, re.IGNORECASE)
    if olasila_match:
        order.balance_due = normalize_amount(olasila_match.group(1))
    else:
        if has_full_prepayment:
            order.balance_due = 0.0
        elif order.total_amount > 0:
            order.balance_due = max(0.0, order.total_amount - order.prepayment_amount)

    # Формула расчета: например, 430-100=330$
    math_match = re.search(r"(\d[\d\s.,]*)\s*-\s*(\d[\d\s.,]*)\s*=\s*(\d[\d\s.,]*)\s*([$A-Za-z]+)?", text)
    if math_match:
        tot = normalize_amount(math_match.group(1))
        pre = normalize_amount(math_match.group(2))
        bal = normalize_amount(math_match.group(3))
        if tot > 0:
            order.total_amount = tot
        if pre > 0:
            order.prepayment_amount = pre
        if bal > 0:
            order.balance_due = bal

    # 4. Дата доставки (DD.MM.YYYY или YYYY-MM-DD)
    date_matches = re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if date_matches:
        day, month, year = date_matches[-1]
        if len(year) == 2:
            year = f"20{year}"
        order.delivery_date = f"{year}-{int(month):02d}-{int(day):02d}"

    # 5. Размеры и количество (179х73-1шт, 199х88-1шт, 200/180 2ta, 90/194 (3ta))
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
    # Ищем строку перед датой, исключая характеристики, ткань и финансы
    ignore_for_address = [
        "summa", "сумма", "olindi", "олинди", "olasila", "оласила",
        "narxi", "нархи", "narx", "нарх",
        "purjina", "пружина", "paralon", "паралон", "поролон", "plotns", "плотност",
        "kakos", "какос", "кокос", "qora", "кора", "tomoni", "томони", "qavat", "кават",
        "xb", "хб", "barxt", "бархат", "seriy", "серый", "palasa", "полоса", "admanka",
        "zet", "зет", "zich", "зич", "bort", "борт", "namatrasnik", "наматрасник", "chixol", "чехол"
    ]
    for i, line in enumerate(lines):
        if order.delivery_date and (re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", line)):
            if i > 0:
                candidate = lines[i-1].strip()
                cand_lower = candidate.lower()
                if (
                    not any(k in cand_lower for k in ignore_for_address)
                    and "=" not in candidate
                    and "$" not in candidate
                    and not re.search(r"^\d+\s*[-+]\s*\d+", candidate)
                ):
                    addr_candidate = re.sub(r"(?i)(ga|ka|ge|ke|га|ка|ге|ке)$", "", candidate).strip()
                    order.delivery_address = addr_candidate
                    break

    # 7. Фильтрация строк и извлечение Модели, Характеристик и Материала
    content_lines: List[str] = []
    
    for line in lines:
        lower = line.lower()
        
        # Стоп на финансовом блоке
        if any(lower.startswith(k) for k in ["summa", "сумма", "narxi", "нархи", "narx", "нарх"]):
            break
        
        # Пропускаем хештеги
        if line.startswith("#"):
            continue
            
        # Пропускаем строки с телефонными номерами
        if re.search(r"\b[0-9]{9}\b", line):
            continue

        # Пропускаем строки с датами
        if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", line):
            continue
            
        content_lines.append(line)

    explicit_model = None
    product_candidates = []
    spec_lines = []
    material_lines = []

    for line in content_lines:
        lower = line.lower()
        clean_decor = re.sub(r"[✨⭐💎👑🌟🔥🏷️]", "", line).strip()
        
        # Проверяем размер
        if any(k in lower for k in ["razmer", "размер"]) or re.search(r"\b\d{2,3}\s*[/x*х]\s*\d{2,3}\b", line):
            continue
            
        # Явное указание модели: ✨Модель М3✨ или ⚜Модель М3⚜ или Model M3
        model_check = re.search(r"^(?:модель|модел|model|modeli)\s*[:;=-]?\s*(.+)", clean_decor, re.IGNORECASE)
        if model_check:
            raw_model = model_check.group(1).strip()
            clean_val = re.sub(r"[^\w\s\d/-]", "", raw_model).strip()
            explicit_model = f"Модель {clean_val}"
            continue

        # Материал / Ткань / Цвет (Material, Rangi, Ранги, Чехол)
        if any(k in lower for k in ["material", "материал", "rangi", "ранги", "matosi", "матоси", "чехол", "chexol"]):
            clean_mat = re.sub(r"(?i)^(?:material|материал|rangi|ранги|matosi|матоси|чехол|chexol)\s*[:;=-]?\s*", "", clean_decor)
            material_lines.append(clean_mat.strip(";:, "))
            continue

        # Характеристики и слои (пружины, слои, поролон, кокос и т.д.)
        spec_keywords = [
            "purjina", "пружина", "независим", "nezavisim",
            "paralon", "паралон", "поролон", "plotns", "плотност",
            "kakos", "какос", "кокос", "qora", "кора", "черн",
            "tomoni", "томони", "qavat", "кават", "слой", "bambuk", "бамбук"
        ]
        if any(k in lower for k in spec_keywords):
            spec_lines.append(clean_decor)
            continue

        # Ткань/расцветка (oq xb, seriy, naqwli, palasa, barxt)
        fabric_keywords = ["xb", "хб", "barxt", "бархат", "seriy", "серый", "naqwli", "накшли", "palasa", "полоса", "admanka", "stop"]
        if any(k in lower for k in fabric_keywords):
            material_lines.append(clean_decor)
            continue

        # Если не подошло ни под один фильтр — кандидат на имя товара
        product_candidates.append(clean_decor)

    # Приоритет выбора названия товара:
    if explicit_model:
        order.product_name = explicit_model
        if product_candidates:
            spec_lines = product_candidates + spec_lines
    elif product_candidates:
        order.product_name = product_candidates[0]
        if len(product_candidates) > 1:
            spec_lines.extend(product_candidates[1:])
    elif spec_lines:
        order.product_name = spec_lines[0]
        spec_lines = spec_lines[1:]

    if material_lines:
        order.material = ", ".join(material_lines)
    if spec_lines:
        order.details = "; ".join(spec_lines)

    return order
