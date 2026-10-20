from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any

def create_label_image(label: Dict[str, Any]) -> Image.Image:
    """
    Создает чистое, высококонтрастное черно-белое изображение наклейки 58х100 мм.
    Разрешение: 464 x 800 пикселей (203 DPI).
    """
    width = 464
    height = 800

    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    # Внешняя рамка
    draw.rectangle([10, 10, width - 10, height - 10], outline="black", width=4)

    # Шрифты
    try:
        font_large = ImageFont.truetype("arialbd.ttf", 36)
        font_mid = ImageFont.truetype("arialbd.ttf", 30)
        font_label = ImageFont.truetype("arial.ttf", 22)
        font_regular = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        font_large = font_mid = font_label = font_regular = ImageFont.load_default()

    code = label.get("code", "—")
    size = label.get("size", "—")
    phone = label.get("phone", "—")
    address = label.get("address", "—")
    balance = label.get("balance_due", "—")

    y = 25

    # 1. KOD
    draw.text((25, y), "KOD:", font=font_label, fill="black")
    y += 30
    draw.text((25, y), str(code)[:24], font=font_mid, fill="black")
    y += 50
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 20

    # 2. RAZMERI (крупно)
    draw.text((25, y), "RAZMERI:", font=font_label, fill="black")
    y += 30
    draw.text((25, y), str(size)[:24], font=font_large, fill="black")
    y += 55
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 20

    # 3. NOMERI
    draw.text((25, y), "NOMERI:", font=font_label, fill="black")
    y += 30
    draw.text((25, y), str(phone)[:28], font=font_mid, fill="black")
    y += 50
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 20

    # 4. ADRES
    draw.text((25, y), "ADRES:", font=font_label, fill="black")
    y += 30
    # Если адрес длинный, разбиваем на 2 строки
    addr_str = str(address)
    if len(addr_str) > 28:
        draw.text((25, y), addr_str[:28], font=font_regular, fill="black")
        y += 35
        draw.text((25, y), addr_str[28:56], font=font_regular, fill="black")
    else:
        draw.text((25, y), addr_str, font=font_regular, fill="black")
    y += 45
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 25

    # 5. QOGAN SUMMASI
    draw.text((25, y), "QOGAN SUMMASI:", font=font_label, fill="black")
    y += 35
    draw.text((25, y), str(balance)[:24], font=font_large, fill="black")

    return img
