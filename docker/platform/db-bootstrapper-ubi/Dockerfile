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
LABEL io.astronomer.docker.component="db-bootstrapper"

ARG VERSION="v0.11.0-alpha.5"
ENV REPO="github.com/astronomerio/db-bootstrapper"
ENV REPO_URL="git+https://${REPO}@${VERSION}"

ENV PATH=${PATH}:/opt/rh/rh-python36/root/usr/bin
ENV LC_ALL="en_US.UTF-8"
ENV LANG="en_US.UTF-8"

# Install packages
RUN yum --disableplugin=subscription-manager -y update \
	&& yum --disableplugin=subscription-manager --setopt=tsflags=noscripts -y install \
		git coreutils gcc kernel-headers make libffi \
		libffi-devel \
		postgresql-devel \
	&& yum --disableplugin=subscription-manager -y install \
		rh-python36 \
	&& scl enable rh-python36 'pip install --no-cache-dir --upgrade pip==18.1; \
		pip install --no-cache-dir --upgrade setuptools==40.3.0; \
		pip install psycopg2-binary; \
		pip install "${REPO_URL}"' \
# We can uninstall the packages to save around 150 MB. or to keep the binaries, comment out the below line
	&& yum  --disableplugin=subscription-manager --setopt=tsflags=noscripts -y history undo last-1 \
	&& yum  --disableplugin=subscription-manager -y clean all

#Run the bootstrapper
ENTRYPOINT ["db-bootstrapper"]
