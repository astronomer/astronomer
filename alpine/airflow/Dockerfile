#
# Copyright 2016 Astronomer Inc.
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
MAINTAINER Astronomer <humans@astronomer.io>

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

ARG ORG="astronomerio"
ARG VERSION=1.9.0rc5
ARG SUBMODULES="all, celery, redis"

ENV AIRFLOW_REPOSITORY="https://github.com/${ORG}/incubator-airflow"
ENV AIRFLOW_MODULE="git+${AIRFLOW_REPOSITORY}@${VERSION}#egg=apache-airflow[${SUBMODULES}]"

ENV AIRFLOW_USER="airflow"
ENV AIRFLOW_HOME="/home/airflow"

ENV PYMSSQL_BUILD_WITH_BUNDLED_FREETDS=1

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
	&& pip3 install --no-cache-dir "${AIRFLOW_MODULE}" \
	&& apk del .build-deps

RUN adduser -D -h ${AIRFLOW_HOME} ${AIRFLOW_USER} && chown -R ${AIRFLOW_USER}: ${AIRFLOW_HOME}

# Allowing for onbuild package installation. We specify user at runtime.
# USER ${AIRFLOW_USER}

WORKDIR ${AIRFLOW_HOME}
ADD include/script script
ADD include/airflow.cfg airflow.cfg

EXPOSE 8080 5555 8793
ENTRYPOINT ["script/entrypoint"]
