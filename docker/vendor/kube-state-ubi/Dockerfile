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
    curl -O https://storage.googleapis.com/golang/go1.13.5.linux-amd64.tar.gz; \
    tar -xf go1.13.5.linux-amd64.tar.gz ; \
    mv go /usr/local ;

ENV PATH=$PATH:/usr/local/go/bin:${GOBIN}


ARG VERSION="v1.7.2"
ENV REPO="github.com/kubernetes/kube-state-metrics"
ENV REPO_URL="https://${REPO}"

WORKDIR /root/go/src/github.com/kubernetes/kube-state-metrics

RUN git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
   # && make build-local 
    && go build

### STAGE 2 - Copying kubed binary into a separate image

FROM registry.access.redhat.com/ubi7/ubi:7.7
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

COPY --from=builder /root/go/src/github.com/kubernetes/kube-state-metrics/kube-state-metrics /bin/kube-state-metrics

EXPOSE 8080 8081
USER nobody
ENTRYPOINT ["kube-state-metrics", "--port=8080", "--telemetry-port=8081"]
