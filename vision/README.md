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
| Zona morta de PWM | `PWM_MINIMO` | `38` | PWM mínimo para vencer o atrito estático na ponte H L298N |
| Timeout de perda da tag | `TIMEOUT_TAG` | `0.40 s` | Tempo máximo sem detecção antes de frear (`0,0\n`) |

### Integração com a máquina de estados e `shared/contracts/`

- O seguidor (`SeguidorAprilTag`) só emite PWM diferente de zero quando o controlador do Rover está no estado `APROXIMACAO` com `station/heartbeat` válido e sem falha ativa (`faulted == False`).
- Ao atingir `DIST_ALVO = 0.15 m` alinhado (`erro_dist <= 0.015 m` e `|erro_ang| < 0.08 rad`), o seguidor zera os motores (`0,0\n`) e aciona `controller.approach_completed()`, realizando a transição para `AGUARDANDO_PEGA` com `manual_enabled: true` e `control_target: "manipulator"`.
- Se a tag sair do campo de visão por mais de `400 ms` (`TIMEOUT_TAG`), o watchdog visual força parada imediata (`0,0\n`).

### O que verificam os 7 testes (`tests/test_vision_apriltag.py`)

Para rodar somente esses testes no terminal: `.\.venv\Scripts\python.exe -m pytest tests/test_vision_apriltag.py -v` (Windows) ou `.venv/bin/python -m pytest tests/test_vision_apriltag.py -v` (Mac/Linux).

1. `test_medidas_do_chassi`: confere se o raio da roda (`0.026 m`), bitola (`0.170 m`), distância de parada (`0.15 m`) e timeout (`0.40 s`) estão com os valores corretos.
2. `test_pwm_zona_morta_e_limites`: verifica se velocidades muito baixas viram `0`, se valores médios respeitam o mínimo para vencer o atrito (`PWM_MINIMO`) e se não passa de `-255` a `255`.
3. `test_cinematica_reta_e_giro`: garante que andar em linha reta manda a mesma velocidade para as duas rodas e que girar no próprio eixo manda velocidades opostas.
4. `test_controle_para_a_15_cm_e_corrige_lado`: checa se o robô para ao chegar a `15 cm`, acelera quando está longe, gira para o lado certo quando a tag está deslocada e formata `"esq,dir\n"`.
5. `test_seguidor_com_controller_do_rover`: testa as travas no `Controller` principal — só anda em `APROXIMACAO`, freia se perder a tag por mais de `0.40 s` e muda para `AGUARDANDO_PEGA` ao chegar.
6. `test_seguidor_com_controller_da_pi3`: faz a mesma checagem de aproximação e transição para `AGUARDANDO_PEGA` usando o `SimulatedController` da Raspberry Pi 3.
7. `test_firmware_tem_watchdog_e_nao_usa_pinos_18_19`: lê os arquivos `.ino` do Arduino Mega para garantir que o watchdog de `350 ms` está presente e os pinos `18` e `19` seguem livres para a ArbotiX-M.
