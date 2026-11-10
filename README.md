# RoboticRover

Infraestrutura inicial de comunicação MQTT entre Rover e estação-base. **Todos os
dados, sensores, falhas e movimentos desta versão são simulados. Nenhum código
aciona hardware.** A estação usa Mosquitto e Node-RED locais; não há APIs externas,
vídeo, YOLO nem dashboard definitiva.

Para preparar e demonstrar a comunicação em Windows, macOS ou Linux, siga
[TESTE_COMUNICACAO.md](TESTE_COMUNICACAO.md).

## Requisitos

- Python 3.9 ou superior (recomendado 3.11/3.12); Raspberry Pi OS atualizado para
  a futura Raspberry Pi 3. Dependências em `pyproject.toml`.
- Docker Engine/Desktop em modo Linux e Docker Compose v2 no notebook.
- VS Code com extensão Python é opcional. Não é necessário Arduino conectado.

## Iniciar no Windows / PowerShell

Execute os comandos na raiz do repositório. Copie o arquivo de ambiente somente
na primeira execução, preservando qualquer `.env` já existente:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path .venv)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
docker --version
docker compose version
docker compose config
docker compose up -d
docker compose ps
docker compose logs --tail 50 mosquitto node-red
.\.venv\Scripts\python.exe -m rover
```

O Compose inicia Mosquitto em `127.0.0.1:1883` e Node-RED em
<http://127.0.0.1:1880>. O simulador lê `.env` explicitamente a partir do diretório
atual; variáveis já exportadas no terminal têm precedência. Pode-se usar
`--env-file caminho` para selecionar outro arquivo. Não é preciso ativar a venv
nem alterar a política de execução do PowerShell.

Em Linux/macOS, use `[ -f .env ] || cp .env.example .env`,
`[ -d .venv ] || python3 -m venv .venv` e substitua
`.\.venv\Scripts\python.exe` por `.venv/bin/python`. Após instalar, também está
disponível o executável `rover-sim` dentro da venv. Não recrie `.venv` enquanto
ela estiver ativa; no Windows isso pode resultar em acesso negado ao próprio
`python.exe` em uso.

Se `docker` não for reconhecido, instale e inicie o Docker Desktop, feche e abra
novamente o terminal e confirme que `docker version` mostra cliente **e** servidor.
Se o simulador registrar `Broker indisponível`, ele está funcionando, mas ainda
não encontrou Mosquitto: inicie o Compose antes ou confira `MQTT_HOST` e
`MQTT_PORT`. As linhas de telemetria no console continuam sendo logs da geração
artificial local; elas não significam que a mensagem chegou ao broker.

No VS Code, selecione o interpretador `.venv`, abra a raiz do projeto e use F5
com a configuração **Rover: simulador MQTT**. Testes são descobertos pelo pytest.

## Testar os dois sentidos no Node-RED

O fluxo de [apps/station/node-red/flows.json](apps/station/node-red/flows.json)
é copiado para o volume persistente na primeira inicialização. Abra a aba
**RoboticRover • SIMULAÇÃO** e o painel **Debug**. O heartbeat começa sozinho;
aguarde um segundo após conectar o simulador.

1. Observe `telemetry`, `state`, `status`, `log` e o alarme `SIMULATION_ACTIVE`.
   Todos os envelopes possuem `simulated: true`. `status.online` significa que
   o cliente MQTT está conectado; heartbeat e estado seguro são condições separadas.
2. Clique nos botões Inject, nesta sequência: **BUSCA → APROXIMACAO →
   AGUARDANDO_PEGA → CAPTURA_MANUAL**. Cada clique gera UUID e validade de cinco
   segundos. Observe `ack.accepted: true` e a mudança de estado.
3. Em CAPTURA_MANUAL, clique **AVANCAR**. O movimento é apenas uma variável
   artificial; após 500 ms, o prazo local leva a SEGURO_ESPERA.
4. Clique **PARAR** ou **SEGURO_ESPERA** para solicitar parada. Clique
   CAPTURA_MANUAL a partir de SEGURO_ESPERA para verificar a rejeição
   `TRANSITION_FORBIDDEN` e seu ACK.

O fluxo também pode ser importado em outra instalação do Node-RED. Configure
`MQTT_HOST`, `MQTT_PORT`, `STATION_CLIENT_ID`, `STATION_SOURCE` no processo da
estação e adicione `crypto: require("crypto")` a `functionGlobalContext` em seu
`settings.js`, conforme o arquivo fornecido. Reinicie e importe o JSON.
Os nós usam apenas recursos padrão do Node-RED.

Deploys feitos no editor ficam no volume `node_red_data`. Para atualizar o fluxo
versionado sem sobrescrever outros trabalhos, exporte/importe pelo editor e faça
Deploy. Alterar o JSON do repositório não substitui automaticamente um fluxo já
existente no volume. Exporte as edições que desejar versionar.

## Configuração

As opções estão em [.env.example](.env.example):

| Variável | Uso / padrão |
| --- | --- |
| `MQTT_HOST`, `MQTT_PORT` | Simulador no host: `127.0.0.1:1883`; porta também publicada pelo Compose |
| `STATION_MQTT_HOST`, `STATION_MQTT_PORT` | Estação dentro do Docker: `mosquitto:1883` |
| `MQTT_CLIENT_ID`, `STATION_CLIENT_ID` | IDs distintos por processo; não execute duas instâncias com o mesmo ID |
| `STATION_SOURCE` | Origem esperada dos comandos e heartbeats: `station-nodered` |
| `MQTT_KEEPALIVE` | 5 s; reconexão Python com espera de 1 a 15 s |
| `TELEMETRY_INTERVAL` | 1 s |
| `HEARTBEAT_TIMEOUT` | 4 s sem heartbeat válido → estado seguro |
| `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_CA_FILE` | Credenciais e CA opcionais do cliente Python |
| `MQTT_BIND_ADDRESS`, `NODE_RED_PORT` | Endereço do listener publicado e porta do editor |
| `LOG_LEVEL` | `INFO`; logs locais também durante desconexões |

Se mudar a porta externa para 1884, mantenha `STATION_MQTT_PORT=1883`: é a porta
interna do serviço. Execute `docker compose up -d` e reinicie o simulador depois
de alterar variáveis. Nesta fase existe um único Rover por conjunto de tópicos.

## Tópicos e contratos

MQTT **5**, JSON UTF-8 até 16 KiB, envelope v1 e JSON Schema Draft 2020-12 em
[shared/contracts/v1/messages.schema.json](shared/contracts/v1/messages.schema.json).
Unidades estão nos nomes dos campos. Horários RFC 3339 com fuso (emissão em UTC).
Sincronize o relógio do notebook e, futuramente, da Pi.

| Tópico | QoS | Retained | Conteúdo |
| --- | --- | --- | --- |
| `rover/estado` | 1 | sim | Estado, estado anterior, motivo e movimento artificial |
| `rover/telemetria` | 0 | não | Bateria (%), temperatura (°C), proximidade (cm) |
| `rover/alarme` | 1 | não | Código, severidade e mensagem |
| `rover/log` | 0 | não | Nível, evento e mensagem |
| `rover/status` | 1 | sim | Disponibilidade MQTT; online, encerramento e Last Will |
| `rover/cmd/modo` | 1 | **não** | UUID, validade e modo desejado |
| `rover/cmd/manual` | 1 | **não** | UUID, validade, ação e duração (100–1000 ms) |
| `rover/cmd/ack` | 1 | não | UUID, tópico, aceitação/rejeição, motivo, estado e duplicata |
| `station/heartbeat` | 1 | **não** | Pulso da estação a cada 1 s, com UUID de sessão |

Exemplo de telemetria artificial:

```json
{"version":"1.0","timestamp":"2026-11-09T12:00:00.000Z","source":"rover-sim-01","simulated":true,"type":"telemetry","data":{"battery_percent":94.8,"temperature_c":42.1,"proximity_cm":{"front":80.0,"left":75.0,"right":110.0}}}
```

Exemplo de comando de modo (gere UUID e horários novos ao publicar; este exemplo
estático expirará):

```json
{"version":"1.0","timestamp":"2026-11-09T12:00:00.000Z","source":"station-nodered","simulated":true,"type":"mode_command","data":{"command_id":"12345678-1234-4234-8234-123456789abc","expires_at":"2026-11-09T12:00:05.000Z","mode":"BUSCA"}}
```

Exemplo de confirmação:

```json
{"version":"1.0","timestamp":"2026-11-09T12:00:00.100Z","source":"rover-sim-01","simulated":true,"type":"ack","data":{"command_id":"12345678-1234-4234-8234-123456789abc","topic":"rover/cmd/modo","accepted":true,"reason":"ACCEPTED","state":"BUSCA","duplicate":false}}
```

Um comando manual usa `type: "manual_command"` e `data` com `command_id`,
`expires_at`, `action` (`PARAR`, `AVANCAR`, `RECUAR`, `ESQUERDA`, `DIREITA`) e
`duration_ms`. `PARAR` aceita qualquer estado; os demais exigem CAPTURA_MANUAL.
O ACK confirma a decisão do simulador, sem comprovar execução de hardware.
Veja [docs/protocolo.md](docs/protocolo.md) para validade, duplicação e estados.

## Falhas e desconexões

```powershell
# Execute uma instância por vez; Ctrl+C encerra normalmente.
.\.venv\Scripts\python.exe -m rover --seed 42 --fault-after 15
.\.venv\Scripts\python.exe -m rover --crash-after 15
```

`--fault-after` injeta falha artificial, publica alarme e bloqueia novos movimentos
até reiniciar. `--crash-after` termina o processo sem DISCONNECT (código 2),
permitindo observar o Last Will `online: false` em `rover/status`.

Com BUSCA ativo, execute `docker compose stop node-red`: após aproximadamente
4 s, o simulador entra em SEGURO_ESPERA e publica alarme de perda de comunicação.
Use `docker compose start node-red`; o estado continua seguro até novo comando.
Para perda do broker, use `docker compose stop mosquitto` e depois
`docker compose start mosquitto`: o cliente tenta reconectar automaticamente e
volta seguro. Mosquitto sem persistência perde mensagens retained ao reiniciar;
o simulador republica estado/disponibilidade na reconexão.

O Last Will é configurado como retained, QoS 1. Seu timestamp é o instante em que
foi armado na criação do cliente, **não** o instante da detecção da queda. Uma
falha do próprio broker não permite publicar Will até ele voltar; heartbeat e
watchdog local são necessários independentemente do status MQTT.

**Parada MQTT não substitui uma parada física de emergência.** O futuro Arduino
deve ter watchdog independente para desligar motores se os comandos periódicos
deixarem de chegar, mesmo se a Raspberry Pi travar. Não conecte atuadores a este
simulador. Orientações de autenticação, ACL e TLS em
[docs/seguranca.md](docs/seguranca.md).

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# Com Compose iniciado e sem outro simulador rodando:
$env:RUN_MQTT_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -q -m integration
Remove-Item Env:RUN_MQTT_INTEGRATION
```

