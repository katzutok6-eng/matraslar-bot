"""
Print Agent для термопринтера этикеток iPOS MA-0780B (Windows).
Автоматически опрашивает сервер Render и отправляет наклейки 58х100 мм на печать.
"""

import sys
import re
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
    code = str(label.get("code", "—"))
    product = str(label.get("product", "")).strip() or "Matras"
    size = str(label.get("size", "—"))
    phone = str(label.get("phone", "—"))
    address = str(label.get("address", "—"))
    balance = str(label.get("balance_due", "—"))

    # Разделение телефона и имени (чтобы скобки не вылезали за рамку)
    phone_clean = phone.strip()
    m_phone = re.match(r"(.*?)\s*\((.*?)\)$", phone_clean)
    if m_phone:
        p_num = m_phone.group(1).strip()
        p_name = f"({m_phone.group(2).strip()})"
    else:
        m_p2 = re.match(r"([\+\d\s\-]+)\s+([A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ].*)", phone_clean)
        if m_p2:
            p_num = m_p2.group(1).strip()
            p_name = f"({m_p2.group(2).strip()})"
        elif len(phone_clean) > 22:
            idx = phone_clean[:22].rfind(" ")
            p_num = phone_clean[:idx].strip() if idx > 7 else phone_clean[:22]
            p_name = phone_clean[len(p_num):].strip()
        else:
            p_num = phone_clean
            p_name = ""

    # Автоперенос адреса
    words = address.split()
    addr_lines = []
    curr_line = ""
    for w in words:
        if not curr_line:
            curr_line = w
        elif len(curr_line) + 1 + len(w) <= 25:
            curr_line += " " + w
        else:
            addr_lines.append(curr_line)
            curr_line = w
    if curr_line:
        addr_lines.append(curr_line)
    if not addr_lines:
        addr_lines = ["—"]

    # Сумма и валюта
    m_sum = re.match(r"^([\d\s\.,]+)\s*([A-Za-zА-Яа-яЁё\$]+)?$", balance.strip())
    if m_sum and len(m_sum.group(1).strip()) <= 10:
        b_amt = m_sum.group(1).strip()
        b_curr = m_sum.group(2) or ""
    else:
        b_amt = balance.strip()
        b_curr = ""

    tspl = [
        "SIZE 58 mm, 100 mm",
        "GAP 2 mm, 0 mm",
        "DIRECTION 1,0",
        "CODEPAGE 1251",
        "CLS",
        # Рамка: опущена ниже (Y=35) и увеличена по высоте (Y=665)
        "BOX 15,35,450,665,2",
        # 1. KOD
        'TEXT 25,48,"3",0,1,1,"KOD:"',
        f'TEXT 25,78,"3",0,1,2,"{code[:25]}"',
        "BAR 15,130,435,2",
        # 2. MAHSULOT / RAZMERI
        'TEXT 25,140,"3",0,1,1,"MAHSULOT / RAZMERI:"',
        f'TEXT 25,168,"3",0,1,2,"{product[:25]}"',
    ]

    if len(size) <= 10:
        tspl.append(f'TEXT 25,220,"3",0,2,2,"{size}"')
    else:
        tspl.append(f'TEXT 25,220,"3",0,1,2,"{size[:24]}"')

    tspl.extend([
        "BAR 15,272,435,2",
        # 3. NOMERI
        'TEXT 25,282,"3",0,1,1,"NOMERI:"',
        f'TEXT 25,312,"3",0,1,2,"{p_num[:25]}"',
    ])

    if p_name:
        tspl.append(f'TEXT 25,355,"3",0,1,1,"{p_name[:25]}"')

    tspl.extend([
        "BAR 15,395,435,2",
        # 4. ADRES
        'TEXT 25,405,"3",0,1,1,"ADRES:"',
    ])

    if len(addr_lines) == 1:
        tspl.append(f'TEXT 25,438,"3",0,1,1,"{addr_lines[0][:26]}"')
    elif len(addr_lines) == 2:
        tspl.append(f'TEXT 25,435,"3",0,1,1,"{addr_lines[0][:26]}"')
        tspl.append(f'TEXT 25,465,"3",0,1,1,"{addr_lines[1][:26]}"')
    else:
        tspl.append(f'TEXT 25,430,"3",0,1,1,"{addr_lines[0][:26]}"')
        tspl.append(f'TEXT 25,458,"3",0,1,1,"{addr_lines[1][:26]}"')
        tspl.append(f'TEXT 25,486,"3",0,1,1,"{addr_lines[2][:26]}"')

    tspl.extend([
        "BAR 15,520,435,2",
        # 5. QOGAN SUMMASI
        'TEXT 25,532,"3",0,1,1,"QOGAN SUMMASI:"',
    ])

    if balance.strip().endswith("$"):
        val = balance.strip()[:-1].strip()
        tspl.append(f'TEXT 25,572,"3",0,2,2,"{val}"')
        curr_x = 25 + len(val) * 32 + 10
        tspl.append(f'TEXT {curr_x},585,"3",0,1,2,"$"')
    elif b_curr:
        tspl.append(f'TEXT 25,572,"3",0,2,2,"{b_amt}"')
        curr_x = 25 + len(b_amt) * 32 + 10
        tspl.append(f'TEXT {curr_x},585,"3",0,1,2,"{b_curr}"')
    else:
        if len(b_amt) <= 10:
            tspl.append(f'TEXT 25,572,"3",0,2,2,"{b_amt}"')
        else:
            tspl.append(f'TEXT 25,578,"3",0,1,2,"{b_amt[:25]}"')

    tspl.append("PRINT 1,1")
    tspl.append("")

    raw_str = "\r\n".join(tspl)
    return raw_str.encode("cp1251", errors="replace")


def print_label_raw(printer_name: str, label: dict) -> bool:
    """Печатает наклейку через прямой RAW TSPL протокол (стоп ровно на зазоре наклейки)."""
    if not HAS_WIN32 or not printer_name:
        # Режим тестирования в консоль
        logger.info(f"[ТЕСТОВАЯ ПЕЧАТЬ] Наклейка:\n{json.dumps(label, ensure_ascii=False, indent=2)}")
        return True

    # 1. Прямой аппаратный вывод TSPL (гарантирует точный размер 58х100 мм и стоп по датчику зазора)
    try:
        raw_data = generate_tspl_bytes(label)
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Matraslar TSPL Label", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, raw_data)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)

        logger.info(f"✅ Напечатана 1 наклейка (TSPL): {label.get('product')} {label.get('size')} для {label.get('code')}")
        return True
    except Exception as e:
        logger.warning(f"Ошибка прямого вывода TSPL ({e}), пробуем через Windows GDI драйвер...")

    # 2. Запасной вариант через GDI
    try:
        img = create_label_image(label)
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        try:
            w = hDC.GetDeviceCaps(win32con.HORZRES)
            h = hDC.GetDeviceCaps(win32con.VERTRES)
            hDC.StartDoc("Matraslar GDI Label")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (0, 0, w, h))

            hDC.EndPage()
            hDC.EndDoc()
        finally:
            hDC.DeleteDC()

        logger.info(f"✅ Напечатана 1 наклейка (GDI): {label.get('size')}")
        return True
    except Exception as e2:
        logger.error(f"❌ Ошибка печати: {e2}")
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
