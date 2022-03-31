FROM python:3.9-alpine3.12

ARG HELM3_VERSION="3.6.3"
ARG KUBECTL_VERSION="1.20.16"

# Install Ansible and the modules we will use for upgrade
RUN apk add build-base libffi-dev openssl-dev postgresql-dev bash curl postgresql-client
ADD requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
RUN ansible-galaxy collection install community.general:1.2.0 community.kubernetes:1.1.0

RUN curl -LO "https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl"

RUN curl -L -s https://get.helm.sh/helm-v${HELM3_VERSION}-linux-amd64.tar.gz |tar xvz && \
    cp linux-amd64/helm /usr/bin/helm3 && \
    cp linux-amd64/helm /usr/bin/helm && \
    chmod +x /usr/bin/helm3 && \
    chmod +x /usr/bin/helm && \
    rm -rf linux-amd64
RUN wget -q https://storage.googleapis.com/kubernetes-release/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl -O /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

WORKDIR /lts-upgrade

COPY . .

ENTRYPOINT ansible-playbook upgrade-astronomer.yaml
