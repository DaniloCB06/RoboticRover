import pytest

from rover.config import Config


@pytest.mark.parametrize("name,value", [("MQTT_PORT", "0"), ("MQTT_PORT", "65536"),
                                      ("MQTT_KEEPALIVE", "0"), ("MQTT_CLIENT_ID", ""),
                                      ("TELEMETRY_INTERVAL", "nan"), ("HEARTBEAT_TIMEOUT", "inf"),
                                      ("HEARTBEAT_TIMEOUT", "-1"), ("LOG_LEVEL", "verbose")])
def test_invalid_environment_rejected(monkeypatch, tmp_path, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Config.from_env(tmp_path / "absent.env")


def test_explicit_env_file_and_environment_precedence(monkeypatch, tmp_path):
    path = tmp_path / "test.env"
    path.write_text("MQTT_HOST=localhost\nMQTT_PORT=1884\n", encoding="utf-8")
    monkeypatch.setenv("MQTT_HOST", "original")
    monkeypatch.delenv("MQTT_HOST")
    monkeypatch.setenv("MQTT_PORT", "1885")
    # O par setenv/delenv garante limpeza inclusive se from_env inserir a chave.
    config = Config.from_env(path)
    assert config.host == "localhost" and config.port == 1885
