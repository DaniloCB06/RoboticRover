# Integração Arduino Mega + ArbotiX-M

## Objetivo

Desenvolver uma arquitetura de controle centralizado para o robô, utilizando o Arduino Mega como controlador principal e a ArbotiX-M como interface dedicada aos servomotores DYNAMIXEL.

Futuramente, o Raspberry Pi será responsável pelo processamento de alto nível, comunicando-se com o Arduino Mega por USB.

## Arquitetura

```text
PC / Raspberry Pi
       |
   USB Serial
   115200 baud
       |
  Arduino Mega
       |
    UART TTL
   57600 baud
       |
    ArbotiX-M
       |
   DYNAMIXEL
       |
  Servomotores
```

## Pinagem da comunicação

Foi utilizada a interface serial externa da ArbotiX-M, com os sinais correspondentes ao conector USB-FTDI de seis vias.

| Pino | Sinal | Cor do fio | Conectar ao Mega |
|---|---|---|---|
| 1 | GND | Preto | GND |
| 2 | CTS | Marrom | Não conectar |
| 3 | VCC | Vermelho | Não conectar |
| 4 | TXD | Laranja | TX1 — pino 18 |
| 5 | RXD | Amarelo | RX1 — pino 19 |
| 6 | RTS | Verde | Não conectar |

**Observação:** a identificação TXD/RXD corresponde à pinagem do adaptador FTDI utilizado como referência. A ligação foi validada experimentalmente com comunicação bidirecional entre as placas. As cores não substituem a conferência da pinagem física.

As placas devem compartilhar GND, mas possuem alimentação própria. Não é necessário interligar os pinos VCC.

## Testes realizados

1. Teste de comunicação serial do Arduino Mega por loopback: OK.
2. Teste de comunicação direta entre PC e ArbotiX-M via FTDI: OK.
3. Comunicação Mega → ArbotiX-M → Mega com `PING`/`PONG`: OK.
4. Leitura de dados dos servomotores DYNAMIXEL: OK.

Os testes confirmaram a comunicação bidirecional e a possibilidade de solicitar informações dos motores por meio do Arduino Mega.

## Estado atual

A integração serial entre as placas está funcional.

A leitura de dados foi validada inicialmente para servos com IDs 1 e 4. Ainda é necessário verificar a confiabilidade das consultas e validar experimentalmente o controle de movimento.

## Próximas etapas

- Testar comandos de posição e velocidade.
- Implementar aquisição periódica de dados.
- Adicionar tratamento de falhas e timeouts.
- Integrar os demais subsistemas eletrônicos ao Mega.
- Implementar a comunicação com o Raspberry Pi.
