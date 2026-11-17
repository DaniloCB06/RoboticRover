from pathlib import Path
import math

from conftest import command, send
from rover.contracts import envelope, validate
from roboticrover_pi3.controller import SimulatedController
from roboticrover_pi3.protocol import Received
from vision import (
    BITOLA,
    DIST_ALVO,
    PWM_DEADBAND,
    R_RODA,
    TIMEOUT_TAG,
    SeguidorAprilTag,
    calcular_controle_proporcional,
    cinematica_inversa_diferencial,
    formatar_comando_serial,
    vel_para_pwm,
)

ROOT = Path(__file__).resolve().parents[1]


def test_chassis_constants_and_deadband():
    assert R_RODA == 0.026
    assert BITOLA == 0.170
    assert DIST_ALVO == 0.15
    assert TIMEOUT_TAG == 0.40
    assert vel_para_pwm(0.0) == 0
    assert vel_para_pwm(0.05) == 0
    assert vel_para_pwm(-0.05) == 0
    assert vel_para_pwm(10.0) == 255
    assert vel_para_pwm(-10.0) == -255
    assert PWM_DEADBAND <= vel_para_pwm(0.5) < 255


def test_differential_inverse_kinematics_symmetry():
    w_esq, w_dir = cinematica_inversa_diferencial(0.13, 0.0)
    assert math.isclose(w_esq, w_dir)
    assert math.isclose(w_esq, 0.13 / R_RODA)

    w_esq_rot, w_dir_rot = cinematica_inversa_diferencial(0.0, 1.0)
    assert math.isclose(w_dir_rot, -w_esq_rot)
    assert math.isclose(w_dir_rot, BITOLA / (2.0 * R_RODA))


def test_proportional_control_stops_at_target_distance():
    cmd_stop = calcular_controle_proporcional(0.0, DIST_ALVO)
    assert cmd_stop.chegou is True
    assert (cmd_stop.pwm_esq, cmd_stop.pwm_dir) == (0, 0)
    assert cmd_stop.motion == "PARAR"

    cmd_far = calcular_controle_proporcional(0.0, 0.50)
    assert cmd_far.chegou is False
    assert cmd_far.pwm_esq == cmd_far.pwm_dir > 0
    assert cmd_far.motion == "AVANCAR"

    # Tag à direita da câmera (x_cam > 0) -> erro_ang negativo -> roda esquerda gira mais rápido
    cmd_right = calcular_controle_proporcional(0.12, 0.45)
    assert cmd_right.pwm_esq > cmd_right.pwm_dir
    assert cmd_right.motion == "DIREITA"
    assert formatar_comando_serial(cmd_right.pwm_esq, cmd_right.pwm_dir) == f"{cmd_right.pwm_esq},{cmd_right.pwm_dir}\n"


def test_tag_timeout_and_fsm_contract_integration(rig, clock):
    controller, messages = rig
    seguidor = SeguidorAprilTag(controller=controller)

    # Fora de APROXIMACAO (ex: SEGURO_ESPERA ou BUSCA), nenhum PWM é enviado
    assert seguidor.atualizar((0.0, 0.50), agora=10.0) == (0, 0)
    send(controller, command(clock, "BUSCA"))
    assert seguidor.atualizar((0.0, 0.50), agora=10.1) == (0, 0)

    # Em APROXIMACAO com heartbeat válido, gera PWM proporcional
    send(controller, command(clock, "APROXIMACAO"))
    pwm_esq, pwm_dir = seguidor.atualizar((0.0, 0.50), agora=10.2)
    assert pwm_esq > 0 and pwm_dir > 0

    # Perda breve (< 400 ms) mantém último comando; após TIMEOUT_TAG (0.40 s) freia
    assert seguidor.atualizar(None, agora=10.4) == (pwm_esq, pwm_dir)
    assert seguidor.atualizar(None, agora=10.65) == (0, 0)
    assert seguidor.tag_perdida is True

    # Ao atingir 0.15 m alinhado, freia (0, 0) e aciona approach_completed() -> AGUARDANDO_PEGA
    assert seguidor.atualizar((0.0, DIST_ALVO), agora=10.7) == (0, 0)
    assert controller.state == "AGUARDANDO_PEGA"
    assert controller.manual_authorized is True
    assert controller.control_target == "manipulator"

    for topic, data in messages:
        validate(topic, envelope(topic, "test", data))


def test_pi3_simulated_controller_integration():
    pi_ctrl = SimulatedController(heartbeat_timeout=4.0)
    pi_ctrl.heartbeat(
        Received("station/heartbeat", "heartbeat", {"online": True, "session_id": "s1"}, True, "station-nodered"),
        at=1.0,
    )
    pi_ctrl.command(
        Received("rover/cmd/modo", "mode_command", {"mode": "BUSCA", "command_id": "c1"}, True, "station-nodered"),
        at=1.1,
    )
    pi_ctrl.command(
        Received("rover/cmd/modo", "mode_command", {"mode": "APROXIMACAO", "command_id": "c2"}, True, "station-nodered"),
        at=1.2,
    )
    seguidor = SeguidorAprilTag(controller=pi_ctrl)
    assert seguidor.atualizar((0.0, 0.40), agora=1.3) != (0, 0)
    assert seguidor.atualizar((0.0, DIST_ALVO), agora=1.4) == (0, 0)
    assert pi_ctrl.state == "AGUARDANDO_PEGA"
    assert pi_ctrl.manual_authorized is True
    assert pi_ctrl.control_target == "manipulator"


def test_firmware_l298n_watchdog_and_arbotix_pins():
    for rel_path in (
        "firmware/arduino-mega/CodeMegaTestV1.0/CodeMegaTestV1.0.ino",
        "firmware/arduino-mega/controle_l298n_mega/controle_l298n_mega.ino",
    ):
        content = (ROOT / rel_path).read_text(encoding="utf-8")
        assert "TIMEOUT_WATCHDOG_MS = 350" in content
        assert "const int ENA = 8;" in content
        assert "const int ENB = 9;" in content
        assert "pararMotores();" in content
        # Garante que os pinos 18 e 19 não são atribuídos à ponte H
        assert "= 18;" not in content and "= 19;" not in content
