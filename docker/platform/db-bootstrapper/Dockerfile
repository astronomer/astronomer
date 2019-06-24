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
LABEL io.astronomer.docker.component="db-bootstrapper"

ARG VERSION="v0.10.0-alpha.1"
ENV REPO="github.com/astronomerio/db-bootstrapper"
ENV REPO_URL="git+https://${REPO}@${VERSION}"

# Install packages
RUN apk update && \
	apk add --no-cache --virtual .build-deps \
		build-base \
		git \
		libffi-dev \
		postgresql-dev \
		python3-dev \
	&& apk add --no-cache \
		python3 \
	&& pip3 install --no-cache-dir --upgrade pip==18.1 \
	&& pip3 install "${REPO_URL}"

# Run the bootstrapper
ENTRYPOINT ["db-bootstrapper"]
