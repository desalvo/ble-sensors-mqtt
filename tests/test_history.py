from datetime import UTC, datetime, timedelta
from pathlib import Path

from ble_sensors_mqtt.history import HistoryStore


def payload(value: float, *, stale: bool = False) -> dict:
    return {
        "name": "Office",
        "manufacturer": "Example",
        "model": "T1",
        "protocol": "BLE",
        "observed_at": datetime.now(UTC).isoformat(),
        "stale": stale,
        "data": {"environment": {"temperature": value}, "humidity": 47},
    }


def test_history_deduplicates_consecutive_equal_values_and_stale(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite3", 30)
    try:
        store.append_snapshot({"AA": payload(21.5)})
        store.append_snapshot({"AA": payload(21.5)})
        store.append_snapshot({"AA": payload(21.5, stale=True)})
        store.append_snapshot({"AA": payload(22.0, stale=True)})
        rows = store.query(["AA"])
        assert len(rows) == 3
        assert rows[0]["values"][0]["path"] == "environment.temperature"
        assert rows[1]["stale"] is True
        assert len(store.query(["AA"], deduplicate=False)) == 4
    finally:
        store.close()


def test_history_delete_selected_interval_or_all(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite3", 30)
    try:
        store.append_snapshot({"AA": payload(20.0), "BB": payload(30.0)})
        assert store.delete(["AA"]) == 1
        assert store.query(["AA"], deduplicate=False) == []
        assert len(store.query(["BB"], deduplicate=False)) == 1
    finally:
        store.close()


def test_history_retention_purges_old_samples(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.sqlite3", 30)
    try:
        store.append_snapshot({"AA": payload(20.0)})
        old = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        store._conn.execute("UPDATE samples SET recorded_at = ?", (old,))
        store._conn.commit()
        store.purge_expired(force=True)
        assert store.query(["AA"], deduplicate=False) == []
    finally:
        store.close()
