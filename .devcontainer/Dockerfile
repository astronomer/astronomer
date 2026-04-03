FROM debian:trixie

ENV DEVCONTAINER=true
ENV PATH="/root/.local/bin:/root/bin:$PATH"

RUN apt update && apt install -y \
    build-essential \
    cmake \
    curl \
    dnsutils \
    file \
    gh \
    git \
    jq \
    less \
    nodejs \
    npm \
    procps \
    unzip \
    vim \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN uv python install 3.14 --default && \
    uv tool install prek && \
    uv tool install ruff

# Reference:
# - https://code.claude.com/docs/en/devcontainer
# - https://github.com/anthropics/claude-code/blob/main/.devcontainer
# - https://www.npmjs.com/package/@anthropic-ai/claude-code
RUN npm install --ignore-scripts --min-release-age=7 -g @anthropic-ai/claude-code

# TODO: make this use the helm version from metadata.yaml
RUN curl -fsSL https://get.helm.sh/helm-v3.20.1-linux-amd64.tar.gz | tar --directory=/usr/local/bin/ --strip-components=1 -xzf - linux-amd64/helm
