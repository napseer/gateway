FROM registry.fedoraproject.org/fedora:42

WORKDIR /workspace

RUN dnf -y install ca-certificates curl git openssh-clients python3 tmux util-linux \
    && dnf clean all

COPY resources/scripts/napseer_mcp_server.py /opt/napseer/napseer_mcp_server.py
COPY resources/scripts/napseer_spake2.py /opt/napseer/napseer_spake2.py

ENV PYTHONPATH=/opt/napseer
ENV NAPSEER_GATEWAY_PORT=0
ENV NAPSEER_SERVICE_ACTIVATION_TIMEOUT_SECONDS=900

VOLUME ["/workspace/.napseer"]

CMD ["python3", "/opt/napseer/napseer_mcp_server.py", "gateway", "service", "run"]
