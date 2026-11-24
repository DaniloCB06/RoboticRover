# Controle manual dos motores LEGO — preparação de bancada

Entrega de 24/11/2026. Testado no Mac com Mega virtual e compilação para Mega
2560. **Nenhum firmware foi gravado e nenhum motor foi acionado.** A confirmação
do módulo, alimentação, sentido das rodas e tempos reais fica para a bancada.

## Caminho implementado

Dashboard (WASD, setas, botões) → Node-RED → MQTT → FSM na Pi →
USB 115200/8N1 → firmware RR1 no Mega → ponte H → motores LEGO NXT.

Início, BUSCA e APROXIMAÇÃO bloqueiam tração manual. Espaço envia PARAR com
tomada de controle; a Pi confirma depois do ACK de desarme do Mega. Com heartbeat
válido, a dashboard solicita modo manual. A futura navegação pode autorizar o
operador ao concluir a aproximação; não há detector que simule essa conclusão.

Selecione **Pilotar Rover**. Segure WASD, uma seta ou botão direcional; soltar
envia PARAR. A interface espera o ACK e renova a referência após 120 ms. Cliques
por teclado/leitor de tela sem pressão contínua continuam pulsos limitados.
Perda de foco, mudança de aba, abertura de popup ou perda da autorização encerra
a renovação. **O braço continua sem atuação** e seus comandos não movem rodas.

## Configuração na Pi

O padrão é **simulation**: não importa pySerial nem abre USB.
Somente roboticrover_pi3 e roboticrover_pi3.competition_rover têm ponte USB.
O simulador separado, python -m rover, continua sem hardware.

| Variável | Padrão | Função |
|---|---|---|
| MOTOR_BACKEND | simulation | serial habilita atuação explicitamente |
| MOTOR_SERIAL_PORT | vazio | Porta /dev/ do Mega; prefira /dev/serial/by-id/... |
| MOTOR_PWM | 80 | Magnitude PWM 1–120, limite de bancada |
| MOTOR_LEASE_MS | 300 | Prazo por referência, 100–500 ms |
| MOTOR_ACK_TIMEOUT_SEC | 0.15 | Prazo por ACK, 0.02–0.5 s |
| MOTOR_RESET_DELAY_SEC | 2 | Espera após abrir USB, 0–5 s |
| MOTOR_INVERT_LEFT / MOTOR_INVERT_RIGHT | 0 | 1 inverte a roda correspondente |
| STATION_SOURCE | station-nodered | Origem aceita para comandos e heartbeat físicos |

PWM não é velocidade em m/s. Não há PID, encoder ou medição de deslocamento.
PWM 80, validade 300 ms, ACK 150 ms e pausa de inversão 50 ms são **parâmetros
provisórios**, sem validação física. O Mega limita PWM a 120 e TTL a 500 ms.

## Firmware para o próximo teste

Use o sketch firmware/arduino-mega/rover_manual/rover_manual.ino junto de
rover_protocol.h, na mesma pasta. Placa: **Mega 2560**.
Os sketches antigos pwmEsq,pwmDir e M1/M2 não implementam RR1.

Escolha um perfil conforme o módulo real, antes de gravar:

| Perfil | Ligações lógicas no Mega |
|---|---|
| ROVER_DRIVER=1 — DRV8833, padrão | IN1 D5, IN2 D6; IN3 D11, IN4 D10 |
| ROVER_DRIVER=2 — L298N | ENA D8, IN1 D4, IN2 D5; ENB D9, IN3 D6, IN4 D7 |

O primeiro par controla a roda esquerda, o segundo a direita. Não misture as
pinagens. A tração não utiliza os pinos 18/19.

Os motores usam fonte externa adequada ao conjunto; GND da fonte, driver e Mega
deve ser comum. Não alimente motores pelo 5 V da Pi/Mega. Confirme identificação
do módulo, alimentação, habilitação, jumpers ENA/ENB no L298N e os dois fios de
potência de cada cabo customizado. Os encoders ficam fora deste primeiro ensaio.
Zero PWM neste firmware é **costa/saídas sem acionamento**: não garante que a roda
já esteja mecanicamente parada.

