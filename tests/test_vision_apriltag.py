import math
from pathlib import Path

from conftest import command, send
from roboticrover_pi3.controller import SimulatedController
from roboticrover_pi3.protocol import Received
from vision import (
    BITOLA, DIST_ALVO, PWM_MINIMO, R_RODA, TIMEOUT_TAG,
    SeguidorAprilTag, calcular_pwm, cinematica_inversa, formatar_comando, vel_para_pwm,
)

ROOT = Path(__file__).resolve().parents[1]


def test_medidas_do_chassi():
    assert (R_RODA, BITOLA, DIST_ALVO, TIMEOUT_TAG) == (0.026, 0.170, 0.15, 0.40)


def test_pwm_zona_morta_e_limites():
    assert vel_para_pwm(0.05) == 0
    assert vel_para_pwm(10.0) == 255
    assert vel_para_pwm(-10.0) == -255
    assert PWM_MINIMO <= vel_para_pwm(0.5) < 255


def test_cinematica_reta_e_giro():
    esq, dire = cinematica_inversa(0.13, 0.0)
    assert math.isclose(esq, dire)
    esq, dire = cinematica_inversa(0.0, 1.0)
    assert math.isclose(esq, -dire)


def test_controle_para_a_15_cm_e_corrige_lado():
    assert calcular_pwm(0.0, DIST_ALVO) == (0, 0, True)
    esq, dire, chegou = calcular_pwm(0.0, 0.50)
    assert esq == dire > 0 and not chegou
    esq, dire, _ = calcular_pwm(0.12, 0.45)  # tag à direita
    assert esq > dire
    assert formatar_comando(10, -20) == "10,-20\n"


def test_seguidor_com_controller_do_rover(rig, clock):
    controller, _ = rig
    seguidor = SeguidorAprilTag(controller)

    assert seguidor.atualizar((0.0, 0.5), agora=10.0) == (0, 0)   # em espera: nao anda
    send(controller, command(clock, "BUSCA"))
    assert seguidor.atualizar((0.0, 0.5), agora=10.1) == (0, 0)   # busca: nao anda
    send(controller, command(clock, "APROXIMACAO"))
    pwm = seguidor.atualizar((0.0, 0.5), agora=10.2)
    assert pwm[0] > 0 and pwm[1] > 0                              # aproximacao: anda

    assert seguidor.atualizar(None, agora=10.4) == pwm            # perda curta: mantem
    assert seguidor.atualizar(None, agora=10.65) == (0, 0)        # perdeu a tag: freia

    assert seguidor.atualizar((0.0, DIST_ALVO), agora=10.7) == (0, 0)
    assert controller.state == "AGUARDANDO_PEGA"
    assert controller.manual_authorized is True


def test_seguidor_com_controller_da_pi3():
    ctrl = SimulatedController(heartbeat_timeout=4.0)
    ctrl.heartbeat(Received("station/heartbeat", "heartbeat",
                            {"online": True, "session_id": "s1"}, True, "station-nodered"))
    for i, modo in enumerate(("BUSCA", "APROXIMACAO")):
        ctrl.command(Received("rover/cmd/modo", "mode_command",
                              {"mode": modo, "command_id": f"c{i}"}, True, "station-nodered"))
    seguidor = SeguidorAprilTag(ctrl)
    assert seguidor.atualizar((0.0, 0.40)) != (0, 0)
    assert seguidor.atualizar((0.0, DIST_ALVO)) == (0, 0)
    assert ctrl.state == "AGUARDANDO_PEGA"


def test_firmware_tem_watchdog_e_nao_usa_pinos_18_19():
    for caminho in ("firmware/arduino-mega/CodeMegaTestV1.0/CodeMegaTestV1.0.ino",
                    "firmware/arduino-mega/controle_l298n_mega/controle_l298n_mega.ino"):
        texto = (ROOT / caminho).read_text(encoding="utf-8")
        assert "TIMEOUT_WATCHDOG_MS = 350" in texto
        assert "= 18;" not in texto and "= 19;" not in texto
