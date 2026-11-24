"""Inicia e encerra a comunicação do Mac e da Pi, sem Docker ou acesso à internet."""
from __future__ import annotations

import argparse
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv/bin/python"
RUNTIME = ROOT / ".runtime"

REMOTE_RUNNER = r'''
import fcntl, json, os, signal, subprocess, sys, threading, time
from pathlib import Path

data = json.loads(sys.stdin.readline())
os.chdir(data["directory"])
runtime = Path(".runtime")
runtime.mkdir(exist_ok=True)
lock = (runtime / "inicia_comunicacao.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
stopped = threading.Event()
for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(signum, lambda *_: stopped.set())
lease = [time.monotonic()]
def watch_parent():
    for line in sys.stdin:
        if line.strip() == "stop": break
        if line.strip() == "keepalive": lease[0] = time.monotonic()
    stopped.set()
threading.Thread(target=watch_parent, daemon=True).start()
processes = []
logs = []
code = 0
try:
    for name, command in data["commands"]:
        log_path = runtime / (data["run_id"] + "-" + name + ".log")
        log = log_path.open("a")
        logs.append(log)
        process = subprocess.Popen(command, env=dict(os.environ, **data["environment"]),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append((name, process))
    print(json.dumps({"ready": True, "pids": {name: proc.pid for name, proc in processes},
                      "logs": [str(Path(log.name).resolve()) for log in logs]}), flush=True)
    while not stopped.wait(.25):
        if time.monotonic() - lease[0] > 10:
            print(json.dumps({"error": "Estação não renovou a sessão; encerrando a Pi"}), flush=True)
            code = 1
            break
        for name, process in processes:
            if process.poll() is not None:
                print(json.dumps({"error": name + " encerrou", "code": process.returncode}), flush=True)
                code = 1
                stopped.set()
                break
finally:
    for _, process in reversed(processes):
        if process.poll() is None:
            try: os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError: pass
    deadline = time.monotonic() + 10
    for _, process in reversed(processes):
        try: process.wait(timeout=max(.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
    for log in logs: log.close()
    print(json.dumps({"stopped": True}), flush=True)
sys.exit(code)
'''

REMOTE_CHECK = r'''
import importlib.util, json, os, socket
from pathlib import Path
directory = Path(__import__("sys").argv[1])
os.chdir(directory)
required = ["roboticrover_pi3.camera", "roboticrover_pi3.competition_video", "aiortc", "av", "dotenv", "paho.mqtt"]
missing = [module for module in required if importlib.util.find_spec(module) is None]
running = []
for item in Path("/proc").iterdir():
    if not item.name.isdigit(): continue
    try: command = (item / "cmdline").read_bytes().split(b"\0")
    except OSError: continue
    if b"-m" in command:
        module = command[command.index(b"-m") + 1]
        if module in (b"roboticrover_pi3", b"roboticrover_pi3.competition_rover",
                      b"roboticrover_pi3.camera", b"roboticrover_pi3.competition_video", b"rover"):
            running.append({"pid": int(item.name), "module": module.decode()})
ports = []
for port, kind in ((8080, socket.SOCK_STREAM), (5002, socket.SOCK_DGRAM)):
    with socket.socket(socket.AF_INET, kind) as sock:
        try: sock.bind(("127.0.0.1", port))
        except OSError: ports.append(port)
camera = Path("/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0").exists()
print(json.dumps({"connection": os.environ.get("SSH_CONNECTION", "").split(), "missing": missing,
                  "running": running, "ports": ports, "camera": camera,
                  "ffmpeg": __import__("shutil").which("ffmpeg")}))
'''


def choose_mode(value=None):
    if value is not None:
        return int(value)
    print("1 = servidor do professor não é alcançável (comunicação local)")
    print("2 = servidor do professor é alcançável (modo competição)")
    print("O servidor pode funcionar sem internet; a opção 2 exige acesso pela rede local.")
    while True:
        value = input("Escolha 1 ou 2: ").strip()
        if value in ("1", "2"):
            return int(value)
        print("Digite apenas 1 ou 2.")


