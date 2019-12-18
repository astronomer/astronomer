FROM registry.access.redhat.com/ubi7/ruby-26

LABEL maintainer "Fluentd developers <fluentd@googlegroups.com>"
LABEL Description="Fluentd docker image" Vendor="Fluent Organization" Version="1.8.0"
ENV TINI_VERSION=v0.18.0
ENV LD_LIBRARY_PATH=/opt/rh/rh-nodejs10/root/usr/lib64:/opt/rh/rh-ruby26/root/usr/local/lib64:/opt/rh/rh-ruby26/root/usr/lib64
ENV PATH=/opt/rh/rh-nodejs10/root/usr/bin:/opt/rh/rh-ruby26/root/usr/local/bin:/opt/rh/rh-ruby26/root/usr/bin:/opt/app-root/src/bin:/opt/app-root/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
USER root

ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini


# Do not split this into multiple RUN!
# Docker creates a layer for every RUN-Statement
# therefore an 'yum purge' has no effect

RUN yum install -y ca-certificates make gcc g++ libc-dev wget bzip2 gnupg dirmngr \
 && gem install oj -v 3.8.1 \
 && gem install json -v 2.2.0 \
 && gem install async-http -v 0.49.1 \
 && gem install fluentd -v 1.8.0 \
 && wget -O /tmp/jemalloc-4.5.0.tar.bz2 https://github.com/jemalloc/jemalloc/releases/download/4.5.0/jemalloc-4.5.0.tar.bz2 \
 && cd /tmp && tar -xjf jemalloc-4.5.0.tar.bz2 && cd jemalloc-4.5.0/ \
 && ./configure && make \
 && mv lib/libjemalloc.so.2 /usr/lib 

RUN groupadd -r fluent && useradd -r -g fluent fluent \
    # for log storage (maybe shared with host)
    && mkdir -p /fluentd/log \
    # configuration/plugins path (default: copied from .)
    && mkdir -p /fluentd/etc /fluentd/plugins \
    && chown -R fluent /fluentd && chgrp -R fluent /fluentd

COPY fluent.conf /fluentd/etc/
COPY entrypoint.sh /bin/

ENV FLUENTD_CONF="/fluentd/etc/fluent.conf"

ENV LD_PRELOAD="/usr/lib/libjemalloc.so.2"
EXPOSE 24224 5140

USER fluent
ENTRYPOINT ["tini",  "--", "/bin/entrypoint.sh"]
CMD ["fluentd"]

