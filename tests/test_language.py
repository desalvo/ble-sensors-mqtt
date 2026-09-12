from pathlib import Path

from ble_sensors_mqtt.cli import parser

ROOT = Path(__file__).resolve().parents[1]


def test_documentation_has_explicit_english_and_italian_pairs():
    pairs = (
        ("README.en.md", "README.it.md"),
        ("SECURITY.en.md", "SECURITY.it.md"),
        ("CHANGELOG.en.md", "CHANGELOG.it.md"),
        ("docs/USAGE.en.md", "docs/USAGE.it.md"),
        ("docs/AGID-SECURITY.en.md", "docs/AGID-SECURITY.it.md"),
        ("docs/PRODUCTION.en.md", "docs/PRODUCTION.it.md"),
        ("docs/ble-sensors-mqtt-manual-v1.0.0-en.pdf", "docs/ble-sensors-mqtt-manual-v1.0.0-it.pdf"),
    )
    for english, italian in pairs:
        assert (ROOT / english).is_file()
        assert (ROOT / italian).is_file()


def test_root_readme_is_language_selector_only():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "README.en.md" in text
    assert "README.it.md" in text
    assert len(text.splitlines()) <= 8
    assert "## Installation" not in text
    assert "## Installazione" not in text


def test_cli_help_is_english():
    help_text = parser().format_help().lower()
    for italian_term in ("sensore", "dispositivo", "obbligatorio", "ripetibile", "espone"):
        assert italian_term not in help_text
