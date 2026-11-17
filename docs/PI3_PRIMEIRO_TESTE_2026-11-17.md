# Primeiro teste real da Raspberry Pi 3 — 17/11/2026

## Ambiente verificado

| Componente | Resultado observado |
|---|---|
| Placa | Raspberry Pi 3 Model B Rev 1.2 |
| Sistema | Debian GNU/Linux 13.7 (trixie), aarch64 |
| Python da Pi | 3.13.5 |
| Dependências instaladas na Pi | paho-mqtt 2.2.0, python-dotenv 1.2.4 |
| Acesso SSH | `puc@192.168.1.116`, hostname `puc` |
| IP do Mac nesta rede | `192.168.1.36` |
| Repositório na Pi | `/home/puc/RoboticRover` |
| Versão transferida | `18ee3255869a28a07a28aa37c9459d8a902c9a01`, branch `main` |
| Ambiente Python | `/home/puc/RoboticRover/apps/rover/.venv` |
| Broker / Node-RED | Executados nativamente no Mac, sem Docker |

O checkout foi transferido por Git bundle, preservando o histórico e sem copiar
`.env`, senha ou `.venv` do Mac. O `origin` da Pi aponta para o GitHub do projeto.
A instalação ficou separada dos demais projetos existentes na pasta do usuário.

## Comunicação utilizada

```text
Dashboard no Mac: http://127.0.0.1:1880/dashboard
                       |
                    Node-RED
                       |
Mosquitto no Mac: 127.0.0.1:1883
                       |
            túnel SSH reverso criptografado
                       |
Porta na Pi: 127.0.0.1:18883
                       |
            python -m roboticrover_pi3
```

`MQTT_HOST=127.0.0.1` na Pi é intencional **neste arranjo**, pois o destino local
é o túnel SSH. Não confundir com acesso direto ao broker por IP da LAN.
Não foi aberto listener MQTT na rede Wi-Fi. O broker anônimo permanece no
loopback do Mac e é acessível pela Pi através da sessão SSH autenticada.
Autenticação/ACL/TLS para uma implantação MQTT direta na LAN continuam pendentes.

Configuração criada em `/home/puc/RoboticRover/apps/rover/.env` (permissão 600):

```dotenv
MQTT_HOST=127.0.0.1
MQTT_PORT=18883
MQTT_CLIENT_ID=roboticrover-pi3
STATUS_INTERVAL_SEC=5
ENABLE_MOCK_TELEMETRY=false
LOG_LEVEL=INFO
```

## Resultados reproduzidos na Pi real

- **21 testes unitários aprovados** com Python 3.13/ARM64.
- `pip check`: nenhuma dependência incompatível.
- Status MQTT real com `simulated: false`, `online: true` e `hostname: puc`.
- **14 cenários de comando/ACK** enviados pelo endpoint HTTP do Node-RED:
  parada, BUSCA, APROXIMACAO, rejeição da entrada manual antecipada, rejeição de
  direção durante aproximação, tomada de controle, entrada manual, braço SUBIR,
  rejeição de SUBIR dirigido às rodas, troca para rodas, direção, retorno a BUSCA
  e espera ao final. IDs dos ACKs foram correlacionados aos comandos.
- ACKs com `execution: simulated_only`, `simulated: true` e destino identificado.
- **Watchdog real de comunicação:** interromper o Node-RED deixou de enviar
  heartbeat; a Pi entrou em SEGURO_ESPERA, publicou `manual_enabled: false` e
  emitiu `STATION_HEARTBEAT_TIMEOUT`. Node-RED foi reiniciado após esse teste.
- Dashboard HTTP respondeu com sucesso; a Pi ficou em espera ao final.

O transporte, a placa e o processo Linux são reais. Os estados, a pilotagem e o
braço continuam sendo simulação de software: nenhum GPIO, serial ou atuador é
acionado. Telemetria artificial permanece desativada, portanto os gráficos não
exibem medidas de sensores que ainda não foram integrados.

## Como iniciar novamente

Não inicie cópias adicionais se os processos desta sessão já estiverem ativos.
Use um terminal para cada processo abaixo; mantenha o Mac e a Pi conectados.

No Mac, na raiz do projeto, inicie o broker:

```bash
.venv/bin/mosquitto -c infra/mqtt/mosquitto.local.conf
```

Em outro terminal do Mac, inicie o Node-RED:

```bash
NODE_RED_HOST=127.0.0.1 node-red \
  --userDir .runtime/pi3-bootstrap/node-red \
  --settings apps/station/node-red/settings.js \
  "$PWD/apps/station/node-red/flows.json"
```

Em outro terminal do Mac, abra o SSH com o túnel reverso e deixe a conexão aberta:

```bash
ssh -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:18883:127.0.0.1:1883 \
  puc@192.168.1.116
```

No terminal conectado à Pi:

```bash
cd /home/puc/RoboticRover/apps/rover
.venv/bin/python -m roboticrover_pi3
```

Caso continue utilizando a conexão compartilhada desta sessão, o túnel já foi
registrado no master SSH de `/private/tmp/roboticrover-pi3.sock`. Não tente
registrar a mesma porta novamente. O acesso compartilhado pode ser conferido no
Mac com:

```bash
ssh -S /private/tmp/roboticrover-pi3.sock -O check puc@192.168.1.116
```

Abra `http://127.0.0.1:1880/dashboard` no Mac. Não execute o simulador `rover`
do Mac simultaneamente: os tópicos atuais representam um único Rover.
Se reiniciar somente o Node-RED, clique em **ESPERA** para atualizar o estado:
o cliente da Pi publica status periodicamente, mas ainda não retém o estado MQTT.
Para encerrar, interrompa o cliente da Pi antes do Node-RED, do broker e do SSH.
Não foram configurados serviços de inicialização automática/systemd neste teste.

## Próximas integrações

1. Identificar a webcam USB real e validar captura e streaming.
2. Definir o protocolo serial Pi↔Mega com handshake, ACK, timeout e integridade.
3. Implementar watchdog e parada local no Mega antes de comandar motores.
4. Integrar telemetria e atuação físicas progressivamente, com testes em bancada.
