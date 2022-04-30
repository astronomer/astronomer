FROM python:3.9-slim

ARG HELM_VERSION="3.8.2"
ARG KUBECTL_VERSION="1.19.16"

RUN apt-get update && apt-get install -y --no-install-recommends curl postgresql-client && rm -rf /var/cache/debconf/* /var/lib/apt/lists/*

# Install kubectl
RUN curl -fsSL https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz | tar --directory=/usr/local/bin/ --strip-components=1 -xzf - linux-amd64/helm
RUN curl -fsSLo /usr/local/bin/kubectl https://storage.googleapis.com/kubernetes-release/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    chmod +x /usr/local/bin/kubectl

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN ansible-galaxy collection install community.general:4.8.0 community.kubernetes:2.0.1

WORKDIR /lts-upgrade

COPY . .

ENTRYPOINT ansible-playbook upgrade-astronomer.yaml
