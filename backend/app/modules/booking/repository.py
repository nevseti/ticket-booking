"""Доступ к удержаниям и проданным местам.

Ключевые операции написаны явным SQL: их корректность при конкурентном доступе держится на
семантике PostgreSQL (частичный уникальный индекс, ON CONFLICT, условный UPDATE), и так её
проще проверить и объяснить.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class HoldRow:
    id: uuid.UUID
    event_id: uuid.UUID
    seat_id: int
    user_id: uuid.UUID
    expires_at: datetime


_HOLD_COLUMNS = "id, event_id, seat_id, user_id, expires_at"

# Захват места — ОДНА вставка. Гонку двух пользователей за одно место разрешает
# частичный уникальный индекс ux_holds_active_seat: второй INSERT не пройдёт
# (ON CONFLICT DO NOTHING → 0 строк), без SELECT-перед-INSERT и без блокировок в приложении.
_CAPTURE_SQL = text(f"""
    INSERT INTO booking.holds (event_id, seat_id, user_id, status, expires_at)
    SELECT :event_id, :seat_id, :user_id, 'active', now() + make_interval(secs => :ttl)
    WHERE NOT EXISTS (
        SELECT 1 FROM booking.sold_seats WHERE event_id = :event_id AND seat_id = :seat_id
    )
    ON CONFLICT (event_id, seat_id) WHERE status = 'active' DO NOTHING
    RETURNING {_HOLD_COLUMNS}
""")

# Ленивое истечение: now() нельзя использовать в предикате индекса, поэтому просроченное
# удержание остаётся «active», пока его не погасят — здесь или фоновым уборщиком.
_EXPIRE_SEATS_SQL = text(f"""
    UPDATE booking.holds SET status = 'expired', closed_at = now()
    WHERE event_id = :event_id AND seat_id = ANY(:seat_ids)
      AND status = 'active' AND expires_at <= now()
    RETURNING {_HOLD_COLUMNS}
