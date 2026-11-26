"""Seguidor de AprilTag: faz o rover se aproximar da tag e parar a 15 cm.

Ordem do que acontece (leia de cima para baixo):
  1. A câmera acha a tag e mede onde ela está (x = lado, z = frente).
  2. calcular_pwm() decide a força dos motores (controle proporcional).
  3. SeguidorAprilTag so deixa os motores girarem se o rover estiver
     no estado APROXIMACAO. Chegou a 15 cm? Para e avisa o rover.
  4. O PWM vai por USB para o Arduino Mega (texto "esq,dir").
"""
import math
import time

# ---------------- Medidas do rover (em metros) ----------------
R_RODA = 0.026       # raio da roda
BITOLA = 0.170       # distância entre as rodas
DIST_ALVO = 0.15     # para a 15 cm da tag

# ---------------- Ajustes do controle ----------------
KP_LIN = 0.85        # ganho de avanço (quanto maior, mais rápido)
KP_ANG = 2.40        # ganho de giro
V_MAX = 0.24         # velocidade máxima de avanço (m/s)
OMEGA_MAX = 1.80     # velocidade máxima de giro (rad/s)
W_MAX_RODA = 10.0    # giro máximo da roda (rad/s)
PWM_MINIMO = 38      # PWM mínimo para o motor sair do lugar
TIMEOUT_TAG = 0.40   # segundos sem ver a tag -> freia
TOL_DIST = 0.015     # tolerância de distância para considerar "chegou"
TOL_ANGULO = 0.08    # tolerância de ângulo (rad) para considerar "chegou"

# ---------------- Câmera e serial (usados só no main) ----------------
PORTA_SERIAL = "/dev/ttyACM0"
BAUD_RATE = 115200
TAMANHO_TAG_M = 0.05
CAMERA_PARAMS = [600.0, 600.0, 320.0, 240.0]  # fx, fy, cx, cy


def vel_para_pwm(w_roda):
    """Transforma velocidade da roda (rad/s) em PWM de -255 a 255."""
    if abs(w_roda) < 0.08:
        return 0
    sinal = 1 if w_roda > 0 else -1
    proporcao = min(1.0, abs(w_roda) / W_MAX_RODA)
    pwm = int(PWM_MINIMO + proporcao * (255 - PWM_MINIMO))
    return sinal * min(255, pwm)


def cinematica_inversa(v, omega):
    """Converte avanço v e giro omega na velocidade de cada roda (esq, dir)."""
    w_dir = (2 * v + omega * BITOLA) / (2 * R_RODA)
    w_esq = (2 * v - omega * BITOLA) / (2 * R_RODA)
    return w_esq, w_dir


def calcular_pwm(x_cam, z_cam):
    """Controle proporcional. Retorna (pwm_esq, pwm_dir, chegou)."""
    distancia = math.hypot(x_cam, z_cam)
    erro_dist = distancia - DIST_ALVO
    erro_ang = -math.atan2(x_cam, z_cam)

    if erro_dist <= TOL_DIST and abs(erro_ang) < TOL_ANGULO:
        return 0, 0, True

    v = KP_LIN * erro_dist * math.cos(erro_ang)
    v = max(0.0, min(V_MAX, v))
    omega = KP_ANG * erro_ang
    omega = max(-OMEGA_MAX, min(OMEGA_MAX, omega))

    w_esq, w_dir = cinematica_inversa(v, omega)
    return vel_para_pwm(w_esq), vel_para_pwm(w_dir), False


def formatar_comando(pwm_esq, pwm_dir):
    """Texto enviado ao Mega, ex: '120,120\\n'."""
    return f"{pwm_esq},{pwm_dir}\n"


class SeguidorAprilTag:
    """Liga o controle à máquina de estados do rover (o 'controller')."""

    def __init__(self, controller=None):
        self.controller = controller
        self.ultimo_pwm = (0, 0)
        self.ultima_vez_vista = None

    def _pode_andar(self):
        c = self.controller
        if c is None:
            return True
        if c.state != "APROXIMACAO" or getattr(c, "faulted", False):
            return False
        # Os dois controllers do projeto usam nomes diferentes para o heartbeat.
        if hasattr(c, "station_alive"):
            return c.station_alive()
        return c.station_ok()

    def atualizar(self, pose, agora=None):
        """pose = (x, z) da tag, ou None se não viu. Retorna (pwm_esq, pwm_dir)."""
        if agora is None:
            agora = time.monotonic()

        if not self._pode_andar():
            self.ultimo_pwm = (0, 0)
            return self.ultimo_pwm

        if pose is None:
            # Perdeu a tag: depois de TIMEOUT_TAG segundos, freia.
            sem_tag = self.ultima_vez_vista is None or agora - self.ultima_vez_vista > TIMEOUT_TAG
            if sem_tag:
                self.ultimo_pwm = (0, 0)
            return self.ultimo_pwm

        self.ultima_vez_vista = agora
        pwm_esq, pwm_dir, chegou = calcular_pwm(pose[0], pose[1])
        self.ultimo_pwm = (pwm_esq, pwm_dir)
        if chegou and self.controller is not None:
            self.controller.approach_completed()  # vai para AGUARDANDO_PEGA
        return self.ultimo_pwm

    @property
    def tag_perdida(self):
        return self.ultimo_pwm == (0, 0) and self.ultima_vez_vista is not None


def main():
    """Roda na Raspberry Pi: câmera -> tag -> controle -> Mega."""
    import cv2
    import serial
    from pupil_apriltags import Detector

    arduino = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=0.05)
    time.sleep(2.0)  # o Mega reinicia ao abrir a serial
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    detector = Detector(families="tag36h11", nthreads=2)
    seguidor = SeguidorAprilTag()

    print("Seguidor iniciado. Ctrl+C para parar.")
    try:
        while True:
            ok, imagem = camera.read()
            pose = None
            if ok:
                cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
                tags = detector.detect(cinza, estimate_tag_pose=True,
                                       camera_params=CAMERA_PARAMS, tag_size=TAMANHO_TAG_M)
                if tags:
                    t = tags[0].pose_t.flatten()
                    pose = (float(t[0]), float(t[2]))
            pwm_esq, pwm_dir = seguidor.atualizar(pose)
            arduino.write(formatar_comando(pwm_esq, pwm_dir).encode())
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Parando...")
    finally:
        arduino.write(b"0,0\n")
        camera.release()
        arduino.close()


if __name__ == "__main__":
    main()
