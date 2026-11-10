# Teste de comunicação MQTT — Windows, macOS e Linux

Este guia reproduz o teste completo da comunicação bidirecional entre o Rover
simulado e a estação-base. Ele cobre a instalação, a execução, o fluxo visual no
Node-RED, os testes automáticos e os problemas mais comuns.

**Nenhum hardware é necessário.** Não conecte Raspberry Pi, Arduino, motores,
servos, sensores ou câmera. Todos os valores e movimentos desta etapa são
artificiais e as mensagens possuem `simulated: true`.

## O que será executado

```text
Simulador Python
      │
      │ MQTT em 127.0.0.1:1883
      ▼
Mosquitto no Docker
      │
      ▼
Node-RED no Docker ─── navegador em 127.0.0.1:1880
```

O Docker executa somente a estação-base no notebook. A aplicação Python é
executada diretamente no sistema operacional. No futuro, ela será executada na
Raspberry Pi sem exigir Docker na placa.

## Dependências

| Dependência | Uso | Observação |
| --- | --- | --- |
| Python | Simulador e testes | Requer 3.9 ou superior; prefira 3.11 ou 3.12 |
| Docker com Compose | Mosquitto e Node-RED | Docker Desktop no Windows/macOS ou Docker Engine no Linux |
| Navegador | Editor e Debug do Node-RED | Chrome, Firefox, Edge, Brave ou Safari |
| Git | Obter e atualizar o repositório | Opcional se o projeto for copiado por outro meio |

As bibliotecas Python são instaladas pelo `pyproject.toml`: Paho MQTT,
JSON Schema, validador RFC 3339, dotenv, pytest, PyYAML e cliente WebSocket.
Node.js, Node-RED e Mosquitto não precisam ser instalados separadamente no host.

Referências oficiais de instalação:

