from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    sku: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    model_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_id_web: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    gift_promotion: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True, server_default=text("0"))
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))

    # Category-specific specs live in JSONB — no per-category columns/entities.
    specifications: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    brand: Mapped["Brand"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
