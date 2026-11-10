import json
from pathlib import Path

import yaml

from rover.mqtt_client import POLICY

ROOT = Path(__file__).resolve().parents[1]


def test_compose_loopback_and_internal_address():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["mosquitto"]["ports"] == ["${MQTT_BIND_ADDRESS:-127.0.0.1}:${MQTT_PORT:-1883}:1883"]
    assert services["node-red"]["ports"] == ["127.0.0.1:${NODE_RED_PORT:-1880}:1880"]
    assert services["node-red"]["environment"]["MQTT_HOST"] == "${STATION_MQTT_HOST:-mosquitto}"
    assert services["node-red"]["environment"]["ROVER_FLOW_FILE"] == "/opt/rover/flows.json"
    assert "./apps/station/node-red/settings.js:/data/settings.js:ro" in services["node-red"]["volumes"]
    assert services["node-red"]["command"] == ["--settings", "/data/settings.js"]
    assert services["node-red-init"]["user"] == "0:0"
    assert services["node-red-init"]["restart"] == "no"
    assert services["node-red-init"]["network_mode"] == "none"
    assert services["node-red"]["depends_on"]["node-red-init"]["condition"] == "service_completed_successfully"


def test_flow_wiring_and_no_retained_commands():
    flow = json.loads((ROOT / "apps/station/node-red/flows.json").read_text(encoding="utf-8"))
    ids = {node["id"] for node in flow}
    assert len(ids) == len(flow)
    for node in flow:
        for output in node.get("wires", []):
            assert all(target in ids for target in output)
    tx = next(node for node in flow if node["type"] == "mqtt out")
    assert tx["retain"] == "false" and tx["qos"] == "1"
    assert next(node for node in flow if node["type"] == "mqtt-broker")["protocolVersion"] == "5"


def test_dashboard_nodes_and_html_sync():
    flow = json.loads((ROOT / "apps/station/node-red/flows.json").read_text(encoding="utf-8"))
    html = (ROOT / "apps/station/node-red/dashboard.html").read_text(encoding="utf-8")
    by_id = {node["id"]: node for node in flow}
    assert by_id["dashboard-http-in"]["url"] == "/dashboard"
    assert by_id["snapshot-http-in"]["url"] == "/api/rover/snapshot"
    assert by_id["cmd-http-in"]["url"] == "/api/rover/command"
    assert by_id["dashboard-ws-server"]["path"] == "/ws/rover"
    assert by_id["dashboard-ui-template"]["template"] == html
    assert "WebRTC (WHEP)" in html
    assert "MJPEG HTTP" in html
    assert "rover/telemetria" in html


def test_retained_policy():
    assert {topic for topic, (_, retain) in POLICY.items() if retain} == {"rover/status", "rover/estado"}
    assert POLICY["rover/telemetria"][0] == 0
    assert POLICY["rover/cmd/ack"] == (1, False)
