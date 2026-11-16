# Arduino Mega 2560 — Comunicação com ArbotiX-M

## Objetivo

Utilizar o Arduino Mega como controlador central da eletrônica, intermediando a comunicação entre o computador (futuramente Raspberry Pi) e a placa ArbotiX-M, responsável pelos servomotores DYNAMIXEL.

## Funcionamento

O programa implementa uma ponte serial bidirecional:

- `Serial` (115200 baud): comunicação com o PC/Raspberry Pi via USB.
- `Serial1` (57600 baud): comunicação com a ArbotiX-M via UART, utilizando os pinos 18 (TX1) e 19 (RX1).

Os dados recebidos pela USB são encaminhados à ArbotiX-M, e as respostas são devolvidas ao computador.

## Testes realizados

- Comunicação USB com o computador: OK.
- Teste de loopback da Serial1: OK.
- Comunicação com a ArbotiX-M usando `PING`/`PONG`: OK.
- Recebimento de dados dos servomotores pela ArbotiX-M: OK.

## Próximas etapas

- Implementar interpretação de comandos no Mega.
- Integrar outros sensores e atuadores.
- Implementar comunicação USB com o Raspberry Pi.
- Adicionar tratamento de erros e timeouts de comunicação.
