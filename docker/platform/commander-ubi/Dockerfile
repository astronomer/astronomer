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
LABEL io.astronomer.docker.component="commander"

ARG VERSION="v0.11.0-alpha.5"
ENV REPO="github.com/astronomerio/commander"
ENV REPO_URL="https://${REPO}"

ENV GCLOUD_VERSION="186.0.0"
ENV GCLOUD_FILE="google-cloud-sdk-${GCLOUD_VERSION}-linux-x86_64.tar.gz"
ENV GCLOUD_URL="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/${GCLOUD_FILE}"
ENV GOPATH=/root/go
ENV GOBIN=${GOPATH}/bin
ENV PATH=${PATH}:${GOBIN}

WORKDIR /opt/rh/go-toolset-7/root/usr/lib/go-toolset-7-golang/src/${REPO}

RUN yum --disableplugin=subscription-manager -y update \
	&& yum --disableplugin=subscription-manager -y install python2 \
	&& yum --disableplugin=subscription-manager -y install git coreutils gcc kernel-headers make \
		https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/go-toolset-7/go-toolset-7-golang-1.10.2-4.el7.x86_64.rpm \
		https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/go-toolset-7/go-toolset-7-runtime-1.10.2-4.el7.x86_64.rpm \
		https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/go-toolset-7/go-toolset-7-golang-bin-1.10.2-4.el7.x86_64.rpm \
		https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/go-toolset-7/go-toolset-7-golang-src-1.10.2-4.el7.noarch.rpm \
		https://buildlogs.centos.org/centos/7/sclo/x86_64/rh/go-toolset-7/go-toolset-7-1.10.2-4.el7.x86_64.rpm \
	&& git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
	&& scl enable go-toolset-7 'make DESTDIR=/usr/bin install' \
	&& curl -O ${GCLOUD_URL} \
	&& tar -xzf ${GCLOUD_FILE} \
	&& rm ${GCLOUD_FILE} \
	&& google-cloud-sdk/install.sh \
	&& mv google-cloud-sdk /opt \
	&& mkdir -p "${GOPATH}/src" \
	&& mkdir -p "${GOPATH}/bin" \
	&& yum  --disableplugin=subscription-manager -y history undo last \
	&& yum  --disableplugin=subscription-manager -y clean all \
#	&& yum  --disableplugin=subscription-manager -y remove git gcc make cpp \
#		scl-utils go-toolset-7 go-toolset-7-golang go-toolset-7-golang-bin go-toolset-7-golang-src go-toolset-7-runtime \
	&& rm -rf /opt/rh/go-toolset-7

ENTRYPOINT ["commander"]
