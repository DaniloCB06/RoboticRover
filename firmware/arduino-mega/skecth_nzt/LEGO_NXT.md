# LEGO NXT — Controle de Dois Motores com DRV8833

## Objetivo

Controlar dois motores LEGO NXT com um ATmega328P e um DRV8833, incluindo a leitura dos encoders de ambos os motores.

## Funcionamento

O DRV8833 determina o sentido e a potência aplicada a cada motor por PWM. Os canais A e B dos encoders permitem acompanhar a **posição relativa em contagens**; o código não implementa controle de velocidade ou posição em malha fechada. Serial: **115200 baud**, final de linha **Nova linha**.

## Conexões — driver e motores

| Pino DRV8833 | Função | Conexão |
|---|---|---|
| IN1 | Controle motor 1 | Arduino **D5** |
| IN2 | Controle motor 1 | Arduino **D6** |
| IN3 | Controle motor 2 | Arduino **D11** (anteriormente D9) |
| IN4 | Controle motor 2 | Arduino **D10** |
| GND | Terra | GND do Arduino e da fonte |
| VCC | Alimentação dos motores | Fonte externa **9 V** |
| EEP (nSLEEP) | Habilitação | **5 V** do Arduino, conforme o módulo |
| ULT (nFAULT) | Indicação de falha | Não conectado neste teste |
| OUT1 | Motor 1 | Primeiro fio vermelho do cabo customizado |
| OUT2 | Motor 1 | Segundo fio vermelho do cabo customizado |
| OUT3 | Motor 2 | Primeiro fio branco do cabo customizado |
| OUT4 | Motor 2 | Segundo fio branco do cabo customizado |

## Conexões — encoders

| Terminal do barramento de 6 pinos | ATmega328P | Função |
|---|---|---|
| GND | GND | Terra |
| VCC | 5 V* | Alimentação dos encoders |
| Canal 1 Encoder 1 | **D2** | Sinal A motor 1 |
| Canal 2 Encoder 1 | **D4** | Sinal B motor 1 |
| Canal 1 Encoder 2 | **D3** | Sinal A motor 2 |
| Canal 2 Encoder 2 | **D7** | Sinal B motor 2 |

\*Confirme a pinagem e a tensão do cabo customizado antes de energizar. Os pares vermelho e branco foram identificados para este cabo do laboratório; não presuma que outros cabos usem as mesmas cores.

## Comandos implementados

| Comando | Função |
|---|---|
| `M1 120` / `M1 -120` | Controla sentido e PWM do NXT 1 |
| `M2 120` / `M2 -120` | Controla sentido e PWM do NXT 2 |
| `M1 0` / `M2 0` | Para o motor selecionado |
| `STOP` | Para os dois NXT |
| `ZERO` | Zera as contagens dos encoders |
| `STATUS` | Exibe PWM solicitado e contagens dos encoders |

PWM permitido: **-255 a +255**. O sentido físico depende da orientação e polaridade das ligações.

## Teste

Com os motores sem carga, envie `ZERO`, `M1 100`, `M2 100`, `STATUS` e `STOP`. Confirme que ambos giram e que as contagens mudam. Não deixe motores travados: a corrente pode exceder o limite do driver.

**Nota:** este é o código exclusivo dos NXT, sem `Servo.h`; por isso, o PWM convencional também funciona no D10. No código integrado, o controle do motor 2 usa uma lógica específica por causa do Timer1.
