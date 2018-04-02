#
# Copyright 2018 Astronomer Inc.
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

FROM astronomerinc/ap-base
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="airflow"
LABEL io.astronomer.docker.component="airflow"

ARG ORG="astronomerio"
ARG VERSION="1.9.0"
ARG SUBMODULES="all, celery, redis, statsd"

ENV AIRFLOW_REPOSITORY="https://github.com/${ORG}/incubator-airflow"
ENV AIRFLOW_MODULE="git+${AIRFLOW_REPOSITORY}@${VERSION}#egg=apache-airflow[${SUBMODULES}]"
ENV AIRFLOW_HOME="/usr/local/airflow"
ENV PYMSSQL_BUILD_WITH_BUNDLED_FREETDS=1
ENV PYTHONPATH=${PYTHONPATH:+${PYTHONPATH}:}${AIRFLOW_HOME}

# Install packages
RUN apk add --no-cache --virtual .build-deps \
		build-base \
		freetype-dev \
		git \
		libffi-dev \
		libxml2-dev \
		libxslt-dev \
		linux-headers \
		mariadb-dev \
		postgresql-dev \
		python3-dev \
	&& apk add --no-cache \
		bash \
		mariadb-client-libs \
		postgresql \
		python3 \
		tini \
	&& pip3 install --no-cache-dir "${AIRFLOW_MODULE}" \
	&& pip3 uninstall -y snakebite \
	&& apk del .build-deps \
	&& ln -sf /usr/bin/python3 /usr/bin/python \
	&& ln -sf /usr/bin/pip3 /usr/bin/pip

# Create logs directory so we can own it when we mount volumes
RUN mkdir -p ${AIRFLOW_HOME}/logs

# Copy entrypoint to root
COPY include/entrypoint /
COPY include/wait-for-command /

# Copy airflow configuration
COPY include/airflow.cfg ${AIRFLOW_HOME}

# Copy cron scripts
COPY include/clean-airflow-logs /etc/periodic/15min/clean-airflow-logs

# Ensure our user has ownership to AIRFLOW_HOME
RUN chown -R ${ASTRONOMER_USER}:${ASTRONOMER_GROUP} ${AIRFLOW_HOME}

# Switch to AIRFLOW_HOME
WORKDIR ${AIRFLOW_HOME}

# Expose all airflow ports
EXPOSE 8080 5555 8793

# Run airflow with minimal init
ENTRYPOINT ["tini", "--", "/entrypoint"]
