#
# Copyright 2018 Astronomer Inc.
#
# Licensed under the Apache License, Version 3.0 (the "License");
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

FROM registry.access.redhat.com/ubi7/ubi:7.7
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
ARG ASTRONOMER_USER=astro
ARG ASTRONOMER_GROUP=astro

ENV ASTRONOMER_USER=${ASTRONOMER_USER}
ENV ASTRONOMER_GROUP=${ASTRONOMER_GROUP}

LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

RUN groupadd -g 1000 ${ASTRONOMER_GROUP} \
	&& useradd -u 1000 -g 1000 ${ASTRONOMER_USER}

RUN yum --disableplugin=subscription-manager -y update \
	&& yum --disableplugin=subscription-manager -y install ca-certificates \
	&& yum --disableplugin=subscription-manager -y clean all \
	&& update-ca-trust enable
