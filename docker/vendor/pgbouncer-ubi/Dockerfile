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

FROM registry.access.redhat.com/ubi7/ubi:7.7 


LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER


ENV PGBOUNCER_VERSION=1.8.1 \
    PGBOUNCER_SHA256=fa8bde2a2d2c8c80d53a859f8e48bc6713cf127e31c77d8f787bbc1d673e8dc8

RUN groupadd -g 1000 pgbouncer \
    && useradd -u 1000 -g 1000 -s /sbin/nologin -G pgbouncer pgbouncer \
    && yum --disableplugin=subscription-manager -y install \
      coreutils \
      gcc \
		  gcc-c++ \
      kernel-headers \
      make \
      autoconf \
      wget \
      openssl \
      openssl-devel \
      libevent \
      http://mirror.centos.org/centos/7/os/x86_64/Packages/libevent-devel-2.0.21-4.el7.x86_64.rpm \
      http://mirror.centos.org/centos/7/os/x86_64/Packages/c-ares-1.10.0-3.el7.x86_64.rpm \
      http://mirror.centos.org/centos/7/os/x86_64/Packages/c-ares-devel-1.10.0-3.el7.x86_64.rpm \
    && wget https://pgbouncer.github.io/downloads/files/$PGBOUNCER_VERSION/pgbouncer-$PGBOUNCER_VERSION.tar.gz \
    && echo "$PGBOUNCER_SHA256  /pgbouncer-$PGBOUNCER_VERSION.tar.gz" | sha256sum -c - \
    && tar -xzf pgbouncer-$PGBOUNCER_VERSION.tar.gz \
    && cd pgbouncer-$PGBOUNCER_VERSION \
    && ./configure --prefix=/usr --disable-debug \
    && make \
    && make install \
    && mkdir /etc/pgbouncer \
    && cp ./etc/pgbouncer.ini /etc/pgbouncer/ \
    && touch /etc/pgbouncer/userlist.txt \
    && sed -i \
      -e "s|logfile = |#logfile = |" \
      -e "s|pidfile = |#pidfile = |" \
      -e "s|listen_addr = .*|listen_addr = 0.0.0.0|" \
      -e "s|auth_type = .*|auth_type = md5|" \
      /etc/pgbouncer/pgbouncer.ini \
    && cd .. \
    && rm pgbouncer-$PGBOUNCER_VERSION.tar.gz \
    && rm -rf pgbouncer-$PGBOUNCER_VERSION 

CMD ["pgbouncer", "-u", "pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
