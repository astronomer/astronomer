# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images.
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds.
BUILD_NUMBER ?= 1

# Build version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 5
ASTRONOMER_PATCH_VERSION ?= 0
ASTRONOMER_VERSION ?= "${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}"

# List of all components and order to build.
PLATFORM_COMPONENTS := base airflow cli-install commander db-bootstrapper default-backend houston-api orbit-ui
PLATFORM_RC_COMPONENTS := cli-install commander db-bootstrapper default-backend houston-api orbit-ui
PLATFORM_ONBUILD_COMPONENTS := airflow

# Vendor components
VENDOR_COMPONENTS := cadvisor grafana nginx pgbouncer pgbouncer-exporter prometheus redis registry statsd-exporter

# All components
ALL_COMPONENTS := ${PLATFORM_COMPONENTS} ${VENDOR_COMPONENTS}

# Set default for make.
.DEFAULT_GOAL := build

.PHONY: build
build:
	PLATFORM_COMPONENTS="${PLATFORM_COMPONENTS}" \
	PLATFORM_RC_COMPONENTS="${PLATFORM_RC_COMPONENTS}" \
	VENDOR_COMPONENTS="${VENDOR_COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-images

.PHONY: push
push: clean build push-latest push-versioned

.PHONY: build-rc-stable
build-rc-stable:
ifndef ASTRONOMER_RC_VERSION
	$(error ASTRONOMER_RC_VERSION must be defined)
endif
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} build

.PHONY: push-rc-stable
push-rc-stable: build-rc-stable
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} push-versioned

.PHONY: build-rc-master
build-rc-master: clean-rc-master
ifndef ASTRONOMER_RC_VERSION
	$(error ASTRONOMER_RC_VERSION must be defined)
endif
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} ASTRONOMER_USE_MASTER=1 build

.PHONY: push-rc-master
push-rc-master: build-rc-master
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} push-versioned

.PHONY: push-latest
push-latest:
	for component in ${ALL_COMPONENTS} ; do \
		echo "Pushing ap-$${component}:latest =================================="; \
		docker push ${REPOSITORY}/ap-$${component}:latest || exit 1; \
	done; \
	for component in ${PLATFORM_ONBUILD_COMPONENTS} ; do \
		docker push ${REPOSITORY}/ap-$${component}:latest-onbuild || exit 1; \
	done

.PHONY: push-versioned
push-versioned:
	for component in ${ALL_COMPONENTS} ; do \
		echo "Pushing ap-$${component}:${ASTRONOMER_VERSION} =================================="; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
	done; \
	for component in ${PLATFORM_ONBUILD_COMPONENTS} ; do \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION}-onbuild || exit 1; \
	done

.PHONY: clean-containers
clean-containers:
	for container in `docker ps -aq -f label=io.astronomer.docker.open=true` ; do \
		docker rm -f -v $${container} ; \
	done

.PHONY: clean-images
clean-images:
	for image in `docker images -q -f label=io.astronomer.docker=true` ; do \
		docker rmi -f $${image} ; \
	done

.PHONY: clean-rc-master
clean-rc-master:
	for image in `docker images -q -f label=io.astronomer.docker.rc=true` ; do \
		docker rmi -f $${image} ; \
	done

.PHONY: clean
clean: clean-containers clean-images
