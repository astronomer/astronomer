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

FROM registry.access.redhat.com/ubi7/ubi:7.7 AS builder

ENV GOPATH=/root/go
ENV GOBIN=${GOPATH}/bin

RUN set -eux; \
	yum --disableplugin=subscription-manager -y update; \
	yum --disableplugin=subscription-manager -y install \
		bzip2 \
		curl \
		gcc \
        gcc-c++ \
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

ARG VERSION="v6.3.3"
ENV REPO="github.com/grafana/grafana"
ENV REPO_URL="https://${REPO}"

WORKDIR /root/go/src/github.com/grafana/grafana

RUN git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
    && go get -u golang.org/x/xerrors \
    && go mod verify \
    && go run build.go build

# Installing Node and Yarn

ENV NODE_VERSION 10.14.2

ENV ARCH x64
  # gpg keys listed at https://github.com/nodejs/node#release-keys
RUN set -ex \
  && for key in \
    94AE36675C464D64BAFA68DD7434390BDBE9B9C5 \
    FD3A5288F042B6850C66B31F09FE44734EB7990E \
    71DCFD284A79C3B38668286BC97EC7A07EDE3FC1 \
    DD8F2338BAE7501E3DD5AC78C273792F7D83545D \
    C4F0DFFF4E8C1A8236409D08E73BC641CC11F4C8 \
    B9AE9905FFD7803F25714661B63B535A4C206CA9 \
    77984A986EBC2AA786BC0F66B01FBB92821C587A \
    8FCCA13FEF1D0C2E91008E09770F7A9A5AE15600 \
    4ED778F539E3634C779C87C6D7062848A1AB005C \
    A48C2BEE680E841632CD4E44F07496B3EB3C1762 \
    B9E2F5981AA6E0CD28160D9FF13993A75599653C \
  ; do \
 #   gpg --batch --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys "$key" || \
    gpg --batch --keyserver hkp://ipv4.pool.sks-keyservers.net --recv-keys "$key" || \
    gpg --batch --keyserver hkp://pgp.mit.edu:80 --recv-keys "$key" ; \
  done \
  && curl -fsSLO --compressed "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-$ARCH.tar.xz" \
  && curl -fsSLO --compressed "https://nodejs.org/dist/v$NODE_VERSION/SHASUMS256.txt.asc" \
  && gpg --batch --decrypt --output SHASUMS256.txt SHASUMS256.txt.asc \
  && grep " node-v$NODE_VERSION-linux-$ARCH.tar.xz\$" SHASUMS256.txt | sha256sum -c - \
  && tar -xJf "node-v$NODE_VERSION-linux-$ARCH.tar.xz" -C /usr/local --strip-components=1 --no-same-owner \
  && rm "node-v$NODE_VERSION-linux-$ARCH.tar.xz" SHASUMS256.txt.asc SHASUMS256.txt \
  && ln -s /usr/local/bin/node /usr/local/bin/nodejs

ENV YARN_VERSION 1.12.3

RUN set -ex \
  && for key in \
    6A010C5166006599AA17F08146C2130DFD2497F5 \
  ; do \
 #   gpg --batch --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys "$key" || \
    gpg --batch --keyserver hkp://ipv4.pool.sks-keyservers.net --recv-keys "$key" || \
    gpg --batch --keyserver hkp://pgp.mit.edu:80 --recv-keys "$key" ; \
  done \
  && curl -fsSLO --compressed "https://yarnpkg.com/downloads/$YARN_VERSION/yarn-v$YARN_VERSION.tar.gz" \
  && curl -fsSLO --compressed "https://yarnpkg.com/downloads/$YARN_VERSION/yarn-v$YARN_VERSION.tar.gz.asc" \
  && gpg --batch --verify yarn-v$YARN_VERSION.tar.gz.asc yarn-v$YARN_VERSION.tar.gz \
  && mkdir -p /opt \
  && tar -xzf yarn-v$YARN_VERSION.tar.gz -C /opt/ \
  && ln -s /opt/yarn-v$YARN_VERSION/bin/yarn /usr/local/bin/yarn \
  && ln -s /opt/yarn-v$YARN_VERSION/bin/yarnpkg /usr/local/bin/yarnpkg \
  && rm yarn-v$YARN_VERSION.tar.gz.asc yarn-v$YARN_VERSION.tar.gz

ENV PATH=$PATH:/usr/local/bin