Referências: [DRV8833 — TI](https://www.ti.com/lit/ds/symlink/drv8833.pdf),
[L298 — ST](https://www.st.com/resource/en/datasheet/l298.pdf).
A confirmação da placa física continua pendente.

Compilar com Arduino CLI, sem upload:

~~~bash
arduino-cli core install arduino:avr@1.8.6
arduino-cli compile --fqbn arduino:avr:mega \
  --build-property build.extra_flags=-DROVER_DRIVER=1 \
  firmware/arduino-mega/rover_manual
~~~

Para L298N, use -DROVER_DRIVER=2. Na IDE, altere ROVER_DRIVER no sketch.
Ambos compilaram com CLI 1.6.0, Arduino AVR Boards 1.8.6 e
avr-gcc 7.3.0-atmel3.6.1-arduino7: DRV8833 8322 bytes flash/421 RAM;
L298N 8346/423. Compilar não valida as ligações elétricas.

## Protocolo USB RR1

Linha ASCII com LF, máximo 128 bytes incluindo LF:

~~~text
RR1|SESSION_HEX8|SEQUENCE|OP|A|B|TTL_MS|CRC_HEX4\n
~~~

CRC-16/CCITT-FALSE: polinômio 0x1021, inicial 0xFFFF, sobre os bytes até TTL_MS,
sem o último separador, CRC ou LF. Números decimais, exceto sessão e CRC em
hexadecimal; sem endianness binária. Sessão aleatória não nula por processo;
sequência começa em 1 e cresce até 0xFFFFFFFF, sem wrap na mesma sessão.

| OP | Parâmetros / efeito |
|---|---|
| HELLO | Inicia sessão, zera/desarma |
| ARM | Rearma para próxima referência manual; não move |
| WHEELS | A/B = PWM esquerdo/direito com sinal; TTL 1–500 ms |
| STOP / DISARM | Zera os canais e desarma |
| ACK | A identifica OP: HELLO 1, ARM 2, WHEELS 3, STOP 4, DISARM 5; B = armado 0/1 |
| NACK | Rejeição; a Pi interrompe a sessão |

Só ACK da sessão, sequência e operação esperadas confirma despacho.
Duplicatas não renovam TTL. Movimento exige sessão válida, sequência nova e ARM.
STOP/DISARM com CRC válido zera a saída mesmo com sessão antiga, embora responda
NACK nesse caso. HELLO desarma antes de substituir sessão.

Parser incremental, sem String/readStringUntil. Quadro truncado por 100 ms,
excessivo, caractere inválido ou CRC incorreto desarma. Bytes processados por
iteração são limitados para não bloquear watchdog sob ruído.
A expiração por millis() usa subtração sem sinal, incluindo rollover.
Inversão exige zero primeiro: Python desarma, espera 50 ms provisórios e rearma
apenas para uma referência nova ainda válida.

## Paradas e significado do ACK

A Pi valida estado, autorização, origem, retained, UUID e validade MQTT. Node-RED
limita a validade de movimentos a 500 ms (ou à duração solicitada, se menor),
mantendo 5 s para paradas e modos. A Pi também rejeita direções emitidas há mais
de 500 ms, mesmo vindas de um cliente antigo com TTL longo. A validade restante
limita o TTL serial, incluindo tempo gasto no rearme.
Soltar, PARAR, trocar de modo/ferramenta, perder heartbeat/sessão da estação,
desconectar broker ou encerrar cliente pede desarme. O Mega expira a referência
mesmo sem a Pi. Esses prazos retiram PWM; parada mecânica precisa ser medida.

USB quebrado, NACK, escrita incompleta ou falta de ACK válido geram
MOTOR_SERIAL_FAULT, revogam autorização e fecham a porta, com tentativa prévia
de DISARM. Se o envio falhar, resta o watchdog do Mega.
**Não há reconexão serial automática nesta entrega:** investigue e reinicie o
cliente, seguido de nova tomada de controle. Reconexão MQTT não retoma movimento.

No modo competição, comandos da dashboard passam pela mesma FSM. Comandos
diretos vel/mode/arm/gripper do professor não contornam essa autorização no
backend serial; stop continua reduzindo atuação.

ACK execution distingue simulated_only, not_dispatched, mega_accepted e failed.
**mega_accepted confirma referência aceita pelo firmware, não movimento medido
ou peça coletada.** A dashboard mostra “Mega aceitou” e ausência de medição física.
hardware_actuation indica habilitação do backend físico, não leitura de sensor.
Não há completed nem telemetria inventada de encoder, bateria ou servo.

## Comandos para o próximo dia de hardware

Primeiro, na Pi com o repositório atualizado:

~~~bash
cd /home/puc/RoboticRover
apps/rover/.venv/bin/python -m pip install -e ".[motor-control]"
ls -l /dev/serial/by-id/
~~~

Confirme a porta real. O identificador observado anteriormente foi
usb-Arduino__www.arduino.cc__0042_1344A474030351916898-if00; outro Mega pode diferir.

Depois de preparar firmware, alimentação e pinagem, no Mac:

~~~bash
.venv/bin/python inicia_comunicacao.py --pi puc@IP_DA_PI \
  --motor-backend serial \
  --serial-port /dev/serial/by-id/IDENTIFICADOR_REAL \
  --motor-pwm 80
~~~

Substitua IP_DA_PI e IDENTIFICADOR_REAL antes de executar. Escolha 1 para local
ou 2 para arena alcançável. O iniciador não troca Wi-Fi. Para corrigir sentidos,
use --invert-left e/ou --invert-right. Sem opt-in, força simulation inclusive
quando o .env remoto contém configuração física antiga.

Na dashboard: Espaço → aguardar confirmação → Pilotar Rover → segurar direção.
Com rodas suspensas, testar sentidos, soltar, parar, inverter e voltar a BUSCA.
Depois testar perda da Pi e USB. Medir retirada do PWM e parada real antes de
usar no chão. Watchdog não substitui interrupção física da alimentação.

## Testar hoje sem hardware

~~~bash
.venv/bin/python -m pytest -q tests/test_manual_motors.py
RUN_MOTOR_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_manual_motors.py
~~~

O primeiro compila parser/FSM C++ e sketch com pinos instrumentados para os dois
drivers, injetando envelopes no cliente com serial virtual. O segundo inicia
Mosquitto/Node-RED temporários em portas locais livres e testa POST da API da
dashboard → MQTT real → Pi → núcleo C++ do Mega → ACK correlacionado.
Requer Mosquitto e Node-RED locais; não abre /dev/ do Mac nem da Pi.

O teste node tests/dashboard_browser.cjs verifica bloqueios, segurar/soltar por
teclado/ponteiro, destinos e popups com transporte simulado, em Chrome temporário
com depuração em 19222.
