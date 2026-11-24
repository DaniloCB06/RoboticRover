# Teste e homologação da equipe rover04

O [contrato do professor](../Contrato_de_interface_das_equipes.md) define o tráfego externo. Este modo é separado do teste antigo de MQTT via túnel SSH. A Pi e a estação conectam ao broker da arena com o mesmo **usuário** `rover04` e IDs de cliente distintos. O Node-RED continua usando o Mosquitto local, sem credencial da arena no fluxo nem no navegador.

O roteiro de vídeo abaixo documenta o modo TCP anterior. A alternativa com **WebRTC em ambos os enlaces e forwarding nativo na estação** está em [WEBRTC_FORWARD.md](WEBRTC_FORWARD.md), com os comandos atualizados em `comandos_comunicacao.txt`. A nova cadeia passou no teste local; a validação com a Pi e a arena ficou pendente após a queda do roteador.

| Tópico no servidor | Origem / comportamento |
| --- | --- |
| `rover/rover04/status` | `online` / `offline` como texto, QoS 1, retain, Last Will `offline` |
| `rover/rover04/state` e `/mode` | Fase e modo do agente, QoS 1/retain ao mudar e ao conectar. Navegação com piloto manual é declarada `NAVEGACAO` + `MANUAL`. |
| `rover/rover04/battery` | Medição recente `v` (V), `pct` (%), `i` (A) com `ts` em ms; cerca de 1,25 Hz, QoS 0 sem retain. |
| `rover/rover04/detection` | Uma confirmação YOLO por identificação, QoS 1 sem retain. A tag é opcional. |
| `rover/rover04/mission` | Opcional: lista de tags e estado, QoS 1/retain; não presume que uma peça foi coletada. |
| `rover/rover04/cmd/{vel,stop,mode,arm,gripper}` | Compatibilidade com estação de referência; `mode` retorna o modo efetivo e `vel` tem prazo de 450 ms no agente. Para tomar o controle fora da fase autorizada, envie `stop` e depois `mode: MANUAL`. |
| `rover/rover04/cmd/rr/#` e `rover/rover04/rr/#` | Tópicos próprios, dentro do namespace autorizado, para comandos, ACKs, dados da dashboard e confirmações do detector quando roda na estação. |
| `arena/state` | Somente assinado. A ponte disponibiliza uma cópia local em `competition/arena/state`. |

## Preparar antes de ir à arena

No Mac, na raiz do projeto, deixe FFmpeg, Node-RED e Mosquitto disponíveis e instale o relé no ambiente Python do projeto:

```bash
.venv/bin/python -m pip install -e '.[competition-video]'
```

Na Pi, copie/atualize o repositório e use o ambiente já criado em `apps/rover/.venv`. Instale o projeto a partir da raiz e confirme que o FFmpeg da placa tem `libx264`:

```bash
cd /home/puc/RoboticRover
apps/rover/.venv/bin/python -m pip install -e .
ffmpeg -hide_banner -encoders | grep libx264
```

Em **cada máquina**, acrescente ao `.env` da raiz sem sobrescrever as opções de laboratório:

```dotenv
COMPETITION_HOST=192.168.50.3
COMPETITION_TEAM=rover04
COMPETITION_PASSWORD='SENHA_ENTREGUE_A_EQUIPE'
COMPETITION_MQTT_PORT=1883
COMPETITION_TELEMETRY_DIR=.runtime/competition
```

Substitua os valores de exemplo pelos dados da arena. Sincronize os relógios da estação e Pi antes de testar os comandos com `ts`/TTL.

No Mac e na Pi, a credencial do `rover04` e `COMPETITION_HOST=192.168.50.3` já estão no `.env` da raiz. O `.env` de laboratório em `apps/rover/` foi preservado. Inicie os processos de competição na raiz do repositório para carregar o arquivo certo.

## Subir em terminais separados

O servidor oficial é a Raspberry Pi 4 em `192.168.50.3`, na rede `ARENA-5G`. O Mac e a Pi do Rover estavam na `LabIoT` e não alcançaram o servidor nessa rede. A placa do Rover é uma Pi 3 Model B com Wi-Fi de 2,4 GHz e não detectou a `ARENA-5G`. Conecte o Mac à `ARENA-5G` e a Pi a uma porta Ethernet da rede da arena, ou a uma rede de 2,4 GHz da organização que tenha rota para o servidor e o Mac.

Depois da troca, anote o IP novo da Pi (`hostname -I`) e o IP Wi-Fi do Mac (`ipconfig getifaddr en0`, se `en0` for o Wi-Fi). Nos exemplos, `IP_PI` e `IP_MAC` são esses endereços; `IP_SERVIDOR` é `192.168.50.3`.

1. **Mac, raiz do projeto — Mosquitto para a dashboard:**
   ```bash
   .venv/bin/mosquitto -c infra/mqtt/mosquitto.local.conf
   ```
