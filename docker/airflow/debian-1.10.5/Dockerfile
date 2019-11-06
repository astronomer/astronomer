#
# Copyright 2019 Astronomer Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
ARG APT_DEPS_IMAGE="airflow-apt-deps"
ARG PYTHON_BASE_IMAGE="python:3.7-slim"

FROM ${PYTHON_BASE_IMAGE} as airflow-apt-deps

LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG ASTRONOMER_USER="astro"
ARG ASTRONOMER_UID="50000"
ARG BUILD_NUMBER=-1

LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.distro="debian"
LABEL io.astronomer.docker.module="airflow"
LABEL io.astronomer.docker.component="airflow"
LABEL io.astronomer.docker.uid="${ASTRONOMER_UID}"


ARG ORG="astronomer"


ENV AIRFLOW_REPOSITORY="https://github.com/${ORG}/airflow"
ENV AIRFLOW_HOME="/usr/local/airflow"
ENV PYTHONPATH=${PYTHONPATH:+${PYTHONPATH}:}${AIRFLOW_HOME}

ENV ASTRONOMER_USER=${ASTRONOMER_USER}
ENV ASTRONOMER_UID=${ASTRONOMER_UID}

# Need to repeat the empty argument here otherwise it will not be set for this stage
# But the default value carries from the one set before FROM
ARG PYTHON_BASE_IMAGE
ENV PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}

# Make sure noninteractie debian install is used and language variables set
ENV DEBIAN_FRONTEND=noninteractive LANGUAGE=C.UTF-8 LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    LC_CTYPE=C.UTF-8 LC_MESSAGES=C.UTF-8

# By increasing this number we can do force build of all dependencies
ARG DEPENDENCIES_EPOCH_NUMBER="1"
# Increase the value below to force renstalling of all dependencies
ENV DEPENDENCIES_EPOCH_NUMBER=${DEPENDENCIES_EPOCH_NUMBER}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
           apt-utils \
           curl \
           libmariadb3 \
           dumb-init \
           freetds-bin \
           git \
           gosu \
           libffi6 \
           libkrb5-3 \
           libpq5 \
           libsasl2-2 \
           libsasl2-modules \
           libssl1.1 \
           locales  \
           netcat \
           rsync \
           sasl2-bin \
           sudo \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip==19.2.3

RUN useradd --uid $ASTRONOMER_UID --create-home ${ASTRONOMER_USER}

# From the airflow image on master

#######################################################
######## Installed dependencies - now installing Airflow
#######################################################

FROM ${APT_DEPS_IMAGE} as devel
SHELL ["/bin/bash", "-o", "pipefail", "-e", "-u", "-x", "-c"]

ENV PIP_NO_CACHE_DIR="true"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        libffi-dev \
        libkrb5-dev \
        libpq-dev \
        libsasl2-dev \
        libssl-dev \
        nodejs \
        npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ARG VERSION="1.10.5-1"
ARG SUBMODULES="async,azure_blob_storage,azure_cosmos,azure_container_instances,celery,crypto,elasticsearch,gcp,kubernetes,mysql,postgres,s3,emr,redis,slack,ssh,statsd,virtualenv"
ENV AIRFLOW_MODULE="git+${AIRFLOW_REPOSITORY}@${VERSION}#egg=apache-airflow[${SUBMODULES}]"

# Force pip to install these specific versions when ever it installs a module
ENV PIP_CONSTRAINT=/usr/local/share/astronomer-pip-constraints.txt
COPY include/pip-constraints.txt /usr/local/share/astronomer-pip-constraints.txt

# Pip install airflow and astro security manager
RUN pip install "${AIRFLOW_MODULE}" \
  && pip install "https://github.com/astronomer/astronomer-fab-securitymanager/releases/download/v1.2.1/astronomer_fab_security_manager-1.2.1-py3-none-any.whl"

RUN cd usr/local/lib/python3.7/site-packages/airflow/www_rbac \
  && npm install \
  && npm run prod \
  && rm -rf node_modules


####################
# Installing node node_modules
###############

## move this to same layer as airflow because its from tag.

FROM ${APT_DEPS_IMAGE} as main

LABEL io.astronomer.docker.airflow.version="1.10.5"

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy all installed python modules. This gets us the compiled without needing dev installed
COPY --from=devel /usr/local/lib/python3.7/site-packages /usr/local/lib/python3.7/site-packages
COPY --from=devel /usr/local/bin /usr/local/bin


# Create logs directory so we can own it when we mount volumes
RUN install --directory --owner="${ASTRONOMER_USER}" "${AIRFLOW_HOME}" \
    && install --directory --owner="${ASTRONOMER_USER}" "${AIRFLOW_HOME}/logs"

COPY include/sudoers /etc/sudoers.d/astro
RUN visudo --check --file=/etc/sudoers.d/astro

# Copy entrypoint to root
COPY include/entrypoint /

# Though this is set here we currently override this in the helm template, so
# this _might_ not have any effect once deployed. The /entrypoint script copes
# with this
USER ${ASTRONOMER_USER}

# Switch to AIRFLOW_HOME
WORKDIR ${AIRFLOW_HOME}

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/entrypoint"]
CMD ["airflow", "--help"]
