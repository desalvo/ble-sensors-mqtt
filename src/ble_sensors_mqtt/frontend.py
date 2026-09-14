"""Optional authenticated web frontend for sensor status and runtime administration."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import tomllib
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from .auth import AuthStore, User, otpauth_uri, verify_totp
from .backup import create_backup, extract_backup
from .config import (
    atomic_write_config,
    deep_merge,
    default_config,
    default_frontend_data_dir,
    dump_config,
    load_config,
)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _frontend_data_dir(args: Any) -> Path:
    if getattr(args, "frontend_data_dir", None):
        return Path(args.frontend_data_dir)
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ble-sensors-mqtt" / "frontend"
    if __import__("sys").platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ble-sensors-mqtt" / "frontend"
    return default_frontend_data_dir()


def _secret_key(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    path.write_text(value + "\n", encoding="utf-8")
    if os.name == "posix":
        os.chmod(path, 0o600)
    return value


def _ldap_auth(config: dict[str, Any], username: str, password: str) -> bool:
    if not config.get("enabled"):
        return False
    try:
        import ldap3
    except ImportError as exc:
        raise RuntimeError("LDAP support requires the web optional dependencies") from exc
    from urllib.parse import urlparse

    parsed = urlparse(str(config.get("uri", "")))
    host = parsed.hostname or str(config.get("uri", ""))
    use_ssl = parsed.scheme.lower() == "ldaps"
    port = parsed.port or (636 if use_ssl else 389)
    server = ldap3.Server(host, port=port, use_ssl=use_ssl, get_info=ldap3.NONE)
    start_tls = bool(config.get("start_tls")) and not use_ssl

    def bind(user: str | None, secret: str | None) -> Any:
        conn = ldap3.Connection(server, user=user or None, password=secret or None, auto_bind=False)
        if not conn.open():
            raise RuntimeError("LDAP connection failed")
        if start_tls and not conn.start_tls():
            conn.unbind()
            raise RuntimeError("LDAP StartTLS failed")
        if not conn.bind():
            conn.unbind()
            return None
        return conn

    template = str(config.get("user_dn_template", "")).strip()
    if template:
        conn = bind(template.format(username=username), password)
        if not conn:
            return False
        conn.unbind()
        return True

    bind_dn = str(config.get("bind_dn", "")).strip()
    bind_password = ""  # nosec B105 - initialized empty, loaded from file when configured
    bind_file = str(config.get("bind_password_file", "")).strip()
    if bind_file:
        bind_password = Path(bind_file).read_text(encoding="utf-8").strip()
    search = bind(bind_dn or None, bind_password or None)
    if not search:
        return False
    try:
        flt = str(config.get("user_filter", "(uid={username})")).format(
            username=ldap3.utils.conv.escape_filter_chars(username)
        )
        if not search.search(str(config.get("base_dn", "")), flt, attributes=[]):
            return False
        entries = search.entries
        if len(entries) != 1:
            return False
        dn = entries[0].entry_dn
    finally:
        search.unbind()
    conn = bind(dn, password)
    if not conn:
        return False
    conn.unbind()
    return True



def _get_nested(config: dict[str, Any], dotted: str) -> Any:
    current: Any = config
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_nested(config: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    current = config
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _collect_secret_references(config: dict[str, Any]) -> dict[str, Path]:
    references: dict[str, Path] = {}
    for dotted in (
        "mqtt.password_file", "mqtt.ca_file", "snmp.community_file",
        "frontend.tls_cert", "frontend.tls_key", "frontend.ldap.bind_password_file",
        "frontend.oidc.client_secret_file",
    ):
        value = _get_nested(config, dotted)
        if value:
            path = Path(str(value)).expanduser()
            if path.exists() and path.is_file() and not path.is_symlink():
                references[f"app:{dotted}"] = path
    cloud_file = _get_nested(config, "cloud.config_file")
    if cloud_file:
        path = Path(str(cloud_file)).expanduser()
        if path.exists() and path.is_file() and not path.is_symlink():
            try:
                cloud = tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cloud = {}
            def walk(prefix: str, value: Any) -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        name = f"{prefix}.{key}" if prefix else str(key)
                        if str(key).endswith("_file") and isinstance(child, str) and child:
                            candidate = Path(child).expanduser()
                            if candidate.exists() and candidate.is_file() and not candidate.is_symlink():
                                references[f"cloud:{name}"] = candidate
                        else:
                            walk(name, child)
            walk("", cloud)
    return references


class FrontendServer:
    def __init__(self, server: Any, thread: threading.Thread, auth: AuthStore):
        self.server, self.thread, self.auth = server, thread, auth

    def shutdown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.auth.close()


def start_frontend(
    store: Any, args: Any, config_path: Path, cache: Any | None = None, history: Any | None = None
) -> FrontendServer:
    try:
        from flask import (
            Flask,
            abort,
            flash,
            jsonify,
            redirect,
            render_template,
            request,
            send_file,
            session,
            url_for,
        )
        from werkzeug.serving import make_server
    except ImportError as exc:
        raise RuntimeError("frontend requires the optional dependency profile .[web]") from exc

    package_dir = Path(__file__).resolve().parent
    app = Flask(__name__, template_folder=str(package_dir / "web_templates"), static_folder=str(package_dir / "web_static"))
    data_dir = _frontend_data_dir(args)
    data_dir.mkdir(parents=True, exist_ok=True)
    app.secret_key = _secret_key(data_dir / "session-secret")
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    auth = AuthStore(data_dir / "users.sqlite3")
    runtime_config_path = data_dir / "runtime-config.toml"

    def cfg() -> dict[str, Any]:
        current = deep_merge(default_config(), load_config(config_path))
        if runtime_config_path.exists():
            current = deep_merge(current, load_config(runtime_config_path, required=True))
        return current

    def persist(current: dict[str, Any]) -> None:
        atomic_write_config(runtime_config_path, current)

    def current_user() -> User | None:
        username = session.get("username")
        return auth.get(username) if username else None

    def csrf() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    @app.context_processor
    def inject() -> dict[str, Any]:
        return {"current_user": current_user(), "csrf_token": csrf(), "app_version": getattr(args, "version", "1.0.0")}

    @app.before_request
    def csrf_check() -> None:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not supplied or not secrets.compare_digest(supplied, session.get("csrf", "")):
                abort(400, "CSRF validation failed")

    def login_required(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapped(*a: Any, **kw: Any) -> Any:
            user = current_user()
            if not user or not user.active:
                return redirect(url_for("login", next=request.path))
            if user.must_change_password and request.endpoint not in {"change_password", "logout", "static"}:
                return redirect(url_for("change_password"))
            return fn(*a, **kw)
        return wrapped

    def admin_required(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        @login_required
        def wrapped(*a: Any, **kw: Any) -> Any:
            if current_user().role != "admin":  # type: ignore[union-attr]
                abort(403)
            return fn(*a, **kw)
        return wrapped

    def finish_login(user: User) -> Any:
        if user.mfa_enabled:
            session["pending_mfa"] = user.username
            return redirect(url_for("mfa"))
        session["username"] = user.username
        session.pop("pending_mfa", None)
        auth.audit(user.username, "login", user.auth_source)
        return redirect(url_for("dashboard"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            source = request.form.get("source", "local")
            user = None
            if source == "ldap":
                ldap_cfg = cfg().get("frontend", {}).get("ldap", {})
                if _ldap_auth(ldap_cfg, username, password):
                    try:
                        user = auth.upsert_external(
                            username, "ldap", default_role=str(ldap_cfg.get("default_role", "reader"))
                        )
                    except ValueError:
                        user = None
            else:
                user = auth.authenticate_local(username, password)
            if user and user.active:
                return finish_login(user)
            auth.audit(username or None, "login_failed", source)
            flash("Invalid credentials", "error")
        oidc_enabled = bool(cfg().get("frontend", {}).get("oidc", {}).get("enabled"))
        ldap_enabled = bool(cfg().get("frontend", {}).get("ldap", {}).get("enabled"))
        return render_template("login.html", oidc_enabled=oidc_enabled, ldap_enabled=ldap_enabled)

    @app.route("/sso/login")
    def oidc_login() -> Any:
        oidc_cfg = cfg().get("frontend", {}).get("oidc", {})
        if not oidc_cfg.get("enabled"):
            abort(404)
        try:
            from authlib.integrations.flask_client import OAuth
        except ImportError as exc:
            raise RuntimeError("OIDC requires Authlib") from exc
        secret_file = str(oidc_cfg.get("client_secret_file", ""))
        client_secret = Path(secret_file).read_text(encoding="utf-8").strip() if secret_file else ""
        oauth = OAuth(app)
        client = oauth.register(
            name="ble_sensors_oidc",
            client_id=str(oidc_cfg.get("client_id", "")), client_secret=client_secret,
            server_metadata_url=str(oidc_cfg.get("metadata_url", "")),
            client_kwargs={"scope": str(oidc_cfg.get("scopes", "openid profile email"))},
        )
        return client.authorize_redirect(url_for("oidc_callback", _external=True))

    @app.route("/sso/callback")
    def oidc_callback() -> Any:
        oidc_cfg = cfg().get("frontend", {}).get("oidc", {})
        from authlib.integrations.flask_client import OAuth
        secret_file = str(oidc_cfg.get("client_secret_file", ""))
        oauth = OAuth(app)
        client = oauth.register(name="ble_sensors_oidc", client_id=str(oidc_cfg.get("client_id", "")), client_secret=Path(secret_file).read_text(encoding="utf-8").strip() if secret_file else "", server_metadata_url=str(oidc_cfg.get("metadata_url", "")), client_kwargs={"scope": str(oidc_cfg.get("scopes", "openid profile email"))})
        token = client.authorize_access_token()
        info = token.get("userinfo") or client.userinfo(token=token)
        claim = str(oidc_cfg.get("username_claim", "preferred_username"))
        username = str(info.get(claim) or info.get("email") or info.get("sub") or "")
        if not username:
            abort(403)
        try:
            user = auth.upsert_external(
                username, "oidc", default_role=str(oidc_cfg.get("default_role", "reader")),
                email=info.get("email"),
            )
        except ValueError:
            abort(403, "SSO username conflicts with an account owned by another authentication source")
        return finish_login(user)

    @app.route("/mfa", methods=["GET", "POST"])
    def mfa() -> Any:
        username = session.get("pending_mfa")
        user = auth.get(username) if username else None
        if not user or not user.mfa_secret:
            return redirect(url_for("login"))
        if request.method == "POST" and verify_totp(user.mfa_secret, request.form.get("code", "")):
            session["username"] = user.username
            session.pop("pending_mfa", None)
            auth.audit(user.username, "login_mfa", user.auth_source)
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            flash("Invalid MFA code", "error")
        return render_template("mfa.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout() -> Any:
        auth.audit(current_user().username, "logout")  # type: ignore[union-attr]
        session.clear()
        return redirect(url_for("login"))

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password() -> Any:
        user = current_user()
        if user.auth_source != "local":
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            if not auth.authenticate_local(user.username, request.form.get("current_password", "")):
                flash("Current password is incorrect", "error")
            elif request.form.get("new_password") != request.form.get("confirm_password"):
                flash("Passwords do not match", "error")
            else:
                try:
                    auth.set_password(user.username, request.form.get("new_password", ""), must_change=False)
                    auth.audit(user.username, "password_changed")
                    flash("Password changed", "success")
                    return redirect(url_for("dashboard"))
                except ValueError as exc:
                    flash(str(exc), "error")
        return render_template("change_password.html")

    @app.route("/")
    @login_required
    def dashboard() -> Any:
        return render_template("dashboard.html", sensors=store.snapshot(), health=store.health())

    @app.route("/api/sensors")
    @login_required
    def api_sensors() -> Any:
        return jsonify({"sensors": store.snapshot(), "health": store.health()})

    def _history_range(value: str | None, *, end: bool = False) -> str | None:
        if not value:
            return None
        from datetime import UTC, datetime
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid history date/time") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        parsed = parsed.astimezone(UTC)
        if end and len(text) <= 10:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed.isoformat()

    @app.route("/history")
    @login_required
    def history_view() -> Any:
        available = history.sensors() if history is not None else []
        selected = request.args.getlist("sensor")
        if not selected and available:
            selected = [str(available[0]["sensor_id"])]
        try:
            start = _history_range(request.args.get("start"))
            end = _history_range(request.args.get("end"), end=True)
        except ValueError as exc:
            flash(str(exc), "error")
            start = end = None
        deduplicate = request.args.get("duplicates") != "1"
        retention_days = int(getattr(args, "history_retention_days", 30))
        presets = [
            {"key": "30m", "label": "30m", "minutes": 30},
            {"key": "1h", "label": "1h", "minutes": 60},
            {"key": "3h", "label": "3h", "minutes": 180},
            {"key": "6h", "label": "6h", "minutes": 360},
            {"key": "12h", "label": "12h", "minutes": 720},
            {"key": "24h", "label": "24h", "minutes": 1440},
            {"key": "1w", "label": "1 week", "minutes": 7 * 1440},
            {"key": "2w", "label": "2 weeks", "minutes": 14 * 1440},
            {"key": "1mo", "label": "1 month", "minutes": 30 * 1440},
            {"key": "3mo", "label": "3 months", "minutes": 90 * 1440},
            {"key": "6mo", "label": "6 months", "minutes": 180 * 1440},
            {"key": "1y", "label": "1 year", "minutes": 365 * 1440},
        ]
        quick_ranges = [item for item in presets if item["minutes"] <= retention_days * 1440]
        rows = history.query(selected, start, end, deduplicate=deduplicate) if history is not None else []
        return render_template(
            "history.html",
            available=available, selected=selected, rows=rows,
            start=request.args.get("start", ""), end=request.args.get("end", ""),
            deduplicate=deduplicate, retention_days=retention_days,
            quick_ranges=quick_ranges, quick_range=request.args.get("range", ""),
        )

    @app.route("/api/history")
    @login_required
    def api_history() -> Any:
        if history is None:
            return jsonify({"sensors": [], "rows": []})
        selected = request.args.getlist("sensor")
        try:
            start = _history_range(request.args.get("start"))
            end = _history_range(request.args.get("end"), end=True)
        except ValueError as exc:
            abort(400, str(exc))
        deduplicate = request.args.get("duplicates") != "1"
        return jsonify({
            "sensors": history.sensors(),
            "rows": history.query(selected, start, end, deduplicate=deduplicate),
        })

    @app.route("/history/delete", methods=["POST"])
    @admin_required
    def history_delete() -> Any:
        if history is None:
            abort(404)
        selected = request.form.getlist("sensor")
        if not selected:
            flash("Select at least one sensor", "error")
            return redirect(url_for("history_view"))
        try:
            start = _history_range(request.form.get("start"))
            end = _history_range(request.form.get("end"), end=True)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("history_view"))
        deleted = history.delete(selected, start, end)
        auth.audit(current_user().username, "history_deleted", f"{deleted} samples")  # type: ignore[union-attr]
        flash(f"Deleted {deleted} historical samples", "success")
        return redirect(url_for("history_view"))

    @app.route("/settings", methods=["GET", "POST"])
    @admin_required
    def settings() -> Any:
        current = cfg()
        restart_required = False
        if request.method == "POST":
            section = request.form.get("section", "runtime")
            if section not in current or not isinstance(current[section], dict):
                abort(400)
            # Bounded generic editor for existing scalar keys only.
            for key in list(current[section]):
                if isinstance(current[section][key], dict) or key not in request.form:
                    continue
                raw = request.form.get(key, "")
                old = current[section][key]
                if isinstance(old, bool):
                    value: Any = raw.lower() in {"1", "true", "yes", "on"}
                elif isinstance(old, int):
                    value = int(raw)
                elif isinstance(old, float):
                    value = float(raw)
                elif isinstance(old, list):
                    value = [item.strip() for item in raw.splitlines() if item.strip()]
                else:
                    value = raw
                current[section][key] = value
            persist(current)
            # Apply safe live values immediately to the active namespace.
            live = {
                ("bluetooth", "adapter"): "bluetooth_adapter",
                ("bluetooth", "scan_duration"): "scan_duration", ("bluetooth", "poll_interval"): "poll_interval",
                ("bluetooth", "plugin_timeout"): "plugin_timeout", ("runtime", "reuse_stale_data"): "reuse_stale_data",
                ("runtime", "state_file"): "state_file", ("runtime", "log_level"): "log_level",
                ("history", "retention_days"): "history_retention_days",
                ("mqtt", "retain"): "retain", ("mqtt", "qos"): "qos", ("mqtt", "stale_cycles"): "stale_cycles",
                ("mqtt", "home_assistant_discovery"): "home_assistant_discovery",
                ("mqtt", "home_assistant_discovery_prefix"): "home_assistant_discovery_prefix",
                ("cloud", "config_file"): "cloud_config",
            }
            for (sec, key), attr in live.items():
                if section == sec and key in current[sec]:
                    value = current[sec][key]
                    if attr in {"state_file", "cloud_config"}:
                        value = Path(str(value)).expanduser() if value else None
                    setattr(args, attr, value)
            if section == "bluetooth":
                from .cli import device_name as parse_device_name
                from .cli import sensor_identifier
                from .cli import sensor_name as parse_sensor_name
                args.plugin = list(current[section].get("plugins", []))
                args.device = [sensor_identifier(str(v)) for v in current[section].get("devices", [])]
                args.device_name = [parse_device_name(str(v)) for v in current[section].get("device_names", [])]
                args.sensor_name = [parse_sensor_name(str(v)) for v in current[section].get("sensor_names", [])]
            if section == "history" and history is not None:
                history.set_retention_days(int(current[section].get("retention_days", 30)))
                history.purge_expired(force=True)
            if section == "runtime" and "log_level" in current[section]:
                import logging
                logging.getLogger().setLevel(str(current[section]["log_level"]))
            restart_required = section in {"mqtt", "prometheus", "snmp", "frontend", "mqtt_cache"} or (section == "history" and "path" in request.form)
            auth.audit(current_user().username, "configuration_changed", section)  # type: ignore[union-attr]
            flash("Configuration saved" + ("; restart required for this section" if restart_required else "; applied live"), "success")
            current = cfg()
        return render_template("settings.html", config=current, restart_required=restart_required)


    @app.route("/authentication", methods=["GET", "POST"])
    @admin_required
    def authentication_settings() -> Any:
        current = cfg()
        frontend_cfg = current.setdefault("frontend", {})
        if request.method == "POST":
            provider = request.form.get("provider")
            if provider not in {"ldap", "oidc"}:
                abort(400)
            table = frontend_cfg.setdefault(provider, {})
            for key, old in list(table.items()):
                if key not in request.form:
                    continue
                raw = request.form.get(key, "")
                table[key] = raw.lower() in {"true", "1", "on", "yes"} if isinstance(old, bool) else raw
            persist(current)
            auth.audit(current_user().username, "authentication_changed", provider)  # type: ignore[union-attr]
            flash("Authentication settings saved; restart the service to apply provider changes", "success")
            current = cfg()
        return render_template("authentication.html", frontend=current.get("frontend", {}))

    @app.route("/users", methods=["GET", "POST"])
    @admin_required
    def users() -> Any:
        if request.method == "POST":
            action = request.form.get("action")
            username = request.form.get("username", "").strip()
            try:
                if action == "create":
                    auth.create_user(username, request.form.get("role", "reader"), auth_source=request.form.get("auth_source", "local"), password=request.form.get("password") or None, must_change=True)
                elif action == "update":
                    auth.update_user(username, role=request.form.get("role"), active=request.form.get("active") == "on")
                elif action == "reset":
                    auth.set_password(username, request.form.get("password", "password"), must_change=True)
                elif action == "delete":
                    auth.delete_user(username)
                auth.audit(current_user().username, f"user_{action}", username)  # type: ignore[union-attr]
                flash("User updated", "success")
            except (ValueError, KeyError) as exc:
                flash(str(exc), "error")
        return render_template("users.html", users=auth.list_users())

    @app.route("/users/<username>/mfa", methods=["GET", "POST"])
    @admin_required
    def user_mfa(username: str) -> Any:
        user = auth.get(username)
        if not user or user.auth_source not in {"local", "ldap"}:
            abort(404)
        secret = auth.ensure_mfa_secret(username)
        if request.method == "POST":
            action = request.form.get("action")
            auth.set_mfa(username, action == "enable", secret=secret)
            auth.audit(current_user().username, f"mfa_{action}", username)  # type: ignore[union-attr]
            flash("MFA updated", "success")
            user = auth.get(username)
        return render_template("user_mfa.html", user=user, secret=secret, uri=otpauth_uri(secret, username))

    @app.route("/backup", methods=["GET", "POST"])
    @admin_required
    def backup() -> Any:
        if request.method == "POST":
            action = request.form.get("action")
            password = request.form.get("password", "")
            if action == "export":
                export_dir = data_dir / "exports"
                export_dir.mkdir(exist_ok=True)
                target = export_dir / f"ble-sensors-mqtt-{int(__import__('time').time())}.bsmqbackup"
                cache_snapshot = None
                with tempfile.TemporaryDirectory(prefix="bsmq-cache-export-") as cache_temp:
                    if cache is not None:
                        cache_snapshot = Path(cache_temp) / "mqtt-cache.sqlite3"
                        cache.snapshot_to(cache_snapshot)
                    history_snapshot = None
                    if history is not None:
                        history_snapshot = Path(cache_temp) / "history.sqlite3"
                        history.snapshot_to(history_snapshot)
                    files = {
                        "mqtt-cache.sqlite3": cache_snapshot,
                        "history.sqlite3": history_snapshot,
                        "state.json": getattr(args, "state_file", None),
                        "cloud.toml": getattr(args, "cloud_config", None),
                    }
                    effective_config = Path(cache_temp) / "config.toml"
                    effective_config.write_text(dump_config(cfg()), encoding="utf-8")
                    create_backup(
                        target, password, config_path=effective_config, users=auth.export_rows(),
                        files=files, references=_collect_secret_references(cfg()),
                    )
                auth.audit(current_user().username, "backup_export")  # type: ignore[union-attr]
                return send_file(target, as_attachment=True, download_name=target.name)
            if action == "import":
                upload = request.files.get("backup")
                if not upload:
                    flash("Choose a backup file", "error")
                else:
                    with tempfile.TemporaryDirectory(prefix="bsmq-import-") as temp:
                        source = Path(temp) / "upload.bsmqbackup"
                        upload.save(source)
                        extracted = Path(temp) / "extract"
                        extract_backup(source, password, extracted)
                        imported_config = extracted / "config/config.toml"
                        imported = tomllib.loads(imported_config.read_text(encoding="utf-8")) if imported_config.exists() else cfg()
                        restore_dir = data_dir / "restored-secrets"
                        restore_dir.mkdir(parents=True, exist_ok=True)
                        references_file = extracted / "references.json"
                        references = json.loads(references_file.read_text(encoding="utf-8")) if references_file.exists() else {}
                        restored_cloud_refs: dict[str, Path] = {}
                        for logical, archive_name in references.items():
                            source_ref = extracted / archive_name
                            if not source_ref.exists():
                                continue
                            digest = hashlib.sha256(logical.encode("utf-8")).hexdigest()[:10]
                            destination = restore_dir / f"{digest}-{source_ref.name.split('-', 1)[-1]}"
                            shutil.copy2(source_ref, destination)
                            if os.name == "posix":
                                os.chmod(destination, 0o600)
                            if logical.startswith("app:"):
                                _set_nested(imported, logical[4:], str(destination))
                            elif logical.startswith("cloud:"):
                                restored_cloud_refs[logical[6:]] = destination

                        imported_cloud = extracted / "files/cloud.toml"
                        if imported_cloud.exists():
                            cloud_data = tomllib.loads(imported_cloud.read_text(encoding="utf-8"))
                            for dotted, destination in restored_cloud_refs.items():
                                _set_nested(cloud_data, dotted, str(destination))
                            restored_cloud = restore_dir / "cloud.toml"
                            atomic_write_config(restored_cloud, cloud_data)
                            _set_nested(imported, "cloud.config_file", str(restored_cloud))

                        atomic_write_config(runtime_config_path, imported)
                        users_json = extracted / "users.json"
                        if users_json.exists():
                            auth.import_rows(json.loads(users_json.read_text(encoding="utf-8")))
                        imported_cache = extracted / "files/mqtt-cache.sqlite3"
                        if imported_cache.exists() and cache is not None:
                            cache.restore_from(imported_cache)
                        imported_history = extracted / "files/history.sqlite3"
                        if imported_history.exists() and history is not None:
                            history.restore_from(imported_history)
                        state_destination = getattr(args, "state_file", None)
                        source_state = extracted / "files/state.json"
                        if source_state.exists() and state_destination:
                            Path(state_destination).parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source_state, state_destination)
                    auth.audit(current_user().username, "backup_import")  # type: ignore[union-attr]
                    flash("Backup imported; restart the service to activate all restored settings", "success")
        return render_template("backup.html")

    host, port = args.frontend_host, args.frontend_port
    ssl_context = None
    if getattr(args, "frontend_tls_cert", None) and getattr(args, "frontend_tls_key", None):
        ssl_context = (str(args.frontend_tls_cert), str(args.frontend_tls_key))
    server = make_server(host, port, app, threaded=True, ssl_context=ssl_context)
    thread = threading.Thread(target=server.serve_forever, name="ble-sensors-frontend", daemon=True)
    thread.start()
    return FrontendServer(server, thread, auth)
