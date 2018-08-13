# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images.
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds.
BUILD_NUMBER ?= 1

# Build version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 3
ASTRONOMER_PATCH_VERSION ?= 3
ASTRONOMER_VERSION ?= "${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}"

# List of all components and order to build.
PLATFORM_COMPONENTS := base db-bootstrapper default-backend commander houston-api orbit-ui airflow
PLATFORM_RC_COMPONENTS := db-bootstrapper default-backend commander houston-api orbit-ui
PLATFORM_ONBUILD_COMPONENTS := airflow

# Vendor components
VENDOR_COMPONENTS := nginx registry cadvisor grafana prometheus redis statsd-exporter

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

.PHONY: build-rc
build-rc: clean-rc
ifndef ASTRONOMER_RC_VERSION
	$(error ASTRONOMER_RC_VERSION must be defined)
endif
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} build

.PHONY: push-rc
push-rc: build-rc
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

.PHONY: clean-rc
clean-rc:
	for image in `docker images -q -f label=io.astronomer.docker.rc=true` ; do \
		docker rmi -f $${image} ; \
	done

.PHONY: clean
clean: clean-containers clean-images
