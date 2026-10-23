"""Отправка писем. В разработке и на демо — Mailpit: SMTP-сервер, который никуда не
пересылает письма, а показывает их в веб-интерфейсе."""

import html
import io
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import aiosmtplib
import segno

from app.core.config import settings

MSK = ZoneInfo("Europe/Moscow")


class Mailer(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class SmtpMailer:
    async def send(self, message: EmailMessage) -> None:
        await aiosmtplib.send(
            message, hostname=settings.smtp_host, port=settings.smtp_port, timeout=15
        )


@dataclass
class MemoryMailer:
    """Для тестов: письма складываются в список."""

    sent: list[EmailMessage] = field(default_factory=list)

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _rub(kopecks: int) -> str:
    return f"{kopecks / 100:,.0f} ₽".replace(",", " ")


def _qr_png(code: str) -> bytes:
    buffer = io.BytesIO()
    segno.make(code, error="m").save(buffer, kind="png", scale=5, border=2)
    return buffer.getvalue()


def tickets_email(to: str, name: str, payload: dict[str, Any]) -> EmailMessage:
    """Письмо с билетами: HTML с QR-кодами, встроенными картинками (cid)."""
    starts = payload.get("event_starts_at")
    when = (
        datetime.fromisoformat(starts).astimezone(MSK).strftime("%d.%m.%Y, %H:%M") if starts else ""
    )
    title = html.escape(payload.get("event_title", "Мероприятие"))
    order_url = f"{settings.public_url}/orders/{payload['order_id']}"

    message = EmailMessage()
    message["Subject"] = f"Ваши билеты: {payload.get('event_title', '')}"
    message["From"] = settings.mail_from
    message["To"] = to

    tickets = payload.get("tickets", [])
    plain = [f"{name}, спасибо за покупку!", f"{payload.get('event_title')} — {when}", ""]
    plain += [f"• {t['seat']} ({t['category']}): {t['code']}" for t in tickets]
    plain += ["", f"Билеты онлайн: {order_url}"]
    message.set_content("\n".join(plain))

    qr_ids = [make_msgid(domain="tickets.local") for _ in tickets]
    rows = "".join(
        f"""
        <tr>
          <td style="padding:14px 16px;border-top:1px dashed #d0d0d0">
            <div style="font-weight:700;font-size:15px">{html.escape(t["seat"])}</div>
            <div style="color:#666;font-size:13px">{html.escape(t["category"])} ·
              {_rub(t["price_kopecks"])}</div>
            <div style="color:#999;font-size:11px;margin-top:6px;font-family:monospace">
              {html.escape(t["code"])}</div>
          </td>
          <td style="padding:10px 16px;border-top:1px dashed #d0d0d0;text-align:right">
            <img src="cid:{cid[1:-1]}" width="120" height="120" alt="QR">
          </td>
        </tr>"""
        for t, cid in zip(tickets, qr_ids, strict=True)
    )
    message.add_alternative(
        f"""<!doctype html>
<html><body style="margin:0;background:#f3f0ff;font-family:Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden">
        <tr><td colspan="2" style="padding:24px;background:linear-gradient(135deg,#5f3dc4,#e64980);
                color:#fff">
          <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;opacity:.85">
            Электронные билеты</div>
          <div style="font-size:24px;font-weight:800;margin-top:6px">{title}</div>
          <div style="margin-top:6px;opacity:.9">{when} · Арена «Северная»</div>
        </td></tr>
        <tr><td colspan="2" style="padding:16px 16px 4px">
          {html.escape(name)}, спасибо за покупку! Покажите QR-код на входе.</td></tr>
        {rows}
        <tr><td style="padding:16px;border-top:1px solid #eee;font-weight:700">Итого</td>
            <td style="padding:16px;border-top:1px solid #eee;text-align:right;font-weight:700">
              {_rub(payload.get("total_kopecks", 0))}</td></tr>
        <tr><td colspan="2" style="padding:0 16px 24px">
          <a href="{order_url}" style="display:inline-block;padding:10px 18px;background:#7048e8;
             color:#fff;border-radius:8px;text-decoration:none">Открыть билеты на сайте</a>
          <div style="color:#999;font-size:11px;margin-top:16px">Учебный проект: мероприятие
            вымышленное, оплата — имитация.</div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>""",
        subtype="html",
    )
    html_part = message.get_payload()[1]
    for t, cid in zip(tickets, qr_ids, strict=True):
        html_part.add_related(_qr_png(t["code"]), maintype="image", subtype="png", cid=cid)
    return message
