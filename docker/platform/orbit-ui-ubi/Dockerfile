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

FROM ap-base-ubi:test-ubi-1
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="astronomer"
LABEL io.astronomer.docker.component="orbit-ui"

ARG VERSION="v0.11.0-alpha.5"
ENV REPO="github.com/astronomerio/orbit-ui"
ENV REPO_URL="https://${REPO}"
ENV ORBIT_PATH=/tmp/orbit-ui
ENV SERVER_ROOT=/usr/share/nginx/html

WORKDIR ${ORBIT_PATH}

RUN yum --disableplugin=subscription-manager -y update \
    && yum --disableplugin=subscription-manager -y install git coreutils gcc gcc-c++ kernel-headers make  \
	&& curl -sL https://rpm.nodesource.com/setup_10.x | bash - \
	&& yum --disableplugin=subscription-manager -y install \
		https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/nginx16/nginx16-nginx-1.6.2-3.el7.x86_64.rpm \
        https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/nginx16/nginx16-runtime-1.2-2.el7.x86_64.rpm \
        https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/nginx16/nginx16-1.2-2.el7.x86_64.rpm \
		nodejs openssl gettext \
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
	&& mkdir -p /run/nginx

# Copy entrypoint to root
COPY include/entrypoint /

# Copy NGINX configuration to default location
COPY include/nginx.conf /etc/nginx/nginx.conf.tpl

# NGINX is configured to listen on 8080
EXPOSE 8080

# Setting ENV for nginx for rhel7 specific path 
ENV PATH=${PATH}:/opt/rh/nginx16/root/usr/bin/:/opt/rh/nginx16/root/usr/sbin/

# Run NGINX
ENTRYPOINT ["/entrypoint"]
