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

FROM alpine:3.10
LABEL maintainer="Astronomer <humans@astronomer.io>"

LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.distro="alpine"
LABEL io.astronomer.docker.module="airflow"
LABEL io.astronomer.docker.component="airflow"
LABEL io.astronomer.docker.airflow.version="1.10.5"

ARG ORG="astronomer"
ARG VERSION="1.10.5-2"
ARG SUBMODULES="all, statsd, elasticsearch"
ARG REPO_BRANCH=master

ENV AIRFLOW_REPOSITORY="https://github.com/${ORG}/airflow"
ENV AIRFLOW_MODULE="git+${AIRFLOW_REPOSITORY}@${VERSION}#egg=apache-airflow[${SUBMODULES}]"
ENV AIRFLOW_HOME="/usr/local/airflow"
ENV PYMSSQL_BUILD_WITH_BUNDLED_FREETDS=1
ENV PYTHONPATH=${PYTHONPATH:+${PYTHONPATH}:}${AIRFLOW_HOME}
ENV AIRFLOW_GPL_UNIDECODE="True"

ARG ASTRONOMER_USER="astro"
ARG ASTRONOMER_GROUP="astro"
ENV ASTRONOMER_USER=${ASTRONOMER_USER}
ENV ASTRONOMER_GROUP=${ASTRONOMER_GROUP}

RUN addgroup -S ${ASTRONOMER_GROUP} \
	&& adduser -S -G ${ASTRONOMER_GROUP} ${ASTRONOMER_USER}

COPY apks/keys/humans@astronomer.io.rsa.pub /etc/apk/keys

# Force pip to install these specific versions when ever it installs a module
ENV PIP_CONSTRAINT=/usr/local/share/astronomer-pip-constraints.txt
COPY include/pip-constraints.txt /usr/local/share/astronomer-pip-constraints.txt

# Install packages
RUN echo https://github.com/astronomer/astronomer/raw/${REPO_BRANCH}/docker/airflow/1.10.5/apks/repo >> /etc/apk/repositories \
	&& apk update \
	&& apk add --no-cache --virtual .build-deps \
		build-base \
		cyrus-sasl-dev \
		freetds-dev \
		freetype-dev \
		git \
		krb5-dev \
		libffi-dev \
		libxml2-dev \
		libxslt-dev \
		linux-headers \
		nodejs \
		nodejs-npm \
		python3-dev \
		tzdata \
	&& apk add --no-cache \
		bash \
		ca-certificates \
		cyrus-sasl \
		cython3 \
		freetds \
		krb5-libs \
		py3-bcrypt \
		py3-cassandra-driver'>='3 \
		py3-cryptography \
		py3-fastavro \
		py3-grpcio \
		py3-mysqlclient \
		py3-numpy-dev \
		py3-numpy \
		py3-pandas \
		py3-psycopg2 \
		py3-pycryptodome \
		py3-pynacl \
		py3-typed-ast \
		python3 \
		tini \
	&& update-ca-certificates \
	&& cp /usr/share/zoneinfo/UTC /etc/localtime \
	&& pip3 install --no-cache-dir --upgrade pip==19.3.1 \
	&& pip3 install --no-cache-dir --upgrade setuptools==41.0.1 \
	&& pip3 install --no-cache-dir --upgrade snowflake-connector-python==1.9.1 \
	&& pip3 install --no-cache-dir "${AIRFLOW_MODULE}" \
	&& pip3 install --no-cache-dir "https://github.com/astronomer/astronomer-fab-securitymanager/releases/download/v1.2.1/astronomer_fab_security_manager-1.2.1-py3-none-any.whl" \
	&& cd /usr/lib/python3.7/site-packages/airflow/www_rbac \
	&& npm install \
	&& npm run build \
	&& rm -rf node_modules \
	&& apk del .build-deps py3-numpy-dev \
	&& ln -sf /usr/bin/python3 /usr/bin/python \
	&& ln -sf /usr/bin/pip3 /usr/bin/pip \
	&& sed -i -e '\#https://github.com/astronomer/astronomer/#d' /etc/apk/repositories

# Create logs directory so we can own it when we mount volumes
RUN mkdir -p ${AIRFLOW_HOME}/logs

# Copy entrypoint to root
COPY include/entrypoint /

# Copy "cron" scripts
COPY include/clean-airflow-logs /usr/local/bin/clean-airflow-logs

# Ensure our user has ownership to AIRFLOW_HOME
RUN chown -R ${ASTRONOMER_USER}:${ASTRONOMER_GROUP} ${AIRFLOW_HOME}

# Switch to AIRFLOW_HOME
WORKDIR ${AIRFLOW_HOME}

# Expose all airflow ports
EXPOSE 8080 5555 8793

# Run airflow with minimal init
ENTRYPOINT ["tini", "--", "/entrypoint"]
