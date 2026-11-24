# Contrato MQTT v1 — preparação Pi 3

Tópicos reaproveitados do `flows.json` apresentado pelo grupo. Esta implementação
é **somente para teste de comunicação**, sem controle de hardware.

| Tópico | Sentido | type | QoS | Retained |
|---|---|---|---|---|
| `station/heartbeat` | Node-RED → Pi | `heartbeat` | 1 | não |
| `rover/cmd/modo` | Node-RED → Pi | `mode_command` | 1 | não |
| `rover/cmd/manual` | Node-RED → Pi | `manual_command` | 1 | não |
| `rover/status` | Pi → Node-RED | `status` | 1 | sim (LWT) |
| `rover/estado` | Pi → Node-RED | `state` | 1 | não |
| `rover/telemetria` | Pi → Node-RED | `telemetry` | 1 | não |
| `rover/alarme` | Pi → Node-RED | `alarm` | 1 | não |
| `rover/log` | Pi → Node-RED | `log` | 1 | não |
| `rover/cmd/ack` | Pi → Node-RED | `ack` | 1 | não |

Envelope de todas as mensagens:

```json
{
  "version":"1.0",
  "timestamp":"2026-11-10T17:30:00.000Z",
  "source":"raspberry-pi3",
  "simulated":false,
  "type":"status",
  "data":{"online":true,"hostname":"roboticrover"}
}
```

- `simulated:false` no status significa **disponibilidade efetiva do cliente Linux**; não significa que o Arduino ou os sensores estão conectados.
- `simulated:true` para ACK/estado indica validação **somente em software**, sem atuação física.
- `command_id` deve ser UUID, `expires_at` é ISO8601 com timezone e TTL ≤ 10 s; a estação emite 5 s para modos/PARAR e até 500 ms para direções, evitando reproduzir movimento atrasado.
- Mensagens maiores que 4096 bytes, com timestamps antigos/futuros, comandos duplicados ou retained são ignorados/rejeitados.
- `station/heartbeat`: `data.online=true` e `data.session_id` obrigatório. Espera em até 4 segundos de ausência de heartbeat.
- O `PARAR` em `rover/cmd/manual` ou `SEGURO_ESPERA` em `rover/cmd/modo` leva à espera segura de qualquer estado; no backend serial opt-in, também exige ACK do desarme do Mega.
- `state.data.manual_enabled` informa a autorização manual. Ela é concedida ao concluir aproximação (`AGUARDANDO_PEGA`) ou por `PARAR` com `take_control:true`, desde que o heartbeat seja válido. BUSCA, falhas e reconexão revogam a autorização; parada comum não cria autorização inicial.
- Comandos manuais aceitam `target:"rover"` (padrão) ou `target:"manipulator"`. O braço usa `SUBIR`/`DESCER`/`ESQUERDA`/`DIREITA`/`PARAR`; as rodas usam `AVANCAR`/`RECUAR`/`ESQUERDA`/`DIREITA`/`PARAR`. Estado e ACK identificam `control_target`. Por padrão não há atuação física; a ponte USB opt-in atua apenas na tração e rejeita movimentos do braço.
- No cliente Pi, `execution` distingue `simulated_only`, `not_dispatched`, `mega_accepted` e `failed`. `mega_accepted` é referência aceita pelo firmware, nunca confirmação de movimento medido. `motor_backend` no estado/status e `hardware_actuation` no estado identificam o backend habilitado. Roteiro: [CONTROLE_MANUAL_MOTORES.md](../../docs/CONTROLE_MANUAL_MOTORES.md).
- ACK documentado:

```json
{
  "version":"1.0",
  "timestamp":"2026-11-10T17:30:00.000Z",
  "source":"raspberry-pi3",
  "simulated":true,
  "type":"ack",
  "data":{
    "command_id":"0f5f52d4-68bb-41cb-ae5a-40b471a2438b",
    "accepted":true,
    "reason":"state_transition_simulated",
    "state":"BUSCA",
    "execution":"simulated_only"
  }
}
```

## Pendências de arquitetura

O firmware do Arduino Mega, ponte H, servos e sensores reais **não estão integrados**.
Este fluxo de teste jamais deverá ser usado como substituto de intertravamento físico,
watchdog no microcontrolador, validação de comandos no Arduino e parada de emergência.
Os estados desta versão são apenas uma demonstração de protocolo, não automação de navegação.
