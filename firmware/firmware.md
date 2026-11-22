# Firmware — Controle de Motores e Comunicação

## Objetivo

Reunir os firmwares de controle de motores, leitura de encoders e comunicação entre o **Arduino Mega 2560**, a **ArbotiX-M** e outros atuadores utilizados no projeto. Os códigos incluem testes independentes e versões de integração; **não devem ser carregados simultaneamente na mesma placa**.

## Estrutura

| Pasta / arquivo | Descrição |
|---|---|
| [`arbotix-board/`](arbotix-board/) | Firmware da ArbotiX-M para consultar e comandar servomotores DYNAMIXEL AX-12A. |
| [`arduino-mega/CodeMegaTestV1.0/`](arduino-mega/CodeMegaTestV1.0/) | Arduino Mega: comunicação USB ↔ ArbotiX-M e controle da ponte H L298N com watchdog de 350 ms. |
| [`arduino-mega/controle_l298n_mega/`](arduino-mega/controle_l298n_mega/) | Teste independente de tração diferencial com L298N e watchdog. |
| [`arduino-mega/skecth_nzt/`](arduino-mega/skecth_nzt/) | Controle de dois motores LEGO NXT pelo DRV8833, com leitura dos encoders. |
| [`arduino-mega/sketch_MG996R/`](arduino-mega/sketch_MG996R/) | Controle individual do servo MG996R. |
| [`arduino-mega/sketch_SG90/`](arduino-mega/sketch_SG90/) | Controle individual do servo SG90. |
| [`arduino-mega/sketch_4Servos/`](arduino-mega/sketch_4Servos/) | Controle conjunto de dois LEGO NXT, um MG996R e um SG90. |

Documentação detalhada: [`arbotix-board/arbotix.md`](arbotix-board/arbotix.md) e [`arduino-mega/README_arduino-mega.md`](arduino-mega/README_arduino-mega.md). Cada sketch de motor também possui um arquivo `.md` em sua pasta.

## Arquitetura de comunicação

```text
PC / Raspberry Pi 3
       │ USB Serial (115200 baud)
       ▼
 Arduino Mega 2560 ───► L298N ───► Motores de tração
       │
       │ Serial1 (57600 baud)
       ▼
    ArbotiX-M ────────► DYNAMIXEL AX-12A
```

Essa arquitetura corresponde ao firmware `CodeMegaTestV1.0`. Os sketches de LEGO NXT e servos convencionais são **experimentos separados**, não parte dessa integração com a ArbotiX-M.

## Comandos principais

| Firmware | Exemplos de comandos | Resultado |
|---|---|---|
| Mega + L298N | `160,160`, `-120,120`, `0,0` | PWM esquerdo e direito, de -255 a 255. |
| Mega ↔ ArbotiX-M | `PING`, `GET 1`, `SET 1 512` | Testa comunicação, lê dados ou solicita posição. |
| LEGO NXT | `M1 120`, `M2 -120`, `STOP`, `ZERO`, `STATUS` | Controla motores e consulta/zera encoders. |
| MG996R | `S1 90`, `CENTER`, `STATUS` | Solicita posição angular. |
| SG90 | `S2 90`, `CENTER`, `STATUS` | Solicita posição angular. |
| Quatro motores | `M1 120`, `M2 -120`, `S1 90`, `S2 45`, `STOP`, `ZERO`, `CENTER`, `STATUS` | Controla os quatro atuadores por comandos independentes. |

Os comandos Serial dos sketches de motores usam **115200 baud** e final de linha `Nova linha`. Nos servos, os ângulos são **solicitados**, não medidos. `STOP` no código integrado interrompe os NXT, mas não desabilita os servos.

## Placas e conexões importantes

| Interface | Conexões |
|---|---|
| Mega ↔ ArbotiX-M | Mega `TX1/D18` → RX da ArbotiX-M; `RX1/D19` ← TX; GND comum. |
| Mega → L298N | `ENA=D8`, `IN1=D4`, `IN2=D5`, `ENB=D9`, `IN3=D6`, `IN4=D7`. |
| ATmega328P → DRV8833 (NXT) | `IN1=D5`, `IN2=D6`, `IN3=D11`, `IN4=D10`. |
| Encoders NXT | Encoder 1: `A=D2`, `B=D4`; encoder 2: `A=D3`, `B=D7`. |
| MG996R / SG90 | Sinais em `D12` / `D8`, respectivamente. |

**Compatibilidade:** os sketches dos NXT e servos foram desenvolvidos com a pinagem de **ATmega328P (Uno/Nano)**, embora estejam armazenados em `arduino-mega/`. Não presuma compatibilidade direta com o Mega 2560 sem conferir PWM, temporizadores e interrupções. No ATmega328P, o uso de `Servo.h` altera a disponibilidade do PWM nos pinos D9/D10; por isso o NXT 2 utiliza D11 e D10 no código integrado.

## Alimentação e cuidados

- Utilize fontes adequadas para as cargas: alimentação dos NXT via DRV8833, dos servos convencionais por fonte externa regulada e da ArbotiX-M conforme seus servos.
- Compartilhe o **GND** entre os dispositivos que trocam sinais, sem unir diretamente linhas de alimentação com tensões diferentes.
- Confira a pinagem do cabo customizado dos NXT e teste motores inicialmente sem carga mecânica.
- A parada automática após **350 ms sem comando válido de tração** está implementada nos firmwares de L298N; **não é uma proteção geral presente em todos os sketches**.

## Uso

1. Abra o `.ino` desejado na Arduino IDE e selecione a placa e a porta corretas.
2. Confira as conexões descritas no `.md` do respectivo sketch.
3. Carregue o programa e teste os comandos no Monitor Serial, observando o comportamento do atuador.

Para detalhes de pinagem, limites e procedimentos de teste, consulte os arquivos de documentação específicos de cada módulo.
