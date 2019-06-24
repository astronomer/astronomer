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

FROM astronomerinc/ap-base:0.10.0-alpha.1
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="astronomer"
LABEL io.astronomer.docker.component="houston-api"

ARG VERSION="v0.10.0-alpha.1"
ENV REPO="github.com/astronomer/houston-api"
ENV REPO_URL="https://${REPO}"


WORKDIR /houston

RUN apk add --no-cache --virtual .build-deps \
		build-base \
		git \
		python \
	&& apk add --no-cache \
		nodejs \
		nodejs-npm \
		openssl \
	&& git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
	&& npm install \
	&& npm run build \
	&& apk del .build-deps

EXPOSE 8871

# Wrap with entrypoint
ENTRYPOINT ["/houston/bin/entrypoint"]
CMD ["npm", "run", "serve"]