- [Python](https://www.python.org/downloads/)
- [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Desktop para macOS](https://docs.docker.com/desktop/setup/install/mac-install/)
- [Docker Engine para distribuições Linux](https://docs.docker.com/engine/install/)

## 1. Instalar e verificar no Windows

Instale Python marcando a opção do instalador que disponibiliza o launcher `py`.
Instale o Docker Desktop usando o backend Linux/WSL 2 e abra o aplicativo. Aguarde
até a interface mostrar **Engine running**.

Feche terminais e o VS Code que estavam abertos antes da instalação. Abra um novo
PowerShell e execute:

```powershell
py --version
docker version
docker compose version
```

`docker version` deve mostrar as seções `Client` e `Server`. Se o Docker Desktop
estiver aberto, mas `docker` não for reconhecido, reabra o PowerShell. Na instalação
global padrão, também é possível atualizar somente o terminal atual:

```powershell
$env:Path += ";C:\Program Files\Docker\Docker\resources\bin"
docker version
```

Se ainda não funcionar, reinicie o Windows uma vez. Não é necessário ativar a
venv para usar o Docker.

## 2. Instalar e verificar no macOS

Descubra a arquitetura do Mac:

```bash
uname -m
```

`arm64` indica Apple Silicon; `x86_64` indica Intel. Instale a edição correspondente
do Docker Desktop, abra `Docker.app` e aguarde o mecanismo iniciar. Instale Python
3 pela distribuição oficial ou pelo gerenciador adotado no laboratório.

Abra um novo Terminal e execute:

```bash
python3 --version
docker version
docker compose version
```

O Docker Desktop deve permanecer aberto durante o teste.

## 3. Instalar e verificar no Linux

Instale Python 3, `pip` e o módulo `venv` pelos pacotes da sua distribuição.
Instale Docker Engine e o plugin Docker Compose seguindo a página oficial da sua
distribuição. Inicie o serviço Docker e configure seu usuário para utilizá-lo de
acordo com a política da máquina.

Verifique:

```bash
python3 --version
docker version
docker compose version
```

Se aparecer `permission denied` ao acessar o socket do Docker, conclua a
configuração de permissões indicada pela documentação da distribuição e entre
novamente na sessão. Usar `sudo` em todos os comandos pode criar arquivos com
proprietário incorreto no diretório do projeto.

## 4. Preparar o projeto

Abra um terminal na raiz do repositório, onde estão `compose.yaml` e
`pyproject.toml`.

### Windows — PowerShell

```powershell
cd C:\caminho\para\RoboticRover

if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path .venv)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
```

### macOS ou Linux

```bash
cd /caminho/para/RoboticRover

[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pip check
```

Não recrie `.venv` enquanto ela estiver ativa. No Windows isso pode gerar
`Permission denied` sobre `.venv\Scripts\python.exe`. Se a pasta já existe e a
instalação das dependências termina com sucesso, continue para a próxima etapa.

O `.env` padrão usa somente o próprio notebook:

```dotenv
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_BIND_ADDRESS=127.0.0.1
NODE_RED_PORT=1880
```

Não altere esses valores para o teste sem hardware.

## 5. Iniciar Mosquitto e Node-RED

No primeiro terminal:

```bash
docker compose config
docker compose pull
docker compose up -d
docker compose ps
```

O resultado esperado contém:

```text
mosquitto   Up ... (healthy)   127.0.0.1:1883->1883/tcp
node-red    Up ... (healthy)   127.0.0.1:1880->1880/tcp
```

Para acompanhar a inicialização:

```bash
docker compose logs --tail 100 mosquitto node-red
```

O serviço `node-red-init` prepara o fluxo no volume e encerra. Em
`docker compose ps --all`, `node-red-init` aparecer como `Exited (0)` é esperado
e significa sucesso.

## 6. Iniciar o Rover simulado

Abra um segundo terminal na raiz do projeto.

Windows:

```powershell
.\.venv\Scripts\python.exe -m rover
```

macOS/Linux:

```bash
.venv/bin/python -m rover
```

Deixe esse terminal aberto. O simulador tentará reconectar automaticamente se o
broker for interrompido. Linhas com `rover/telemetria`, `rover/estado` e
`rover/status` são esperadas.

Se aparecer repetidamente `Broker indisponível`, confira:

```bash
docker compose ps
docker compose logs --tail 100 mosquitto
```

As linhas de telemetria no terminal são logs da geração local. Elas só chegam ao
Node-RED depois que a conexão com Mosquitto é estabelecida.

## 7. Abrir e testar no Node-RED

Abra diretamente:

[http://127.0.0.1:1880/#flow/rover-tab](http://127.0.0.1:1880/#flow/rover-tab)

A aba deve se chamar **RoboticRover • SIMULAÇÃO**. Se o navegador estava aberto
antes da inicialização, atualize com `Ctrl+F5` no Windows/Linux ou
`Command+Shift+R` no macOS.

No canto superior direito, clique no ícone de inseto para abrir o painel
**Debug**. Aguarde aparecerem:

- `rover/telemetria`
- `rover/estado`
- `rover/status`
- `rover/log`
- o alarme `SIMULATION_ACTIVE`

Use o botão `−` no canto inferior direito para reduzir o zoom se todos os nós não
estiverem visíveis. Nos nós azuis, o pequeno botão à esquerda envia o comando.

Clique, aguardando o ACK após cada etapa:

```text
BUSCA
  ↓
APROXIMACAO
  ↓
AGUARDANDO_PEGA
  ↓
CAPTURA_MANUAL
```

Para cada comando, o Debug deve mostrar um `rover/cmd/ack` semelhante a:

```json
{
  "accepted": true,
  "reason": "ACCEPTED",
  "state": "BUSCA",
  "duplicate": false
}
```

Também aparece `rover/estado` com o estado anterior, novo estado, motivo e
`motion: "PARAR"`.

Em `CAPTURA_MANUAL`, clique em **AVANCAR**. O estado mostrará
`motion: "AVANCAR"`. Após aproximadamente 500 ms, o prazo local de segurança
expira e o Rover volta para:

```text
state: SEGURO_ESPERA
motion: PARAR
reason: manual_deadline_expired
```

O botão **PARAR** pode ser usado em qualquer estado e leva imediatamente a
`SEGURO_ESPERA`.

### Testar uma rejeição

Estando em `SEGURO_ESPERA`, clique diretamente em **CAPTURA_MANUAL**. Essa
transição não é permitida e deve produzir:

```json
{
  "accepted": false,
  "reason": "TRANSITION_FORBIDDEN",
  "state": "SEGURO_ESPERA"
}
```

Depois, clique em **BUSCA** para iniciar novamente a sequência válida.

## 8. Executar os testes automáticos

### Testes sem infraestrutura externa

Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

macOS/Linux:

```bash
.venv/bin/python -m pytest -q
```

Os testes de integração aparecem como ignorados nessa execução, pois precisam ser
habilitados explicitamente. Na verificação desta versão, o resultado foi
**105 aprovados e 7 ignorados**.

### Integração real com o Compose

Pare primeiro qualquer simulador iniciado manualmente com `Ctrl+C`. Os testes de
integração criam e encerram suas próprias instâncias.

Windows:

```powershell
$env:RUN_MQTT_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m integration
Remove-Item Env:RUN_MQTT_INTEGRATION
```

macOS/Linux:

```bash
RUN_MQTT_INTEGRATION=1 .venv/bin/python -m pytest -q -p no:cacheprovider -m integration
```

O resultado de referência desta versão é **7 aprovados**. Esses testes verificam
o fluxo Debug, Injects do Node-RED, ACKs, comandos inválidos, duplicatas, Last
Will, falha artificial, heartbeat, parada segura e reconexão.

O projeto foi desenhado para um Rover por conjunto de tópicos. Dois simuladores
manuais executados ao mesmo tempo recebem os mesmos comandos e geram dois ACKs.

## 9. Testar falhas e reconexão

Execute um cenário por vez.

### Falha artificial

Windows:

```powershell
.\.venv\Scripts\python.exe -m rover --fault-after 15
```

macOS/Linux:

```bash
.venv/bin/python -m rover --fault-after 15
```

Após 15 segundos, deve aparecer `SIMULATED_SENSOR_FAULT`; novos movimentos são
rejeitados até reiniciar o simulador.

### Queda abrupta e Last Will

Windows:

```powershell
.\.venv\Scripts\python.exe -m rover --crash-after 15
```

macOS/Linux:

```bash
.venv/bin/python -m rover --crash-after 15
```

O processo encerra abruptamente e o broker publica `rover/status` com
`online: false` e motivo `last_will_armed_at_timestamp`.

### Perda do Node-RED

Com o Rover em `BUSCA`:

```bash
docker compose stop node-red
```

Após aproximadamente quatro segundos sem heartbeat, o simulador entra em
`SEGURO_ESPERA`. Reinicie:

```bash
docker compose start node-red
```

Ele permanece em espera até receber um novo comando válido.

### Perda do broker

```bash
docker compose stop mosquitto
docker compose start mosquitto
```

O simulador registra indisponibilidade, tenta reconectar e retorna em estado
seguro quando o broker volta.

## 10. Encerrar

No terminal do simulador, pressione `Ctrl+C`. Depois:

```bash
docker compose down
```

O volume do Node-RED é preservado. Para também apagar o volume seria necessário
um comando destrutivo separado; isso não faz parte do procedimento normal.

## Solução de problemas

### Abriu apenas `Flow 1`

Atualize o repositório e recrie o Node-RED:

```bash
docker compose up -d --force-recreate node-red
docker compose logs --tail 100 node-red-init node-red
```

Depois abra novamente o link com `#flow/rover-tab`. O inicializador substitui
somente o fluxo padrão conhecido e preserva fluxos reais já editados.

### Node-RED ou Mosquitto não está `healthy`

```bash
docker compose ps --all
docker compose logs --tail 150 mosquitto node-red-init node-red
```

Verifique também se as portas estão ocupadas. Os padrões são 1883 para MQTT e
1880 para o editor.

### O painel Debug não recebe mensagens

Confirme que:

1. o simulador Python continua aberto;
2. Mosquitto e Node-RED estão `healthy`;
3. o terminal não mostra `Broker indisponível`;
4. a aba aberta é `RoboticRover • SIMULAÇÃO`;
5. o painel Debug está habilitado.

### Um comando foi rejeitado

Consulte `reason` no `rover/cmd/ack`. Os motivos mais comuns são:

| Motivo | Significado |
| --- | --- |
| `TRANSITION_FORBIDDEN` | A sequência de estados foi pulada |
| `MANUAL_MODE_REQUIRED` | Movimento enviado fora de CAPTURA_MANUAL |
| `STATION_UNAVAILABLE` | Heartbeat da estação ausente |
| `RETAINED_FORBIDDEN` | Comando de movimento chegou como retained |
| `COMMAND_EXPIRED_OR_INVALID_TTL` | Comando expirado ou relógio incorreto |
| `SOURCE_INVALID` | Origem diferente da estação configurada |

## Checklist para o laboratório

- [ ] Repositório disponível no notebook.
- [ ] Python 3.11 ou 3.12 instalado.
- [ ] Docker iniciado e `docker version` mostra Client e Server.
- [ ] Imagens baixadas com `docker compose pull` enquanto há Internet.
- [ ] `.env` criado a partir de `.env.example`.
- [ ] Dependências instaladas na `.venv`.
- [ ] Mosquitto e Node-RED aparecem como `healthy`.
- [ ] Simulador Python em um segundo terminal.
- [ ] Aba `RoboticRover • SIMULAÇÃO` aberta.
- [ ] Telemetria e ACKs visíveis no Debug.
- [ ] Sequência de estados e rejeição inválida demonstradas.

Para este teste local, firewall, Raspberry Pi e Arduino não precisam ser
configurados. A conexão com o Rover físico exigirá liberar o broker para a rede
local e habilitar autenticação, ACL e preferencialmente TLS, conforme
[docs/seguranca.md](docs/seguranca.md).
