from pathlib import Path

import yaml

PROTOCOL_DIR = Path(__file__).parents[2] / "packages" / "protocol"


def load_yaml(filename: str) -> dict[str, object]:
    with (PROTOCOL_DIR / filename).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def test_openapi_declares_versioned_health_contract() -> None:
    document = load_yaml("openapi.yaml")

    assert document["openapi"] == "3.1.0"
    assert "/system/health" in document["paths"]


def test_asyncapi_declares_partner_wss_server() -> None:
    document = load_yaml("asyncapi.yaml")

    assert document["asyncapi"] == "3.0.0"
    assert document["servers"]["partner"]["protocol"] == "wss"
