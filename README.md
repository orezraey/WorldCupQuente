# WorldCupQuente

Bot Telegram para acompanhar a Copa do Mundo 2026 usando endpoints públicos da ESPN.

## Comandos

- `/start` - ajuda rápida
- `/hoje` - jogos do dia
- `/aovivo` - partidas ao vivo no momento
- `/calendario` - calendário por datas ou seleções
- `/selecoes` - lista seleções e permite abrir o elenco geral

## Configuração

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edite `.env` e preencha:

```env
TELEGRAM_BOT_TOKEN=seu_token
LIVE_NOTIFICATION_CHAT_IDS=123456789,-1001234567890
LIVE_POLL_INTERVAL_SECONDS=30
```

`LIVE_NOTIFICATION_CHAT_IDS` aceita múltiplos chats separados por vírgula. O bot envia alertas automáticos de gol para esses chats quando detectar novas jogadas de gol na API da ESPN.

## Execução

```powershell
python -m worldcupquente --drop-pending-updates
```

Ou, após instalação:

```powershell
worldcupquente --drop-pending-updates
```
