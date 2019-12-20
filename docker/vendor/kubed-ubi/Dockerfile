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


### STAGE 1 - Creation of kubed binary in UBI

FROM registry.access.redhat.com/ubi7/ubi:7.7 AS builder


ENV GOPATH=/root/go
ENV GOBIN=${GOPATH}/bin


RUN set -eux; \
	yum --disableplugin=subscription-manager -y update; \
	yum --disableplugin=subscription-manager -y install \
		bzip2 \
		curl \
		gcc \
		gnupg \		
		make \
		ca-certificates \
		git \
		coreutils \
		kernel-headers \
	; \
    curl -O https://storage.googleapis.com/golang/go1.12.9.linux-amd64.tar.gz; \
    tar -xf go1.12.9.linux-amd64.tar.gz ; \
    mv go /usr/local ; \
    curl -fsSL -o osm https://cdn.appscode.com/binaries/osm/0.9.1/osm-linux-amd64; \
    chmod 755 osm; \
    mv osm /usr/local ;

ENV PATH=$PATH:/usr/local/go/bin:${GOBIN}


ARG VERSION="v0.11.0"
ENV REPO="github.com/appscode/kubed"
ENV REPO_URL="https://${REPO}"

WORKDIR /root/go/src/github.com/appscode/kubed

RUN git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
    && go build


### STAGE 2 - Copying kubed binary into a separate image

FROM registry.access.redhat.com/ubi7/ubi:7.7
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

COPY --from=builder /usr/local/osm /bin/osm
COPY --from=builder /root/go/src/github.com/appscode/kubed/kubed /bin/kubed

USER nobody

ENTRYPOINT ["kubed"]
