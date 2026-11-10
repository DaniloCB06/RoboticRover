# RoboticRover — Preparação da Raspberry Pi 3 ↔ estação-base

Este pacote complementa o repositório principal para o **teste de fumaça MQTT da Raspberry Pi 3** (`roboticrover_pi3`), coexistindo com o simulador completo (`rover`) e com a Dashboard do Node-RED.

## O que está pronto

- Cliente MQTT 5/Paho em Python (`apps/rover/roboticrover_pi3`, mesmos tópicos do Node-RED).
- Estado inicial `SEGURO_ESPERA` e validação de comandos para simulação (`execution: "simulated_only"`).
- Heartbeat, ACK/NACK, bloqueio de comando vencido, duplicado ou retained (`retainAsPublished=True`).
- MQTT Last Will + status retained; status do cliente Linux com `simulated: false` (indicando disponibilidade do processo Linux, sem atuação física).
- Telemetria artificial **desabilitada por padrão** (`ENABLE_MOCK_TELEMETRY=false`, podendo ser habilitada para demonstração).
- Testes unitários que não exigem a Raspberry Pi nem o broker.

**Ainda não:** controle real do Arduino, sensores reais, visão computacional, streaming real da câmera física e endpoints externos do professor.

## Testar agora no notebook (sem a Raspberry Pi 3)

Você pode rodar a partir da raiz do monorepo (usando a `.venv` principal) ou diretamente dentro de `apps/rover`:

### Opção 1 — A partir da raiz do monorepo
```bash
[ -f .env ] || cp .env.example .env
.venv/bin/python -m pytest -q
.venv/bin/python -m roboticrover_pi3
```

### Opção 2 — Isolado dentro de `apps/rover` (mesmo procedimento que será usado na Pi 3)
```bash
cd apps/rover
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS; no PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env       # No notebook, ajuste MQTT_HOST=127.0.0.1
python -m unittest discover -s tests -v
python -m roboticrover_pi3
```

## Quando a Raspberry Pi 3 estiver pronta

1. Instale Raspberry Pi OS, configure SSH e conecte a Pi e o notebook à mesma rede Wi-Fi.
2. Clone ou sincronize o repositório na Pi.
3. Entre em `apps/rover`, crie a `.venv` e instale `requirements.txt` (apenas `paho-mqtt` e `python-dotenv`, super leve para a Pi 3).
4. Crie `apps/rover/.env` a partir de `apps/rover/.env.example`, configurando `MQTT_HOST` com o **IP da estação-base (notebook)** na rede local (não `127.0.0.1`).
5. Na estação-base, certifique-se de que o Mosquitto escuta na interface de rede local (com autenticação/ACL configuradas conforme `docs/seguranca.md`) e que nenhum outro simulador esteja rodando ao mesmo tempo.
6. Na Raspberry Pi 3, execute:
   ```bash
   python -m roboticrover_pi3
   ```
7. Na Dashboard (<http://127.0.0.1:1880/dashboard>) ou no Debug do Node-RED, verifique `rover/status`: `simulated: false`, `online: true` e o `hostname` da Raspberry Pi.
8. Comande `BUSCA` na Dashboard e observe em `rover/cmd/ack` a confirmação com `execution: "simulated_only"`.
9. Comande `PARAR` (ou `Espaço`) e confirme o retorno imediato a `SEGURO_ESPERA`; nenhum motor físico será acionado.

## Ajuste realizado no Node-RED e na Dashboard

No nó `Verificar envelope e tópico` (`validate`) de `apps/station/node-red/flows.json`, a validação foi atualizada de:
```javascript
// antes: p.simulated !== true
// depois: typeof p.simulated !== "boolean"
```
E a Dashboard (`apps/station/node-red/dashboard.html`) foi atualizada para reconhecer tanto os pacotes do simulador completo (`rover`) quanto os pacotes do cliente de preparação da Raspberry Pi 3 (`roboticrover_pi3`, incluindo `simulated: false` no status, `hostname`, `execution: "simulated_only"` nos ACKs e `battery_voltage_v` quando `ENABLE_MOCK_TELEMETRY=true`).