""")


def _row(r) -> HoldRow:
    return HoldRow(r.id, r.event_id, r.seat_id, r.user_id, r.expires_at)


class HoldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user_event(self, user_id: uuid.UUID, event_id: uuid.UUID) -> None:
        """Сериализует запросы ОДНОГО пользователя по ОДНОМУ мероприятию (лимит мест),
        не мешая остальным: блокировка снимается в конце транзакции."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"hold:{user_id}:{event_id}"},
        )

    async def lock_zone(self, event_id: uuid.UUID, section_id: int) -> None:
        """Сериализует захват мест в ОДНОЙ стоячей зоне. Без неё две транзакции, берущие
        по несколько мест зоны, могут ждать вставок друг друга крест-накрест (deadlock).
        Сидячие места не сериализуются: там одна вставка на запрос, взаимоблокировки нет."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"zone:{event_id}:{section_id}"},
        )

    async def count_active(self, user_id: uuid.UUID, event_id: uuid.UUID) -> int:
        result = await self._session.scalar(
            text("""
                SELECT count(*) FROM booking.holds
                WHERE user_id = :user_id AND event_id = :event_id
                  AND status = 'active' AND expires_at > now()
            """),
            {"user_id": user_id, "event_id": event_id},
        )
        return int(result or 0)

    async def expire_stale(self, event_id: uuid.UUID, seat_ids: list[int]) -> list[HoldRow]:
        rows = await self._session.execute(
            _EXPIRE_SEATS_SQL, {"event_id": event_id, "seat_ids": seat_ids}
        )
        return [_row(r) for r in rows]

    async def try_capture(
        self, event_id: uuid.UUID, seat_id: int, user_id: uuid.UUID, ttl_seconds: int
    ) -> HoldRow | None:
        row = (
            await self._session.execute(
                _CAPTURE_SQL,
                {
                    "event_id": event_id,
                    "seat_id": seat_id,
                    "user_id": user_id,
                    "ttl": ttl_seconds,
                },
            )
        ).first()
        return _row(row) if row else None

    async def active_on_seat(self, event_id: uuid.UUID, seat_id: int) -> HoldRow | None:
        row = (
            await self._session.execute(
                text(f"""
                    SELECT {_HOLD_COLUMNS} FROM booking.holds
                    WHERE event_id = :event_id AND seat_id = :seat_id AND status = 'active'
                """),
                {"event_id": event_id, "seat_id": seat_id},
            )
        ).first()
        return _row(row) if row else None

    async def free_seats(self, event_id: uuid.UUID, candidates: list[int], limit: int) -> list[int]:
        """Свободные места из списка (для стоячей зоны), в случайном порядке — чтобы
        одновременные покупатели не сталкивались на одних и тех же «первых» местах."""
        rows = await self._session.scalars(
            text("""
                SELECT s.seat_id FROM unnest(CAST(:candidates AS integer[])) AS s(seat_id)
                WHERE NOT EXISTS (
                    SELECT 1 FROM booking.holds h
                    WHERE h.event_id = :event_id AND h.seat_id = s.seat_id
                      AND h.status = 'active' AND h.expires_at > now()
                )
                AND NOT EXISTS (
                    SELECT 1 FROM booking.sold_seats ss
                    WHERE ss.event_id = :event_id AND ss.seat_id = s.seat_id
                )
                ORDER BY random()
                LIMIT :limit
            """),
            {"event_id": event_id, "candidates": candidates, "limit": limit},
        )
        return list(rows)

    async def release(self, hold_id: uuid.UUID, user_id: uuid.UUID) -> HoldRow | None:
        row = (
            await self._session.execute(
                text(f"""
                    UPDATE booking.holds SET status = 'released', closed_at = now()
                    WHERE id = :hold_id AND user_id = :user_id AND status = 'active'
                    RETURNING {_HOLD_COLUMNS}
                """),
                {"hold_id": hold_id, "user_id": user_id},
            )
        ).first()
        return _row(row) if row else None

    async def release_all(self, user_id: uuid.UUID, event_id: uuid.UUID) -> list[HoldRow]:
        rows = await self._session.execute(
            text(f"""
                UPDATE booking.holds SET status = 'released', closed_at = now()
                WHERE user_id = :user_id AND event_id = :event_id AND status = 'active'
                RETURNING {_HOLD_COLUMNS}
            """),
            {"user_id": user_id, "event_id": event_id},
        )
        return [_row(r) for r in rows]

    async def my_active(self, user_id: uuid.UUID, event_id: uuid.UUID) -> list[HoldRow]:
        rows = await self._session.execute(
            text(f"""
                SELECT {_HOLD_COLUMNS} FROM booking.holds
                WHERE user_id = :user_id AND event_id = :event_id
                  AND status = 'active' AND expires_at > now()
                ORDER BY created_at
            """),
            {"user_id": user_id, "event_id": event_id},
        )
        return [_row(r) for r in rows]

    async def taken_seats(self, event_id: uuid.UUID) -> tuple[list[int], list[int]]:
        """Занятые места мероприятия: (удержанные сейчас, проданные)."""
        held = await self._session.scalars(
            text("""
                SELECT seat_id FROM booking.holds
                WHERE event_id = :event_id AND status = 'active' AND expires_at > now()
            """),
            {"event_id": event_id},
        )
        sold = await self._session.scalars(
            text("SELECT seat_id FROM booking.sold_seats WHERE event_id = :event_id"),
            {"event_id": event_id},
        )
        return list(held), list(sold)

    async def extend_for_checkout(
        self, user_id: uuid.UUID, event_id: uuid.UUID, min_seconds: int
    ) -> list[HoldRow]:
        """Активные удержания пользователя; оставшееся время продлевается до min_seconds,
        чтобы уборщик не погасил их, пока идёт оплата."""
        rows = await self._session.execute(
            text(f"""
                UPDATE booking.holds
                SET expires_at = greatest(expires_at, now() + make_interval(secs => :secs))
                WHERE user_id = :user_id AND event_id = :event_id
                  AND status = 'active' AND expires_at > now()
                RETURNING {_HOLD_COLUMNS}
            """),
            {"user_id": user_id, "event_id": event_id, "secs": min_seconds},
        )
        return [_row(r) for r in rows]

    async def convert(self, user_id: uuid.UUID, hold_ids: list[uuid.UUID]) -> list[HoldRow]:
        """Погасить удержания покупкой. Условный UPDATE: только свои и только активные."""
        rows = await self._session.execute(
            text(f"""
                UPDATE booking.holds SET status = 'converted', closed_at = now()
                WHERE id = ANY(:hold_ids) AND user_id = :user_id AND status = 'active'
                RETURNING {_HOLD_COLUMNS}
            """),
            {"hold_ids": hold_ids, "user_id": user_id},
        )
        return [_row(r) for r in rows]

    async def mark_sold(
        self, event_id: uuid.UUID, seat_ids: list[int], order_id: uuid.UUID
    ) -> None:
        """Пометить места проданными. PK (event_id, seat_id) не даст продать место дважды:
        повторная вставка упадёт с IntegrityError и откатит всю покупку."""
        await self._session.execute(
            text("""
                INSERT INTO booking.sold_seats (event_id, seat_id, order_id)
                SELECT :event_id, seat_id, :order_id
                FROM unnest(CAST(:seat_ids AS integer[])) AS seat_id
            """),
            {"event_id": event_id, "seat_ids": seat_ids, "order_id": order_id},
        )

    async def release_many(self, user_id: uuid.UUID, hold_ids: list[uuid.UUID]) -> list[HoldRow]:
        rows = await self._session.execute(
            text(f"""
                UPDATE booking.holds SET status = 'released', closed_at = now()
                WHERE id = ANY(:hold_ids) AND user_id = :user_id AND status = 'active'
                RETURNING {_HOLD_COLUMNS}
            """),
            {"hold_ids": hold_ids, "user_id": user_id},
        )
        return [_row(r) for r in rows]
