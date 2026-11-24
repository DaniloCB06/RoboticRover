"""Tração USB opt-in. Nenhum movimento é renovado sem um novo comando MQTT."""
from __future__ import annotations

from dataclasses import dataclass
import binascii
import math
import os
import secrets
import time

MAX_FRAME = 128
OPCODES = {"HELLO": 1, "ARM": 2, "WHEELS": 3, "STOP": 4, "DISARM": 5}
DIRECTIONS = {"AVANCAR": (1, 1), "RECUAR": (-1, -1), "ESQUERDA": (-1, 1), "DIREITA": (1, -1)}


class MotorError(RuntimeError):
    pass


@dataclass(frozen=True)
class MotorConfig:
    backend: str = "simulation"
    port: str = ""
    pwm: int = 80
    lease_ms: int = 300
    ack_timeout: float = 0.15
    reset_delay: float = 2.0
    invert_left: bool = False
    invert_right: bool = False

    def __post_init__(self):
        if self.backend not in ("simulation", "serial"):
            raise ValueError("MOTOR_BACKEND deve ser simulation ou serial")
        if self.backend == "serial" and (not self.port.startswith("/dev/") or "\n" in self.port):
            raise ValueError("MOTOR_SERIAL_PORT deve indicar explicitamente a porta /dev/ do Mega")
        if not 1 <= self.pwm <= 120 or not 100 <= self.lease_ms <= 500:
            raise ValueError("MOTOR_PWM deve ser 1..120 e MOTOR_LEASE_MS 100..500 (limites de bancada)")
        if not math.isfinite(self.ack_timeout) or not 0.02 <= self.ack_timeout <= 0.5:
            raise ValueError("MOTOR_ACK_TIMEOUT_SEC deve ser 0.02..0.5")
        if not math.isfinite(self.reset_delay) or not 0 <= self.reset_delay <= 5:
            raise ValueError("MOTOR_RESET_DELAY_SEC deve ser 0..5")

    @classmethod
    def from_env(cls):
        return cls(os.getenv("MOTOR_BACKEND", "simulation"), os.getenv("MOTOR_SERIAL_PORT", ""),
                   int(os.getenv("MOTOR_PWM", "80")), int(os.getenv("MOTOR_LEASE_MS", "300")),
                   float(os.getenv("MOTOR_ACK_TIMEOUT_SEC", ".15")), float(os.getenv("MOTOR_RESET_DELAY_SEC", "2")),
                   os.getenv("MOTOR_INVERT_LEFT", "0") == "1", os.getenv("MOTOR_INVERT_RIGHT", "0") == "1")


def frame(session, sequence, operation, a=0, b=0, ttl=0):
    body = f"RR1|{session:08X}|{sequence}|{operation}|{a}|{b}|{ttl}".encode("ascii")
    return body + f"|{binascii.crc_hqx(body, 0xFFFF):04X}\n".encode("ascii")


def parse_frame(raw):
    if len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
        raise ValueError("quadro serial incompleto/excessivo")
    try:
        body, checksum = raw[:-1].rsplit(b"|", 1)
        if len(checksum) != 4 or int(checksum, 16) != binascii.crc_hqx(body, 0xFFFF):
            raise ValueError("CRC inválido")
        version, session, seq, op, a, b, ttl = body.decode("ascii").split("|")
        if version != "RR1" or len(session) != 8:
            raise ValueError("versão inválida")
        return int(session, 16), int(seq), op, int(a), int(b), int(ttl)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("quadro serial inválido") from exc


