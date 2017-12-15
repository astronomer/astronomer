#
# Copyright 2016 Astronomer Inc.
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

FROM astronomerinc/base
MAINTAINER Astronomer <humans@astronomer.io>

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

ARG VERSION=v0.3.6

ENV REPO="github.com/astronomerio/houston"
ENV REPO_URL="https://${REPO}"
ENV NODE_VERSION 9.2.1

WORKDIR /usr/src/node/${REPO}
RUN apk add --no-cache --virtual .build-deps \
		build-base \
		curl \
		git \
		linux-headers \
		python \
	&& curl -SLO "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION.tar.xz" \
	&& tar -xf "node-v$NODE_VERSION.tar.xz" \
	&& cd "node-v$NODE_VERSION" \
	&& ./configure \
	&& make -j$(getconf _NPROCESSORS_ONLN) \
	&& make install \
	&& cd .. \
	&& rm -Rf "node-v$NODE_VERSION" \
	&& rm "node-v$NODE_VERSION.tar.xz" \
    && git clone -c advice.detachedHead=false --depth 1 --branch ${VERSION} ${REPO_URL} . \
    && npm install --production \
	&& apk del .build-deps