Em Linux/macOS: `RUN_MQTT_INTEGRATION=1 .venv/bin/python -m pytest -q -m integration`.
Os testes de integração criam seus próprios simuladores e publicam comandos
retained intencionalmente para verificar rejeição; execute somente no ambiente de
desenvolvimento dedicado. `MQTT_HOST`, `MQTT_PORT` e `NODE_RED_URL` podem apontar
para instâncias locais em outras portas. Sem a variável de integração, esses
testes são explicitamente ignorados, não considerados aprovados.

Os testes unitários cobrem contratos, os 25 pares de transição, TTL, UUID,
retenção, origem, duplicação, heartbeat, parada, prazo manual e falha. A integração
exercita MQTT real, nós Debug via WebSocket e comandos Inject do Node-RED.
Os testes de integração leem host/porta das variáveis exportadas no terminal;
se personalizou `.env`, exporte os mesmos valores antes da rodada. Resultados
realmente executados e limitações em [docs/verificacao.md](docs/verificacao.md).

## Estrutura e evolução

```text
apps/rover/rover/        cliente MQTT, controlador, sensores simulados e CLI
apps/station/node-red/  fluxo importável e configuração da estação
firmware/arduino-mega/  requisitos para o futuro firmware
vision/                limites da futura visão computacional
shared/contracts/v1/   schema versionado, incluído no pacote Python
infra/mqtt/            Mosquitto para desenvolvimento
tests/                 testes unitários e integração optativa
docs/                  protocolo, segurança e execução
```

Para o Rover físico, implemente uma fonte de sensores separada no lugar de
`SimulatedSensors`, mantenha validação/transporte e introduza uma interface de
atuadores com confirmação e watchdog no Arduino. Revise os contratos para
permitir `simulated: false` apenas após adicionar a fonte real: v1 desta entrega
exige `true`. Não basta alterar o rótulo dos valores artificiais.
O enlace serial Pi ↔ Mega, sensores, motores, servos, câmera, visão e endpoints
externos permanecem fora desta etapa.

Para encerrar a infraestrutura: `docker compose down`. O volume do Node-RED é
preservado; exporte seus fluxos antes de qualquer remoção desse volume.
