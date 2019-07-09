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

FROM astronomerinc/ap-base:0.10.0-alpha.1
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="astronomer"
LABEL io.astronomer.docker.component="orbit-ui"

ARG VERSION="v0.10.0-alpha.1"
ENV REPO="github.com/astronomerio/orbit-ui"
ENV REPO_URL="https://${REPO}"
ENV ORBIT_PATH=/tmp/orbit-ui
ENV SERVER_ROOT=/usr/share/nginx/html

WORKDIR ${ORBIT_PATH}

RUN apk add --no-cache --virtual .build-deps \
		build-base \
		git \
	&& apk add --no-cache \
		gettext \
		nginx \
		nodejs \
		nodejs-npm \
		openssl \
	&& git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
	&& npm install \
	&& npm run build-production \
	&& mkdir -p ${SERVER_ROOT} \
	&& mv dist/* ${SERVER_ROOT} \
	&& mv src/favicon.ico ${SERVER_ROOT} \
	&& rm -rf ${ORBIT_PATH} \
	&& mkdir -p /run/nginx \
	&& apk del .build-deps

# Copy entrypoint to root
COPY include/entrypoint /

# Copy NGINX configuration to default location
COPY include/nginx.conf /etc/nginx/nginx.conf.tpl

# NGINX is configured to listen on 8080
EXPOSE 8080

# Run NGINX
ENTRYPOINT ["/entrypoint"]
