FROM registry.fedoraproject.org/fedora:42@sha256:63773f454664cd77e239f8e0b13ae7f18effe9e3d6612a325b5646eb3bda11f1

WORKDIR /workspace

ARG GATEWAY_SOURCE_REVISION=unresolved
LABEL org.opencontainers.image.source="https://github.com/napseer/gateway" \
      org.opencontainers.image.revision="${GATEWAY_SOURCE_REVISION}"

RUN dnf -y install ca-certificates git openssh-clients python3 tmux util-linux \
    && dnf clean all

COPY resources/scripts/napseer_mcp_server.py /opt/napseer/napseer_mcp_server.py
COPY resources/scripts/napseer_spake2.py /opt/napseer/napseer_spake2.py
COPY resources/scripts/terminal/ /opt/napseer/terminal/

RUN python3 -m py_compile \
        /opt/napseer/napseer_mcp_server.py \
        /opt/napseer/napseer_spake2.py \
        /opt/napseer/terminal/__init__.py \
        /opt/napseer/terminal/protocol.py \
        /opt/napseer/terminal/pty_manager.py \
    && chmod 0755 /opt/napseer/napseer_mcp_server.py

ENV PYTHONPATH=/opt/napseer
ENV NAPSEER_BASE_URL=https://api.napseer.com
ENV NAPSEER_GATEWAY_PORT=0
ENV NAPSEER_GATEWAY_PTY_TERMINAL=1
ENV NAPSEER_SERVICE_ACTIVATION_TIMEOUT_SECONDS=900

VOLUME ["/workspace/.napseer"]

CMD ["python3", "/opt/napseer/napseer_mcp_server.py", "gateway", "service", "run"]
