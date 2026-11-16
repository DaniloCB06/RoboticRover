# ArbotiX-M — Controle de Servomotores DYNAMIXEL

## Objetivo

Utilizar a ArbotiX-M como controladora dedicada aos servomotores DYNAMIXEL, recebendo comandos do Arduino Mega e retornando informações dos motores.

## Funcionamento

O firmware utiliza a biblioteca `ax12.h` para comunicação com os servomotores DYNAMIXEL por meio do protocolo 1.0.

A comunicação com o Arduino Mega é realizada pela interface serial externa, configurada em 57600 baud.

## Comandos implementados

| Comando | Função |
|---|---|
| `PING` | Testa a comunicação, retornando `PONG` |
| `GET <ID>` | Solicita os dados do servo informado |
| `SET <ID> <POS>` | Envia uma posição desejada ao servo |
| `ERR SERVO` | Indica falha ao consultar o servo |

O comando `GET` retorna:

`DATA ID POSICAO VELOCIDADE CARGA TENSAO TEMPERATURA`

Os valores são obtidos dos registradores dos servomotores, incluindo posição atual, velocidade, carga estimada, tensão e temperatura.

O comando `SET` confirma o envio da posição desejada, mas não garante que o motor tenha alcançado essa posição.

## Testes realizados

- Programação da ArbotiX-M pela Arduino IDE: OK.
- Comunicação direta com o PC via USB-FTDI: OK.
- Comunicação com o Arduino Mega: OK.
- Leitura de dados dos servos com IDs 1 e 4: OK.

Exemplos de respostas obtidas:

```text
DATA 1 282 0 0 120 26
DATA 4 562 0 0 120 27
```

Também ocorreram respostas `ERR SERVO`, indicando falhas em algumas consultas.

## Próximas etapas

- Verificar a estabilidade das leituras.
- Validar o controle de posição dos motores.
- Confirmar os limites dos servos utilizados.
- Implementar tratamento de falhas de comunicação.
