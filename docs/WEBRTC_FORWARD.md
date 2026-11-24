# Vídeo WebRTC com forwarding na estação

```text
Webcam USB → H.264 na Pi (uma codificação)
  → aiortc / WHIP pela rede → MediaMTX no Mac
                               ├→ WHEP → dashboard local
                               └→ WHIP → servidor do professor → painel
```

O protocolo entre o robô e a estação é livre no contrato; a saída da estação ao servidor deve ser WebRTC/WHIP. Esta alternativa usa WebRTC nos dois enlaces da rede. O Mac encaminha H.264 comprimido, sem filtros e sem recodificação. A visualização local usa o mesmo vídeo H.264, sem transportar um segundo MJPEG pelo Wi-Fi. O snapshot/MJPEG na Pi continua disponível a 1 FPS para diagnóstico e percepção, quando necessário.

O `aiortc` publica na Pi. O MediaMTX v1.21.4 recebe esse WHIP no Mac e usa o recurso nativo de [forwarding WebRTC](https://mediamtx.org/docs/forward/webrtc). Forwarding é retransmissão do vídeo codificado. Não corrige quadros USB incompletos e não garante a meta de latência em uma rede congestionada. O objetivo é evitar filas e tráfego duplicado e manter o operador vendo o POV local quando o servidor do professor ficar indisponível.

## Preparação

Mac Intel deste projeto, sem Docker: o binário oficial foi baixado e conferido por SHA256 em `.runtime/mediamtx-v1.21.4/mediamtx`. Para preparar outro checkout no mesmo tipo de Mac:

```bash
mkdir -p .runtime/mediamtx-v1.21.4
cd .runtime/mediamtx-v1.21.4
curl -fLO https://github.com/bluenviron/mediamtx/releases/download/v1.21.4/mediamtx_v1.21.4_darwin_amd64.tar.gz
curl -fLO https://github.com/bluenviron/mediamtx/releases/download/v1.21.4/checksums.sha256
shasum -a 256 -c checksums.sha256 --ignore-missing
tar -xzf mediamtx_v1.21.4_darwin_amd64.tar.gz mediamtx LICENSE
```

Use o pacote da arquitetura correspondente em outros sistemas. A configuração é gerada pelo módulo `competition_forward`; não precisa editar o YAML distribuído. O caminho publicado e encaminhado é exclusivamente `rover/rover04`, e a estação confirma a credencial da Pi com HTTP Basic. A saída para o professor usa o Bearer do contrato.

Na Pi, na raiz do projeto:

```bash
apps/rover/.venv/bin/python -m pip install --only-binary=:all: 'aiortc==1.16.0'
```

Os módulos `competition_video.py` e `competition_forward.py` devem ser atualizados a partir deste checkout. O `competition_forward` só precisa rodar no Mac. Mantenha `COMPETITION_HOST`, `COMPETITION_TEAM` e `COMPETITION_PASSWORD` no `.env` da raiz das duas máquinas.

## Operação

Siga a seção de competição de [comandos_comunicacao.txt](../comandos_comunicacao.txt). Os endereços `192.168.50.130` (Mac), `192.168.50.149` (Pi) e `192.168.50.3` (servidor) correspondem à rede da arena e devem ser conferidos após reconexões. Na queda do roteador, a Pi pode voltar à `LabIoT`; a sessão SSH antiga e os destinos na outra sub-rede deixam de funcionar.

No Mac, primeiro inicie `competition_forward --host IP_MAC`. Ele usa HTTP 8890 para WHIP/WHEP e UDP 8190 para a mídia WebRTC. A dashboard passa a receber a URL local WHEP por `ROVER_CAMERA_PROTOCOL=whep` e `ROVER_CAMERA_URL=http://127.0.0.1:8890/rover/rover04/whep`. Se havia configuração personalizada salva, atualize-a pela engrenagem.

Na Pi, o módulo de câmera envia H.264 apenas ao endereço local `127.0.0.1:5002`. O publicador `competition_video` consome esse MPEG-TS local e envia os pacotes H.264 por `aiortc` à entrada `http://IP_MAC:8890/rover/rover04/whip`, com `--basic --destination`. A ordem de início dos dois processos da Pi não é crítica: o publicador retenta enquanto espera o vídeo.

O acesso à página local `http://127.0.0.1:8890/rover/rover04` deve continuar funcionando sem o servidor do professor. A mídia de saída usa o UDP 8189 do servidor. MQTT mantém os processos do roteiro anterior.

## Validação

- A suíte local verifica a configuração, as permissões do caminho e o destino WHIP parametrizado. O teste de integração reproduziu publicação por `aiortc` em um MediaMTX e forwarding WHIP a um segundo MediaMTX, onde um leitor WHEP decodificou 20 quadros H.264 de 640×480.
- A instalação do binário foi reproduzida no Mac Intel/macOS 12.7.4 e o listener WHIP/WHEP iniciou corretamente.
- A Pi recebeu `aiortc` 1.16.0 e `av` 19.0.2 em 19/11/2026; `pip check` passou e os 29 testes da placa também. Os módulos anteriores foram preservados em `.runtime/pre-webrtc.AqBQiD/original` na Pi.
- Na LabIoT, com a Pi `192.168.1.113` e o Mac `192.168.1.36`, a webcam real foi publicada por WHIP e lida por WHEP no Mac: 151 quadros de 640×480, 15,06 FPS, maior intervalo observado de 138 ms entre quadros, 803 pacotes RTP recebidos e zero perdas reportadas na janela de teste. Essa medida não demonstra a latência óptica ponta a ponta.
- O envio real dessa nova cadeia ao servidor do professor ainda depende do retorno à rede da arena. O encaminhador do Mac retenta esse destino sem interromper a visualização local.

A captura e o publicador da Pi ficaram ativos em segundo plano após esse teste. Seus PIDs estão em `.runtime/webrtc-pids.json` e os logs em `.runtime/webrtc-camera.log` e `.runtime/webrtc-publisher.log`. No Mac, o log da estação fica em `.runtime/competition-forward.log` e o Node-RED foi iniciado com WHEP local. Não inicie cópias adicionais da câmera ou do publicador enquanto estiverem ativos.

Para reproduzir os testes (com o binário local instalado):

```bash
.venv/bin/python -m pytest -q tests/test_competition_forward.py
RUN_COMPETITION_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_competition_forward.py
```

Compare FPS decodificado, congelamentos, perdas RTP, CPU da Pi e latência óptica de ponta a ponta com uma cena em movimento e relógio visível. Um teste de FPS isolado não comprova latência menor que 0,5 s. Durante a troca, pare o relé TCP antigo para evitar dois publicadores tentando usar `rover/rover04` no professor.
