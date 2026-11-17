# Webcam da Pi 3 na dashboard

## Implementação e ambiente testado em 17/11/2026

- Webcam USB `1908:2310` (GEMBIRD / Generic USB2.0 PC CAMERA), driver UVC.
- Captura: `/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0` → `/dev/video0`.
- `/dev/video1` é a interface de metadados, não o dispositivo de captura escolhido.
- Formatos anunciados: YUYV em 640×480, 352×288, 320×240, 176×144 e 160×120,
  a 15 ou 30 FPS. A webcam não anunciou MJPEG nativo.
- Pi 3 B, Debian 13 ARM64, Python 3.13.5 e FFmpeg 7.1.5 já instalado na placa.

O módulo `apps/rover/roboticrover_pi3/camera.py` usa somente a biblioteca padrão
Python e o executável FFmpeg. Captura YUYV, codifica JPEG e fornece HTTP MJPEG.
Ele roda como **processo separado do cliente MQTT**, sem importar navegação,
abrir serial/GPIO ou acionar motores. Não foram adicionados pacotes pip.

## Ligação com a estação

```text
Webcam USB → FFmpeg → serviço Python na Pi, 127.0.0.1:8080
                                |
                        túnel SSH local (-L)
                                |
Mac, 127.0.0.1:8081 → dashboard / Visão Rover
```

Na Pi, o serviço escuta somente no loopback. No Mac, o túnel também escuta
somente no loopback. O vídeo passa pela conexão SSH autenticada e criptografada;
nenhuma porta de câmera foi exposta diretamente ao Wi-Fi. MQTT continua no seu
túnel reverso, independente da captura de vídeo.

## Iniciar

No SSH da Pi, em um terminal próprio para a câmera:

```bash
cd /home/puc/RoboticRover/apps/rover
.venv/bin/python -m roboticrover_pi3.camera
```

Para outra webcam, informe o dispositivo estável e parâmetros anunciados por ela:

```bash
v4l2-ctl --list-devices
v4l2-ctl --device /dev/video0 --list-formats-ext
.venv/bin/python -m roboticrover_pi3.camera \
  --device /dev/video0 --width 640 --height 480 --fps 15 --quality 5
```

O serviço limita o formato a parâmetros explícitos, usa apenas um processo de
captura e mantém somente o JPEG mais recente. Clientes lentos saltam quadros;
não há uma fila ilimitada de vídeo. Até quatro clientes MJPEG simultâneos são
admitidos, sujeitos à banda e ao desempenho da rede.

No Mac, com a sessão compartilhada desta instalação já aberta, registre o túnel
uma única vez:

```bash
ssh -S /private/tmp/roboticrover-pi3.sock -o ExitOnForwardFailure=yes \
  -O forward -L 127.0.0.1:8081:127.0.0.1:8080 puc@192.168.1.116
```

Alternativamente, em uma sessão SSH nova, o mesmo comando pode abrir os túneis
de vídeo e MQTT e apresentar o terminal remoto:

```bash
ssh -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8081:127.0.0.1:8080 \
  -R 127.0.0.1:18883:127.0.0.1:1883 \
  puc@192.168.1.116
```

Não registre novamente uma porta já ocupada pelo túnel ativo. Mantenha o SSH
aberto. O cliente `python -m roboticrover_pi3` continua rodando em outro terminal.
Nenhum serviço de boot/systemd foi instalado nesta etapa.

## Dashboard

Atualize `http://127.0.0.1:1880/dashboard` com Command+Shift+R. A Visão Rover
recebe automaticamente a configuração de `/api/rover/cameras`:

- stream: `http://127.0.0.1:8081/stream.mjpg`;
- saúde: `http://127.0.0.1:8081/health`.

Se o navegador já tiver uma URL personalizada salva, abra a engrenagem, escolha
**MJPEG HTTP** e informe a URL do stream acima. A configuração da Visão Satélite
permanece independente; nenhuma segunda câmera foi adicionada.

Os defaults podem ser alterados por `ROVER_CAMERA_URL` e
`ROVER_CAMERA_HEALTH_URL` no ambiente do Node-RED. A configuração própria salva
no navegador tem precedência. **Desconectar** salva a preferência desativada e
impede a reconexão automática; conectar novamente pelo popup reativa o vídeo.

O indicador AO VIVO informa resolução e FPS observados pelo produtor. A
dashboard consulta a saúde a cada 1,5 s, com timeout de 2 s, e oculta a imagem
se o produtor ficar indisponível ou seu último JPEG tiver mais de 2 s. Depois
retenta automaticamente. O serviço reinicia o FFmpeg após falha ou ausência de
quadros por 5 s; o fechamento de um encoder travado pode exigir até 3 s antes
de uma nova tentativa, acrescida de 2 s de espera entre tentativas.

Streams externos genéricos continuam disponíveis pelo popup, mas a checagem de
frescor exige um endpoint de saúde compatível. O player externo/iframe não
comprova frescor de quadros por si só.

## Endpoints e identificação dos quadros

```bash
# No Mac, com túnel ativo:
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:8081/snapshot.jpg -o /private/tmp/rover-camera.jpg
```

`/health` responde 200 com quadros frescos ou 503 sem captura válida. Inclui
`frame_id`, `sequence`, `frame_received_at`, `frame_age_ms`, FPS e reinícios.
`/snapshot.jpg` e cada parte do MJPEG incluem `X-Frame-Id` e
`X-Frame-Received-At`. O ID combina sessão e sequência, sem reutilizar IDs ao
reiniciar o serviço. Um futuro consumidor de visão pode usar esses endpoints
em vez de disputar a webcam com um segundo processo de captura.

**Limite do timestamp:** `timestamp_source: encoder_output_received` indica o
recebimento do JPEG na aplicação, após o encoder. Não é o instante da exposição
do sensor e não comprova latência óptica ponta a ponta. A integração de visão
e a decisão autônoma ainda precisam tratar idade/incerteza da observação.

## Validações realizadas

- Quadro real capturado e vídeo 640×480 renderizado no Chrome dentro da dashboard.
- Captura em torno de 15 FPS. Em uma janela de 5,02 s no Mac, chegaram 70 quadros:
  aproximadamente **13,94 FPS / 1,65 Mbps**, com produtor em 14,93 FPS.
- FFmpeg em torno de 59–61% de um núcleo (aproximadamente 15% dos quatro núcleos),
  cerca de 73 MB RSS; temperatura observada de 48,3 °C. São medidas desta sessão,
  não garantias para outros cenários, número de clientes ou redes.
- Pausa controlada do encoder: quadro antigo ocultado, watchdog reiniciou a
  captura e a dashboard recuperou AO VIVO automaticamente. Isso não substitui
  um teste físico de retirar/reconectar o USB.
- O teste inicial de rede encontrou timeouts; foram ajustados fechamento de
  conexões HTTP/timeout de sockets e renovado o encaminhamento local. Na
  verificação final, saúde e stream voltaram a responder e a banda foi medida.
- **8 testes novos de câmera**, cobrindo parser JPEG, limites de buffer,
  metadados HTTP, falta de captura, expiração e recuperação; **29 testes do
  pacote da Pi aprovados na placa** e **149 testes locais aprovados** (9 de
  integração continuam opt-in nessa execução local).
- **14 cenários de comandos MQTT/API contra a Pi aprovados com vídeo ativo**;
  o teste termina em espera e não aciona hardware.

Ainda pendem: foco/calibração óptica, latência medida desde aquisição/exposição,
teste físico de desconexão USB e associação frame↔detecção. Perder vídeo sinaliza
a dashboard, mas ainda não implementa intertravamento físico da navegação.
