# Visão Computacional e Navegação por AprilTag

Espaço dedicado à captura da webcam, detecção de marcadores AprilTag (`tag36h11`) e cálculo de controle de aproximação do Rover, respeitando a máquina de estados e os contratos versionados em `shared/contracts/`.

## Módulo `vision/seguidor_apriltag_pi3.py`

Implementa o controlador proporcional de aproximação e a cinemática inversa diferencial validados em simulação, integrados com a máquina de estados do Rover (`APROXIMACAO` → `AGUARDANDO_PEGA` via `approach_completed()`).

### Parâmetros físicos e de controle validados

| Parâmetro | Constante | Valor | Descrição |
| --- | --- | --- | --- |
| Raio efetivo da roda | `R_RODA` | `0.026 m` | Raio efetivo do pneu com deformação (`52 mm / 2`) |
| Bitola do chassi | `BITOLA` | `0.170 m` | Distância entre os centros das rodas (`17 cm`) |
| Distância de parada | `DIST_ALVO` | `0.15 m` | Distância segura de parada antes do alvo (`15 cm`) |
| Lado da AprilTag | `TAMANHO_TAG_M` | `0.05 m` | Tamanho real do lado preto da tag (`5 cm`) |
| Ganho linear / angular | `KP_LIN` / `KP_ANG` | `0.85` / `2.40` | Ganhos do controlador proporcional |
| Limites de velocidade | `V_MAX` / `OMEGA_MAX` | `0.24 m/s` / `1.80 rad/s` | Saturação linear e angular do chassi |
| Zona morta de PWM | `PWM_DEADBAND` | `38` | PWM mínimo para vencer o atrito estático na ponte H L298N |
| Timeout de perda da tag | `TIMEOUT_TAG` | `0.40 s` | Tempo máximo sem detecção antes de frear (`0,0\n`) |

### Integração com a máquina de estados e `shared/contracts/`

- O seguidor (`SeguidorAprilTag`) só emite PWM diferente de zero quando o controlador do Rover está no estado `APROXIMACAO` com `station/heartbeat` válido e sem falha ativa (`faulted == False`).
- Ao atingir `DIST_ALVO = 0.15 m` alinhado (`erro_dist <= 0.015 m` e `|erro_ang| < 0.08 rad`), o seguidor zera os motores (`0,0\n`) e aciona `controller.approach_completed()`, realizando a transição para `AGUARDANDO_PEGA` com `manual_enabled: true` e `control_target: "manipulator"`.
- Se a tag sair do campo de visão por mais de `400 ms` (`TIMEOUT_TAG`), o watchdog visual força parada imediata (`0,0\n`).
