# Arduino — Firmwares de Controle e Comunicação

## Objetivo

Reunir os códigos de teste e integração de atuadores, pontes H e comunicação serial com a **ArbotiX-M**. A pasta contém projetos independentes: cada sketch pode ser carregado separadamente para testar um subsistema.

> **Placas:** os projetos `CodeMegaTestV1.0` e `controle_l298n_mega` são destinados ao **Arduino Mega 2560**. Os exemplos de LEGO NXT, MG996R, SG90 e controle integrado foram desenvolvidos com a pinagem do **ATmega328P (Uno/Nano)**. Ao migrar entre placas, confira timers, PWM, interrupções e conexões.

## Estrutura da pasta

| Diretório | Arquivo principal | Finalidade |
|---|---|---|
| [`CodeMegaTestV1.0/`](CodeMegaTestV1.0/) | `CodeMegaTestV1.0.ino` | Mega: comunicação USB–ArbotiX-M e controle de tração por L298N com watchdog de 350 ms |
| [`controle_l298n_mega/`](controle_l298n_mega/) | `controle_l298n_mega.ino` | Mega: teste independente da ponte H L298N com watchdog de 350 ms |
| [`skecth_nzt/`](skecth_nzt/) | `skecth_nzt.ino` | Controle de dois LEGO NXT por DRV8833, com leitura de encoders |
| [`sketch_MG996R/`](sketch_MG996R/) | `sketch_MG996R.ino` | Controle individual de posição do servo MG996R |
| [`sketch_SG90/`](sketch_SG90/) | `sketch_SG90.ino` | Controle individual de posição do servo SG90 |
| [`sketch_4Servos/`](sketch_4Servos/) | `sketch_4Servos.ino` | Controle conjunto de **2 NXT + MG996R + SG90** |

## Comunicação e comandos

A comunicação com o PC é feita em **115200 baud**, com comandos terminados em nova linha. A comunicação com a ArbotiX-M, quando usada, ocorre em **57600 baud** pela `Serial1` do Mega.

| Projeto | Comandos | Observações |
|---|---|---|
| `CodeMegaTestV1.0` | `160,160`, `-120,120`, `0,0` | PWM esquerdo/direito de -255 a 255; watchdog de 350 ms |
| `CodeMegaTestV1.0` | `PING`, `GET <ID>`, `SET <ID> <POS>` | Linhas sem vírgula são encaminhadas à ArbotiX-M |
| `controle_l298n_mega` | `160,160`, `0,0` | Apenas L298N; watchdog de 350 ms |
| `skecth_nzt` | `M1 <PWM>`, `M2 <PWM>`, `STOP`, `ZERO`, `STATUS` | PWM de -255 a 255; leitura relativa dos encoders |
| `sketch_MG996R` | `S1 <ANG>`, `CENTER`, `STATUS` | Ângulo solicitado de 0° a 180° |
| `sketch_SG90` | `S2 <ANG>`, `CENTER`, `STATUS` | Ângulo solicitado de 0° a 180° |
| `sketch_4Servos` | `M1`, `M2`, `S1`, `S2`, `STOP`, `ZERO`, `CENTER`, `STATUS` | Comandos dos quatro motores reunidos |

## Pinagem principal

### Arduino Mega 2560 — L298N e ArbotiX-M

| Dispositivo | Terminal | Pino Arduino Mega |
|---|---|---|
| L298N — motor esquerdo | ENA / IN1 / IN2 | D8 / D4 / D5 |
| L298N — motor direito | ENB / IN3 / IN4 | D9 / D6 / D7 |
| ArbotiX-M | RX (recebe do Mega) | D18 (TX1) |
| ArbotiX-M | TX (envia ao Mega) | D19 (RX1) |
| ArbotiX-M | GND | GND comum |

### ATmega328P — DRV8833, encoders e servos

| Dispositivo | Terminais | Pinos Arduino |
|---|---|---|
| DRV8833 — NXT 1 | IN1 / IN2 | D5 / D6 |
| DRV8833 — NXT 2 | IN3 / IN4 | **D11 / D10** |
| Encoder NXT 1 | Canal A / B | D2 / D4 |
| Encoder NXT 2 | Canal A / B | D3 / D7 |
| MG996R | Sinal | D12 |
| SG90 | Sinal | D8 |

**Alimentação:** o DRV8833 utiliza fonte externa de aproximadamente **9 V** para os NXT; encoders usam a alimentação lógica especificada pelo cabo; MG996R utiliza fonte adequada de **5–6 V** e SG90, **5 V**. Compartilhe o GND entre as fontes e o microcontrolador, sem unir diretamente as linhas de 9 V e 5 V. Confirme o cabo customizado antes de energizar.

**Nota de integração:** no ATmega328P, `Servo.h` usa o Timer1 e interfere no PWM convencional de D9/D10. Por isso, o IN3 do DRV8833 foi transferido de **D9 para D11**, e o sketch integrado usa uma lógica específica de acionamento do NXT 2. A pinagem da tabela já reflete essa alteração.

## Documentação detalhada

- [Arduino Mega ↔ ArbotiX-M](CodeMegaTestV1.0/ArduinoToArbotix.md)
- [LEGO NXT e DRV8833](skecth_nzt/LEGO_NXT.md)
- [MG996R](sketch_MG996R/MG996R.md)
- [SG90](sketch_SG90/SG90.md)
- [Controle integrado dos quatro motores](sketch_4Servos/Controle_Integrado.md)

## Uso

1. Abra o arquivo `.ino` da pasta desejada na Arduino IDE e selecione a placa correta.
2. Confira pinagem, alimentação externa e GND comum antes de conectar os motores.
3. Carregue o sketch e abra o Monitor Serial em **115200 baud** com **Nova linha**.
4. Envie os comandos correspondentes ao projeto, começando com os atuadores sem carga.

Os códigos dos NXT usam os encoders para **contagens de posição relativa**, sem controle PID. Os códigos dos servos enviam **posições solicitadas**, não medições do ângulo real. Os diferentes sketches são alternativas de teste e integração, não firmwares executados simultaneamente no mesmo microcontrolador.
