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


def test_history_template_prefers_sensor_name_and_strips_data_prefix():
    from pathlib import Path

    template = Path('src/ble_sensors_mqtt/web_templates/history.html').read_text(encoding='utf-8')
    assert "return name && name !== sensorId ? name : sensorId;" in template
    assert "text.startsWith('data.') ? text.slice(5) : text" in template
    assert "value.path[5:] if value.path.startswith('data.') else value.path" in template


def test_history_template_has_hover_tooltip():
    template = Path("src/ble_sensors_mqtt/web_templates/history.html").read_text(encoding="utf-8")
    assert "history-chart-tooltip" in template
    assert "mousemove" in template
    assert "sameTime" in template
    assert "stale" in template


def test_history_template_persists_browser_preferences_in_cookie():
    template = Path("src/ble_sensors_mqtt/web_templates/history.html").read_text(encoding="utf-8")
    assert "ble_sensors_mqtt_history_prefs" in template
    assert "Max-Age=${HISTORY_PREFS_MAX_AGE}" in template
    assert "SameSite=Lax" in template
    assert "filterForm.addEventListener('submit'" in template
    assert "control.addEventListener('change'" in template
    assert "checklist.addEventListener('change'" in template
    assert "clearHistoryPrefs()" in template
    assert "window.location.replace" in template


def test_history_template_has_retention_aware_quick_ranges():
    template = Path("src/ble_sensors_mqtt/web_templates/history.html").read_text(encoding="utf-8")
    assert 'data-history-range' in template
    assert 'data-minutes' in template
    assert 'formatLocalDateTime' in template
    assert 'filterForm.requestSubmit()' in template
    assert 'quickRange' in template
    assert 'type="datetime-local"' in template


def test_history_frontend_filters_quick_ranges_by_retention():
    frontend = Path("src/ble_sensors_mqtt/frontend.py").read_text(encoding="utf-8")
    assert '"30m", "label": "30m"' in frontend
    assert '"1y", "label": "1 year"' in frontend
    assert 'item["minutes"] <= retention_days * 1440' in frontend


def test_history_template_groups_series_into_paginated_checkbox_charts():
    template = Path("src/ble_sensors_mqtt/web_templates/history.html").read_text(encoding="utf-8")
    assert 'id="series-checklist"' in template
    assert "input.type = 'checkbox'" in template
    assert 'id="graphs-per-page"' in template
    assert '<option value="10">10</option>' in template
    assert '<option value="20">20</option>' in template
    assert '<option value="50">50</option>' in template
    assert "title:'Temperature in °C'" in template
    assert "title:'Temperature in °F'" in template
    assert "title:'Battery level'" in template
    assert 'groupedSelectedSeries' in template
    assert 'renderPagination' in template
    assert 'graphsPerPage' in template
    assert 'graphPage' in template
    assert 'data-history-value' in template


def test_history_graphs_support_zero_axis_percent_ceiling_and_smoothing():
    template = Path("src/ble_sensors_mqtt/web_templates/history.html").read_text(encoding="utf-8")
    assert 'id="graph-zero-min"' in template
    assert "graphZeroMin" in template
    assert "if (percentScale) maxV = 100" in template
    assert "ctx.bezierCurveTo" in template


def test_base_template_has_mobile_navigation_drawer():
    template = Path("src/ble_sensors_mqtt/web_templates/base.html").read_text(encoding="utf-8")
    assert 'id="mobile-menu-toggle"' in template
    assert 'id="mobile-navigation"' in template
    assert 'id="mobile-nav-overlay"' in template
    assert "mobile-nav-open" in template
