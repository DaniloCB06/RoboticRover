"""Seguidor de AprilTag para Raspberry Pi 3 com controle proporcional,
cinemática inversa diferencial e integração com a FSM/contratos do RoboticRover.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Optional, Tuple

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - opcional fora da bancada/Pi 3
    cv2 = None

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - opcional fora da bancada/Pi 3
    serial = None

try:
    from pupil_apriltags import Detector  # type: ignore
except ImportError:  # pragma: no cover - opcional fora da bancada/Pi 3
    Detector = None

# ==============================================================================
# 1. CONFIGURAÇÕES DO ROVER E DA CÂMERA (AJUSTE CONFORME A BANCADA)
# ==============================================================================
PORTA_SERIAL = "/dev/ttyACM0"  # No Windows use "COM3", na Pi geralmente "/dev/ttyACM0" ou "/dev/ttyUSB0"
BAUD_RATE = 115200

# Medidas reais do chassi (m)
R_RODA = 0.026       # Raio efetivo do pneu com deformação (52 mm / 2)
BITOLA = 0.170       # Distância entre as rodas (17 cm)
DIST_ALVO = 0.15     # Distância segura de parada (15 cm)

# Parâmetros da AprilTag e da webcam (640x480 para rodar leve na Pi 3)
TAMANHO_TAG_M = 0.05  # Tamanho real do lado preto da tag em metros (ex: 5 cm = 0.05)
# Substitua pelos parâmetros intrínsecos da calibração de vocês: [fx, fy, cx, cy]
CAMERA_PARAMS = [600.0, 600.0, 320.0, 240.0]

# Controle Proporcional e Limites L298N
KP_LIN = 0.85
KP_ANG = 2.40
V_MAX = 0.24         # Velocidade linear máxima (m/s)
OMEGA_MAX = 1.80     # Velocidade angular máxima (rad/s)
W_MAX_RODA = 10.0    # Rotação máxima aproximada da roda com L298N em 9V (rad/s)
PWM_DEADBAND = 38    # PWM mínimo para vencer o atrito estático
TIMEOUT_TAG = 0.40   # Segundos sem ver a tag antes de frear (Card D)

# Tolerâncias de parada na distância alvo
TOL_DIST_PARADA = 0.015  # 1.5 cm
TOL_ANG_PARADA = 0.08    # ~4.6 graus
W_RODA_ZONA_MORTA = 0.08


@dataclass(frozen=True)
class ComandoAproximacao:
    """Resultado do passo de controle proporcional e cinemática diferencial."""

    dist: float
    erro_dist: float
    erro_ang: float
    v: float
    omega: float
    w_esq: float
    w_dir: float
    pwm_esq: int
    pwm_dir: int
    chegou: bool
    motion: str


def vel_para_pwm(
    w_roda: float,
    *,
    w_max_roda: float = W_MAX_RODA,
    pwm_deadband: int = PWM_DEADBAND,
) -> int:
    """Converte velocidade angular da roda (rad/s) em PWM (-255 a 255) com zona morta."""
    if abs(w_roda) < W_RODA_ZONA_MORTA:
        return 0
    sinal = 1 if w_roda > 0 else -1
    proporcao = min(1.0, abs(w_roda) / w_max_roda)
    pwm = int(pwm_deadband + proporcao * (255 - pwm_deadband))
    return sinal * min(255, pwm)


def cinematica_inversa_diferencial(
    v: float,
    omega: float,
    *,
    r_roda: float = R_RODA,
    bitola: float = BITOLA,
) -> Tuple[float, float]:
    """Converte velocidades linear (m/s) e angular (rad/s) em (w_esq, w_dir) (rad/s)."""
    w_dir = (2.0 * v + omega * bitola) / (2.0 * r_roda)
    w_esq = (2.0 * v - omega * bitola) / (2.0 * r_roda)
    return w_esq, w_dir


def classificar_movimento_contrato(pwm_esq: int, pwm_dir: int) -> str:
    """Mapeia o par de PWM para o enum `motion` de `shared/contracts/v1/messages.schema.json`."""
    if pwm_esq == 0 and pwm_dir == 0:
        return "PARAR"
    if pwm_esq < 0 and pwm_dir < 0:
        return "RECUAR"
    if pwm_dir > pwm_esq:
        return "ESQUERDA"
    if pwm_esq > pwm_dir:
        return "DIREITA"
    return "AVANCAR"


def formatar_comando_serial(pwm_esq: int, pwm_dir: int) -> str:
    """Formata o comando serial esperado pelo Arduino Mega (`pwmEsq,pwmDir\\n`)."""
    esq = max(-255, min(255, int(pwm_esq)))
    dire = max(-255, min(255, int(pwm_dir)))
    return f"{esq},{dire}\n"


def calcular_controle_proporcional(
    x_cam: float,
    z_cam: float,
    *,
    dist_alvo: float = DIST_ALVO,
    kp_lin: float = KP_LIN,
    kp_ang: float = KP_ANG,
    v_max: float = V_MAX,
    omega_max: float = OMEGA_MAX,
    r_roda: float = R_RODA,
    bitola: float = BITOLA,
) -> ComandoAproximacao:
    """Calcula velocidades e PWMs para aproximação proporcional à AprilTag."""
    dist = math.hypot(x_cam, z_cam)
    erro_dist = dist - dist_alvo
    erro_ang = -math.atan2(x_cam, z_cam)  # Negativo para corrigir para o lado certo

    if erro_dist <= TOL_DIST_PARADA and abs(erro_ang) < TOL_ANG_PARADA:
        return ComandoAproximacao(
            dist=dist,
            erro_dist=erro_dist,
            erro_ang=erro_ang,
            v=0.0,
            omega=0.0,
            w_esq=0.0,
            w_dir=0.0,
            pwm_esq=0,
            pwm_dir=0,
            chegou=True,
            motion="PARAR",
        )

    v = max(0.0, min(v_max, kp_lin * erro_dist * math.cos(erro_ang)))
    omega = max(-omega_max, min(omega_max, kp_ang * erro_ang))
    w_esq, w_dir = cinematica_inversa_diferencial(v, omega, r_roda=r_roda, bitola=bitola)
    pwm_esq = vel_para_pwm(w_esq)
    pwm_dir = vel_para_pwm(w_dir)
    return ComandoAproximacao(
        dist=dist,
        erro_dist=erro_dist,
        erro_ang=erro_ang,
        v=v,
        omega=omega,
        w_esq=w_esq,
        w_dir=w_dir,
        pwm_esq=pwm_esq,
        pwm_dir=pwm_dir,
        chegou=False,
        motion=classificar_movimento_contrato(pwm_esq, pwm_dir),
    )


class SeguidorAprilTag:
    """Controlador de aproximação por AprilTag com watchdog de perda visual e integração FSM."""

    def __init__(
        self,
        controller: Optional[Any] = None,
        *,
        timeout_tag: float = TIMEOUT_TAG,
        dist_alvo: float = DIST_ALVO,
    ) -> None:
        self.controller = controller
        self.timeout_tag = timeout_tag
        self.dist_alvo = dist_alvo
        self.ultimo_tempo_tag: Optional[float] = None
        self.ultimo_pwm: Tuple[int, int] = (0, 0)
        self.tag_perdida: bool = False

    def _atuacao_autorizada(self, agora: float) -> bool:
        if self.controller is None:
            return True
        if getattr(self.controller, "state", None) != "APROXIMACAO":
            return False
        if getattr(self.controller, "faulted", False):
            return False
        if hasattr(self.controller, "station_alive"):
            return bool(self.controller.station_alive())
        if hasattr(self.controller, "station_ok"):
            return bool(self.controller.station_ok(at=agora))
        return True

    def _notificar_chegada(self, agora: float) -> bool:
        if self.controller is None or not hasattr(self.controller, "approach_completed"):
            return False
        try:
            return bool(self.controller.approach_completed(at=agora))
        except TypeError:
            return bool(self.controller.approach_completed())

    def atualizar(
        self,
        pose_xz: Optional[Tuple[float, float]],
        *,
        agora: Optional[float] = None,
    ) -> Tuple[int, int]:
        """Atualiza o seguidor com `pose_xz=(x_cam, z_cam)` ou `None` se nenhuma tag foi vista."""
        instante = time.monotonic() if agora is None else agora

        if not self._atuacao_autorizada(instante):
            self.ultimo_pwm = (0, 0)
            return self.ultimo_pwm

        if pose_xz is not None:
            self.ultimo_tempo_tag = instante
            self.tag_perdida = False
            x_cam, z_cam = float(pose_xz[0]), float(pose_xz[1])
            cmd = calcular_controle_proporcional(x_cam, z_cam, dist_alvo=self.dist_alvo)
            if cmd.chegou:
                self.ultimo_pwm = (0, 0)
                self._notificar_chegada(instante)
                return self.ultimo_pwm
            self.ultimo_pwm = (cmd.pwm_esq, cmd.pwm_dir)
            return self.ultimo_pwm

        if self.ultimo_tempo_tag is None or (instante - self.ultimo_tempo_tag > self.timeout_tag):
            # Card D: perdeu a tag por mais de 400 ms -> freia
            self.tag_perdida = True
            self.ultimo_pwm = (0, 0)
        return self.ultimo_pwm


def main() -> None:
    if serial is None or cv2 is None or Detector is None:
        raise RuntimeError(
            "Dependências de bancada ausentes (pyserial, opencv-python, pupil-apriltags)."
        )

    # Conecta ao Arduino Mega via USB
    arduino = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=0.05)
    time.sleep(2.0)  # Aguarda o reset automático do Arduino ao abrir a serial

    # Inicializa webcam e detector AprilTag
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    detector = Detector(families="tag36h11", nthreads=2)
    seguidor = SeguidorAprilTag(timeout_tag=TIMEOUT_TAG, dist_alvo=DIST_ALVO)
    seguidor.ultimo_tempo_tag = time.monotonic()

    print("Seguidor de AprilTag iniciado. Pressione Ctrl+C para parar.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                arduino.write(b"0,0\n")
                continue

            cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            tags = detector.detect(
                cinza,
                estimate_tag_pose=True,
                camera_params=CAMERA_PARAMS,
                tag_size=TAMANHO_TAG_M,
            )

            agora = time.monotonic()
            pose_xz: Optional[Tuple[float, float]] = None
            if tags:
                # Usa a primeira tag detectada; t = [x_lateral, y_vertical, z_profundidade]
                t = tags[0].pose_t.flatten()
                pose_xz = (float(t[0]), float(t[2]))

            pwm_esq, pwm_dir = seguidor.atualizar(pose_xz, agora=agora)

            # Envia comando para o Arduino Mega no formato "pwm_esq,pwm_dir\n"
            comando = formatar_comando_serial(pwm_esq, pwm_dir)
            arduino.write(comando.encode("utf-8"))

            time.sleep(0.05)  # ~20 Hz (leve para a CPU da Raspberry Pi 3)

    except KeyboardInterrupt:
        print("\nParando robô...")
    finally:
        arduino.write(b"0,0\n")
        cap.release()
        arduino.close()


if __name__ == "__main__":
    main()
