import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str = "8942360382:AAGOIipze9lGIjVwwuNWCN4YasR1geMaKPg"
    ALLOWED_CHAT_IDS: Optional[str] = None  # Например: "-1001234567890,-1009876543210"

    # Bitrix24 Webhook URL
    BITRIX_WEBHOOK_URL: str = "https://matraslar.bitrix24.uz/rest/7/4n7isora87z2wykc/"
    
    # Стадия сделки по умолчанию при создании из Telegram ("Zakaz olindi")
    DEFAULT_STAGE_ID: str = "UC_5Z222Q"

    # Стадия за 1 день до готовности / доставки ("Zakaz tayyor bolish kuni")
    READY_DATE_STAGE_ID: str = "UC_B8U2XC"

    # Стадия готовности ("Zakaz yaratildi")
    ZAKAZ_YARATILDI_STAGE_ID: str = "UC_MG82DT"

    # Стадия доставки ("Dostavka")
    DOSTAVKA_STAGE_ID: str = "UC_NK07QJ"

    # AI API Keys (опционально, для интеллектуального парсинга сленга)
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Коды пользовательских полей в Битрикс24 (UF_CRM_...)
    UF_CRM_DELIVERY_MAN: str = "UF_CRM_DELIVERY_MAN"
    UF_CRM_TAGS: str = "UF_CRM_TAGS"
    UF_CRM_MATTRESS_SIZE: str = "UF_CRM_MATTRESS_SIZE"
    UF_CRM_MATERIAL: str = "UF_CRM_MATERIAL"
    UF_CRM_DETAILS: str = "UF_CRM_DETAILS"
    UF_CRM_PREPAYMENT: str = "UF_CRM_PREPAYMENT"
    UF_CRM_PAY_TYPE: str = "UF_CRM_PAY_TYPE"
    UF_CRM_BALANCE: str = "UF_CRM_BALANCE"
    UF_CRM_DELIVERY_ADDR: str = "UF_CRM_DELIVERY_ADDR"
    UF_CRM_DELIVERY_DATE: str = "UF_CRM_DELIVERY_DATE"

    # Справочник курьеров (ID значений списочного поля UF_CRM_DELIVERY_MAN)
    COURIER_MAP: dict = {
        "orif": {"id": 45, "name": "Orif"},
        "bilol": {"id": 47, "name": "Bilol"},
        "zohit": {"id": 49, "name": "Zohit"}
    }

    # Секретный токен для подключения локального агента печати на ноутбуке
    PRINT_SECRET_TOKEN: str = "matraslar_print_secret_2026"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_allowed_chats(self) -> List[int]:
        if not self.ALLOWED_CHAT_IDS:
            return []
        return [int(cid.strip()) for cid in self.ALLOWED_CHAT_IDS.split(",") if cid.strip()]

    def get_custom_fields_map(self) -> dict:
        return {
            "order_tags": self.UF_CRM_TAGS,
            "size": self.UF_CRM_MATTRESS_SIZE,
            "material": self.UF_CRM_MATERIAL,
            "details": self.UF_CRM_DETAILS,
            "prepayment_amount": self.UF_CRM_PREPAYMENT,
            "prepayment_type": self.UF_CRM_PAY_TYPE,
            "balance_due": self.UF_CRM_BALANCE,
            "delivery_address": self.UF_CRM_DELIVERY_ADDR,
            "delivery_date": self.UF_CRM_DELIVERY_DATE,
        }


settings = Settings()
