# Integração Arduino Mega + Ponte H L298N + ArbotiX-M

## Objetivo

Desenvolver uma arquitetura de controle centralizado para o robô, utilizando o Arduino Mega como controlador principal de tração (Ponte H L298N com *watchdog* local) e a ArbotiX-M como interface dedicada aos servomotores DYNAMIXEL AX-12A.

A Raspberry Pi 3 é responsável pelo processamento de alto nível e supervisão MQTT, comunicando-se com o Arduino Mega por USB Serial (`115200 baud`).

## Arquitetura

```text
PC / Raspberry Pi 3
       |
   USB Serial
   115200 baud ("pwmEsq,pwmDir\n" / comandos ArbotiX)
       |
  Arduino Mega 2560 ──► Ponte H L298N (ENA=8, IN1=4, IN2=5, ENB=9, IN3=6, IN4=7)
       |                + Watchdog de segurança (350 ms)
    UART TTL (Serial1: pinos 18 TX1 / 19 RX1)
   57600 baud
       |
    ArbotiX-M
       |
   DYNAMIXEL
       |
  Servomotores AX-12A
```

## Pinagem da comunicação (ArbotiX-M)

Foi utilizada a interface serial externa da ArbotiX-M, com os sinais correspondentes ao conector USB-FTDI de seis vias. Os pinos **18 (`TX1`)** e **19 (`RX1`)** do Arduino Mega permanecem exclusivos para essa UART, sem conflito com a ponte H L298N.

| Pino | Sinal | Cor do fio | Conectar ao Mega |
|---|---|---|---|
| 1 | GND | Preto | GND |
| 2 | CTS | Marrom | Não conectar |
| 3 | VCC | Vermelho | Não conectar |
| 4 | TXD | Laranja | TX1 — pino 18 |
| 5 | RXD | Amarelo | RX1 — pino 19 |
| 6 | RTS | Verde | Não conectar |

## Pinagem da Ponte H L298N (Tração Diferencial)

| Canal | Pino Mega | Função |
|---|---|---|
| Motor Esquerdo (PWM) | `8` (`ENA`) | Velocidade PWM (`0..255`) |
| Motor Esquerdo (Dir A) | `4` (`IN1`) | Sentido de giro A |
| Motor Esquerdo (Dir B) | `5` (`IN2`) | Sentido de giro B |
| Motor Direito (PWM) | `9` (`ENB`) | Velocidade PWM (`0..255`) |
| Motor Direito (Dir A) | `6` (`IN3`) | Sentido de giro A |
| Motor Direito (Dir B) | `7` (`IN4`) | Sentido de giro B |

**Observação:** o firmware aplica `constrain(pwm, -255, 255)` e possui *watchdog* de segurança de `350 ms` (`TIMEOUT_WATCHDOG_MS = 350`), desligando imediatamente ambos os motores caso a comunicação serial com a Raspberry Pi 3 seja interrompida.

## Testes realizados

1. Teste de comunicação serial do Arduino Mega por loopback: OK.
2. Teste de comunicação direta entre PC e ArbotiX-M via FTDI: OK.
3. Comunicação Mega → ArbotiX-M → Mega com `PING`/`PONG`: OK.
4. Leitura de dados dos servomotores DYNAMIXEL: OK.
5. Controle diferencial L298N (`pwmEsq,pwmDir\n`) e parada por *watchdog* (`350 ms`): OK.
