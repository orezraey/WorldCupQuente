"""Persistent per-chat live notification preferences."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from worldcupquente.config import ChatId
from worldcupquente.i18n import DEFAULT_LANGUAGE, normalize_language

logger = logging.getLogger(__name__)

GOAL_NOTIFICATION = "goal"
HALFTIME_NOTIFICATION = "halftime"
FULL_TIME_NOTIFICATION = "full_time"
PENALTY_NOTIFICATION = "penalty"
RED_CARD_NOTIFICATION = "red_card"

NOTIFICATION_TYPES = (
    GOAL_NOTIFICATION,
    PENALTY_NOTIFICATION,
    RED_CARD_NOTIFICATION,
    HALFTIME_NOTIFICATION,
    FULL_TIME_NOTIFICATION,
)
LEGACY_NOTIFICATION_TYPES = (GOAL_NOTIFICATION, PENALTY_NOTIFICATION, RED_CARD_NOTIFICATION)
STATUS_NOTIFICATION_TYPES = (HALFTIME_NOTIFICATION, FULL_TIME_NOTIFICATION)
DEFAULT_NOTIFICATION_SETTINGS = dict.fromkeys(NOTIFICATION_TYPES, True)
LANGUAGE_KEY = "language"
LEGACY_DEFAULT_LANGUAGE = "pt"


class NotificationPreferences:
    def __init__(self, path: Path):
        self.path = path
        self._items: dict[str, dict[str, Any]] = {}
        self._load()

    def ensure_chat(self, chat_id: ChatId) -> dict[str, Any]:
        key = self._chat_key(chat_id)
        if key not in self._items:
            self._items[key] = self._default_settings()
            self.save()
        return self.get(chat_id)

    def get(self, chat_id: ChatId) -> dict[str, Any]:
        settings = self._default_settings()
        settings.update(self._items.get(self._chat_key(chat_id), {}))
        return settings

    def get_language(self, chat_id: ChatId) -> str:
        return normalize_language(str(self.get(chat_id).get(LANGUAGE_KEY, DEFAULT_LANGUAGE)))

    def set_language(self, chat_id: ChatId, language: str) -> dict[str, Any]:
        key = self._chat_key(chat_id)
        current = self._items.get(key, {}).copy()
        current[LANGUAGE_KEY] = normalize_language(language)
        self._items[key] = current
        self.save()
        return self.get(chat_id)

    def toggle(self, chat_id: ChatId, notification_type: str) -> dict[str, Any]:
        if notification_type not in NOTIFICATION_TYPES:
            raise ValueError(f"Invalid notification type: {notification_type}")
        current = self.ensure_chat(chat_id)
        current[notification_type] = not current[notification_type]
        self._items[self._chat_key(chat_id)] = current
        self.save()
        return current

    def enabled_chat_ids(self, notification_type: str, static_chat_ids: tuple[ChatId, ...]) -> list[ChatId]:
        chat_ids = [*static_chat_ids, *self.configured_chat_ids()]
        seen: set[str] = set()
        enabled: list[ChatId] = []
        for chat_id in chat_ids:
            key = self._chat_key(chat_id)
            if key in seen or not self.get(chat_id).get(notification_type, True):
                continue
            seen.add(key)
            enabled.append(chat_id)
        return enabled

    def has_recipients(self, static_chat_ids: tuple[ChatId, ...]) -> bool:
        return bool(static_chat_ids or self.configured_chat_ids())

    def configured_chat_ids(self) -> list[ChatId]:
        return [
            self._parse_chat_key(chat_id)
            for chat_id, settings in self._items.items()
            if self._has_notification_settings(settings)
        ]

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"chats": self._items}
            self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.exception("Failed to save notification preferences", extra={"path": str(self.path)})

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load notification preferences", extra={"path": str(self.path)})
            return

        chats = payload.get("chats", {}) if isinstance(payload, dict) else {}
        if not isinstance(chats, dict):
            return
        self._items = {
            self._chat_key(chat_id): self._validated_settings(settings)
            for chat_id, settings in chats.items()
            if isinstance(settings, dict)
        }

    @staticmethod
    def _validated_settings(settings: dict[str, Any]) -> dict[str, Any]:
        has_notification_settings = NotificationPreferences._has_notification_settings(settings)
        validated: dict[str, Any] = {}
        if has_notification_settings:
            validated.update(
                {
                    notification_type: bool(
                        settings.get(
                            notification_type,
                            NotificationPreferences._missing_notification_default(
                                settings, notification_type
                            ),
                        )
                    )
                    for notification_type in NOTIFICATION_TYPES
                }
            )
        default_language = LEGACY_DEFAULT_LANGUAGE if has_notification_settings else DEFAULT_LANGUAGE
        validated[LANGUAGE_KEY] = normalize_language(str(settings.get(LANGUAGE_KEY, default_language)))
        return validated

    @staticmethod
    def _has_notification_settings(settings: dict[str, Any]) -> bool:
        return any(notification_type in settings for notification_type in NOTIFICATION_TYPES)

    @staticmethod
    def _default_settings() -> dict[str, Any]:
        return {**DEFAULT_NOTIFICATION_SETTINGS, LANGUAGE_KEY: DEFAULT_LANGUAGE}

    @staticmethod
    def _missing_notification_default(settings: dict[str, Any], notification_type: str) -> bool:
        if notification_type not in STATUS_NOTIFICATION_TYPES:
            return True

        legacy_values = [bool(settings[item]) for item in LEGACY_NOTIFICATION_TYPES if item in settings]
        return not (legacy_values and not any(legacy_values))

    @staticmethod
    def _chat_key(chat_id: ChatId) -> str:
        return str(chat_id)

    @staticmethod
    def _parse_chat_key(chat_id: str) -> ChatId:
        return int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
