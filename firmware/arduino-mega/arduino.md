# Arduino Mega 2560 — Controle da Ponte H L298N e Comunicação com ArbotiX-M

## Objetivo

Utilizar o Arduino Mega como controlador central da eletrônica de baixo nível, acionando os motores de tração via ponte H L298N com *watchdog* local de segurança e intermediando a comunicação entre a Raspberry Pi 3 e a placa ArbotiX-M (responsável pelos servomotores DYNAMIXEL AX-12A).

## Funcionamento

O diretório `firmware/arduino-mega/` disponibiliza:

- `CodeMegaTestV1.0/CodeMegaTestV1.0.ino`: firmware integrado com controle da ponte H L298N, *watchdog* de `350 ms` e ponte `Serial1` para a ArbotiX-M.
- `controle_l298n_mega/controle_l298n_mega.ino`: sketch dedicado de validação da ponte H L298N com *watchdog* de segurança.

### Interfaces e Pinagem

- `Serial` (`115200 baud`): comunicação com a Raspberry Pi 3 / PC via USB.
  - Comandos de tração no formato `"pwmEsq,pwmDir\n"` (ex.: `"160,160\n"`, `"-120,120\n"`, `"0,0\n"`), com faixa limitada a `[-255, 255]`.
  - Comandos sem vírgula (ex.: `PING`, `GET <ID>`, `SET <ID> <POS>`) são encaminhados à `Serial1` em `CodeMegaTestV1.0.ino`.
- `Serial1` (`57600 baud`): comunicação com a ArbotiX-M via UART, mantendo os pinos **18 (`TX1`)** e **19 (`RX1`)** livres e exclusivos para os servomotores AX-12A.
- **Ponte H L298N**:
  - Motor Esquerdo: `ENA = 8` (PWM), `IN1 = 4`, `IN2 = 5`.
  - Motor Direito: `ENB = 9` (PWM), `IN3 = 6`, `IN4 = 7`.
- **Watchdog de Segurança (`TIMEOUT_WATCHDOG_MS = 350 ms`)**:
  - Se o Arduino Mega ficar mais de `350 ms` sem receber um comando válido de PWM pela USB Serial, `pararMotores()` é chamado automaticamente (fail-safe).

## Testes realizados

- Comunicação USB com o computador / Raspberry Pi 3: OK.
- Controle diferencial L298N e parada por *watchdog* (`350 ms`): OK (validado em simulação/bancada).
- Teste de loopback da Serial1: OK.
- Comunicação com a ArbotiX-M usando `PING`/`PONG`: OK.
- Recebimento de dados dos servomotores pela ArbotiX-M: OK.
