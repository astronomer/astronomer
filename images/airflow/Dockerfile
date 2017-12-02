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

FROM python:3.4.6-slim
MAINTAINER  Astronomer <humans@astronomer.io>
# LABEL io.astronomer.docker=true

# Never prompts the user for choices on installation/configuration of packages
ENV DEBIAN_FRONTEND=noninteractive \
    TERM=linux \
    LANGUAGE=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LC_CTYPE=en_US.UTF-8 \
    LC_MESSAGES=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    AIRFLOW_HOME=/usr/local/airflow

# Add python requirements
ADD include/requirements.txt .

RUN set -ex \
    && buildDeps=' \
        libkrb5-dev \
        libsasl2-dev \
        libssl-dev \
        build-essential \
        libblas-dev \
        liblapack-dev \
    ' \
    && apt-get update -yqq \
    && apt-get install -yqq --no-install-recommends \
        $buildDeps \
        git \
        rsync \
        zip \
        unzip \
        s3cmd \
        locales \
        libmysqlclient-dev \
        python-cffi \
        libcairo2 \
        libpango1.0-0 \
        libgdk-pixbuf2.0-0 \
        libffi-dev \
        shared-mime-info \
    && sed -i 's/^# en_US.UTF-8 UTF-8$/en_US.UTF-8 UTF-8/g' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 \
    && useradd -ms /bin/bash -d ${AIRFLOW_HOME} airflow \
    && pip install -r requirements.txt \
    && apt-get remove --purge -y $buildDeps

# Add AIRFLOW_HOME to PYTHONPATH
ENV PYTHONPATH ${PYTHONPATH}:${AIRFLOW_HOME}

# Add plugins
ADD include/plugins ${AIRFLOW_HOME}/plugins

# Add scripts
ADD include/script script

# Add Airflow config
ADD include/airflow.cfg ${AIRFLOW_HOME}/airflow.cfg

# Give ownership to our user
RUN chown -R airflow: ${AIRFLOW_HOME}

EXPOSE 8080 5555 8793

USER airflow
WORKDIR ${AIRFLOW_HOME}

ENTRYPOINT ["/script/entrypoint.sh"]