2. **Mac, raiz do projeto — Node-RED e câmera da arena:**
   ```bash
   NODE_RED_HOST=127.0.0.1 COMPETITION_ARENA_URL=http://IP_SERVIDOR:8080/arena.html node-red \
     --userDir .runtime/pi3-bootstrap/node-red \
     --settings apps/station/node-red/settings.js "$PWD/apps/station/node-red/flows.json"
   ```
3. **Mac, raiz do projeto — ponte MQTT:**
   ```bash
   .venv/bin/python -m roboticrover_pi3.competition_station
   ```
4. **Mac, raiz do projeto — relé WHIP:**
   ```bash
   .venv/bin/python -m roboticrover_pi3.competition_video --listen-host IP_MAC --transport tcp
   ```
   Recebe MPEG-TS na porta TCP 5000 do Mac e retransmite H.264 com `aiortc` para `http://IP_SERVIDOR:8889/rover/rover04/whip`, sem recodificar. A mídia WebRTC do servidor continua usando UDP 8189. O relé usa Bearer por padrão; `--basic` seleciona HTTP Basic se necessário. Para interoperar com o emissor de referência em UDP, use `--transport udp` no Mac e `--relay-transport udp` na Pi.
5. **Mac — abrir SSH para a Pi com o túnel do POV local:**
   ```bash
   ssh -o ExitOnForwardFailure=yes -L 127.0.0.1:8081:127.0.0.1:8080 puc@IP_PI
   ```
   **Na Pi**, após conectar:
   ```bash
   cd /home/puc/RoboticRover
   apps/rover/.venv/bin/python -m roboticrover_pi3.competition_rover
   ```
6. **Pi, em outra sessão SSH — iniciar a webcam só uma vez:**
   ```bash
   cd /home/puc/RoboticRover
   apps/rover/.venv/bin/python -m roboticrover_pi3.camera --relay-host IP_MAC \
     --relay-transport tcp --fps 15 --preview-fps 8
   ```
   A mesma webcam gera o vídeo da arena a 15 FPS e o MJPEG da dashboard a 8 FPS para reduzir tráfego. H.264: 640×480, Constrained Baseline, sem B-frames, 1 fatia, GOP de 1 s com SPS/PPS, alvo de 650 kbps e teto de encoder de 800 kbps. A fila de envio é limitada e pode descartar quadros se a rede atrasar; o relé espera um quadro-chave com SPS/PPS depois de um pacote inválido ou descarte. Inicie o relé antes da câmera.

No Mac, abra `http://127.0.0.1:1880/dashboard`. O **POV da Pi** usa o túnel SSH e continua disponível se o servidor da arena cair, desde que a conexão Mac–Pi se mantenha. A aba **Visão Arena** abre a página oficial. Se houver uma URL de câmera antiga salva no navegador, ajuste pela engrenagem ou limpe a preferência. Para conferir o POV recebido pelo juiz, abra `http://IP_SERVIDOR:8080/arena.html?path=rover/rover04`.

## Conectar as fontes de telemetria

Na Pi, escreva dados reais em `.runtime/competition/` com troca atômica (arquivo temporário no mesmo diretório, seguido de rename). Estes arquivos são interfaces com os módulos produtores, e não vêm preenchidos pelo projeto:

- `battery.json`: `{"ts":1790000000000,"v":7.82,"pct":71.0,"i":1.3}`. Exemplo de formato: o produtor deve escrever o **epoch atual em ms** e atualizar a medição ao menos uma vez por segundo. Amostras de 2 s ou mais são ignoradas. Não há fonte confirmada de corrente e porcentagem na Pi; tensão de servo sozinha não completa o tópico.
- `mission.json`: `{"tags":[{"id":4,"status":"ENCONTRADA"}]}`. Use `COLETADA` só após confirmação da coleta. O agente acrescenta `ts` e publica mudanças.
- `detection.json`: produzido pelo comando abaixo. Use uma identificação estável por alvo e rodada; o agente ignora repetições da mesma identificação e eventos com mais de 10 s. Inicie o agente antes do detector. Faça a identificação durante `APROXIMACAO` ou na posição de captura. YOLO não libera o controle manual por si só.

Para executar o detector na Pi, primeiro copie `vision/weights_model.pt` e confirme que PyTorch/Ultralytics são compatíveis com a versão do Python/OS da placa:

```bash
apps/rover/.venv/bin/python -m pip install -e '.[competition-vision]'
apps/rover/.venv/bin/python -m vision.competition_detect --identification rodada12-tag4 --tag 4
```

Para poupar a CPU da Pi, use o Mac com o túnel do vídeo ativo. O detector consome o snapshot por SSH e envia a confirmação à Pi pelo broker; o agente da Pi valida, deduplica e publica no tópico oficial:

```bash
.venv/bin/python -m pip install -e '.[competition-vision]'
.venv/bin/python -m vision.competition_detect --via-arena --identification rodada12-tag4 --tag 4
```

