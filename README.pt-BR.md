# WorldCupQuente

[English](README.md)

WorldCupQuente é um bot para Telegram que acompanha jogos da Copa do Mundo FIFA 2026 usando endpoints públicos do SofaScore. Ele exibe agenda, partidas ao vivo, classificação, seleções, elencos e notificações automáticas de eventos relevantes da partida.

## Funcionalidades

- Consulta de jogos do dia.
- Consulta de partidas ao vivo.
- Navegação pelo calendário por data ou seleção.
- Classificação da fase de grupos.
- Lista de seleções e elencos.
- Notificações configuráveis por chat para início de jogo, gol, pênalti, cartão vermelho, intervalo e fim de jogo.
- Escopo de notificações por seleção: todas por padrão ou apenas seleções seguidas pelo `/selecoes`.
- Seleção de idioma por chat em inglês ou português pelo `/config`.

## Comandos Do Bot

- `/start` - mostra uma ajuda rápida.
- `/hoje` - lista os jogos do dia.
- `/aovivo` - mostra partidas ao vivo no momento.
- `/calendario` - abre o calendário por datas ou seleções.
- `/historico` - mostra o histórico de partidas finalizadas.
- `/tabela` - mostra a classificação da fase de grupos.
- `/selecoes` - lista seleções e permite abrir o elenco geral.
- `/config` - configura notificações e idioma no chat atual.

Os aliases em inglês também estão disponíveis: `/today`, `/live`, `/calendar`, `/history`, `/standings` e `/teams`.

## Requisitos

- Python 3.12 ou superior.
- Um token de bot do Telegram criado pelo BotFather.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Em Linux ou macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Configuração

Edite o arquivo `.env` e preencha as variáveis necessárias.

```env
TELEGRAM_BOT_TOKEN=seu_token
BOT_TIME_ZONE=America/Sao_Paulo
LIVE_NOTIFICATION_CHAT_IDS=123456789,-1001234567890
LIVE_POLL_INTERVAL_SECONDS=30
NOTIFICATION_CONFIG_PATH=notification_config.json
REQUEST_TIMEOUT=30
HTTP_USER_AGENT=WorldCupQuente/0.1
LOG_LEVEL=INFO
```

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Sim | Token do bot do Telegram. |
| `BOT_TIME_ZONE` | Não | Fuso horário usado para exibir datas e horários. O padrão é `America/Sao_Paulo`. |
| `LIVE_NOTIFICATION_CHAT_IDS` | Não | Lista de chats que recebem notificações automáticas, separados por vírgula. |
| `LIVE_POLL_INTERVAL_SECONDS` | Não | Intervalo de consulta do monitor ao vivo. O valor mínimo aplicado é 10 segundos. |
| `NOTIFICATION_CONFIG_PATH` | Não | Caminho do arquivo local onde preferências por chat são salvas. |
| `REQUEST_TIMEOUT` | Não | Timeout, em segundos, para requisições HTTP. |
| `HTTP_USER_AGENT` | Não | User-Agent usado nas requisições HTTP. |
| `LOG_LEVEL` | Não | Nível de log da aplicação, como `INFO`, `WARNING` ou `DEBUG`. |

Não versione arquivos `.env` nem `notification_config.json`. Eles podem conter tokens, IDs de chats e preferências locais de usuários. O `.gitignore` do projeto já ignora esses arquivos.

## Idioma

Inglês é o idioma padrão para novos chats. Cada chat pode trocar o bot para português em `/config`. O idioma escolhido é salvo no arquivo configurado por `NOTIFICATION_CONFIG_PATH`.

O menu padrão de comandos do Telegram é registrado em inglês. Quando um chat troca de idioma no `/config`, o bot também atualiza o menu de comandos daquele chat para o idioma escolhido quando o Telegram permite essa atualização por escopo.

## Execução

```powershell
python -m worldcupquente --drop-pending-updates
```

Ou, após instalar o pacote em modo editável:

```powershell
worldcupquente --drop-pending-updates
```

O parâmetro `--drop-pending-updates` descarta mensagens acumuladas enquanto o bot estava offline.

## Notificações

O monitor em segundo plano consulta partidas próximas e ativas, então envia alertas para os chats configurados. As notificações são deduplicadas em memória durante a execução do processo.

Por padrão, um chat recebe notificações de todas as seleções, incluindo um alerta cerca de 5 minutos antes de a bola rolar. O comando `/config` permite alternar entre todas as seleções e apenas seleções seguidas, ligar ou desligar tipos específicos de alerta e escolher inglês ou português.

Quando o chat está configurado para apenas seleções seguidas, abra `/selecoes`, escolha uma seleção e use o botão de notificações na tela do elenco. Se o chat estiver configurado para todas as seleções, esse botão fica oculto porque seguir seleções individualmente não é necessário.

Essas preferências são salvas no caminho definido por `NOTIFICATION_CONFIG_PATH`.

Para notificações de fim de jogo, o bot tenta usar `sendRichMessage` quando disponível no ambiente do Telegram utilizado. Caso esse método falhe, a aplicação registra o erro e envia uma mensagem HTML convencional como fallback.

## Qualidade De Código

Execute os testes:

```bash
python -m pytest
```

Execute o lint:

```bash
python -m ruff check .
```

## Fonte Dos Dados

Os dados são obtidos a partir de endpoints públicos do SofaScore. Esses endpoints não são uma API oficial versionada para este projeto e podem mudar sem aviso. Em caso de mudanças na estrutura das respostas, parsers e formatadores podem precisar de ajustes.

## Licença

Este projeto é distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais detalhes.