class SerialMotors:
    def __init__(self, config, *, serial_factory=None, clock=time.monotonic, sleep=time.sleep):
        self.config, self.factory, self.clock, self.sleep = config, serial_factory, clock, sleep
        self.serial = None
        self.session = secrets.randbelow(0xFFFFFFFF) + 1
        self.sequence = 0
        self.armed = False
        self.deadline = 0.0
        self.fault = None
        self.left = self.right = 0

    def start(self):
        if self.serial is not None:
            return
        try:
            factory = self.factory
            if factory is None:
                try:
                    from serial import Serial
                except ImportError as exc:
                    raise MotorError("Instale o extra motor-control (pyserial) na Pi") from exc
                factory = Serial
            self.serial = factory(self.config.port, baudrate=115200, timeout=0.01,
                                  write_timeout=self.config.ack_timeout, exclusive=True)
            self.sleep(self.config.reset_delay)
            self.serial.reset_input_buffer()
            self._request("HELLO")
            self.stop()
        except Exception as exc:
            self._fail(exc)

    def _request(self, operation, a=0, b=0, ttl=0):
        if self.serial is None or self.fault:
            raise MotorError(self.fault or "serial não iniciada")
        try:
            self.sequence += 1
            if self.sequence > 0xFFFFFFFF:
                raise MotorError("sequência esgotada; reinicie o cliente")
            packet = frame(self.session, self.sequence, operation, a, b, ttl)
            if self.serial.write(packet) != len(packet):
                raise MotorError("escrita serial incompleta")
            until = self.clock() + self.config.ack_timeout
            pending = bytearray()
            while self.clock() < until:
                pending.extend(self.serial.read(1))
                if len(pending) > MAX_FRAME:
                    raise MotorError("resposta serial excessiva")
                if not pending.endswith(b"\n"):
                    continue
                try:
                    session, seq, op, code, armed, _ = parse_frame(bytes(pending))
                except ValueError:
                    pending.clear()
                    continue
                pending.clear()
                if session != self.session or seq != self.sequence:
                    continue
                expected_armed = 1 if operation in ("ARM", "WHEELS") else 0
                if op != "ACK" or code != OPCODES[operation] or armed != expected_armed:
                    raise MotorError(f"Mega recusou {operation}: {op}/{code}")
                self.armed = bool(armed)
                return
            raise MotorError("timeout esperando ACK do Mega")
        except Exception as exc:
            self._fail(exc)

    def _fail(self, exc):
        self.fault = str(exc)
        self.deadline = 0
        self.left = self.right = 0
        self.armed = False
        if self.serial is not None:
            try:
                self.serial.write(frame(self.session, min(self.sequence + 1, 0xFFFFFFFF), "DISARM"))
            except Exception:
                pass
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None
        raise MotorError(self.fault) from exc

    def move(self, action, duration_ms):
        if self.fault:
            raise MotorError(self.fault)
        left, right = DIRECTIONS[action]
        ttl = min(self.config.lease_ms, duration_ms)
        if ttl < 1:
            raise MotorError("comando já expirado")
        started = self.clock()
        left *= self.config.pwm * (-1 if self.config.invert_left else 1)
        right *= self.config.pwm * (-1 if self.config.invert_right else 1)
        if self.left * left < 0 or self.right * right < 0:
            self.stop()
            self.sleep(.05)  # Intervalo provisório de bancada; medir sob carga.
        if not self.armed:
            self._request("ARM")
        # O tempo gasto esperando ARM também consome a validade da referência.
        ttl -= int((self.clock() - started) * 1000)
        if ttl < 1:
            self.stop()
            raise MotorError("comando expirou durante o rearme")
        self.deadline = started + min(self.config.lease_ms, duration_ms) / 1000
        self._request("WHEELS", left, right, ttl)
        self.left, self.right = left, right

    def stop(self):
        self.deadline = 0
        self.left = self.right = 0
        self._request("DISARM")

    def tick(self, current):
        if self.deadline and current >= self.deadline:
            self.stop()
            return True
        return False

    def close(self):
        if self.serial is not None:
            try:
                self.stop()
            finally:
                if self.serial is not None:
                    self.serial.close()
                    self.serial = None


def configured_motors():
    config = MotorConfig.from_env()
    return SerialMotors(config) if config.backend == "serial" else None
