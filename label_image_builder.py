from PIL import Image, ImageDraw, ImageFont
import re
from typing import Dict, Any

def create_label_image(label: Dict[str, Any]) -> Image.Image:
    """
    Создает компактное изображение наклейки 58х100 мм (464 x 800 пикселей при 203 DPI).
    Гарантированно умещается в 1 этикетку с запасом снизу 100+ пикселей.
    """
    width = 464
    height = 800

    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    # Внешняя рамка (от 15 до 730 пикселей, снизу 70 пикселей чистого запаса до среза)
    box_bottom = 720
    draw.rectangle([15, 15, width - 15, box_bottom], outline="black", width=3)

    # Подгрузка шрифтов
    try:
        font_large = ImageFont.truetype("arialbd.ttf", 32)
        font_title = ImageFont.truetype("arialbd.ttf", 26)
        font_label = ImageFont.truetype("arial.ttf", 18)
        font_regular = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font_large = font_title = font_label = font_regular = ImageFont.load_default()

    code = str(label.get("code", "—"))
    size = str(label.get("size", "—"))
    phone = str(label.get("phone", "—"))
    address = str(label.get("address", "—"))
    balance = str(label.get("balance_due", "—"))

    y = 28

    # 1. KOD
    draw.text((25, y), "KOD:", font=font_label, fill="black")
    y += 24
    draw.text((25, y), code[:28], font=font_title, fill="black")
    y += 38
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 14

    # 2. RAZMERI
    draw.text((25, y), "RAZMERI:", font=font_label, fill="black")
    y += 24
    draw.text((25, y), size[:24], font=font_large, fill="black")
    y += 42
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 14

    # 3. NOMERI
    draw.text((25, y), "NOMERI:", font=font_label, fill="black")
    y += 24
    draw.text((25, y), phone[:32], font=font_title, fill="black")
    y += 38
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 14

    # 4. ADRES (автоперенос, если длинный)
    draw.text((25, y), "ADRES:", font=font_label, fill="black")
    y += 24
    if len(address) > 28:
        # Делим на 2 строки
        part1 = address[:28]
        part2 = address[28:56]
        draw.text((25, y), part1, font=font_regular, fill="black")
        y += 28
        draw.text((25, y), part2, font=font_regular, fill="black")
        y += 34
    else:
        draw.text((25, y), address, font=font_regular, fill="black")
        y += 36
    draw.line([(20, y), (width - 20, y)], fill="black", width=2)
    y += 16

    # 5. QOGAN SUMMASI
    draw.text((25, y), "QOGAN SUMMASI:", font=font_label, fill="black")
    y += 26
    draw.text((25, y), balance[:24], font=font_large, fill="black")

    return img
