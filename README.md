# WorldCupQuente

Bot Telegram para acompanhar a Copa do Mundo 2026 usando endpoints públicos da ESPN.

## Comandos

- `/start` - ajuda rápida
- `/hoje` - jogos do dia
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
```

## Execução

```powershell
python -m worldcupquente --drop-pending-updates
```

Ou, após instalação:

```powershell
worldcupquente --drop-pending-updates
```
