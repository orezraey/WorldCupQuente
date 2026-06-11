"""Portuguese names and flag emojis for World Cup teams."""

from __future__ import annotations

from html import escape
from typing import Any

TEAM_TRANSLATIONS: dict[str, dict[str, str]] = {
    "624": {"name": "Argélia", "emoji": "🇩🇿"},
    "202": {"name": "Argentina", "emoji": "🇦🇷"},
    "628": {"name": "Austrália", "emoji": "🇦🇺"},
    "474": {"name": "Áustria", "emoji": "🇦🇹"},
    "459": {"name": "Bélgica", "emoji": "🇧🇪"},
    "452": {"name": "Bósnia e Herzegovina", "emoji": "🇧🇦"},
    "205": {"name": "Brasil", "emoji": "🇧🇷"},
    "206": {"name": "Canadá", "emoji": "🇨🇦"},
    "2597": {"name": "Cabo Verde", "emoji": "🇨🇻"},
    "208": {"name": "Colômbia", "emoji": "🇨🇴"},
    "2850": {"name": "República Democrática do Congo", "emoji": "🇨🇩"},
    "477": {"name": "Croácia", "emoji": "🇭🇷"},
    "11678": {"name": "Curaçao", "emoji": "🇨🇼"},
    "450": {"name": "Tchéquia", "emoji": "🇨🇿"},
    "209": {"name": "Equador", "emoji": "🇪🇨"},
    "2620": {"name": "Egito", "emoji": "🇪🇬"},
    "448": {"name": "Inglaterra", "emoji": "🏴", "custom_emoji_id": "5388763627975095656"},
    "478": {"name": "França", "emoji": "🇫🇷"},
    "481": {"name": "Alemanha", "emoji": "🇩🇪"},
    "4469": {"name": "Gana", "emoji": "🇬🇭"},
    "2654": {"name": "Haiti", "emoji": "🇭🇹"},
    "469": {"name": "Irã", "emoji": "🇮🇷"},
    "4375": {"name": "Iraque", "emoji": "🇮🇶"},
    "4789": {"name": "Costa do Marfim", "emoji": "🇨🇮"},
    "627": {"name": "Japão", "emoji": "🇯🇵"},
    "2917": {"name": "Jordânia", "emoji": "🇯🇴"},
    "203": {"name": "México", "emoji": "🇲🇽"},
    "2869": {"name": "Marrocos", "emoji": "🇲🇦"},
    "449": {"name": "Países Baixos", "emoji": "🇳🇱"},
    "2666": {"name": "Nova Zelândia", "emoji": "🇳🇿"},
    "464": {"name": "Noruega", "emoji": "🇳🇴"},
    "2659": {"name": "Panamá", "emoji": "🇵🇦"},
    "210": {"name": "Paraguai", "emoji": "🇵🇾"},
    "482": {"name": "Portugal", "emoji": "🇵🇹"},
    "4398": {"name": "Catar", "emoji": "🇶🇦"},
    "655": {"name": "Arábia Saudita", "emoji": "🇸🇦"},
    "580": {"name": "Escócia", "emoji": "🏴"},
    "654": {"name": "Senegal", "emoji": "🇸🇳"},
    "467": {"name": "África do Sul", "emoji": "🇿🇦"},
    "451": {"name": "Coreia do Sul", "emoji": "🇰🇷"},
    "164": {"name": "Espanha", "emoji": "🇪🇸"},
    "466": {"name": "Suécia", "emoji": "🇸🇪"},
    "475": {"name": "Suíça", "emoji": "🇨🇭"},
    "659": {"name": "Tunísia", "emoji": "🇹🇳"},
    "465": {"name": "Turquia", "emoji": "🇹🇷"},
    "660": {"name": "Estados Unidos", "emoji": "🇺🇸"},
    "212": {"name": "Uruguai", "emoji": "🇺🇾"},
    "2570": {"name": "Uzbequistão", "emoji": "🇺🇿"},
}


def translated_team_name(team: dict[str, Any], include_emoji: bool = True) -> str:
    translation = TEAM_TRANSLATIONS.get(str(team.get("id", "")), {})
    name = _translated_name(team, translation)
    emoji = translation.get("emoji") if include_emoji else ""
    return f"{emoji} {name}" if emoji else name


def translated_team_name_html(team: dict[str, Any], include_emoji: bool = True) -> str:
    translation = TEAM_TRANSLATIONS.get(str(team.get("id", "")), {})
    name = escape(_translated_name(team, translation))
    if not include_emoji:
        return name

    emoji = translation.get("emoji", "")
    custom_emoji_id = translation.get("custom_emoji_id")
    if custom_emoji_id and emoji:
        return f'<tg-emoji emoji-id="{escape(custom_emoji_id)}">{escape(emoji)}</tg-emoji> {name}'
    if emoji:
        return f"{escape(emoji)} {name}"
    return name


def _translated_name(team: dict[str, Any], translation: dict[str, str]) -> str:
    return str(
        translation.get("name")
        or team.get("shortDisplayName")
        or team.get("displayName")
        or team.get("name")
        or "Seleção"
    )
