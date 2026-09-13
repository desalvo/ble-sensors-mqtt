from pathlib import Path

from ble_sensors_mqtt.auth import AuthStore, generate_totp_secret, totp, verify_totp


def test_bootstrap_admin_requires_password_change(tmp_path: Path):
    store = AuthStore(tmp_path / "users.sqlite3")
    user = store.authenticate_local("admin", "password")
    assert user is not None
    assert user.role == "admin"
    assert user.must_change_password
    store.close()


def test_totp_round_trip():
    secret = generate_totp_secret()
    code = totp(secret)
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000") or code == "000000"


def test_mfa_secret_can_be_exported_and_reimported(tmp_path: Path):
    first = AuthStore(tmp_path / "a.sqlite3")
    first.create_user("reader1", "reader", password="longpassword", auth_source="local")
    secret = first.ensure_mfa_secret("reader1")
    first.set_mfa("reader1", True, secret=secret)
    rows = first.export_rows()
    second = AuthStore(tmp_path / "b.sqlite3")
    second.import_rows(rows)
    restored = second.get("reader1")
    assert restored and restored.mfa_enabled and restored.mfa_secret == secret
    first.close()
    second.close()


def test_external_identity_cannot_take_over_local_username(tmp_path: Path):
    store = AuthStore(tmp_path / "users.sqlite3")
    try:
        try:
            store.upsert_external("admin", "oidc")
        except ValueError:
            pass
        else:
            raise AssertionError("OIDC must not auto-link to the local admin account")
    finally:
        store.close()
