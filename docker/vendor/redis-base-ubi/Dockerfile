FROM registry.access.redhat.com/ubi7/ubi:7.7

# add our user and group first to make sure their IDs get assigned consistently, regardless of whatever dependencies get added
RUN groupadd -g 1000 redis && useradd -g redis -u 999 redis
# alpine already has a gid 999, so we'll use the next id

ENV REDIS_VERSION 4.0.14
ENV REDIS_DOWNLOAD_URL http://download.redis.io/releases/redis-4.0.14.tar.gz
ENV REDIS_DOWNLOAD_SHA 1e1e18420a86cfb285933123b04a82e1ebda20bfb0a289472745a087587e93a7

ENV SU_EXEC_VERSION 0.2
ENV SU_EXEC_URL "https://github.com/ncopa/su-exec/archive/v${SU_EXEC_VERSION}.tar.gz"

ENV PAX_UTILS "http://download-ib01.fedoraproject.org/pub/epel/7/x86_64/Packages/p/pax-utils-1.2.3-1.el7.x86_64.rpm"

RUN set -eux; \
    yum --disableplugin=subscription-manager -y install tzdata coreutils gcc kernel-headers make unzip $PAX_UTILS \
	&& curl -sL "${SU_EXEC_URL}" | tar -C /tmp -zxf - \
	&& make -C "/tmp/su-exec-${SU_EXEC_VERSION}" \
	&& cp "/tmp/su-exec-${SU_EXEC_VERSION}/su-exec" /usr/bin \
	&& rm -fr "/tmp/su-exec-${SU_EXEC_VERSION}" \
	&& rm -fr /var/cache/yum/* /tmp/yum_save*.yumtx \
	&& curl -o redis.tar.gz "$REDIS_DOWNLOAD_URL"; \
	echo "$REDIS_DOWNLOAD_SHA *redis.tar.gz" | sha256sum -c -; \
	mkdir -p /usr/src/redis; \
	tar -xzf redis.tar.gz -C /usr/src/redis --strip-components=1; \
	rm redis.tar.gz; \
	\
# disable Redis protected mode [1] as it is unnecessary in context of Docker
# (ports are not automatically exposed when running inside Docker, but rather explicitly by specifying -p / -P)
# [1]: https://github.com/antirez/redis/commit/edd4d555df57dc84265fdfb4ef59a4678832f6da
	grep -q '^#define CONFIG_DEFAULT_PROTECTED_MODE 1$' /usr/src/redis/src/server.h; \
	sed -ri 's!^(#define CONFIG_DEFAULT_PROTECTED_MODE) 1$!\1 0!' /usr/src/redis/src/server.h; \
	grep -q '^#define CONFIG_DEFAULT_PROTECTED_MODE 0$' /usr/src/redis/src/server.h; \
# for future reference, we modify this directly in the source instead of just supplying a default configuration flag because apparently "if you specify any argument to redis-server, [it assumes] you are going to specify everything"
# see also https://github.com/docker-library/redis/issues/4#issuecomment-50780840
# (more exactly, this makes sure the default behavior of "save on SIGTERM" stays functional by default)
	\
	make -C /usr/src/redis -j "$(nproc)"; \
	make -C /usr/src/redis install; \
	\
# TODO https://github.com/antirez/redis/pull/3494 (deduplicate "redis-server" copies)
	serverMd5="$(md5sum /usr/local/bin/redis-server | cut -d' ' -f1)"; export serverMd5; \
	find /usr/local/bin/redis* -maxdepth 0 \
		-type f -not -name redis-server \
		-exec sh -eux -c ' \
			md5="$(md5sum "$1" | cut -d" " -f1)"; \
			test "$md5" = "$serverMd5"; \
		' -- '{}' ';' \
		-exec ln -svfT 'redis-server' '{}' ';' \
	; \
	\
	rm -r /usr/src/redis; \
	\
	yum --disableplugin=subscription-manager -y clean all; \
	yum --disableplugin=subscription-manager -y remove gcc make pax-utils; \
	\
	redis-cli --version; \
	redis-server --version

RUN mkdir /data && chown redis:redis /data
VOLUME /data
WORKDIR /data

COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 6379
CMD ["redis-server"]
