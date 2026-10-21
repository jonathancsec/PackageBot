import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import aiohttp
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SHIP24_API_KEY = os.getenv("SHIP24_API_KEY")
API_URL = "https://api.ship24.com/public/v1/trackers/track"

STATUS_EMOJI = {
    "pending": "📝",
    "info_received": "📝",
    "in_transit": "📦",
    "out_for_delivery": "🚚",
    "available_for_pickup": "🏬",
    "failed_attempt": "⚠️",
    "exception": "🚨",
    "delivered": "✅",
}

STATUS_COLOURS = {
    "pending": 0x95A5A6,
    "info_received": 0x95A5A6,
    "in_transit": 0x3498DB,
    "out_for_delivery": 0xF1C40F,
    "available_for_pickup": 0x9B59B6,
    "failed_attempt": 0xE67E22,
    "exception": 0xE74C3C,
    "delivered": 0x2ECC71,
}


def _status_key(status: str) -> str:
    return (status or "").lower().replace(" ", "_")


def status_emoji(status: str) -> str:
    return STATUS_EMOJI.get(_status_key(status), "📦")


def status_colour(status: str) -> int:
    return STATUS_COLOURS.get(_status_key(status), 0x95A5A6)


# ---------- Errors ----------

class TrackingError(Exception):
    user_message = (
        "❌ I couldn't retrieve tracking information right now. "
        "Please try again later."
    )


class InvalidTrackingNumberError(TrackingError):
    user_message = (
        "❌ That doesn't look like a valid tracking number. "
        "Double-check it and try again."
    )


class NoTrackingDataError(TrackingError):
    user_message = (
        "📭 No tracking data is available for that number yet. "
        "If the label was just created, try again in a little while."
    )


class ServiceUnavailableError(TrackingError):
    user_message = (
        "⚠️ The tracking service is having trouble right now. "
        "This isn't a problem with your tracking number, so please try again in a few minutes."
    )


# ---------- Data ----------

@dataclass
class TrackingEvent:
    status: str
    location: str
    occurred_at: Optional[datetime]
    raw_time: str


@dataclass
class TrackingInfo:
    tracking_number: str
    milestone: str
    status_text: str
    carrier: str
    estimated_delivery: Optional[str]
    events: list = field(default_factory=list)

    @property
    def latest_event(self) -> Optional[TrackingEvent]:
        return self.events[0] if self.events else None

    @property
    def is_delivered(self) -> bool:
        return self.milestone == "delivered"


_TRACKING_RE = re.compile(r"^[A-Za-z0-9\-]{5,50}$")


def normalize_tracking_number(raw: str) -> str:
    cleaned = raw.strip().replace(" ", "")
    if not _TRACKING_RE.match(cleaned):
        raise InvalidTrackingNumberError()
    return cleaned


def tracking_url(tracking_number: str) -> str:
    return f"https://www.ship24.com/tracking?p={quote(tracking_number)}"


def _parse_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _courier_name(value) -> Optional[str]:
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value).upper() if value else None


def _parse_result(tracking_number: str, result: dict) -> TrackingInfo:
    trackings = ((result or {}).get("data") or {}).get("trackings") or []
    if not trackings:
        raise NoTrackingDataError()

    tracking = trackings[0]
    shipment = tracking.get("shipment") or {}
    raw_events = tracking.get("events") or []

    events = [
        TrackingEvent(
            status=str(event.get("status") or "Unknown"),
            location=event.get("location") or "Unknown",
            occurred_at=_parse_datetime(event.get("occurrenceDatetime")),
            raw_time=str(event.get("occurrenceDatetime") or "Unknown"),
        )
        for event in raw_events
    ]
    # Newest first, when every event has a usable timestamp.
    if events and all(event.occurred_at for event in events):
        events.sort(key=lambda event: event.occurred_at, reverse=True)

    carrier = None
    if raw_events:
        carrier = _courier_name(raw_events[0].get("courierCode"))
    if not carrier:
        carrier = _courier_name((tracking.get("tracker") or {}).get("courierCode"))

    milestone = shipment.get("statusMilestone") or "pending"
    delivery = shipment.get("delivery") or {}

    return TrackingInfo(
        tracking_number=tracking_number,
        milestone=milestone,
        status_text=milestone.replace("_", " ").title(),
        carrier=carrier or "Unknown",
        estimated_delivery=delivery.get("estimatedDeliveryDate"),
        events=events,
    )


# ---------- HTTP ----------

_session: Optional[aiohttp.ClientSession] = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
    return _session


async def close_session():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def track_package(tracking_number: str) -> TrackingInfo:
    headers = {
        "Authorization": f"Bearer {SHIP24_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with _get_session().post(
            API_URL,
            headers=headers,
            json={"trackingNumber": tracking_number}
        ) as response:
            body = await response.text()
            status = response.status

            if status >= 400:
                logger.warning("Ship24 returned HTTP %s: %s", status, body[:500])

                if status in (400, 404, 422):
                    raise InvalidTrackingNumberError()
                if status in (401, 403):
                    logger.error("Ship24 rejected the API key. Check SHIP24_API_KEY.")
                    raise ServiceUnavailableError()
                if status == 429 or status >= 500:
                    raise ServiceUnavailableError()
                raise TrackingError()

            result = await response.json(content_type=None)

    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("Network error talking to Ship24: %s", exc)
        raise ServiceUnavailableError() from exc

    return _parse_result(tracking_number, result)