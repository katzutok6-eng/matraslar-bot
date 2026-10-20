from typing import List, Optional
from pydantic import BaseModel, Field


class OrderData(BaseModel):
    """Сделка/заказ, извлечённый из сообщения в Telegram группе."""

    order_tags: List[str] = Field(
        default_factory=list,
        description="Хештеги заказа (например: ['#10x10x59', '#lz20'])"
    )
    phones: List[str] = Field(
        default_factory=list,
        description="Номера телефонов клиента в формате +998XXXXXXXXX"
    )
    phone_notes: dict[str, str] = Field(
        default_factory=dict,
        description="Пометки к номерам (например: {'+998881978909': 'Maniki', '+998974493645': 'Erimliki'})"
    )
    product_name: str = Field(
        default="Матрас",
        description="Название модели или изделия (например: 'Toper 10 sm', 'Mayami kaprz')"
    )
    size: Optional[str] = Field(
        default=None,
        description="Размер изделия (например: '200/175', '200/180')"
    )
    items: List[dict] = Field(
        default_factory=list,
        description="Список отдельных позиций/размеров с количеством [{'size': '179х73', 'qty': 1}, ...]"
    )
    material: Optional[str] = Field(
        default=None,
        description="Ткань, цвет, боковины (например: 'oq xb yoni jigaren barxt🤎orqasi stop')"
    )
    details: Optional[str] = Field(
        default=None,
        description="Характеристики/наполнение (пружины, слои, плотность поролона)"
    )
    total_amount: float = Field(
        default=0.0,
        description="Общая сумма заказа (Summa)"
    )
    prepayment_amount: float = Field(
        default=0.0,
        description="Сумма предоплаты (Olindi)"
    )
    prepayment_type: Optional[str] = Field(
        default=None,
        description="Способ оплаты (karta, QR, naqd, etc.)"
    )
    balance_due: float = Field(
        default=0.0,
        description="Остаток к получению (Olasila)"
    )
    delivery_address: Optional[str] = Field(
        default=None,
        description="Адрес или локация доставки (например: 'Limanariya', 'Sergili')"
    )
    delivery_date: Optional[str] = Field(
        default=None,
        description="Дата доставки (в формате YYYY-MM-DD или DD.MM.YYYY)"
    )
    raw_text: str = Field(
        default="",
        description="Исходный текст сообщения из Telegram"
    )

    def summary_title(self) -> str:
        tags_str = " ".join(self.order_tags)
        size_str = f" ({self.size})" if self.size else ""
        return f"{self.product_name}{size_str} {tags_str}".strip()
