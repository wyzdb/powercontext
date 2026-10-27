"""Domain models for the orderflow demo service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Order:
    """A single order record."""

    id: str
    customer: str
    status: str
    total_cents: int
    created_at: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Order":
        return cls(
            id=str(raw["id"]),
            customer=str(raw["customer"]),
            status=str(raw["status"]),
            total_cents=int(raw["total_cents"]),
            created_at=str(raw["created_at"]),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "customer": self.customer,
            "status": self.status,
            "total_cents": self.total_cents,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Page:
    """One page of orders plus the paging metadata callers rely on."""

    items: tuple[Order, ...]
    total: int
    page: int
    page_size: int
    pages: int

    def to_mapping(self) -> dict[str, Any]:
        return {
            "items": [item.to_mapping() for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "pages": self.pages,
        }
