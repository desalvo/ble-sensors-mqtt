#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build the ble-sensors-mqtt Docker image with Docker Buildx.

By default the script builds linux/amd64 + linux/arm64 and pushes the versioned
image to Docker Hub. Authenticate first with `docker login`.

Usage: scripts/build-docker.sh [options]
  --image NAME         default desalvo/ble-sensors-mqtt
  --version VERSION    default from VERSION
  --platforms LIST     default linux/amd64,linux/arm64
  --builder NAME       default ble-sensors-mqtt-builder
  --latest             also push/tag NAME:latest
  --no-push            do not push; export a multiarch OCI archive instead
  --oci-output FILE    OCI archive path used with --no-push
  --skip-binfmt        do not install amd64/arm64 binfmt handlers
EOF
}

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

version=$(tr -d '[:space:]' < VERSION)
image='desalvo/ble-sensors-mqtt'
platforms='linux/amd64,linux/arm64'
builder='ble-sensors-mqtt-builder'
push=true
latest=false
binfmt=true
oci_output=''

while (($#)); do
  case "$1" in
    --image) image=${2:?}; shift 2 ;;
    --version) version=${2:?}; shift 2 ;;
    --platforms) platforms=${2:?}; shift 2 ;;
    --builder) builder=${2:?}; shift 2 ;;
    --latest) latest=true; shift ;;
    --no-push) push=false; shift ;;
    --oci-output) oci_output=${2:?}; shift 2 ;;
    --skip-binfmt) binfmt=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

project_version=$(python3 - <<'PY'
import tomllib
from pathlib import Path

print(tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
PY
)
if [[ $version != "$project_version" ]]; then
  echo "requested image version $version != pyproject.toml version $project_version" >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || { echo 'docker not found' >&2; exit 1; }
docker buildx version >/dev/null

if [[ $binfmt == true ]]; then
  docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64 >/dev/null
fi

if docker buildx inspect "$builder" >/dev/null 2>&1; then
  docker buildx use "$builder"
else
  docker buildx create --name "$builder" --driver docker-container --use >/dev/null
fi
docker buildx inspect --bootstrap >/dev/null

tags=(-t "$image:$version")
if [[ $latest == true ]]; then
  tags+=(-t "$image:latest")
fi

output=()
if [[ $push == true ]]; then
  output+=(--push)
else
  if [[ -z $oci_output ]]; then
    mkdir -p release/docker
    oci_output="release/docker/ble-sensors-mqtt-${version}.oci.tar"
  else
    mkdir -p "$(dirname -- "$oci_output")"
  fi
  output+=(--output "type=oci,dest=$oci_output")
fi

docker buildx build \
  --platform "$platforms" \
  --build-arg "VERSION=$version" \
  --file docker/Dockerfile \
  "${tags[@]}" \
  "${output[@]}" \
  .

if [[ $push == true ]]; then
  echo "Published $image:$version for $platforms"
  [[ $latest == false ]] || echo "Published $image:latest for $platforms"
else
  echo "Wrote multiarch OCI archive: $oci_output"
fi
