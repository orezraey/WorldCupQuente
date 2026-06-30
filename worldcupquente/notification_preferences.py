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
PRE_GAME_NOTIFICATION = "pre_game"
HALFTIME_NOTIFICATION = "halftime"
FULL_TIME_NOTIFICATION = "full_time"
PENALTY_NOTIFICATION = "penalty"
RED_CARD_NOTIFICATION = "red_card"

NOTIFICATION_TYPES = (
    PRE_GAME_NOTIFICATION,
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
TEAM_SCOPE_KEY = "team_scope"
FOLLOWED_TEAM_IDS_KEY = "followed_team_ids"
BLOCKED_KEY = "blocked"
TEAM_SCOPE_ALL = "all"
TEAM_SCOPE_FOLLOWED = "followed"
TEAM_SCOPES = (TEAM_SCOPE_ALL, TEAM_SCOPE_FOLLOWED)
LEGACY_DEFAULT_LANGUAGE = "pt"
TEAM_ID_VERSION_KEY = "team_id_version"
CURRENT_TEAM_ID_VERSION = 2


class NotificationPreferences:
    def __init__(self, path: Path):
        self.path = path
        self._items: dict[str, dict[str, Any]] = {}
        self._team_id_version: int = 1
        self._load()

    def ensure_chat(self, chat_id: ChatId) -> dict[str, Any]:
        key = self._chat_key(chat_id)
        if key not in self._items:
            self._items[key] = self._default_settings()
            self.save()
        elif self._items[key].pop(BLOCKED_KEY, None) is not None:
            self.save()
        return self.get(chat_id)

    def get(self, chat_id: ChatId) -> dict[str, Any]:
        settings = self._default_settings()
        settings.update(self._items.get(self._chat_key(chat_id), {}))
        return settings

    def get_language(self, chat_id: ChatId) -> str:
        return normalize_language(str(self.get(chat_id).get(LANGUAGE_KEY, DEFAULT_LANGUAGE)))

    def is_blocked(self, chat_id: ChatId) -> bool:
        return bool(self.get(chat_id).get(BLOCKED_KEY, False))

    def disable_chat(self, chat_id: ChatId) -> dict[str, Any]:
        key = self._chat_key(chat_id)
        if key not in self._items:
            self._items[key] = self._default_settings()
        current = self.get(chat_id)
        current[BLOCKED_KEY] = True
        self._items[key] = current
        self.save()
        return self.get(chat_id)

    def set_language(self, chat_id: ChatId, language: str) -> dict[str, Any]:
        key = self._chat_key(chat_id)
        current = self.ensure_chat(chat_id)
        current[LANGUAGE_KEY] = normalize_language(language)
        self._items[key] = current
        self.save()
        return self.get(chat_id)

    def get_team_scope(self, chat_id: ChatId) -> str:
        return str(self.get(chat_id).get(TEAM_SCOPE_KEY, TEAM_SCOPE_ALL))

    def set_team_scope(self, chat_id: ChatId, team_scope: str) -> dict[str, Any]:
        if team_scope not in TEAM_SCOPES:
            raise ValueError(f"Invalid team notification scope: {team_scope}")
        current = self.ensure_chat(chat_id)
        current[TEAM_SCOPE_KEY] = team_scope
        self._items[self._chat_key(chat_id)] = current
        self.save()
        return current

    def followed_team_ids(self, chat_id: ChatId) -> list[str]:
        return list(self.get(chat_id).get(FOLLOWED_TEAM_IDS_KEY, []))

    def is_following_team(self, chat_id: ChatId, team_id: str) -> bool:
        return str(team_id) in set(self.followed_team_ids(chat_id))

    def toggle_followed_team(self, chat_id: ChatId, team_id: str) -> dict[str, Any]:
        team_id = str(team_id)
        current = self.ensure_chat(chat_id)
        followed = set(self.followed_team_ids(chat_id))
        if team_id in followed:
            followed.remove(team_id)
        else:
            followed.add(team_id)
        current[FOLLOWED_TEAM_IDS_KEY] = sorted(followed)
        self._items[self._chat_key(chat_id)] = current
        self.save()
        return current

    def toggle(self, chat_id: ChatId, notification_type: str) -> dict[str, Any]:
        if notification_type not in NOTIFICATION_TYPES:
            raise ValueError(f"Invalid notification type: {notification_type}")
        current = self.ensure_chat(chat_id)
        current[notification_type] = not current[notification_type]
        self._items[self._chat_key(chat_id)] = current
        self.save()
        return current

    def migrate_followed_team_ids(self, mapping: dict[str, str]) -> int:
        if self._team_id_version >= CURRENT_TEAM_ID_VERSION:
            return 0
        migrated = 0
        for settings in self._items.values():
            followed = settings.get(FOLLOWED_TEAM_IDS_KEY)
            if not isinstance(followed, list):
                continue
            new_ids: list[str] = []
            changed = False
            for team_id in followed:
                sofascore_id = mapping.get(str(team_id))
                if sofascore_id and sofascore_id != str(team_id):
                    new_ids.append(sofascore_id)
                    migrated += 1
                    changed = True
                else:
                    new_ids.append(str(team_id))
            if changed:
                settings[FOLLOWED_TEAM_IDS_KEY] = sorted(set(new_ids))
        self._team_id_version = CURRENT_TEAM_ID_VERSION
        if migrated:
            self.save()
        return migrated

    def enabled_chat_ids(
        self,
        notification_type: str,
        static_chat_ids: tuple[ChatId, ...],
        team_ids: set[str] | None = None,
    ) -> list[ChatId]:
        chat_ids = [*static_chat_ids, *self.configured_chat_ids()]
        seen: set[str] = set()
        enabled: list[ChatId] = []
        for chat_id in chat_ids:
            key = self._chat_key(chat_id)
            if (
                key in seen
                or self.is_blocked(chat_id)
                or not self.get(chat_id).get(notification_type, True)
                or not self._matches_team_scope(chat_id, team_ids)
            ):
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
            if self._has_recipient_settings(settings)
        ]

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"chats": self._items, TEAM_ID_VERSION_KEY: self._team_id_version}
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

        if isinstance(payload, dict):
            self._team_id_version = int(payload.get(TEAM_ID_VERSION_KEY, 1))
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
        has_team_settings = NotificationPreferences._has_team_settings(settings)
        validated: dict[str, Any] = {}
        if has_notification_settings or has_team_settings:
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
            team_scope = str(settings.get(TEAM_SCOPE_KEY, TEAM_SCOPE_ALL))
            validated[TEAM_SCOPE_KEY] = team_scope if team_scope in TEAM_SCOPES else TEAM_SCOPE_ALL
            validated[FOLLOWED_TEAM_IDS_KEY] = NotificationPreferences._validated_team_ids(
                settings.get(FOLLOWED_TEAM_IDS_KEY, [])
            )
        default_language = LEGACY_DEFAULT_LANGUAGE if has_notification_settings else DEFAULT_LANGUAGE
        validated[LANGUAGE_KEY] = normalize_language(str(settings.get(LANGUAGE_KEY, default_language)))
        if settings.get(BLOCKED_KEY):
            validated[BLOCKED_KEY] = True
        return validated

    @staticmethod
    def _has_notification_settings(settings: dict[str, Any]) -> bool:
        return any(notification_type in settings for notification_type in NOTIFICATION_TYPES)

    @staticmethod
    def _has_team_settings(settings: dict[str, Any]) -> bool:
        return TEAM_SCOPE_KEY in settings or FOLLOWED_TEAM_IDS_KEY in settings

    @staticmethod
    def _has_recipient_settings(settings: dict[str, Any]) -> bool:
        return NotificationPreferences._has_notification_settings(
            settings
        ) or NotificationPreferences._has_team_settings(settings)

    @staticmethod
    def _default_settings() -> dict[str, Any]:
        return {
            **DEFAULT_NOTIFICATION_SETTINGS,
            TEAM_SCOPE_KEY: TEAM_SCOPE_ALL,
            FOLLOWED_TEAM_IDS_KEY: [],
            LANGUAGE_KEY: DEFAULT_LANGUAGE,
        }

    @staticmethod
    def _validated_team_ids(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return sorted({str(item) for item in value if str(item)})

    def _matches_team_scope(self, chat_id: ChatId, team_ids: set[str] | None) -> bool:
        if self.get_team_scope(chat_id) == TEAM_SCOPE_ALL:
            return True
        if team_ids is None:
            return True
        return bool(set(self.followed_team_ids(chat_id)) & {str(team_id) for team_id in team_ids})

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
