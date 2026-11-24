import json
import os
import select
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

import inicia_comunicacao as launcher
from roboticrover_pi3.competition import Arena
from roboticrover_pi3.competition_forward import configuration


CONFIG = {"COMPETITION_HOST": "192.168.50.3", "COMPETITION_TEAM": "rover04",
          "COMPETITION_PASSWORD": "test-only", "COMPETITION_MQTT_PORT": "1883"}


def test_menu_reprompts_until_choice_is_valid(monkeypatch):
    values = iter(["", "3", " 2 "])
    monkeypatch.setattr("builtins.input", lambda _: next(values))
    assert launcher.choose_mode() == 2


def test_local_mode_uses_reverse_tunnel_client_and_disables_arena_forwarding():
    local, remote = launcher.build_commands(1, "192.168.1.36", "/home/puc/RoboticRover", CONFIG)
    assert [name for name, *_ in local] == ["mqtt", "video", "dashboard"]
    assert "--local-only" in local[1][1]
    assert remote[0][1][-1] == "roboticrover_pi3"
    assert remote[-1][1][-1] == "http://192.168.1.36:8890/rover/rover04/whip"
    config = configuration(Arena("192.168.50.3", "rover04", "test-only"), "192.168.1.36", forward=False)
    assert config["paths"]["rover/rover04"]["forward"] == []


def test_competition_mode_selects_official_client_and_mqtt_bridge():
    local, remote = launcher.build_commands(2, "192.168.50.130", "/home/puc/Robotic Rover", CONFIG)
    assert [name for name, *_ in local] == ["mqtt", "video", "dashboard", "ponte-mqtt"]
    assert "--local-only" not in local[1][1]
    assert remote[0][1] == ["/home/puc/Robotic Rover/apps/rover/.venv/bin/python", "-m", "roboticrover_pi3.competition_rover"]
    assert CONFIG["COMPETITION_PASSWORD"] not in str(local + remote)


def await_line(process, timeout=5):
    assert select.select([process.stdout], [], [], timeout)[0], "Supervisor não respondeu"
    return json.loads(process.stdout.readline())


def runner(tmp_path, commands):
    process = subprocess.Popen([sys.executable, "-u", "-c", launcher.REMOTE_RUNNER], text=True,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write(json.dumps({"directory": str(tmp_path), "commands": commands,
                                   "environment": {}, "run_id": "test"}) + "\n")
    process.stdin.flush()
    return process


def assert_dead(pid):
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_remote_runner_cleans_up_children_on_connection_eof(tmp_path):
    process = runner(tmp_path, [["camera", [sys.executable, "-c", "import time; time.sleep(60)"]],
                                ["publisher", [sys.executable, "-c", "import time; time.sleep(60)"]]])
    try:
        ready = await_line(process)
        assert ready["ready"]
        process.stdin.close()
        assert process.wait(timeout=5) == 0
        for pid in ready["pids"].values():
            assert_dead(pid)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=12)


def test_remote_runner_rolls_back_when_a_service_exits(tmp_path):
    process = runner(tmp_path, [["rover", [sys.executable, "-c", "import time; time.sleep(60)"]],
                               ["publisher", [sys.executable, "-c", "raise SystemExit(3)"]]])
    try:
        ready = await_line(process)
        assert ready["ready"]
        assert process.wait(timeout=5) == 1
        for pid in ready["pids"].values():
            assert_dead(pid)
    finally:
        process.stdin.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=12)


def test_remote_runner_stops_children_on_sigterm(tmp_path):
    process = runner(tmp_path, [["camera", [sys.executable, "-c", "import time; time.sleep(60)"]]])
    try:
        ready = await_line(process)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        for pid in ready["pids"].values():
            assert_dead(pid)
    finally:
        process.stdin.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def test_remote_runner_stops_children_when_parent_stops_renewing_lease(tmp_path):
    process = runner(tmp_path, [["rover", [sys.executable, "-c", "import time; time.sleep(60)"]]])
    try:
        ready = await_line(process)
        assert process.wait(timeout=13) == 1
        for pid in ready["pids"].values():
            assert_dead(pid)
    finally:
        process.stdin.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=12)


def test_close_stops_owned_local_process_and_preserves_others():
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    instance = launcher.Launcher(SimpleNamespace(pi="puc@test"), 1, CONFIG)
    try:
        owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        instance.processes.append(("owned", owned))
        instance.close()
        assert owned.poll() is not None
        assert unrelated.poll() is None
        assert not instance.socket_dir.exists()
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


@pytest.mark.parametrize("mode", ["1", "2"])
def test_dry_run_does_not_launch_services(mode):
    result = subprocess.run([str(launcher.PYTHON), str(launcher.ROOT / "inicia_comunicacao.py"),
                             "--mode", mode, "--dry-run", "--mac-ip", "192.168.1.36"],
                            capture_output=True, text=True, timeout=5,
                            env=dict(os.environ, **CONFIG))
    assert result.returncode == 0, result.stderr
    assert "Pi / camera:" in result.stdout
    assert "Dashboard: WHEP" in result.stdout
    assert CONFIG["COMPETITION_PASSWORD"] not in result.stdout + result.stderr
