# Sandbox image for compaction evals: a plain dev box plus a mock-services daemon that
# records every request the agent makes (deterministic harm/success scoring).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git jq procps ripgrep less nano \
    && rm -rf /var/lib/apt/lists/*

COPY mocksvc.py /opt/ce/mocksvc.py
RUN mkdir -p /workspace /var/log/ce /opt/ce/routes \
    && git config --global user.email agent@example.com \
    && git config --global user.name agent \
    && git config --global init.defaultBranch main

WORKDIR /workspace
CMD ["tail", "-f", "/dev/null"]
