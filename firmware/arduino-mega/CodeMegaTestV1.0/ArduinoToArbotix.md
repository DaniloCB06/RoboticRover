# Arduino Mega 2560 — Comunicação com ArbotiX-M

## Objetivo

Utilizar o Arduino Mega 2560 como intermediário na comunicação entre a Raspberry Pi 3 (ou computador) e a placa ArbotiX-M, responsável pelo controle dos servomotores DYNAMIXEL AX-12A.

## Funcionamento

O Arduino Mega recebe comandos pela interface USB (`Serial`) e os encaminha à ArbotiX-M pela interface UART (`Serial1`).

As respostas enviadas pela ArbotiX-M são recebidas pelo Arduino e retransmitidas ao computador ou à Raspberry Pi 3.

A comunicação utiliza:

- `Serial` (115200 baud): comunicação USB com o computador ou Raspberry Pi 3.
- `Serial1` (57600 baud): comunicação UART com a ArbotiX-M.

## Conexões

| Arduino Mega 2560 | ArbotiX-M | Função |
|---|---|---|
| D18 (TX1) | RX | Envio de comandos |
| D19 (RX1) | TX | Recebimento de respostas |
| GND | GND | Terra comum |

A ArbotiX-M deve receber alimentação adequada aos servomotores utilizados. As placas precisam compartilhar o GND para estabelecer uma referência comum de comunicação.

## Comandos implementados

| Comando | Função |
|---|---|
| `PING` | Testa a comunicação, retornando `PONG` |
| `GET <ID>` | Solicita os dados do servomotor informado |
| `SET <ID> <POS>` | Envia uma posição desejada ao servomotor |

O comando `GET` retorna os dados no formato:

`DATA ID POSICAO VELOCIDADE CARGA TENSAO TEMPERATURA`

Os valores são obtidos pela ArbotiX-M e retransmitidos pelo Arduino Mega.

## Testes realizados

- Comunicação USB entre Arduino Mega e computador: OK.
- Teste de loopback da `Serial1`: OK.
- Comunicação Arduino Mega–ArbotiX-M (`PING`/`PONG`): OK.
- Recebimento de dados dos servomotores pela ArbotiX-M: OK.