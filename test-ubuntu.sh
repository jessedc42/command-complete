#!/usr/bin/env bash
set -euo pipefail

project_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Match the Ubuntu version and architecture of the collected reference system.
docker run --rm --platform linux/amd64 \
    --mount "type=bind,src=$project_directory,dst=/work,readonly" \
    --workdir /work \
    ubuntu:24.04 \
    bash -lc '
        set -e
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 ncurses-base
        python3 -B install_commands.py --bin-dir /usr/local/bin
        python3 --version
        bash --version | head -n 1
        command-complete --version
        cs --version
        python3 -B -m unittest -v
    '
