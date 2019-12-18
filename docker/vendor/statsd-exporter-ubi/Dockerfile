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


### STAGE 1 - Creation of busybox and statsd_exporter binaries in UBI

FROM registry.access.redhat.com/ubi7/ubi:7.7 AS builder


ENV BUSYBOX_VERSION 1.31.1
ENV GOPATH=/root/go
ENV GOBIN=${GOPATH}/bin


RUN set -eux; \
	yum --disableplugin=subscription-manager -y update; \
	yum --disableplugin=subscription-manager -y install \
		http://mirror.centos.org/centos/7/os/x86_64/Packages/libksba-1.3.0-5.el7.x86_64.rpm \
		http://mirror.centos.org/centos/7/os/x86_64/Packages/libksba-devel-1.3.0-5.el7.x86_64.rpm \
		http://ftp.fau.de/trinity/trinity/rpm/el7/trinity-r14/RPMS/x86_64//dirmngr-1.1.1-6.el7.x86_64.rpm \
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
	rm -rf /var/lib/apt/lists/* ; \
    curl -O https://storage.googleapis.com/golang/go1.13.5.linux-amd64.tar.gz; \
    tar -xf go1.13.5.linux-amd64.tar.gz ; \
    mv go /usr/local;

ENV PATH=$PATH:/usr/local/go/bin:${GOBIN}


# pub   1024D/ACC9965B 2006-12-12
#       Key fingerprint = C9E9 416F 76E6 10DB D09D  040F 47B7 0C55 ACC9 965B
# uid                  Denis Vlasenko <vda.linux@googlemail.com>
# sub   1024g/2C766641 2006-12-12
RUN gpg --batch --keyserver ha.pool.sks-keyservers.net --recv-keys C9E9416F76E610DBD09D040F47B70C55ACC9965B

RUN set -eux; \
	tarball="busybox-${BUSYBOX_VERSION}.tar.bz2"; \
	curl -fL -o busybox.tar.bz2 "https://busybox.net/downloads/$tarball"; \
	curl -fL -o busybox.tar.bz2.sig "https://busybox.net/downloads/$tarball.sig"; \
	gpg --batch --verify busybox.tar.bz2.sig busybox.tar.bz2; \
	mkdir -p /usr/src/busybox /go/src/github.com/prometheus/alertmanager; \
	tar -xf busybox.tar.bz2 -C /usr/src/busybox --strip-components 1; \
	rm busybox.tar.bz2*

WORKDIR /usr/src/busybox

# CONFIG_LAST_SUPPORTED_WCHAR: see https://github.com/docker-library/busybox/issues/13 (UTF-8 input)
RUN set -eux; \
	\
	setConfs=' \
		CONFIG_AR=y \
		CONFIG_FEATURE_AR_CREATE=y \
		CONFIG_FEATURE_AR_LONG_FILENAMES=y \
		CONFIG_LAST_SUPPORTED_WCHAR=0 \
# As long as we rely on libnss, we have to have libc.so anyhow, so
# we've removed CONFIG_STATIC here for now... :cry:
	'; \
	\
	unsetConfs=' \
		CONFIG_FEATURE_SYNC_FANCY \
	'; \
	\
	make defconfig; \
	\
	for conf in $unsetConfs; do \
		sed -i \
			-e "s!^$conf=.*\$!# $conf is not set!" \
			.config; \
	done; \
	\
	for confV in $setConfs; do \
		conf="${confV%=*}"; \
		sed -i \
			-e "s!^$conf=.*\$!$confV!" \
			-e "s!^# $conf is not set\$!$confV!" \
			.config; \
		if ! grep -q "^$confV\$" .config; then \
			echo "$confV" >> .config; \
		fi; \
	done; \
	\
	make oldconfig; \
	\
# trust, but verify
	for conf in $unsetConfs; do \
		! grep -q "^$conf=" .config; \
	done; \
	for confV in $setConfs; do \
		grep -q "^$confV\$" .config; \
	done;

RUN set -eux; \
	make -j "$(nproc)" \
		busybox \
	; \
	./busybox --help; \
	mkdir -p rootfs/bin; \
	ln -vL busybox rootfs/bin/; \
	\
	ln -vL "$(which getconf)" rootfs/bin/getconf; \
	\
# hack hack hack hack hack
# with glibc, static busybox uses libnss for DNS resolution :(
	mkdir -p rootfs/etc; \
	cp /etc/nsswitch.conf rootfs/etc/; \
	mkdir -p rootfs/lib; \
	ln -sT lib rootfs/lib64; \
	set -- \
		rootfs/bin/busybox \
		rootfs/bin/getconf \
		/lib64/"$(gcc -print-multiarch)"/libnss*.so.* \
# libpthread is part of glibc: https://stackoverflow.com/a/11210463/433558
		/lib64/"$(gcc -print-multiarch)"/libpthread*.so.* \
	; \
	while [ "$#" -gt 0 ]; do \
		f="$1"; shift; \
		fn="$(basename "$f")"; \
		if [ -e "rootfs/lib/$fn" ]; then continue; fi; \
		if [ "${f#rootfs/}" = "$f" ]; then \
			if [ "${fn#ld-}" = "$fn" ]; then \
				ln -vL "$f" "rootfs/lib/$fn"; \
			else \
				cp -v "$f" "rootfs/lib/$fn"; \
			fi; \
		fi; \
		set -- "$@" $(ldd "$f" | awk ' \
			$1 ~ /^\// { print $1; next } \
			$2 == "=>" && $3 ~ /^\// { print $3; next } \
		'); \
	done; \
	\
	chroot rootfs /bin/getconf _NPROCESSORS_ONLN; \
	\
	chroot rootfs /bin/busybox --install /bin

RUN set -x \
    && mkdir -p rootfs/lib \
    && set -- \
        /etc/nsswitch.conf \
        /etc/ssl/certs/ca-certificates.crt \
        /usr/share/zoneinfo \
        /etc/services \
        /lib64/"$(gcc -print-multiarch)"/libpthread.so.* \
    && while [ "$#" -gt 0  ]; do \
        f="$1"; shift; \
        fn="$(basename "$f")"; \
        if [ -e "rootfs/lib/$fn" ]; then continue; fi; \
        if [ "${f#/lib/}" != "$f" ]; then \
            ln -vL "$f" "rootfs/lib/$fn"; \
        else \
            d="$(dirname $f)" \
            && mkdir -p "rootfs/${d#/}" \
            && cp -av "$f" "rootfs/${f#/}"; \
        fi; \
    done


# download a few extra files from buildroot (/etc/passwd, etc)
RUN set -eux; \
	buildrootVersion='2019.11'; \
	mkdir -p rootfs/etc; \
	for f in passwd shadow group; do \
		curl -fL -o "rootfs/etc/$f" "https://git.busybox.net/buildroot/plain/system/skeleton/etc/$f?id=$buildrootVersion"; \
	done; \
# CVE-2019-5021, https://github.com/docker-library/official-images/pull/5880#issuecomment-490681907
	grep -E '^root::' rootfs/etc/shadow; \
	sed -ri -e 's/^root::/root:*:/' rootfs/etc/shadow; \
	grep -E '^root:[*]:' rootfs/etc/shadow; \
# set expected permissions, etc too (https://git.busybox.net/buildroot/tree/system/device_table.txt)
	curl -fL -o buildroot-device-table.txt "https://git.busybox.net/buildroot/plain/system/device_table.txt?id=$buildrootVersion"; \
	awk ' \
		!/^#/ { \
			if ($2 != "d" && $2 != "f") { \
				printf "error: unknown type \"%s\" encountered in line %d: %s\n", $2, NR, $0 > "/dev/stderr"; \
				exit 1; \
			} \
			sub(/^\/?/, "rootfs/", $1); \
			if ($2 == "d") { \
				printf "mkdir -p %s\n", $1; \
			} \
			printf "chmod %s %s\n", $3, $1; \
		} \
	' buildroot-device-table.txt | bash -Eeuo pipefail -x; \
	rm buildroot-device-table.txt

# create missing home directories
RUN set -eux; \
	cd rootfs; \
	for userHome in $(awk -F ':' '{ print $3 ":" $4 "=" $6 }' etc/passwd); do \
		user="${userHome%%=*}"; \
		home="${userHome#*=}"; \
		home="./${home#/}"; \
		if [ ! -d "$home" ]; then \
			mkdir -p "$home"; \
			chown "$user" "$home"; \
			chmod 755 "$home"; \
		fi; \
	done

# test and make sure it works
RUN chroot rootfs /bin/sh -xec 'true'

# ensure correct timezone (UTC)
RUN set -eux; \
	ln -vL /usr/share/zoneinfo/UTC rootfs/etc/localtime; \
	[ "$(chroot rootfs date +%Z)" = 'UTC' ]

# test and make sure DNS works too
RUN cp -L /etc/resolv.conf rootfs/etc/; \
	chroot rootfs /bin/sh -xec 'nslookup google.com'; \
	rm rootfs/etc/resolv.conf


ARG VERSION="v0.5.0"
ENV REPO="github.com/prometheus/statsd_exporter"
ENV REPO_URL="https://${REPO}"

WORKDIR /root/go/src/github.com/prometheus/statsd_exporter

RUN git clone \
		-c advice.detachedHead=false \
		--depth 1 \
		--branch ${VERSION} \
		${REPO_URL} . \
    && make build


### STAGE 2 - Copying busybox and statsd_exporter binaries into a separate image

FROM scratch
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

COPY --from=builder /usr/src/busybox/rootfs /
COPY --from=builder /root/go/src/github.com/prometheus/statsd_exporter/statsd_exporter /bin/statsd_exporter

USER       nobody
COPY include/mappings.yml /etc/statsd-exporter/mappings.yml


EXPOSE      9102 9125 9125/udp
ENTRYPOINT  [ "/bin/statsd_exporter" ]

