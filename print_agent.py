"""
Print Agent для термопринтера этикеток iPOS MA-0780B (Windows).
Автоматически опрашивает сервер Render и отправляет наклейки 58х100 мм на печать.
"""

import sys
import time
import json
import logging
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Настройка логирования в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PrintAgent")

# Конфигурация сервера
SERVER_URL = "https://matraslar-bot.onrender.com"
POLL_INTERVAL_SEC = 2.5
SECRET_TOKEN = "matraslar_print_secret_2026"

# Попытка импорта Windows-печати (win32print, win32ui)
try:
    import win32print
    import win32ui
    import win32con
    from PIL import Image, ImageDraw, ImageFont, ImageWin
    from label_image_builder import create_label_image
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("Модуль pywin32 или Pillow не установлен. Будет использован эмулятор/прямой вывод.")


def find_ipos_printer():
    """Находит подключенный принтер iPOS / MA-0780B среди принтеров Windows."""
    if not HAS_WIN32:
        return "DEFAULT_PRINTER"

    try:
        printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        logger.info(f"Найденные принтеры в Windows: {printers}")
        
        # 1. Ищем по ключевым словам
        for name in printers:
            lower = name.lower()
            if any(k in lower for k in ["ipos", "0780", "ma-0780", "barcode", "label", "xprinter", "pos-"]):
                return name
        
        # 2. Если не нашли по имени, берем принтер по умолчанию
        default_printer = win32print.GetDefaultPrinter()
        logger.info(f"Принтер по умолчанию: {default_printer}")
        return default_printer
    except Exception as e:
        logger.error(f"Ошибка поиска принтера: {e}")
        return None


def generate_tspl_bytes(label: dict) -> bytes:
    """
    Генерирует бинарные команды TSPL для термопринтера 203 DPI (размер 58х100 мм).
    58 мм = ~464 точки, 100 мм = ~800 точек.
    """
    code = label.get("code", "—")
    size = label.get("size", "—")
    phone = label.get("phone", "—")
    address = label.get("address", "—")
    balance = label.get("balance_due", "—")

    # Формируем TSPL команды
    commands = [
        "SIZE 58 mm, 100 mm",
        "GAP 2 mm, 0 mm",
        "DIRECTION 1,0",
        "CLS",
        # Рамка этикетки
        "BOX 10,10,454,790,3",
        # Код заказа
        "TEXT 30,40,\"TSS24.BF2\",0,1,1,\"KOD:\"",
        f"TEXT 30,70,\"TSS24.BF2\",0,2,2,\"{code[:24]}\"",
        "BAR 20,150,424,3",
        # Размер изделия (крупно)
        "TEXT 30,170,\"TSS24.BF2\",0,1,1,\"RAZMERI:\"",
        f"TEXT 30,200,\"TSS24.BF2\",0,2,2,\"{size[:24]}\"",
        "BAR 20,290,424,3",
        # Телефон
        "TEXT 30,310,\"TSS24.BF2\",0,1,1,\"NOMERI:\"",
        f"TEXT 30,340,\"TSS24.BF2\",0,1,2,\"{phone[:30]}\"",
        "BAR 20,430,424,3",
        # Адрес доставки
        "TEXT 30,450,\"TSS24.BF2\",0,1,1,\"ADRES:\"",
        f"TEXT 30,480,\"TSS24.BF2\",0,1,1,\"{address[:40]}\"",
        "BAR 20,580,424,3",
        # Остаток к получению (очень крупно)
        "TEXT 30,600,\"TSS24.BF2\",0,1,1,\"QOGAN SUMMASI:\"",
        f"TEXT 30,640,\"TSS24.BF2\",0,2,2,\"{balance[:24]}\"",
        "PRINT 1,1",
        ""
    ]
    raw_str = "\r\n".join(commands)
    return raw_str.encode("cp1251", errors="replace")


def print_label_raw(printer_name: str, label: dict) -> bool:
    """Печатает наклейку через Windows GDI драйвер с автоматическим откатом на TSPL."""
    if not HAS_WIN32 or not printer_name:
        # Режим тестирования в консоль
        logger.info(f"[ТЕСТОВАЯ ПЕЧАТЬ] Наклейка:\n{json.dumps(label, ensure_ascii=False, indent=2)}")
        return True

    # 1. Попытка GDI печати через драйвер (идеальные шрифты и центровка)
    try:
        img = create_label_image(label)
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        try:
            w = hDC.GetDeviceCaps(win32con.HORZRES)
            h = hDC.GetDeviceCaps(win32con.VERTRES)
            hDC.StartDoc("Matraslar Label")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (0, 0, w, h))

            hDC.EndPage()
            hDC.EndDoc()
        finally:
            hDC.DeleteDC()

        logger.info(f"✅ Успешно напечатана наклейка (GDI): {label.get('size')} для {label.get('code')}")
        return True
    except Exception as e:
        logger.warning(f"Предупреждение GDI печати ({e}), пробуем прямой вывод RAW TSPL...")

    # 2. Откат на прямые команды TSPL
    try:
        raw_data = generate_tspl_bytes(label)
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Matraslar Label", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, raw_data)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)

        logger.info(f"✅ Успешно напечатана наклейка (RAW TSPL): {label.get('size')} для {label.get('code')}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки на принтер {printer_name}: {e}")
        return False


def fetch_pending_jobs():
    """Запрашивает очередь печати с сервера Render."""
    url = f"{SERVER_URL}/api/print-queue?token={SECRET_TOKEN}"
    req = urllib.request.Request(url, headers={"User-Agent": "MatraslarPrintAgent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("jobs", [])
    except urllib.error.URLError as e:
        # Сервер перезагружается или нет связи
        pass
    except Exception as e:
        logger.warning(f"Ошибка опроса очереди: {e}")
    return []


def confirm_job_done(job_id: int):
    """Подтверждает серверу успешную печать задания."""
    url = f"{SERVER_URL}/api/print-ack?token={SECRET_TOKEN}"
    payload = json.dumps({"job_id": job_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "MatraslarPrintAgent/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"Ошибка подтверждения задания #{job_id}: {e}")
        return False


def main():
    print("=" * 60)
    print("   🖨  MATRASLAR BOT — АГЕНТ ПЕЧАТИ ЭТИКЕТОК 58x100 мм")
    print(f"   Подключение к серверу: {SERVER_URL}")
    print("=" * 60)

    printer_name = find_ipos_printer()
    print(f"\n[+] Выбран принтер: {printer_name}\n")
    print("[*] Ожидание заказов из Telegram... (нажмите Ctrl+C для выхода)\n")

    while True:
        try:
            jobs = fetch_pending_jobs()
            if jobs:
                for job in jobs:
                    job_id = job["id"]
                    deal_id = job["deal_id"]
                    labels = job.get("labels", [])
                    logger.info(f"📥 Получено задание #{job_id}: Сделка #{deal_id} ({len(labels)} наклеек)")

                    all_ok = True
                    for lbl in labels:
                        ok = print_label_raw(printer_name, lbl)
                        if not ok:
                            all_ok = False
                        time.sleep(0.3)  # Пауза 300мс между наклейками для качественной протяжки

                    if all_ok:
                        confirm_job_done(job_id)
                        logger.info(f"🎉 Задание #{job_id} полностью напечатано!")

            time.sleep(POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\n[!] Остановка агента печати.")
            break
        except Exception as e:
            logger.error(f"Непредвиденная ошибка в цикле: {e}")
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
