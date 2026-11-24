# RoboticRover

Infraestrutura MQTT, cliente da Raspberry Pi 3 e **Dashboard do Operador**. O vídeo pode vir da webcam real. A tração tem uma ponte USB opt-in para Mega/NXT e firmware de bancada; o padrão continua em simulação. O braço ainda não tem atuação integrada.

O caminho dashboard → MQTT → Pi → Mega foi preparado e verificado com firmware virtual, sem acionar hardware. Para o teste físico futuro, consulte [CONTROLE_MANUAL_MOTORES.md](docs/CONTROLE_MANUAL_MOTORES.md).

A estação-base utiliza **Mosquitto** (broker MQTT v5) e **Node-RED** (fluxos MQTT + servidor da Dashboard em <http://127.0.0.1:1880/dashboard>), com duas visões de câmera configuráveis por **WebRTC/WHEP**, player WebRTC ou **MJPEG sobre HTTP**.

Você pode executar o projeto de **duas formas** em **Windows, macOS ou Linux**:
- **Opção 1 — Com Docker:** Mosquitto e Node-RED rodam em containers Docker; o simulador Python roda localmente.
- **Opção 2 — Sem Docker (Nativo):** Mosquitto, Node-RED e o simulador Python rodam diretamente no sistema operacional.

Para um roteiro adicional de laboratório, consulte também [TESTE_COMUNICACAO.md](TESTE_COMUNICACAO.md).

Para o modo oficial `rover04` (MQTT da arena, câmera H.264 e relé WHIP), siga o [roteiro da competição](docs/COMPETICAO_ROVER04.md).

Para iniciar os serviços do Mac e da Pi com um único comando, use `.venv/bin/python inicia_comunicacao.py` e escolha **1** (local) ou **2** (professor acessível pela rede). O servidor não precisa de internet. O roteiro completo, incluindo encerramento por Ctrl+C, está em [INICIA_COMUNICACAO.md](docs/INICIA_COMUNICACAO.md).

---

## Sumário

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Windows — Instalação e Execução (Com e Sem Docker)](#2-windows--instalação-e-execução)
3. [macOS — Instalação e Execução (Com e Sem Docker)](#3-macos--instalação-e-execução)
4. [Linux — Instalação e Execução (Com e Sem Docker)](#4-linux--instalação-e-execução)
5. [Como Visualizar e Testar o Funcionamento](#5-como-visualizar-e-testar-o-funcionamento)
6. [Como Executar os Testes Automatizados](#6-como-executar-os-testes-automatizados)
7. [Cliente de Preparação da Raspberry Pi 3 (`roboticrover_pi3`)](#7-cliente-de-preparação-da-raspberry-pi-3-roboticrover_pi3)
8. [Simulação de Falhas, Quedas e Reconexão](#8-simulação-de-falhas-quedas-e-reconexão)
9. [Configuração (`.env`), Tópicos e Contratos JSON](#9-configuração-env-tópicos-e-contratos-json)
10. [Estrutura do Repositório e Evolução para o Rover Físico](#10-estrutura-do-repositório-e-evolução-para-o-rover-físico)

---

## 1. Visão Geral da Arquitetura

```text
Simulador Python (rover)
       │
       │ MQTT v5 em 127.0.0.1:1883
       ▼
Broker Mosquitto (Docker ou Nativo)
       │
       ▼
Node-RED (Docker ou Nativo) ──► Editor do Fluxo:  http://127.0.0.1:1880/#flow/rover-tab
                             ──► Dashboard Web:   http://127.0.0.1:1880/dashboard
                             ──► WebSocket Tempo Real: ws://127.0.0.1:1880/ws/rover
```

---

## 2. Windows — Instalação e Execução

Abra o **PowerShell** na raiz do repositório (`cd C:\caminho\para\RoboticRover`).

### 2.A. Windows COM Docker

#### 1. Instalar dependências
1. Instale o **Python 3.11 ou 3.12** ([python.org](https://www.python.org/downloads/)) marcando *"Add python.exe to PATH"* e o launcher `py`, ou via Winget:
   ```powershell
   winget install Python.Python.3.12
   ```
2. Instale o **Docker Desktop para Windows** ([docs.docker.com](https://docs.docker.com/desktop/setup/install/windows-install/)) com backend WSL 2, abra o aplicativo e aguarde o status **Engine running**.
3. Feche e reabra o PowerShell e confirme:
   ```powershell
   py --version
   docker version
   docker compose version
   ```

#### 2. Preparar e executar
No **Terminal 1 (PowerShell)**:
```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path .venv)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Iniciar Mosquitto e Node-RED no Docker
docker compose up -d --force-recreate node-red-init node-red
docker compose ps

# Iniciar o simulador do Rover
.\.venv\Scripts\python.exe -m rover
```

---

### 2.B. Windows SEM Docker (Mosquitto + Node-RED nativos)

#### 1. Instalar dependências
No PowerShell, instale **Python 3.12**, **Node.js LTS**, **Mosquitto** e o **Node-RED**:
```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install EclipseFoundation.Mosquitto
```
Feche e reabra o PowerShell para atualizar o `PATH`, depois instale o Node-RED globalmente:
```powershell
npm install -g --unsafe-perm node-red
```
*(Observação: se o serviço do Mosquitto do Windows já iniciar automaticamente na porta 1883, pare-o antes com `Stop-Service mosquitto` caso queira rodá-lo manualmente no terminal com o arquivo de configuração do projeto).*

#### 2. Preparar o ambiente Python
```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path .venv)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

#### 3. Executar em 3 terminais PowerShell na raiz do projeto

- **Terminal 1 — Mosquitto:**
  ```powershell
  & "C:\Program Files\mosquitto\mosquitto.exe" -c infra\mqtt\mosquitto.conf -v
  ```
  *(Se o comando `mosquitto` já estiver no PATH, basta `mosquitto -c infra\mqtt\mosquitto.conf -v`).*

- **Terminal 2 — Node-RED (já carregando o fluxo e a Dashboard do projeto):**
  ```powershell
  node-red --settings apps\station\node-red\settings.js apps\station\node-red\flows.json
  ```
  *(Alternativa: se o seu Node-RED já estiver aberto pelo comando `node-red` padrão, abra `http://127.0.0.1:1880`, clique no menu `☰ → Import`, selecione `apps\station\node-red\flows.json` e clique em **Deploy**).*

- **Terminal 3 — Simulador Python do Rover:**
  ```powershell
  .\.venv\Scripts\python.exe -m rover
  ```

---

## 3. macOS — Instalação e Execução

Abra o **Terminal** na raiz do repositório (`cd /caminho/para/RoboticRover`).

### 3.A. macOS COM Docker

#### 1. Instalar dependências
1. Instale o **Python 3.11+** e o **Docker Desktop para Mac** (Apple Silicon `arm64` ou Intel `x86_64`):
   ```bash
   brew install python
   brew install --cask docker
   ```
2. Abra o aplicativo `Docker.app` e aguarde o motor inicializar.
3. Confirme no Terminal:
   ```bash
   python3 --version
   docker version
   docker compose version
   ```

#### 2. Preparar e executar
```bash
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Iniciar Mosquitto e Node-RED no Docker
docker compose up -d --force-recreate node-red-init node-red
docker compose ps

# Iniciar o simulador do Rover
.venv/bin/python -m rover
```

---

### 3.B. macOS SEM Docker (Mosquitto + Node-RED nativos)

#### 1. Instalar dependências
Com o [Homebrew](https://brew.sh/) instalado:
```bash
brew install python mosquitto node
npm install -g --unsafe-perm node-red
```

#### 2. Preparar o ambiente Python
```bash
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

#### 3. Executar em 3 abas do Terminal na raiz do projeto

- **Terminal 1 — Mosquitto:**
  ```bash
  mosquitto -c infra/mqtt/mosquitto.conf -v
  ```
  *(Caso o comando `mosquitto` não esteja no PATH padrão do Apple Silicon, use `/opt/homebrew/sbin/mosquitto -c infra/mqtt/mosquitto.conf -v` ou, em Mac Intel, `/usr/local/sbin/mosquitto -c infra/mqtt/mosquitto.conf -v`. Se já estiver rodando via `brew services start mosquitto`, pule este terminal).*

- **Terminal 2 — Node-RED (carregando o fluxo e a Dashboard do projeto):**
  ```bash
  node-red --settings apps/station/node-red/settings.js apps/station/node-red/flows.json
  ```
  *(Alternativa: se você já estiver com o `node-red` aberto, acesse `http://127.0.0.1:1880`, vá no menu `☰ → Import`, importe o arquivo `apps/station/node-red/flows.json` e clique em **Deploy**).*

- **Terminal 3 — Simulador Python do Rover:**
  ```bash
  .venv/bin/python -m rover
  ```

---

## 4. Linux — Instalação e Execução

Abra um terminal na raiz do repositório (`cd /caminho/para/RoboticRover`).

### 4.A. Linux COM Docker

#### 1. Instalar dependências
- **Ubuntu / Debian / Raspberry Pi OS:**
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip
  ```
  Instale o **Docker Engine** e o plugin **Docker Compose** seguindo a [documentação oficial do Docker para Linux](https://docs.docker.com/engine/install/) e adicione seu usuário ao grupo `docker` (`sudo usermod -aG docker $USER`, depois encerre e inicie a sessão).
- Confirme:
  ```bash
  python3 --version
  docker version
  docker compose version
  ```

#### 2. Preparar e executar
```bash
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Iniciar Mosquitto e Node-RED no Docker
docker compose up -d --force-recreate node-red-init node-red
docker compose ps

# Iniciar o simulador do Rover
.venv/bin/python -m rover
```

---

### 4.B. Linux SEM Docker (Mosquitto + Node-RED nativos)

#### 1. Instalar dependências
- **Ubuntu / Debian:**
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip mosquitto mosquitto-clients nodejs npm
  sudo npm install -g --unsafe-perm node-red
  ```
- **Fedora:**
  ```bash
  sudo dnf install -y python3 python3-pip mosquitto nodejs npm
  sudo npm install -g --unsafe-perm node-red
  ```
- **Arch Linux:**
  ```bash
  sudo pacman -S python python-pip mosquitto nodejs npm
  sudo npm install -g --unsafe-perm node-red
  ```

*(Observação: no Linux, o pacote `mosquitto` geralmente inicia um serviço em segundo plano na porta 1883. Para usar o arquivo `infra/mqtt/mosquitto.conf` do projeto no terminal, pare o serviço padrão antes com `sudo systemctl stop mosquitto`, ou mantenha o serviço ativo caso ele já escute em `127.0.0.1:1883`).*

#### 2. Preparar o ambiente Python
```bash
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

#### 3. Executar em 3 terminais na raiz do projeto

- **Terminal 1 — Mosquitto:**
  ```bash
  mosquitto -c infra/mqtt/mosquitto.conf -v
  ```
- **Terminal 2 — Node-RED:**
  ```bash
  node-red --settings apps/station/node-red/settings.js apps/station/node-red/flows.json
  ```
  *(Ou importe `apps/station/node-red/flows.json` pelo menu `☰ → Import` no Node-RED já aberto e clique em **Deploy**).*
- **Terminal 3 — Simulador Python do Rover:**
  ```bash
  .venv/bin/python -m rover
  ```

---

## 5. Como Visualizar e Testar o Funcionamento

Assim que **Mosquitto**, **Node-RED** e o **Simulador Python** estiverem rodando, estão disponíveis os seguintes endereços locais:

| Recurso | URL | Descrição |
| --- | --- | --- |
| **Dashboard do Operador** | <http://127.0.0.1:1880/dashboard> | Painel completo de telemetria, câmera híbrida e comandos |
| **Editor de Fluxos Node-RED** | <http://127.0.0.1:1880/#flow/rover-tab> | Fluxo MQTT visual, botões Inject e aba Debug |
| **Snapshot JSON (API REST)** | <http://127.0.0.1:1880/api/rover/snapshot> | Estado atual, última telemetria e histórico recente em JSON |
| **WebSocket da Dashboard** | `ws://127.0.0.1:1880/ws/rover` | Stream bidirecional de envelopes MQTT e comandos |

### 5.1. Roteiro passo a passo na Dashboard (<http://127.0.0.1:1880/dashboard>)

1. Verifique **WS: conectado** e **Rover: online**. O link **Fluxo Node-RED** abre o editor; a origem dos dados e a idade do último pacote ficam no rodapé.
2. Os modos **ESPERA**, **BUSCA**, **APROXIMAÇÃO** e **MANUAL** ficam alinhados abaixo da navbar. O destaque indica o estado recebido do Rover, não apenas o botão clicado. Busca/aproximação continuam sendo estados simulados, sem navegação física implementada.
3. Selecione **Visão Rover** ou **Visão Satélite** e use a engrenagem para configurar um stream MJPEG, WHEP ou player WebRTC. Cada visão conserva sua própria URL no navegador. Sem stream configurado, o painel mostra a câmera indisponível; não produz vídeo artificial. A câmera satélite depende de uma fonte externa fornecida pelo operador.
4. Em BUSCA e APROXIMAÇÃO, todos os botões do direcional, inclusive **■**, ficam apagados e desabilitados; WASD, setas e Esc não enviam comandos manuais. MANUAL também permanece indisponível até a autorização do Rover. A conclusão da aproximação (`AGUARDANDO_PEGA`, `manual_enabled: true`) libera o controle com o braço selecionado. O método `approach_completed()` é o ponto de entrada para a futura navegação confirmar chegada e parada; o simulador não inventa chegada por temporizador. Os Injects do fluxo permitem representar essa conclusão nos testes.
5. **Espaço**, fora de campos de edição, solicita parada forçada com `take_control: true`; após confirmação e autorização do Rover, a dashboard entra em modo manual. O alternador no canto superior direito escolhe **Pilotar Rover / Controlar braço** e envia parada antes da troca. WASD, setas e cliques controlam o destino selecionado; **■** ou Esc interrompe o manual. O ícone **ⓘ** abre o mapa dos controles. Cada movimento dura 500 ms; o prazo local permanece ativo. O botão **BUSCA** devolve a operação ao automático e revoga a autorização manual. Falhas, perda do heartbeat e reconexões também revogam essa autorização no controlador.
6. O **Registro de operações** reúne estados, conexões, ACKs, avisos e erros, com cores e filtros. Clique em um registro para abrir o envelope completo. O Node-RED conserva até 200 eventos em memória; reiniciar o serviço limpa esse histórico.
7. **Bateria e temperatura** abre os gráficos em popup. Eles recebem telemetria continuamente, mas só são desenhados quando o popup está aberto. Feche com Esc, pelo botão ou clicando fora.

Após editar `dashboard.html`, sincronize o template e reinicie o Node-RED:

```bash
node apps/station/node-red/sync-dashboard.js
```

A webcam USB da Pi 3 já pode alimentar a **Visão Rover** por MJPEG através de
túnel SSH, com indicação de FPS e reconexão. Instalação, comandos, limites de
frescor e resultados medidos estão em [docs/PI3_CAMERA.md](docs/PI3_CAMERA.md).
O módulo é executado separadamente: `python -m roboticrover_pi3.camera`.

---

### 5.2. Roteiro pelo Editor do Node-RED (<http://127.0.0.1:1880/#flow/rover-tab>)

1. Abra <http://127.0.0.1:1880/#flow/rover-tab> e clique no ícone de inseto (**Debug**) na barra lateral direita.
2. Observe as mensagens chegando nos nós `SIMULADO · telemetry`, `SIMULADO · state`, `SIMULADO · status`, `SIMULADO · log` e `SIMULADO · alarm`.
3. Clique nos botões azuis à esquerda dos nós Inject (`BUSCA`, `APROXIMACAO`, `AGUARDANDO_PEGA`, `CAPTURA_MANUAL`, `AVANCAR`, `PARAR`) e confira as respostas em `SIMULADO · ack`.

---

## 6. Como Executar os Testes Automatizados

### 6.1. Testes Unitários e de Infraestrutura (não exigem Mosquitto nem Node-RED rodando)

- **Windows (PowerShell):**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q
  ```
- **macOS / Linux:**
  ```bash
  .venv/bin/python -m pytest -q
  ```
*(Resultado esperado: **149 aprovados** e **9 ignorados**, referentes aos testes de integração real).*

Também é possível rodar isoladamente a suíte `unittest` do pacote da Raspberry Pi 3:
```bash
cd apps/rover
../../.venv/bin/python -m unittest discover -s tests -v
```
*(Resultado esperado: **29 testes aprovados**).*

### 6.2. Testes de Integração Real (com Mosquitto e Node-RED ativos — Com ou Sem Docker)

1. Certifique-se de que **Mosquitto** (`127.0.0.1:1883`) e **Node-RED** (`127.0.0.1:1880` com o fluxo do projeto) estão em execução.
2. **Pare** qualquer instância manual do simulador (`Ctrl+C`), pois a suíte de integração inicia e encerra seus próprios processos do simulador.
3. Execute:
   - **Windows (PowerShell):**
     ```powershell
     $env:RUN_MQTT_INTEGRATION = "1"
     .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m integration
     Remove-Item Env:RUN_MQTT_INTEGRATION
     ```
   - **macOS / Linux:**
     ```bash
     RUN_MQTT_INTEGRATION=1 .venv/bin/python -m pytest -q -p no:cacheprovider -m integration
     ```
*(Resultado esperado: **9 aprovados**, validando MQTT real, Debug do Node-RED, Injects, ACKs, rejeições, Last Will, watchdog de heartbeat, Dashboard HTTP/WebSocket e tomada de controle manual com correlação de comandos).*

---

## 7. Cliente de Preparação da Raspberry Pi 3 (`roboticrover_pi3`)

Além do simulador completo (`python -m rover`), o repositório inclui o pacote leve **`roboticrover_pi3`** (em `apps/rover/roboticrover_pi3/`), projetado especificamente para o **teste de fumaça MQTT da Raspberry Pi 3 ↔ estação-base** antes de conectar o Arduino Mega ou motores. Detalhes adicionais estão em [docs/PI3_MQTT.md](docs/PI3_MQTT.md) e [shared/contracts/MQTT_V1.md](shared/contracts/MQTT_V1.md).

Características do `roboticrover_pi3`:
- Publica `rover/status` com `simulated: false`, `online: true/false` (incluindo LWT retained) e o `hostname` real do Linux, comprovando a conectividade da placa.
- Por padrão mantém ACK/estado simulados, sem abrir USB. Com `MOTOR_BACKEND=serial` explícito, usa o firmware RR1 e publica `execution: "mega_accepted"` somente após ACK do Mega; isso não confirma deslocamento físico. Veja o [roteiro de tração](docs/CONTROLE_MANUAL_MOTORES.md).
- Não publica telemetria inventada por padrão (`ENABLE_MOCK_TELEMETRY=false`).
- Valida UUID, TTL (`expires_at`), janela de timestamp, sessão de `station/heartbeat` e rejeita comandos `retained`.

### 7.1. Rodar o cliente da Pi 3 agora no notebook (sem a placa física)

Pare o simulador `rover` anterior (`Ctrl+C`) para não haver dois clientes disputando os mesmos tópicos e execute na raiz do projeto:

- **Windows (PowerShell):**
  ```powershell
  .\.venv\Scripts\python.exe -m roboticrover_pi3
  ```
- **macOS / Linux:**
  ```bash
  .venv/bin/python -m roboticrover_pi3
  ```
*(Ou diretamente em `apps/rover`: copie `apps/rover/.env.example` para `apps/rover/.env`, defina `MQTT_HOST=127.0.0.1` e execute `python -m roboticrover_pi3`).*

Abra a Dashboard (<http://127.0.0.1:1880/dashboard>): o topo mostrará `PI 3 MQTT • SEM ATUAÇÃO FÍSICA` e `ROVER: ONLINE (raspberry-pi3 • <hostname>)`, permitindo testar toda a máquina de estados e os ACKs (`execution: simulated_only`).

### 7.2. Rodar posteriormente na Raspberry Pi 3 real (quando a placa estiver pronta)

1. Conecte a Raspberry Pi 3 e o notebook (estação-base) à mesma rede Wi-Fi.
2. No notebook, configure o Mosquitto para escutar na rede local com autenticação/ACL (veja [docs/seguranca.md](docs/seguranca.md)) e descubra o IP local do notebook (ex.: `192.168.1.100`).
3. Na Raspberry Pi 3 (via SSH), clone o repositório e instale apenas as dependências leves de `apps/rover`:
   ```bash
   cd RoboticRover/apps/rover
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   cp .env.example .env
   ```
4. Edite `apps/rover/.env` na Raspberry Pi 3 apontando `MQTT_HOST` para o **IP do notebook** (nunca `127.0.0.1` na Pi, pois o broker roda no notebook).
5. Execute os testes locais e inicie o cliente na Pi 3:
   ```bash
   python -m unittest discover -s tests -v
   python -m roboticrover_pi3
   ```

---

## 8. Simulação de Falhas, Quedas e Reconexão

Execute apenas uma instância do simulador por vez (`Ctrl+C` para parar):

- **Falha artificial de sensor (bloqueia novos movimentos até reiniciar):**
  - Windows: `.\.venv\Scripts\python.exe -m rover --seed 42 --fault-after 15`
  - macOS/Linux: `.venv/bin/python -m rover --seed 42 --fault-after 15`
  - Após 15 s, publica `SIMULATED_SENSOR_FAULT` em `rover/alarme`, entra em `SEGURO_ESPERA` e rejeita comandos com `FAULT_LATCHED`.

- **Queda abrupta do processo (teste de Last Will no broker):**
  - Windows: `.\.venv\Scripts\python.exe -m rover --crash-after 15`
  - macOS/Linux: `.venv/bin/python -m rover --crash-after 15`
  - Após 15 s, encerra sem enviar `DISCONNECT`; o Mosquitto publica automaticamente o Last Will em `rover/status` com `online: false` e `reason: "last_will_armed_at_timestamp"`.

- **Perda do Node-RED (teste de timeout de Heartbeat):**
  - Coloque o Rover em `BUSCA` e pare o Node-RED (`Ctrl+C` no terminal do Node-RED ou `docker compose stop node-red`).
  - Após ~4 s sem `station/heartbeat`, o simulador entra em `SEGURO_ESPERA` e emite o alarme `COMMUNICATION_LOST`.

> A parada via MQTT não substitui interrupção física da alimentação. O firmware RR1 possui watchdog local de referência; os prazos e a parada mecânica ainda precisam de medição na bancada.

---

## 9. Configuração (`.env`), Tópicos e Contratos JSON

As opções estão documentadas em [.env.example](.env.example):

| Variável | Uso / padrão |
| --- | --- |
| `MQTT_HOST`, `MQTT_PORT` | Endereço do broker para o simulador Python: `127.0.0.1:1883` |
| `STATION_MQTT_HOST`, `STATION_MQTT_PORT` | Endereço do broker para o container Node-RED no Docker: `mosquitto:1883` |
| `MQTT_CLIENT_ID`, `STATION_CLIENT_ID` | Identificadores únicos dos clientes MQTT (`rover-sim-01`, `station-nodered-01`) |
| `STATION_SOURCE` | Origem esperada nos comandos e heartbeats: `station-nodered` |
| `MQTT_KEEPALIVE` | `5` segundos (reconexão automática de 1 a 15 s) |
| `TELEMETRY_INTERVAL` | `1` segundo entre amostras de telemetria |
| `HEARTBEAT_TIMEOUT` | `4` segundos sem heartbeat válido → entra em `SEGURO_ESPERA` |
| `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_CA_FILE` | Credenciais e certificado CA opcionais |
| `MQTT_BIND_ADDRESS`, `NODE_RED_PORT` | Bind local (`127.0.0.1`) e porta web do Node-RED (`1880`) |
| `LOG_LEVEL` | `INFO` |

### Tópicos MQTT v5 e Políticas

Schema completo (JSON Schema Draft 2020-12) em [shared/contracts/v1/messages.schema.json](shared/contracts/v1/messages.schema.json) e detalhes em [docs/protocolo.md](docs/protocolo.md):

A telemetria contém somente bateria e temperatura. Sensores dedicados de distância/proximidade e movimento foram retirados do escopo; o campo antigo `proximity_cm` não é mais aceito pelo schema. Atualize os clientes e reinicie o Node-RED com o fluxo atual para carregar a dashboard sem radar.

| Tópico | QoS | Retained | Conteúdo |
| --- | --- | --- | --- |
| `rover/estado` | 1 | sim | Estado atual, estado anterior, motivo e movimento artificial |
| `rover/telemetria` | 0 | não | Bateria (`%`) e temperatura (`°C`) |
| `rover/alarme` | 1 | não | Código, severidade (`warning`, `critical`) e mensagem |
| `rover/log` | 0 | não | Nível (`INFO`, `WARNING`, `ERROR`), evento e mensagem |
| `rover/status` | 1 | sim | Disponibilidade MQTT (`online`), motivo de encerramento e Last Will |
| `rover/cmd/modo` | 1 | **não** | `command_id` (UUID), `expires_at` e `mode` desejado |
| `rover/cmd/manual` | 1 | **não** | `command_id` (UUID), `expires_at`, `action` e `duration_ms` (100–1000 ms) |
| `rover/cmd/ack` | 1 | não | `command_id`, `topic`, `accepted`, `reason`, `state` e `duplicate` |
| `station/heartbeat` | 1 | **não** | Pulso da estação a cada 1 s com `session_id` (UUID) |

---

## 10. Estrutura do Repositório e Evolução para o Rover Físico

```text
apps/rover/rover/              Simulador completo com telemetria artificial e injeção de falhas
apps/rover/roboticrover_pi3/   Cliente MQTT leve da Raspberry Pi 3 (status real Linux + estados simulados)
apps/station/node-red/         Fluxo importável (flows.json), Dashboard HTML (dashboard.html) e settings.js
firmware/arduino-mega/         Especificação e espaço para o futuro firmware do Arduino Mega 2560
vision/                        Espaço para captura de câmera e modelos de visão computacional
shared/contracts/v1/           JSON Schema versionado das mensagens MQTT e contrato MQTT_V1.md
infra/mqtt/                    Configuração do broker Mosquitto para desenvolvimento
tests/                         Testes unitários, de infraestrutura e de integração MQTT/Node-RED
docs/                          Documentação de protocolo, segurança, verificação e preparação da Pi 3
```

Para substituir o simulador pelo Rover físico na Raspberry Pi 3:
1. Implemente uma classe de leitura real (ex.: serial com Arduino Mega) substituindo `SimulatedSensors` em `apps/rover/rover/`.
2. Atualize o schema para permitir `simulated: false` somente quando os dados vierem do hardware real.
3. Configure autenticação, ACL e TLS no Mosquitto conforme [docs/seguranca.md](docs/seguranca.md) antes de abrir o broker na rede Wi-Fi local.
4. Na Dashboard (<http://127.0.0.1:1880/dashboard>), selecione **Visão Rover**, abra a engrenagem e configure **WebRTC (WHEP)** ou **MJPEG HTTP** com a URL do stream da Raspberry Pi.
