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
LABEL io.astronomer.docker.component="commander"

ARG VERSION="v0.10.0-alpha.1"
ENV REPO="github.com/astronomerio/commander"
ENV REPO_URL="https://${REPO}"

ENV GCLOUD_VERSION="186.0.0"
ENV GCLOUD_FILE="google-cloud-sdk-${GCLOUD_VERSION}-linux-x86_64.tar.gz"
ENV GCLOUD_URL="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/${GCLOUD_FILE}"
ENV GOPATH=/root/go
ENV GOBIN=${GOPATH}/bin
ENV PATH=${PATH}:${GOBIN}


WORKDIR /usr/lib/go/src/${REPO}

RUN apk update && \
	apk add --no-cache --virtual .build-deps \
		build-base \
		git \
		go \
	&& apk add --no-cache \
		python2 \
	&& git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
	&& make DESTDIR=/usr/bin install \
	&& wget ${GCLOUD_URL} \
	&& tar -xvf ${GCLOUD_FILE} \
	&& rm ${GCLOUD_FILE} \
	&& google-cloud-sdk/install.sh \
	&& mv google-cloud-sdk /opt \
	&& mkdir -p "${GOPATH}/src" \
	&& mkdir -p "${GOPATH}/bin" \
	&& rm -rf /usr/lib/go \
	&& apk del .build-deps

ENTRYPOINT ["commander"]
