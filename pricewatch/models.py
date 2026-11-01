from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Strategy(enum.StrEnum):
    auto = "auto"  # shopify → jsonld → css → heuristic
    shopify = "shopify"
    woocommerce = "woocommerce"  # WP Store API JSON, no browser needed
    jsonld = "jsonld"
    css = "css"
    heuristic = "heuristic"


class LinkStatus(enum.StrEnum):
    pending = "pending"
    found = "found"
    not_found = "not_found"
    error = "error"


class AlertKind(enum.StrEnum):
    flash_sale = "flash_sale"
    target_hit = "target_hit"
    all_time_low = "all_time_low"
    back_in_stock = "back_in_stock"
    test = "test"


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(300))
    # `{q}` is replaced with the URL-encoded search query
    search_url: Mapped[str] = mapped_column(String(500))
    strategy: Mapped[Strategy] = mapped_column(Enum(Strategy), default=Strategy.auto)
    render_js: Mapped[bool] = mapped_column(Boolean, default=True)
    # CSS selectors: {"card": "...", "title": "...", "price": "...", "link": "...",
    #                 "product_price": "..."} — product_price is for pinned product pages
    selectors: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trusted: Mapped[bool] = mapped_column(Boolean, default=True)
    min_interval_sec: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    links: Mapped[list[ItemVendor]] = relationship(back_populates="vendor", cascade="all, delete")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(String(200))  # search text sent to vendors
    category: Mapped[str] = mapped_column(String(80), default="Home electronics")
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    links: Mapped[list[ItemVendor]] = relationship(
        back_populates="item", cascade="all, delete", order_by="ItemVendor.vendor_id"
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="item", cascade="all, delete")


class ItemVendor(Base):
    """The item as seen on one vendor: the discovered (or pinned) product URL and status."""

    __tablename__ = "item_vendors"
    __table_args__ = (UniqueConstraint("item_id", "vendor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"))
    product_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[LinkStatus] = mapped_column(Enum(LinkStatus), default=LinkStatus.pending)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    item: Mapped[Item] = relationship(back_populates="links")
    vendor: Mapped[Vendor] = relationship(back_populates="links")
    snapshots: Mapped[list[PriceSnapshot]] = relationship(
        back_populates="link", cascade="all, delete", order_by="PriceSnapshot.captured_at"
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (Index("ix_snap_link_time", "item_vendor_id", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_vendor_id: Mapped[int] = mapped_column(ForeignKey("item_vendors.id", ondelete="CASCADE"))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EGP")
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    link: Mapped[ItemVendor] = relationship(back_populates="snapshots")


class MarketRate(Base):
    """kind ∈ usd_egp | gold_usd_oz | gold_egp_21k_g"""

    __tablename__ = "market_rates"
    __table_args__ = (Index("ix_rate_kind_time", "kind", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(80))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True
    )
    item_vendor_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_vendors.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[AlertKind] = mapped_column(Enum(AlertKind))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    send_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped[Item | None] = relationship(back_populates="alerts")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
