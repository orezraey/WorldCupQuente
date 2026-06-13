"""Localized names and flag emojis for World Cup teams."""

from __future__ import annotations

from html import escape
from typing import Any

from worldcupquente.i18n import normalize_language, text

TEAM_TRANSLATIONS: dict[str, dict[str, Any]] = {
    "624": {"names": {"en": "Algeria", "pt": "Argélia"}, "emoji": "🇩🇿"},
    "202": {"names": {"en": "Argentina", "pt": "Argentina"}, "emoji": "🇦🇷"},
    "628": {"names": {"en": "Australia", "pt": "Austrália"}, "emoji": "🇦🇺"},
    "474": {"names": {"en": "Austria", "pt": "Áustria"}, "emoji": "🇦🇹"},
    "459": {"names": {"en": "Belgium", "pt": "Bélgica"}, "emoji": "🇧🇪"},
    "452": {"names": {"en": "Bosnia and Herzegovina", "pt": "Bósnia e Herzegovina"}, "emoji": "🇧🇦"},
    "205": {"names": {"en": "Brazil", "pt": "Brasil"}, "emoji": "🇧🇷"},
    "206": {"names": {"en": "Canada", "pt": "Canadá"}, "emoji": "🇨🇦"},
    "2597": {"names": {"en": "Cape Verde", "pt": "Cabo Verde"}, "emoji": "🇨🇻"},
    "208": {"names": {"en": "Colombia", "pt": "Colômbia"}, "emoji": "🇨🇴"},
    "2850": {"names": {"en": "DR Congo", "pt": "República Democrática do Congo"}, "emoji": "🇨🇩"},
    "477": {"names": {"en": "Croatia", "pt": "Croácia"}, "emoji": "🇭🇷"},
    "11678": {"names": {"en": "Curacao", "pt": "Curaçao"}, "emoji": "🇨🇼"},
    "450": {"names": {"en": "Czechia", "pt": "Tchéquia"}, "emoji": "🇨🇿"},
    "209": {"names": {"en": "Ecuador", "pt": "Equador"}, "emoji": "🇪🇨"},
    "2620": {"names": {"en": "Egypt", "pt": "Egito"}, "emoji": "🇪🇬"},
    "448": {
        "names": {"en": "England", "pt": "Inglaterra"},
        "emoji": "🏴",
        "custom_emoji_id": "5388763627975095656",
    },
    "478": {"names": {"en": "France", "pt": "França"}, "emoji": "🇫🇷"},
    "481": {"names": {"en": "Germany", "pt": "Alemanha"}, "emoji": "🇩🇪"},
    "4469": {"names": {"en": "Ghana", "pt": "Gana"}, "emoji": "🇬🇭"},
    "2654": {"names": {"en": "Haiti", "pt": "Haiti"}, "emoji": "🇭🇹"},
    "469": {"names": {"en": "Iran", "pt": "Irã"}, "emoji": "🇮🇷"},
    "4375": {"names": {"en": "Iraq", "pt": "Iraque"}, "emoji": "🇮🇶"},
    "4789": {"names": {"en": "Ivory Coast", "pt": "Costa do Marfim"}, "emoji": "🇨🇮"},
    "627": {"names": {"en": "Japan", "pt": "Japão"}, "emoji": "🇯🇵"},
    "2917": {"names": {"en": "Jordan", "pt": "Jordânia"}, "emoji": "🇯🇴"},
    "203": {"names": {"en": "Mexico", "pt": "México"}, "emoji": "🇲🇽"},
    "2869": {"names": {"en": "Morocco", "pt": "Marrocos"}, "emoji": "🇲🇦"},
    "449": {"names": {"en": "Netherlands", "pt": "Países Baixos"}, "emoji": "🇳🇱"},
    "2666": {"names": {"en": "New Zealand", "pt": "Nova Zelândia"}, "emoji": "🇳🇿"},
    "464": {"names": {"en": "Norway", "pt": "Noruega"}, "emoji": "🇳🇴"},
    "2659": {"names": {"en": "Panama", "pt": "Panamá"}, "emoji": "🇵🇦"},
    "210": {"names": {"en": "Paraguay", "pt": "Paraguai"}, "emoji": "🇵🇾"},
    "482": {"names": {"en": "Portugal", "pt": "Portugal"}, "emoji": "🇵🇹"},
    "4398": {"names": {"en": "Qatar", "pt": "Catar"}, "emoji": "🇶🇦"},
    "655": {"names": {"en": "Saudi Arabia", "pt": "Arábia Saudita"}, "emoji": "🇸🇦"},
    "580": {
        "names": {"en": "Scotland", "pt": "Escócia"},
        "emoji": "🏴",
        "custom_emoji_id": "5388717405537053993",
    },
    "654": {"names": {"en": "Senegal", "pt": "Senegal"}, "emoji": "🇸🇳"},
    "467": {"names": {"en": "South Africa", "pt": "África do Sul"}, "emoji": "🇿🇦"},
    "451": {"names": {"en": "South Korea", "pt": "Coreia do Sul"}, "emoji": "🇰🇷"},
    "164": {"names": {"en": "Spain", "pt": "Espanha"}, "emoji": "🇪🇸"},
    "466": {"names": {"en": "Sweden", "pt": "Suécia"}, "emoji": "🇸🇪"},
    "475": {"names": {"en": "Switzerland", "pt": "Suíça"}, "emoji": "🇨🇭"},
    "659": {"names": {"en": "Tunisia", "pt": "Tunísia"}, "emoji": "🇹🇳"},
    "465": {"names": {"en": "Turkiye", "pt": "Turquia"}, "emoji": "🇹🇷"},
    "660": {"names": {"en": "United States", "pt": "Estados Unidos"}, "emoji": "🇺🇸"},
    "212": {"names": {"en": "Uruguay", "pt": "Uruguai"}, "emoji": "🇺🇾"},
    "2570": {"names": {"en": "Uzbekistan", "pt": "Uzbequistão"}, "emoji": "🇺🇿"},
}


def translated_team_name(
    team: dict[str, Any],
    include_emoji: bool = True,
    language: str = "en",
) -> str:
    translation = TEAM_TRANSLATIONS.get(str(team.get("id", "")), {})
    name = _translated_name(team, translation, language)
    emoji = translation.get("emoji") if include_emoji else ""
    return f"{emoji} {name}" if emoji else name


def translated_team_name_html(
    team: dict[str, Any],
    include_emoji: bool = True,
    language: str = "en",
) -> str:
    translation = TEAM_TRANSLATIONS.get(str(team.get("id", "")), {})
    name = escape(_translated_name(team, translation, language))
    if not include_emoji:
        return name

    emoji = translation.get("emoji", "")
    custom_emoji_id = translation.get("custom_emoji_id")
    if custom_emoji_id and emoji:
        return f'<tg-emoji emoji-id="{escape(custom_emoji_id)}">{escape(emoji)}</tg-emoji> {name}'
    if emoji:
        return f"{escape(emoji)} {name}"
    return name


def _translated_name(team: dict[str, Any], translation: dict[str, Any], language: str) -> str:
    names = translation.get("names") or {}
    translated_name = names.get(normalize_language(language)) if isinstance(names, dict) else None
    return str(
        translated_name
        or team.get("shortDisplayName")
        or team.get("displayName")
        or team.get("name")
        or text("team", language)
    )