def port_free(port, kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as exc:
            raise RuntimeError(f"Porta {port} ocupada no Mac. Pare o processo anterior antes de iniciar.") from exc


def require_connection(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError as exc:
        raise RuntimeError(f"Sem acesso a {host}:{port}. Verifique a rede ou escolha o modo 1.") from exc


def build_commands(mode, mac_ip, pi_dir, config):
    python = f"{pi_dir}/apps/rover/.venv/bin/python"
    remote = [
        ["rover", [python, "-m", "roboticrover_pi3.competition_rover" if mode == 2 else "roboticrover_pi3"]],
        ["camera", [python, "-m", "roboticrover_pi3.camera", "--relay-host", "127.0.0.1",
                    "--relay-port", "5002", "--relay-transport", "udp", "--fps", "15", "--preview-fps", "1"]],
        ["publicador", [python, "-m", "roboticrover_pi3.competition_video", "--listen-host", "127.0.0.1",
                        "--listen-port", "5002", "--transport", "udp", "--basic", "--destination",
                        f"http://{mac_ip}:8890/rover/{config['COMPETITION_TEAM']}/whip"]],
    ]
    forward = [str(PYTHON), "-m", "roboticrover_pi3.competition_forward", "--host", mac_ip]
    if mode == 1:
        forward.append("--local-only")
    local = [
        ["mqtt", [str(ROOT / ".venv/bin/mosquitto"), "-c", str(ROOT / "infra/mqtt/mosquitto.local.conf")], 1883],
        ["video", forward, 8890],
        ["dashboard", ["node-red", "--userDir", str(ROOT / ".runtime/pi3-bootstrap/node-red"),
                       "--settings", str(ROOT / "apps/station/node-red/settings.js"),
                       str(ROOT / "apps/station/node-red/flows.json")], 1880],
    ]
    if mode == 2:
        local.append(["ponte-mqtt", [str(PYTHON), "-m", "roboticrover_pi3.competition_station"], None])
    return local, remote


class Launcher:
    def __init__(self, args, mode, config):
        self.args, self.mode, self.config = args, mode, config
        self.processes = []
        self.logs = []
        self.remote = None
        self.remote_ready = threading.Event()
        self.remote_stopped = threading.Event()
        self.messages = []
        self.master = False
        self.master_pid = None
        self.socket_dir = Path(tempfile.mkdtemp(prefix="rr-start-", dir="/tmp"))
        self.socket = str(self.socket_dir / "ssh.sock")
        self.run_id = "comunicacao-" + time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"

    def ssh(self, *extra):
        return ["ssh", "-4", "-S", self.socket, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                *extra, self.args.pi]

    def connect(self):
        command = ["ssh", "-4", "-M", "-f", "-N", "-S", self.socket, "-o", "ControlMaster=yes",
                   "-o", "ControlPersist=no", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
                   "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
                   "-o", "StrictHostKeyChecking=accept-new"]
        if self.mode == 1:
            command += ["-R", "127.0.0.1:18883:127.0.0.1:1883"]
        print(f"Conectando a {self.args.pi}. Digite a senha SSH se ela for solicitada.", flush=True)
        self.master = True
        subprocess.run(command + [self.args.pi], check=True)
        result = subprocess.run(self.ssh("-O", "check"), capture_output=True, text=True, timeout=3)
        match = re.search(r"pid=(\d+)", result.stderr)
        if result.returncode or match is None:
            raise RuntimeError("A conexão SSH não confirmou o compartilhamento da sessão.")
        self.master_pid = int(match.group(1))

    def check_pi(self):
        python = self.args.pi_dir + "/apps/rover/.venv/bin/python"
        command = shlex.join([python, "-c", REMOTE_CHECK, self.args.pi_dir])
        result = subprocess.run(self.ssh() + [command], input="", capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise RuntimeError("Não foi possível verificar a instalação na Pi:\n" + result.stderr.strip())
        info = json.loads(result.stdout)
        if info["missing"]:
            raise RuntimeError("Faltam módulos na Pi: " + ", ".join(info["missing"]))
        if info["running"] or info["ports"]:
            raise RuntimeError("Já há processos/portas do Rover ativos na Pi. Pare-os primeiro: " +
                               json.dumps({"processos": info["running"], "portas": info["ports"]}))
        if not info["camera"] or not info["ffmpeg"]:
            raise RuntimeError("A Pi precisa da webcam USB conectada e do FFmpeg instalado.")
        if len(info["connection"]) != 4:
            raise RuntimeError("Não foi possível obter o IP do Mac pela conexão SSH. Use --mac-ip.")
        mac_ip = self.args.mac_ip or info["connection"][0]
        address = ipaddress.ip_address(mac_ip)
        if address.version != 4:
            raise RuntimeError("Use --mac-ip com o IPv4 do Mac acessível pela Pi.")
        if self.mode == 2:
            check = shlex.join([python, "-c", "import socket,sys; socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=3).close()",
                                self.config["COMPETITION_HOST"], self.config["COMPETITION_MQTT_PORT"]])
            result = subprocess.run(self.ssh() + [check], input="", capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise RuntimeError("A Pi não alcança o broker do professor. Verifique a rede ou use o modo 1.")
        print(f"IP do Mac para o vídeo: {mac_ip}; IP da Pi: {info['connection'][2]}", flush=True)
        return mac_ip

    def ensure_running(self):
        for name, process in self.processes:
            if process.poll() is not None:
                raise RuntimeError(f"{name} encerrou (código {process.returncode}). Consulte {RUNTIME / (self.run_id + '-' + name + '.log')}")
        if self.remote is not None and self.remote.poll() is not None:
            raise RuntimeError("A sessão dos processos da Pi encerrou. " + " ".join(self.messages[-3:]))

    def start_local(self, name, command, environment, port):
        log = (RUNTIME / (self.run_id + "-" + name + ".log")).open("a")
        self.logs.append(log)
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((name, process))
        print(f"Mac: {name} iniciado (PID {process.pid}).", flush=True)
        if port:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                self.ensure_running()
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        return
                except OSError:
                    time.sleep(.1)
            raise RuntimeError(f"{name} não abriu a porta {port} a tempo.")

    def start_remote(self, commands, environment):
        python = self.args.pi_dir + "/apps/rover/.venv/bin/python"
        command = shlex.join([python, "-u", "-c", REMOTE_RUNNER])
        self.remote = subprocess.Popen(self.ssh() + [command], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, start_new_session=True)
        self.remote.stdin.write(json.dumps({"directory": self.args.pi_dir, "run_id": self.run_id,
                                           "commands": commands, "environment": environment}) + "\n")
        self.remote.stdin.flush()

        def read_messages():
            for line in self.remote.stdout:
                self.messages.append(line.strip())
                self.messages[:] = self.messages[-10:]
                try:
                    data = json.loads(line)
                except ValueError:
                    print("SSH: " + line.strip(), flush=True)
                    continue
                if data.get("ready"):
                    print("Pi: Rover, webcam e publicador WebRTC iniciados.", flush=True)
                    print("Logs na Pi: " + ", ".join(data["logs"]), flush=True)
                    self.remote_ready.set()
                if data.get("stopped"):
                    self.remote_stopped.set()

        threading.Thread(target=read_messages, daemon=True).start()
        deadline = time.monotonic() + 15
        while not self.remote_ready.wait(.1):
            self.ensure_running()
            if time.monotonic() >= deadline:
                raise RuntimeError("A Pi não confirmou a inicialização dos processos.")

    def close(self):
        print("\nEncerrando os processos iniciados por este programa…", flush=True)
        if self.remote is not None:
            if self.remote.stdin and not self.remote.stdin.closed:
                try:
                    self.remote.stdin.write("stop\n")
                    self.remote.stdin.flush()
                    self.remote.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
            try:
                self.remote.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.remote.terminate()
                try:
                    self.remote.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.remote.kill()
                    self.remote.wait()
            if not self.remote_stopped.wait(.5):
                print("Sem confirmação de encerramento da Pi. Se a rede caiu, confira os processos nela.", flush=True)
        for _, process in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 8
        for _, process in reversed(self.processes):
            try:
                process.wait(timeout=max(.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        for log in self.logs:
            log.close()
        if self.master:
            closed = False
            try:
                result = subprocess.run(self.ssh("-O", "exit"), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=3)
                closed = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
            if not closed and self.master_pid is not None:
                try:
                    os.kill(self.master_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        shutil.rmtree(self.socket_dir, ignore_errors=True)
        print("Processos do Mac encerrados.", flush=True)


def main():
    if not PYTHON.exists():
        raise SystemExit("Ambiente Python ausente: prepare .venv na raiz do projeto.")
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        os.execv(str(PYTHON), [str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
    from dotenv import load_dotenv
    from roboticrover_pi3.competition import Arena

    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("1", "2"), help="Pula o menu: 1 local, 2 professor")
    parser.add_argument("--pi", default=os.getenv("ROVER_SSH", "puc@puc.local"))
    parser.add_argument("--pi-dir", default="/home/puc/RoboticRover")
    parser.add_argument("--mac-ip", help="IPv4 do Mac; por padrão é obtido da sessão SSH")
    parser.add_argument("--dry-run", action="store_true", help="Exibe o plano sem iniciar processos ou SSH")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+", args.pi):
        parser.error("Use --pi usuario@IP ou usuario@hostname")
    if not args.pi_dir.startswith("/") or any(char in args.pi_dir for char in "\n\r\0"):
        parser.error("--pi-dir deve ser um caminho absoluto válido")
    mode = choose_mode(args.mode)
    arena = (Arena.from_env() if mode == 2 else
             Arena(os.getenv("COMPETITION_HOST") or "127.0.0.1", os.getenv("COMPETITION_TEAM") or "rover04",
                   os.getenv("COMPETITION_PASSWORD") or secrets.token_urlsafe(24)))
    config = {"COMPETITION_HOST": arena.host, "COMPETITION_TEAM": arena.team,
              "COMPETITION_PASSWORD": arena.password, "COMPETITION_MQTT_PORT": str(arena.port)}
    if args.dry_run:
        mac_ip = args.mac_ip or "IP_MAC_OBTIDO_PELO_SSH"
        local, remote = build_commands(mode, mac_ip, args.pi_dir, config)
        for name, command, _ in local:
            print("Mac / " + name + ": " + shlex.join(command))
        if mode == 1:
            print("SSH: túnel reverso 127.0.0.1:18883 → MQTT do Mac em 127.0.0.1:1883")
        for name, command in remote:
            print("Pi / " + name + ": " + shlex.join(command))
        print("Dashboard: WHEP em http://127.0.0.1:8890/rover/" + arena.team + "/whep")
        return
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / "inicia_comunicacao.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Já existe uma execução de inicia_comunicacao.py ativa.")
        for name in ("ssh", "node-red"):
            if not shutil.which(name):
                raise SystemExit(f"Comando necessário não encontrado: {name}")
        for file in (ROOT / ".venv/bin/mosquitto", ROOT / ".runtime/mediamtx-v1.21.4/mediamtx"):
            if not os.access(file, os.X_OK):
                raise SystemExit(f"Executável necessário não encontrado: {file}")
        for port, kind in ((1883, socket.SOCK_STREAM), (1880, socket.SOCK_STREAM),
                           (8890, socket.SOCK_STREAM), (8190, socket.SOCK_DGRAM)):
            port_free(port, kind)
        if mode == 2:
            for port in (arena.port, 8889):
                require_connection(arena.host, port)
        launcher = Launcher(args, mode, config)
        stopping = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(signum, lambda *_: stopping.set())
        try:
            launcher.connect()
            mac_ip = launcher.check_pi()
            if stopping.is_set():
                return
            local, remote = build_commands(mode, mac_ip, args.pi_dir, config)
            environment = dict(os.environ, **config, NODE_RED_HOST="127.0.0.1", PORT="1880",
                               MQTT_HOST="127.0.0.1", MQTT_PORT="1883", COMPETITION_LOCAL_MQTT_PORT="1883",
                               ROVER_CAMERA_PROTOCOL="whep", ROVER_CAMERA_HEALTH_URL="",
                               ROVER_CAMERA_URL=f"http://127.0.0.1:8890/rover/{arena.team}/whep",
                               COMPETITION_ARENA_URL=f"http://{arena.host}:8080/arena.html" if mode == 2 else "")
            for name, command, port in local:
                if stopping.is_set():
                    return
                launcher.start_local(name, command, environment, port)
            remote_environment = dict(config, MQTT_HOST="127.0.0.1", MQTT_PORT="18883", MQTT_CLIENT_ID="roboticrover-pi3",
                                      MQTT_USER="", MQTT_USERNAME="", MQTT_PASSWORD="", ENABLE_MOCK_TELEMETRY="false",
                                      COMPETITION_MOCK_BATTERY="0", COMPETITION_TELEMETRY_DIR=".runtime/competition")
            launcher.start_remote(remote, remote_environment)
            print("\nServiços iniciados. Dashboard: http://127.0.0.1:1880/dashboard", flush=True)
            print(f"Vídeo local: http://127.0.0.1:8890/rover/{arena.team}", flush=True)
            print(f"Logs do Mac: {RUNTIME}/{launcher.run_id}-*.log", flush=True)
            print("Pressione Ctrl+C para encerrar todos os processos desta execução.", flush=True)
            last_keepalive = time.monotonic()
            while not stopping.wait(.25):
                launcher.ensure_running()
                if time.monotonic() - last_keepalive >= 1:
                    launcher.remote.stdin.write("keepalive\n")
                    launcher.remote.stdin.flush()
                    last_keepalive = time.monotonic()
        finally:
            launcher.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print("Erro: " + str(exc), file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nInicialização cancelada.")
