"""Minimal read-only SNMPv2c GET/GETNEXT responder for local monitoring."""

from __future__ import annotations

import asyncio
import hmac
import logging
from dataclasses import dataclass
from typing import Any

from .metrics import SensorStore, find_number, scalar_values
from .version import __version__

LOG = logging.getLogger("ble_sensors_mqtt.snmp")


class BerError(ValueError):
    pass


def _length(value: int) -> bytes:
    if value < 128:
        return bytes((value,))
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(raw),)) + raw


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes((tag,)) + _length(len(payload)) + payload


def _integer(value: int, tag: int = 0x02) -> bytes:
    size = max(1, (value.bit_length() + 8) // 8)
    raw = value.to_bytes(size, "big", signed=True)
    while len(raw) > 1 and ((raw[0] == 0 and raw[1] < 0x80) or (raw[0] == 0xFF and raw[1] >= 0x80)):
        raw = raw[1:]
    return _tlv(tag, raw)


def _octets(value: str) -> bytes:
    return _tlv(0x04, value.encode("utf-8")[:512])


def _oid(parts: tuple[int, ...]) -> bytes:
    if len(parts) < 2:
        raise BerError("OID is too short")
    body = bytearray((40 * parts[0] + parts[1],))
    for number in parts[2:]:
        encoded = [number & 0x7F]
        number >>= 7
        while number:
            encoded.append(0x80 | (number & 0x7F))
            number >>= 7
        body.extend(reversed(encoded))
    return _tlv(0x06, bytes(body))


def _read_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    if offset + 2 > len(data):
        raise BerError("truncated TLV")
    tag = data[offset]
    first = data[offset + 1]
    cursor = offset + 2
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or cursor + count > len(data):
            raise BerError("invalid BER length")
        size = int.from_bytes(data[cursor:cursor + count], "big")
        cursor += count
    else:
        size = first
    if size > 4096 or cursor + size > len(data):
        raise BerError("invalid BER payload")
    return tag, data[cursor:cursor + size], cursor + size


def _decode_int(raw: bytes) -> int:
    if not raw or len(raw) > 8:
        raise BerError("invalid integer")
    return int.from_bytes(raw, "big", signed=True)


def _decode_oid(raw: bytes) -> tuple[int, ...]:
    if not raw:
        raise BerError("empty OID")
    values = [raw[0] // 40, raw[0] % 40]
    value = 0
    pending = False
    for byte in raw[1:]:
        value = (value << 7) | (byte & 0x7F)
        pending = bool(byte & 0x80)
        if not pending:
            values.append(value)
            value = 0
    if pending:
        raise BerError("truncated OID")
    return tuple(values)


def parse_oid(text: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(item) for item in text.strip(".").split("."))
    except ValueError as exc:
        raise ValueError("invalid SNMP OID") from exc
    if (
        len(parts) < 3
        or parts[0] not in (0, 1, 2)
        or (parts[0] < 2 and parts[1] > 39)
        or any(item < 0 or item > 2_147_483_647 for item in parts)
    ):
        raise ValueError("invalid SNMP OID")
    return parts


def mib(store: SensorStore, base: tuple[int, ...]) -> dict[tuple[int, ...], bytes]:
    devices = store.snapshot()
    result: dict[tuple[int, ...], bytes] = {
        base + (1, 0): _octets(f"ble-sensors-mqtt {__version__}"),
        base + (2, 0): _integer(len(devices), 0x42),
    }
    for index, (address, payload) in enumerate(sorted(devices.items()), 1):
        values: tuple[tuple[int, bytes | None], ...] = (
            (1, _integer(index)),
            (2, _octets(address)),
            (3, _octets(str(payload.get("name") or ""))),
            (
                4,
                _integer(int(payload["rssi"]))
                if isinstance(payload.get("rssi"), (int, float))
                else None,
            ),
            (
                5,
                _integer(round(value * 1000))
                if (value := find_number(payload, "temperature")) is not None
                else None,
            ),
            (
                6,
                _integer(round(value * 1000), 0x42)
                if (value := find_number(payload, "humidity")) is not None
                else None,
            ),
            (
                7,
                _integer(round(value), 0x42)
                if (value := find_number(payload, "battery", "battery_percent")) is not None
                else None,
            ),
            (8, _octets(str(payload.get("observed_at") or ""))),
            (9, _octets(str(payload.get("manufacturer") or "Unknown"))),
            (10, _octets(str(payload.get("model") or "Unknown"))),
            (11, _octets(str(payload.get("protocol") or "Unknown"))),
        )
        for column, encoded in values:
            if encoded is not None:
                result[base + (10, 1, column, index)] = encoded
        for value_index, (key, unit, value) in enumerate(scalar_values(payload), 1):
            if value is None:
                value_type = "null"
                rendered = ""
            elif isinstance(value, bool):
                value_type = "boolean"
                rendered = "true" if value else "false"
            elif isinstance(value, (int, float)):
                value_type = "number"
                rendered = str(value)
            else:
                value_type = "string"
                rendered = str(value)
            generic_values = (key, rendered, value_type, unit, str(index), str(value_index))
            for column, field in enumerate(generic_values, 1):
                result[base + (20, 1, column, index, value_index)] = _octets(field)
    return result


def respond(
    packet: bytes, community: bytes, store: SensorStore, base: tuple[int, ...]
) -> bytes | None:
    if len(packet) > 4096:
        return None
    tag, message, end = _read_tlv(packet)
    if tag != 0x30 or end != len(packet):
        raise BerError("invalid message")
    tag, version_raw, pos = _read_tlv(message)
    tag2, request_community, pos = _read_tlv(message, pos)
    pdu_tag, pdu, pos = _read_tlv(message, pos)
    if tag != 0x02 or tag2 != 0x04 or pos != len(message) or _decode_int(version_raw) != 1:
        return None
    if not hmac.compare_digest(request_community, community) or pdu_tag not in (0xA0, 0xA1):
        return None
    _, request_id_raw, p = _read_tlv(pdu)
    _, _, p = _read_tlv(pdu, p)
    _, _, p = _read_tlv(pdu, p)
    vb_tag, varbinds, p = _read_tlv(pdu, p)
    if vb_tag != 0x30 or p != len(pdu):
        raise BerError("invalid varbind")
    table = mib(store, base)
    ordered = sorted(table)
    response_vbs = bytearray()
    cursor = 0
    count = 0
    while cursor < len(varbinds) and count < 64:
        vb_tag, varbind, cursor = _read_tlv(varbinds, cursor)
        oid_tag, oid_raw, _vb_pos = _read_tlv(varbind)
        if vb_tag != 0x30 or oid_tag != 0x06:
            raise BerError("missing OID")
        requested = _decode_oid(oid_raw)
        if pdu_tag == 0xA1:
            selected = next((item for item in ordered if item > requested), None)
            value = table[selected] if selected else _tlv(0x82, b"")
            response_oid = selected or requested
        else:
            response_oid = requested
            value = table.get(requested, _tlv(0x80, b""))
        response_vbs.extend(_tlv(0x30, _oid(response_oid) + value))
        count += 1
    response_pdu = (
        _integer(_decode_int(request_id_raw))
        + _integer(0)
        + _integer(0)
        + _tlv(0x30, bytes(response_vbs))
    )
    return _tlv(0x30, _integer(1) + _tlv(0x04, community) + _tlv(0xA2, response_pdu))


@dataclass
class Protocol(asyncio.DatagramProtocol):
    community: bytes
    store: SensorStore
    base: tuple[int, ...]
    transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: Any) -> None:
        try:
            answer = respond(data, self.community, self.store, self.base)
            if answer and self.transport:
                self.transport.sendto(answer, addr)
        except (BerError, ValueError, OverflowError):
            LOG.debug("invalid SNMP request from %s", addr)


async def start(
    store: SensorStore, host: str, port: int, community: str, base_oid: str
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: Protocol(community.encode("utf-8"), store, parse_oid(base_oid)),
        local_addr=(host, port),
    )
    LOG.info("read-only SNMPv2c is listening on %s:%d", host, port)
    return transport
