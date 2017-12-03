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

ENV AIRFLOW_HOME=/usr/local/airflow

RUN apk add dumb-init \
	musl \
	linux-headers \
	build-base \
	git \
	ca-certificates \
	python3 \
	python3-dev \
	libffi-dev \
	libpng \
	freetype-dev \
	postgresql-dev \
	libxml2-dev \
	libxslt-dev \
	bash

RUN if [[ ! -e /usr/bin/python ]];         then ln -sf /usr/bin/python3 /usr/bin/python; fi \
	&& if [[ ! -e /usr/bin/easy_install ]];  then ln -sf /usr/bin/easy_install-3* /usr/bin/easy_install; fi \
	&& easy_install pip \
	&& pip install --upgrade pip \
	&& if [[ ! -e /usr/bin/pip ]]; then ln -sf /usr/bin/pip3 /usr/bin/pip; fi

ADD include/requirements.txt .
RUN pip install -r requirements.txt

ENV PYTHONPATH ${PYTHONPATH}:${AIRFLOW_HOME}
ADD include/script ${AIRFLOW_HOME}/script
ADD include/airflow.cfg ${AIRFLOW_HOME}/airflow.cfg
RUN adduser -D -h ${AIRFLOW_HOME} airflow \
    && chown -R airflow: ${AIRFLOW_HOME}

EXPOSE 8080 5555 8793
USER airflow
WORKDIR ${AIRFLOW_HOME}
ENTRYPOINT ["script/entrypoint"]
