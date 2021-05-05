FROM python:3.9-alpine3.12

ARG HELM3_VERSION="3.5.3"
ARG KUBECTL_VERSION="1.18.15"

ENV USE_INTERNAL_HELM_REPO False

# Install Ansible and the modules we will use for upgrade
RUN apk add build-base libffi-dev openssl-dev postgresql-dev bash curl postgresql-client
RUN pip install ansible==2.9.14 psycopg2==2.8.6 openshift==0.11.2 cryptography==3.1.1
RUN ansible-galaxy collection install community.general:1.2.0 community.kubernetes:1.1.0
# Install kubectl
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

ENTRYPOINT ansible-playbook -e "USE_INTERNAL_HELM_REPO=$USE_INTERNAL_HELM_REPO" upgrade-astronomer.yaml
