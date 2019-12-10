#
# Copyright 2019 Astronomer Inc.
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
LABEL io.astronomer.docker.component="houston-api"

ARG VERSION="v0.11.0-alpha.5"
ENV REPO="github.com/astronomer/houston-api"
ENV REPO_URL="https://${REPO}"


WORKDIR /houston

RUN yum --disableplugin=subscription-manager -y update \
	&& curl -sL https://rpm.nodesource.com/setup_10.x | bash - \
    && yum --disableplugin=subscription-manager -y install git coreutils gcc \
		gcc-c++ kernel-headers make python nodejs openssl \
	&& git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
	&& npm install \
	&& npm run build

EXPOSE 8871

# Wrap with entrypoint
ENTRYPOINT ["/houston/bin/entrypoint"]
CMD ["npm", "run", "serve"]
