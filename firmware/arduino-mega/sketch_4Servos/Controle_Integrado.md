# Controle Integrado — 2 LEGO NXT + MG996R + SG90

## Objetivo

Controlar quatro atuadores por um ATmega328P: **dois motores LEGO NXT com encoders**, um **MG996R** e um **SG90**, usando comandos independentes pelo Monitor Serial.

## Funcionamento

Os NXT recebem PWM por meio do DRV8833 e fornecem contagens relativas dos encoders; os servos usam a biblioteca `Servo.h` para receber posições angulares. Serial: **115200 baud**, final de linha **Nova linha**.

**Particularidade do código integrado:** a `Servo.h` utiliza o Timer1 do ATmega328P e interfere no PWM convencional em D9/D10. Por isso, **IN3 foi transferido de D9 para D11**; IN4 permanece no D10, que é usado como saída digital. O código integrado usa PWM invertido no M2 para o sentido negativo.

## Conexões — DRV8833 e motores NXT

| Pino DRV8833 | Função | Conexão |
|---|---|---|
| IN1 | Controle NXT 1 | Arduino **D5** |
| IN2 | Controle NXT 1 | Arduino **D6** |
| IN3 | Controle NXT 2 | Arduino **D11** |
| IN4 | Controle NXT 2 | Arduino **D10** |
| GND | Terra | GND do Arduino e da fonte |
| VCC | Alimentação dos NXT | Fonte externa **9 V** |
| EEP (nSLEEP) | Habilitação | **5 V** do Arduino, conforme o módulo |
| ULT (nFAULT) | Saída de falha | Não conectado inicialmente |
| OUT1 | NXT 1 | Primeiro fio vermelho do cabo |
| OUT2 | NXT 1 | Segundo fio vermelho do cabo |
| OUT3 | NXT 2 | Primeiro fio branco do cabo |
| OUT4 | NXT 2 | Segundo fio branco do cabo |

## Conexões — encoders e servos

| Componente / terminal | Conexão | Função |
|---|---|---|
| Barramento encoder — GND | GND do Arduino | Terra |
| Barramento encoder — VCC | 5 V* | Alimentação dos encoders |
| Encoder 1 — canal 1 | **D2** | Sinal A NXT 1 |
| Encoder 1 — canal 2 | **D4** | Sinal B NXT 1 |
| Encoder 2 — canal 1 | **D3** | Sinal A NXT 2 |
| Encoder 2 — canal 2 | **D7** | Sinal B NXT 2 |
| MG996R — laranja | **D12** | Sinal de controle |
| MG996R — vermelho | Fonte externa **5–6 V** | Alimentação |
| MG996R — marrom | GND comum | Terra |
| SG90 — laranja | **D8** | Sinal de controle |
| SG90 — vermelho | Fonte externa **5 V** | Alimentação |
| SG90 — marrom | GND comum | Terra |

\*Confirme a tensão e a pinagem do cabo customizado. Utilize fontes reguladas e dimensionadas para a corrente dos motores, **sem ligar 9 V à linha de 5 V**. Todas as fontes precisam compartilhar GND; não alimente os servos diretamente pelos pinos do Arduino.

## Comandos implementados

| Comando | Função |
|---|---|
| `M1 <PWM>` | NXT 1, de -255 a +255 |
| `M2 <PWM>` | NXT 2, de -255 a +255 |
| `S1 <ANG>` | MG996R, ângulo solicitado de 0° a 180° |
| `S2 <ANG>` | SG90, ângulo solicitado de 0° a 180° |
| `STOP` | Para somente os dois NXT |
| `ZERO` | Zera as contagens dos encoders |
| `CENTER` | Solicita 90° aos dois servos |
| `STATUS` | Mostra os comandos e contagens atuais |

As posições dos servos são **solicitadas**, não medidas. `STOP` não desenergiza os servos: eles continuam tentando manter suas posições.

## Teste

Com os atuadores sem carga e a alimentação conferida, envie `M1 100`, `M2 100`, `S1 110`, `S2 70`, `STATUS`, `STOP` e `CENTER`. Confira o sentido de rotação, as contagens dos encoders e os movimentos dos servos.
