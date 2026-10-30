import logging
import re
from typing import Dict, Any, List, Optional
import httpx
from models import OrderData

logger = logging.getLogger(__name__)


class Bitrix24Client:
    def __init__(self, webhook_url: str, custom_fields_map: Optional[Dict[str, str]] = None):
        """
        webhook_url: например 'https://mycompany.bitrix24.ru/rest/1/abcdef12345/'
        custom_fields_map: словарь маппинга полей заказа на системные коды полей в Битрикс24 (UF_CRM_...)
        """
        self.webhook_url = webhook_url.rstrip("/") + "/"
        self.custom_fields_map = custom_fields_map or {
            "order_tags": "UF_CRM_TAGS",
            "size": "UF_CRM_MATTRESS_SIZE",
            "material": "UF_CRM_MATERIAL",
            "details": "UF_CRM_MATTRESS_DETAILS",
            "prepayment_amount": "UF_CRM_PREPAYMENT",
            "prepayment_type": "UF_CRM_PAYMENT_TYPE",
            "balance_due": "UF_CRM_BALANCE",
            "delivery_address": "UF_CRM_DELIVERY_ADDR",
            "delivery_date": "UF_CRM_DELIVERY_DATE",
        }

    @property
    def domain(self) -> str:
        """Извлекает домен Битрикс24 из вебхука для формирования прямых ссылок."""
        match = re.search(r"https?://([^/]+)", self.webhook_url)
        return match.group(1) if match else "bitrix24.ru"

    def get_deal_url(self, deal_id: int) -> str:
        """Возвращает прямую ссылку на сделку в веб-интерфейсе Битрикс24."""
        return f"https://{self.domain}/crm/deal/details/{deal_id}/"

    async def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Отправляет асинхронный REST-запрос к вебхуку Битрикс24."""
        url = f"{self.webhook_url}{method}.json"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=params or {})
            resp.raise_for_status()
            res_data = resp.json()
            if "error" in res_data:
                raise RuntimeError(f"Bitrix24 Error: {res_data.get('error_description', res_data['error'])}")
            return res_data

    async def find_contact_by_phone(self, phone: str) -> Optional[int]:
        """Ищет существующий контакт по номеру телефона (с нормализацией +998)."""
        try:
            raw_digits = re.sub(r"\D", "", phone)
            search_phones = []
            if len(raw_digits) == 9:
                search_phones.extend([f"+998{raw_digits}", raw_digits])
            elif len(raw_digits) == 12 and raw_digits.startswith("998"):
                search_phones.extend([f"+{raw_digits}", raw_digits[3:]])
            else:
                search_phones.append(phone.strip())

            for p in search_phones:
                res = await self._call("crm.contact.list", {
                    "filter": {"PHONE": p},
                    "select": ["ID", "NAME"]
                })
                contacts = res.get("result", [])
                if contacts:
                    return int(contacts[0]["ID"])
        except Exception as e:
            logger.warning(f"Не удалось найти контакт по телефону {phone}: {e}")
        return None

    async def create_contact(self, phones: List[str], name: str = "Клиент из Telegram") -> int:
        """Создает новый контакт с привязанными телефонами."""
        phone_items = []
        for p in phones:
            phone_items.append({"VALUE": p, "VALUE_TYPE": "WORK"})

        payload = {
            "fields": {
                "NAME": name,
                "TYPE_ID": "CLIENT",
                "SOURCE_ID": "TELEGRAM",
                "PHONE": phone_items
            }
        }
        res = await self._call("crm.contact.add", payload)
        return int(res["result"])

    async def find_or_create_contact(self, phones: List[str], name: str = "Клиент") -> Optional[int]:
        """Ищет контакт по любому из переданных телефонов, если нет — создает."""
        if not phones:
            return None

        for p in phones:
            contact_id = await self.find_contact_by_phone(p)
            if contact_id:
                return contact_id

        # Не найден ни один телефон -> создаем контакт
        first_phone = phones[0]
        contact_name = f"Клиент ({first_phone})"
        return await self.create_contact(phones, name=contact_name)

    def _format_deal_comments(self, order: OrderData) -> str:
        """Форматирует детальное описание заказа для поля 'Комментарий' в сделке."""
        phones_list = []
        for p in order.phones:
            note = order.phone_notes.get(p)
            phones_list.append(f"{p} ({note})" if note else p)
        phones_str = ", ".join(phones_list) if phones_list else "не указан"

        curr = getattr(order, "currency", "UZS") or "UZS"
        lines = [
            "Детали заказа из Telegram:\n",
            f"Теги: {' '.join(order.order_tags)}\n" if order.order_tags else "",
            f"Модель: {order.product_name}\n",
            f"Размер: {order.size}\n" if order.size else "",
            f"Телефоны: {phones_str}\n",
            f"Материал/чехол: {order.material}\n" if order.material else "",
            f"Наполнение/детали: {order.details}\n" if order.details else "",
            f"Общая сумма: {order.total_amount:,.0f} {curr}\n",
            f"Предоплата: {order.prepayment_amount:,.0f} {curr} ({order.prepayment_type or 'не указано'})\n",
            f"Остаток к получению: {order.balance_due:,.0f} {curr}\n",
            f"Доставка в: {order.delivery_address}\n" if order.delivery_address else "",
            f"Дата доставки: {order.delivery_date}\n" if order.delivery_date else "",
            "\n--- Исходный текст сообщения ---\n",
            f"{order.raw_text}"
        ]
        return "".join(lines)

    def _build_deal_fields(self, order: OrderData, stage_id: Optional[str] = None, contact_id: Optional[int] = None) -> Dict[str, Any]:
        """Формирует словарь полей сделки."""
        deal_title = f"{order.product_name}"
        if order.size:
            deal_title += f" {order.size}"
        if order.order_tags:
            deal_title += f" ({' '.join(order.order_tags)})"

        curr = getattr(order, "currency", "UZS") or "UZS"
        fields: Dict[str, Any] = {
            "TITLE": deal_title,
            "OPPORTUNITY": order.total_amount,
            "CURRENCY_ID": curr,
            "SOURCE_ID": "TELEGRAM",
            "COMMENTS": self._format_deal_comments(order)
        }

        if stage_id:
            fields["STAGE_ID"] = stage_id

        if contact_id:
            fields["CONTACT_ID"] = contact_id

        # Если задана дата доставки, проставляем ожидаемую дату завершения сделки CLOSEDATE
        if order.delivery_date:
            fields["CLOSEDATE"] = f"{order.delivery_date}T18:00:00+05:00"

        # Добавляем пользовательские поля UF_CRM_... если они сопоставлены
        order_dict = order.model_dump()
        for order_key, uf_code in self.custom_fields_map.items():
            val = order_dict.get(order_key)
            if val is not None and uf_code:
                if isinstance(val, list):
                    fields[uf_code] = " ".join(val)
                else:
                    fields[uf_code] = val

        return fields

    async def find_active_deal_by_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Ищет самую свежую активную (незакрытую) сделку контакта (например, созданную из Instagram)."""
        try:
            res = await self._call("crm.deal.list", {
                "filter": {"CONTACT_ID": contact_id, "CLOSED": "N"},
                "order": {"ID": "DESC"},
                "select": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY"]
            })
            deals = res.get("result", [])
            if deals:
                return deals[0]
        except Exception as e:
            logger.warning(f"Ошибка поиска активной сделки для контакта {contact_id}: {e}")
        return None

    async def create_deal(self, order: OrderData, contact_id: Optional[int] = None, stage_id: Optional[str] = "UC_5Z222Q") -> int:
        """Создает сделку в Битрикс24 со всеми стандартными и пользовательскими полями."""
        fields = self._build_deal_fields(order, stage_id=stage_id, contact_id=contact_id)

        try:
            res = await self._call("crm.deal.add", {"fields": fields})
            return int(res["result"])
        except Exception as e:
            logger.warning(f"Ошибка при создании со спецполями ({e}), создаем базовую сделку...")
            basic_fields = {
                "TITLE": fields["TITLE"],
                "OPPORTUNITY": fields["OPPORTUNITY"],
                "CURRENCY_ID": fields["CURRENCY_ID"],
                "SOURCE_ID": fields["SOURCE_ID"],
                "COMMENTS": fields["COMMENTS"],
            }
            if stage_id:
                basic_fields["STAGE_ID"] = stage_id
            if contact_id:
                basic_fields["CONTACT_ID"] = contact_id
            if "CLOSEDATE" in fields:
                basic_fields["CLOSEDATE"] = fields["CLOSEDATE"]

            res = await self._call("crm.deal.add", {"fields": basic_fields})
            return int(res["result"])

    async def update_deal(self, deal_id: int, order: OrderData, stage_id: Optional[str] = "UC_5Z222Q") -> int:
        """Обновляет существующую сделку (из Instagram или CRM) новыми деталями заказа."""
        fields = self._build_deal_fields(order, stage_id=stage_id)
        # При обновлении SOURCE_ID не перезаписываем, чтобы сохранить исходный источник (например, INSTAGRAM)
        fields.pop("SOURCE_ID", None)

        try:
            await self._call("crm.deal.update", {"id": deal_id, "fields": fields})
            return deal_id
        except Exception as e:
            logger.warning(f"Ошибка обновления сделки {deal_id} со спецполями: {e}")
            basic_fields = {
                "TITLE": fields["TITLE"],
                "OPPORTUNITY": fields["OPPORTUNITY"],
                "CURRENCY_ID": fields["CURRENCY_ID"],
                "COMMENTS": fields["COMMENTS"],
            }
            if stage_id:
                basic_fields["STAGE_ID"] = stage_id
            if "CLOSEDATE" in fields:
                basic_fields["CLOSEDATE"] = fields["CLOSEDATE"]
            await self._call("crm.deal.update", {"id": deal_id, "fields": basic_fields})
            return deal_id

    async def create_or_update_deal(
        self,
        order: OrderData,
        contact_id: Optional[int] = None,
        stage_id: Optional[str] = "UC_5Z222Q"
    ) -> tuple[int, bool]:
        """
        Умное создание/обновление сделки:
        1. Если заказ уже существует по тегам (#...) -> обновляет его без сброса стадии назад.
        2. Если у контакта уже есть активная сделка -> обновляет её.
        3. Иначе -> создает новую сделку на этапе stage_id ('Zakaz olindi').
        Возвращает кортеж: (deal_id, is_updated)
        """
        advanced_stages = {"UC_B8U2XC", "UC_MG82DT", "UC_NK07QJ", "WON"}

        # 1. Поиск по тегам
        if order.order_tags:
            existing_by_tag = await self.find_deal_by_tags(order.order_tags)
            if existing_by_tag:
                deal_id = int(existing_by_tag["ID"])
                curr_stage = existing_by_tag.get("STAGE_ID")
                effective_stage = curr_stage if curr_stage in advanced_stages else stage_id
                logger.info(f"Сделка #{deal_id} найдена по тегам (стадия: {curr_stage}). Обновляем без отката стадии.")
                await self.update_deal(deal_id, order, stage_id=effective_stage)
                return deal_id, True

        # 2. Поиск по контакту (ТОЛЬКО если заказ без уникальных тегов #...)
        if contact_id and not order.order_tags:
            active_deal = await self.find_active_deal_by_contact(contact_id)
            if active_deal:
                deal_id = int(active_deal["ID"])
                curr_stage = active_deal.get("STAGE_ID")
                effective_stage = curr_stage if curr_stage in advanced_stages else stage_id
                logger.info(f"Найдена активная сделка контакта #{deal_id} для заказа без тегов (стадия: {curr_stage}). Обновляем её.")
                await self.update_deal(deal_id, order, stage_id=effective_stage)
                return deal_id, True

        # 3. Создаем новую сделку
        deal_id = await self.create_deal(order, contact_id=contact_id, stage_id=stage_id)
        return deal_id, False

    async def move_upcoming_deals_to_ready_stage(
        self,
        from_stages: Optional[List[str]] = None,
        to_stage: str = "UC_B8U2XC",
        days_before: int = 1
    ) -> List[int]:
        """
        Проверяет все открытые сделки на этапах from_stages (по умолчанию только 'Zakaz olindi').
        Если дата готовности/доставки наступает через days_before дней или раньше (сегодня/завтра),
        переводит сделку на этап to_stage ('Zakaz tayyor bolish kuni').
        Сделки на этапе 'Zakaz yaratildi' или 'Dostavka' никогда не откатываются назад!
        """
        if from_stages is None:
            from_stages = ["UC_5Z222Q"]

        from datetime import datetime, timezone, timedelta
        tashkent_tz = timezone(timedelta(hours=5))
        today = datetime.now(tashkent_tz).date()
        target_date = today + timedelta(days=days_before)

        try:
            res = await self._call("crm.deal.list", {
                "filter": {
                    "STAGE_ID": from_stages,
                    "CLOSED": "N"
                },
                "select": ["ID", "TITLE", "STAGE_ID", "UF_CRM_DELIVERY_DATE", "CLOSEDATE"]
            })
            deals = res.get("result", [])
        except Exception as e:
            logger.error(f"Ошибка получения сделок для проверки дат готовности: {e}")
            return []

        updated_deal_ids = []
        for d in deals:
            deal_id = int(d["ID"])
            raw_date = d.get("UF_CRM_DELIVERY_DATE") or d.get("CLOSEDATE")
            if not raw_date:
                continue

            date_str = str(raw_date)[:10]
            try:
                deal_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            # Игнорируем некорректные даты далеко в прошлом (например опечатки года 0202)
            if deal_date.year < 2024:
                continue

            # Если до даты доставки остался 1 день или меньше
            if deal_date <= target_date:
                try:
                    await self._call("crm.deal.update", {
                        "id": deal_id,
                        "fields": {"STAGE_ID": to_stage}
                    })
                    updated_deal_ids.append(deal_id)
                    logger.info(f"Сделка #{deal_id} ({d.get('TITLE')}) переведена на этап '{to_stage}' (дата: {deal_date})")
                except Exception as e:
                    logger.warning(f"Не удалось обновить стадию сделки #{deal_id}: {e}")

        return updated_deal_ids

    async def find_deal_by_tags(self, tags: List[str]) -> Optional[Dict[str, Any]]:
        """Ищет сделку по одному из хештегов заказа."""
        if not tags:
            return None
        for tag in tags:
            clean_tag = tag.strip()
            if not clean_tag:
                continue
            try:
                res = await self._call("crm.deal.list", {
                    "filter": {"%TITLE": clean_tag},
                    "order": {"ID": "DESC"},
                    "select": ["ID", "TITLE", "STAGE_ID", "UF_CRM_DELIVERY_MAN"]
                })
                deals = res.get("result", [])
                if deals:
                    return deals[0]

                res_comm = await self._call("crm.deal.list", {
                    "filter": {"%COMMENTS": clean_tag},
                    "order": {"ID": "DESC"},
                    "select": ["ID", "TITLE", "STAGE_ID", "UF_CRM_DELIVERY_MAN"]
                })
                deals_comm = res_comm.get("result", [])
                if deals_comm:
                    return deals_comm[0]
            except Exception as e:
                logger.warning(f"Ошибка поиска сделки по тегу {clean_tag}: {e}")
        return None

    async def find_deal_by_phones(self, phones: List[str]) -> Optional[Dict[str, Any]]:
        """Ищет сделку по номерам телефона клиента."""
        if not phones:
            return None
        for p in phones:
            try:
                clean_phone = re.sub(r"[^\d+]", "", p)
                contact_id = await self.find_contact_by_phone(clean_phone)
                if contact_id:
                    deal = await self.find_active_deal_by_contact(contact_id)
                    if deal:
                        return deal

                raw_digits = re.sub(r"\D", "", p)
                if len(raw_digits) >= 9:
                    sub = raw_digits[-9:]
                    res = await self._call("crm.deal.list", {
                        "filter": {"%COMMENTS": sub},
                        "order": {"ID": "DESC"},
                        "select": ["ID", "TITLE", "STAGE_ID", "UF_CRM_DELIVERY_MAN"]
                    })
                    deals = res.get("result", [])
                    if deals:
                        return deals[0]
            except Exception as e:
                logger.warning(f"Ошибка поиска сделки по телефону {p}: {e}")
        return None

    async def find_deal_by_id(self, deal_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные сделки по её ID."""
        try:
            res = await self._call("crm.deal.get", {"id": deal_id})
            return res.get("result")
        except Exception as e:
            logger.warning(f"Ошибка получения сделки #{deal_id}: {e}")
        return None

    async def find_deal_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Умный поиск сделки из текста (по ID, хештегам или номерам телефонов)."""
        if not text:
            return None

        # 1. Поиск прямого ID сделки (#123, Сделка #123, details/123/)
        id_match = re.search(r"(?:сделка|deal|zakaz|заказ)\s*#?\s*(\d+)", text, re.IGNORECASE)
        if not id_match:
            id_match = re.search(r"/crm/deal/details/(\d+)/", text)
        if id_match:
            deal = await self.find_deal_by_id(int(id_match.group(1)))
            if deal:
                return deal

        # 2. Поиск по хештегам (#19x10x108, #lz36, etc.)
        tags = re.findall(r"#[A-Za-z0-9_x-]+", text)
        if tags:
            deal = await self.find_deal_by_tags(tags)
            if deal:
                return deal

        # 3. Поиск по телефонам (+998...)
        phones = re.findall(r"(?:\+?998)?[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}", text)
        if phones:
            deal = await self.find_deal_by_phones(phones)
            if deal:
                return deal

        return None

    async def update_deal_stage_and_courier(
        self,
        deal_id: int,
        stage_id: str,
        courier_id: Optional[int] = None
    ) -> bool:
        """Переводит сделку на этап stage_id и опционально проставляет курьера."""
        fields: Dict[str, Any] = {"STAGE_ID": stage_id}
        if courier_id is not None:
            fields["UF_CRM_DELIVERY_MAN"] = courier_id

        try:
            await self._call("crm.deal.update", {
                "id": deal_id,
                "fields": fields
            })
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления сделки #{deal_id}: {e}")
            return False

