FROM registry.fedoraproject.org/fedora:42

WORKDIR /workspace

RUN dnf -y install ca-certificates curl git openssh-clients python3 tmux util-linux \
    && dnf clean all

RUN python3 - <<'PY'
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

base_url = "https://api.napseer.com"
request = urllib.request.Request(
    f"{base_url}/v1/scripts/nap_install.py",
    headers={"User-Agent": "napseer-gateway-docker/0.1"},
)
payload = json.loads(urllib.request.urlopen(request, timeout=30).read().decode("utf-8"))
installer = pathlib.Path("/tmp/nap_install.py")
installer.write_text(payload["content"], encoding="utf-8")
subprocess.check_call(
    [sys.executable, str(installer), "install"],
    env={**os.environ, "NAPSEER_HOME": "/opt/napseer", "NAPSEER_BIN_DIR": "/usr/local/bin", "NAPSEER_BASE_URL": base_url},
)
PY

ENV PYTHONPATH=/opt/napseer
ENV NAPSEER_HOME=/opt/napseer
ENV NAPSEER_BIN_DIR=/usr/local/bin
ENV NAPSEER_BASE_URL=https://api.napseer.com
ENV NAPSEER_GATEWAY_PORT=0
ENV NAPSEER_GATEWAY_PTY_TERMINAL=1
ENV NAPSEER_SERVICE_ACTIVATION_TIMEOUT_SECONDS=900

VOLUME ["/workspace/.napseer"]

CMD ["nap", "gateway", "service", "run"]
