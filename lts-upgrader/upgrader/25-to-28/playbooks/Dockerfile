FROM python:3.9-slim

ARG HELM3_VERSION="3.8.1"
ARG KUBECTL_VERSION="1.21.11"

RUN apt-get update
RUN apt-get install -y libpq-dev libffi-dev libssl-dev curl postgresql-client
RUN apt-get install -y build-essential
ADD requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
RUN ansible-galaxy collection install community.general:1.2.0 community.kubernetes:1.1.0

RUN curl -fsSL https://get.helm.sh/helm-v${HELM3_VERSION}-linux-amd64.tar.gz | \
        tar xvz --directory=/usr/local/bin/ --strip-components=1 linux-amd64/helm && \
    chmod +x /usr/local/bin/helm

RUN curl -fsSLo /usr/local/bin/kubectl https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl \
    && chmod +x /usr/local/bin/kubectl

WORKDIR /lts-upgrade

COPY . .

ENTRYPOINT ansible-playbook upgrade-astronomer.yaml