O comando confirma o alvo em três quadros distintos. O modelo atual contém `paraboloide_hiperbolico`, `helice` e `dado_hexagonal`; confirme com o professor quais desses rótulos correspondem a `hiperboloide` ou `exotico` e forneça o mapeamento JSON com `--labels`. Classes sem associação confirmada não são enviadas.

## Conferir sem a Pi

```bash
.venv/bin/python -m pytest -q
RUN_COMPETITION_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_competition_integration.py
```

Os testes de integração sobem brokers em portas temporárias no loopback e usam vídeo sintético com um servidor WHIP de teste. Não usam o IP ou as credenciais do professor. `COMPETITION_MOCK_BATTERY=1` é exclusivo de broker local de laboratório; não o use na rede da arena.

## Testado na Pi em 19/11/2026

- Raspberry Pi 3 com Debian 13 ARM64 e Python 3.13, instalação no ambiente `apps/rover/.venv`; `pip check` e os 29 testes da placa passaram.
- Webcam USB real com preview JPEG a 14,92 FPS e H.264 Constrained Baseline a 640×480/15 FPS, sem B-frames. Em sete segundos de captura local, o MPEG-TS ficou em torno de 1,05 Mbps. O vídeo também percorreu o Wi-Fi até o relé no Mac e foi decodificado por um receptor WHIP de laboratório.
- Agente da Pi e ponte do Mac trocaram status online/offline, bateria de teste, `arena/state`, comando `BUSCA` e ACK via brokers locais. `stop`, `mode` e `vel` também passaram com timestamps alinhados, incluindo a parada simulada por falta de renovação da velocidade.
- A Pi estava sincronizada por NTP e cerca de 2 s adiantada em relação ao Mac. O ensaio corrigiu somente os timestamps gerados pelo teste. Antes de usar a estação de referência, sincronize também o Mac; não amplie a janela de validade de `cmd/vel`.
- Nenhum dado foi enviado ao servidor do professor. Falta confirmar credencial/IP oficiais, acesso ao painel, latência de ponta a ponta, telemetria de bateria medida e atuação física.

## Vídeo na rede da arena

Em teste com UDP da Pi ao Mac, houve 179 quebras de continuidade no PID do vídeo e 646 linhas de avisos/erros ao decodificar a captura. Os logs da Pi também apontaram quadros USB incompletos. A troca para TCP nesse trecho evita que UDP entregue ao relé um quadro H.264 incompleto. No teste com a webcam real e o servidor oficial, o leitor WHEP decodificou 196 quadros de 640×480 a cerca de 14 FPS, com 1.052 pacotes RTP e zero perdas reportadas. Ainda houve um intervalo de até 1,57 s entre quadros; esse intervalo não mede latência óptica. Se os avisos V4L2 persistirem, teste outra porta USB ou webcam.

O receptor TCP agora permanece escutando mesmo quando o WHIP está reconectando ou a Pi ainda não enviou vídeo. A entrada TCP é encaminhada por UDP somente no loopback do Mac para o demuxer; a porta da rede fica independente das sessões WHIP. Uma queda do relé não deve interromper o preview MJPEG. Com `--relay-host`, o preview passa a 8 FPS por padrão, com JPEG mais leve, mesmo quando `--preview-fps` é omitido. O timeout TCP da Pi passou de 750 ms para 3 s, mantendo a fila limitada e a recuperação por quadro-chave.

Depois dessa correção, o preview real respondeu a 8 FPS, com idade de quadro de 6,5 ms no produtor, e o leitor WHEP do servidor oficial recebeu 174 quadros a 15,1 FPS em uma janela de aproximadamente 12 s: 923 pacotes RTP e zero perdas reportadas. Esse teste confirma entrega e decodificação; não mede latência óptica ou estabilidade durante uma rodada inteira.

Se os serviços tiverem sido iniciados em segundo plano nesta sessão, os logs estão em `.runtime/competition-video.log` no Mac e `.runtime/camera-live.log` na Pi. Não abra uma segunda cópia do relé ou da câmera enquanto estiverem ativos. Para conferir o preview no Mac, use `curl --max-time 3 http://127.0.0.1:8081/health` e atualize a dashboard com Command+Shift+R. `FIFO queue full` indica que a saída está descartando dados para não bloquear a captura; `Connection refused` indica falta de receptor TCP naquele endereço/porta.

Antes da homologação, confira com o juiz: conexão e Last Will ao derrubar o cliente, estados/modo/bateria e detecções no painel, câmera da arena, POV local com servidor indisponível, vídeo retransmitido com latência abaixo de 0,5 s e parada física em até 0,5 s sem `cmd/vel`. A regra de navegação autônoma vale para aproximação e ida à descarga. O watchdog atual zera velocidade **simulada**; ainda falta integrar e testar tração, juntas/garra e a navegação real. Não use este teste como evidência de parada dos motores físicos.