WORKDIR /usr/src/app/

RUN cp -r /root/go/src/github.com/grafana/grafana/* .

RUN yarn install --pure-lockfile --no-progress

ENV NODE_ENV production
RUN ./node_modules/.bin/grunt build

# Final container
FROM registry.access.redhat.com/ubi7/ubi:7.7

LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

ARG GF_UID="472"
ARG GF_GID="472"

ENV PATH=/usr/share/grafana/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    GF_PATHS_CONFIG="/etc/grafana/grafana.ini" \
    GF_PATHS_DATA="/var/lib/grafana" \
    GF_PATHS_HOME="/usr/share/grafana" \
    GF_PATHS_LOGS="/var/log/grafana" \
    GF_PATHS_PLUGINS="/var/lib/grafana/plugins" \
    GF_PATHS_PROVISIONING="/etc/grafana/provisioning"

WORKDIR $GF_PATHS_HOME

RUN yum --disableplugin=subscription-manager -y update; \
    yum --disableplugin=subscription-manager -y install \
    fontconfig \
    ca-certificates 

COPY --from=0 /root/go/src/github.com/grafana/grafana/conf ./conf

RUN mkdir -p "$GF_PATHS_HOME/.aws" && \
    groupadd -r -g $GF_GID grafana && \
    useradd -r -u $GF_UID -g grafana grafana && \
    mkdir -p "$GF_PATHS_PROVISIONING/datasources" \
             "$GF_PATHS_PROVISIONING/dashboards" \
             "$GF_PATHS_PROVISIONING/notifiers" \
             "$GF_PATHS_LOGS" \
             "$GF_PATHS_PLUGINS" \
             "$GF_PATHS_DATA" && \
    cp "$GF_PATHS_HOME/conf/sample.ini" "$GF_PATHS_CONFIG" && \
    cp "$GF_PATHS_HOME/conf/ldap.toml" /etc/grafana/ldap.toml && \
    chown -R grafana:grafana "$GF_PATHS_DATA" "$GF_PATHS_HOME/.aws" "$GF_PATHS_LOGS" "$GF_PATHS_PLUGINS" "$GF_PATHS_PROVISIONING" && \
    chmod 777 -R "$GF_PATHS_DATA" "$GF_PATHS_HOME/.aws" "$GF_PATHS_LOGS" "$GF_PATHS_PLUGINS" "$GF_PATHS_PROVISIONING"

COPY --from=0 /root/go/src/github.com/grafana/grafana/packaging/docker/run.sh /run.sh
COPY --from=0 /root/go/src/github.com/grafana/grafana/bin/linux-amd64/grafana-server /root/go/src/github.com/grafana/grafana/bin/linux-amd64/grafana-cli ./bin/
COPY --from=0 /usr/src/app/public ./public
COPY --from=0 /usr/src/app/tools ./tools
COPY --from=0 /root/go/src/github.com/grafana/grafana/tools/phantomjs/render.js ./tools/phantomjs/render.js

# Copy default dashboards and datasource configuration
COPY include/dashboard.yaml /etc/grafana/provisioning/dashboards/dashboard.yaml
COPY include/nginx-ingress.json /var/lib/grafana/dashboards/nginx-ingress.json
COPY include/airflow-overview.json /var/lib/grafana/dashboards/airflow-overview.json
COPY include/airflow-scheduler.json /var/lib/grafana/dashboards/airflow-scheduler.json
COPY include/airflow-containers.json /var/lib/grafana/dashboards/airflow-containers.json
COPY include/airflow-state.json /var/lib/grafana/dashboards/airflow-state.json
COPY include/airflow-database-activity.json /var/lib/grafana/dashboards/airflow-database-activity.json
COPY include/fluentd.json /var/lib/grafana/dashboards/fluentd.json
COPY include/elasticsearch.json /var/lib/grafana/dashboards/elasticsearch.json
COPY include/prometheus.json /var/lib/grafana/dashboards/prometheus.json
COPY include/docker-registry.json /var/lib/grafana/dashboards/docker-registry.json
COPY include/platform-overview.json /var/lib/grafana/dashboards/platform-overview.json
COPY include/kubernetes-pods-metrics.json /var/lib/grafana/dashboards/kubernetes-pods-metrics.json


EXPOSE 3000

USER grafana
ENTRYPOINT [ "/run.sh" ]
