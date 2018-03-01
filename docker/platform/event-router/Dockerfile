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

FROM golang:alpine

ARG VERSION="v0.0.14-beta"
ARG LIBRDKAFKA_VERSION="0.11.1-r1"

ENV REPO="github.com/astronomerio/event-router"
ENV REPO_URL="https://${REPO}"

WORKDIR /usr/local/go/src/${REPO}

RUN apk add --no-cache \
		build-base \
		cyrus-sasl-dev \
		git \
		librdkafka-dev=${LIBRDKAFKA_VERSION} \
		libressl \
		openssl-dev \
		yajl-dev \
		zlib-dev \
	&& git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
	&& make DESTDIR=/tmp install

FROM astronomerinc/ap-base
MAINTAINER Astronomer <humans@astronomer.io>

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="clickstream"
LABEL io.astronomer.docker.component="event-router"

RUN apk add --no-cache openssl
COPY --from=0 /tmp/event-router /usr/bin/event-router

EXPOSE 9091
ENTRYPOINT ["event-router"]
