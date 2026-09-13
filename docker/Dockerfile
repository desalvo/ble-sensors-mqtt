FROM python:3.11-slim-bookworm
ARG VERSION=dev
LABEL org.opencontainers.image.title="ble-sensors-mqtt" org.opencontainers.image.source="https://github.com/desalvo/ble-sensors-mqtt" org.opencontainers.image.version="${VERSION}" org.opencontainers.image.licenses="EUPL-1.2"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket
WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir --upgrade pip "setuptools>=83" wheel \
 && python -m pip install --no-cache-dir ".[all]" \
 && install -d -m 0750 -o 10001 -g 10001 /var/lib/ble-sensors-mqtt /etc/ble-sensors-mqtt \
 && chmod 0755 /app/docker/entrypoint.sh
USER 10001:10001
VOLUME ["/var/lib/ble-sensors-mqtt"]
EXPOSE 8080/tcp 9105/tcp 1161/udp
ENTRYPOINT ["/app/docker/entrypoint.sh"]
