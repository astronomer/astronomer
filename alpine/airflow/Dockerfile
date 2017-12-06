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

FROM astronomerio/base
MAINTAINER  Astronomer <humans@astronomer.io>

ARG VERSION=v1.8.2

ENV AIRFLOW_HOME="/usr/local/airflow"
ENV AIRFLOW_REPOSITORY="https://github.com/astronomerio/incubator-airflow"
ENV AIRFLOW_SUBMODULES="s3, postgres, password, celery"
ENV AIRFLOW_MODULE="git+${AIRFLOW_REPOSITORY}@${VERSION}#egg=apache-airflow[${AIRFLOW_SUBMODULES}]"

RUN apk add --no-cache --virtual .build-deps \
		linux-headers \
		build-base \
		git \
		libffi-dev \
		freetype-dev \
		libxml2-dev \
		libxslt-dev \
	&& apk add \
		bash \
		python3-dev \
		postgresql-dev \
	&& pip3 install "${AIRFLOW_MODULE}" celery[redis]==3.1.25 \
	&& apk del .build-deps

ADD include/script ${AIRFLOW_HOME}/script
ADD include/airflow.cfg ${AIRFLOW_HOME}/airflow.cfg

RUN adduser -D -h ${AIRFLOW_HOME} airflow \
    && chown -R airflow: ${AIRFLOW_HOME}

ENV PYTHONPATH="${PYTHONPATH}:${AIRFLOW_HOME}"
EXPOSE 8080 5555 8793
USER airflow
WORKDIR ${AIRFLOW_HOME}
ENTRYPOINT ["./script/entrypoint"]
