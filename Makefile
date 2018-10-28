# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds
BUILD_NUMBER ?= 1

# List of all components and order to build
PLATFORM_COMPONENTS := base cli-install commander db-bootstrapper default-backend houston-api orbit-ui

# Airflow versions
AIRFLOW_VERSIONS := 1.9.0 1.10.0

# Vendor components
VENDOR_COMPONENTS := alertmanager cadvisor curator elasticsearch elasticsearch-exporter fluentd grafana kibana kube-state nginx pgbouncer pgbouncer-exporter prometheus redis registry statsd-exporter

# Set default for make
.DEFAULT_GOAL := build

#
# Main build/push
#
.PHONY: build
build: check-env
	$(MAKE) build-platform
	$(MAKE) build-airflow

.PHONY: push
push: check-env clean-images build
	$(MAKE) push-platform
	$(MAKE) push-airflow

#
# Platform build/push
#
.PHONY: build-platform
build-platform: check-env
	PLATFORM_COMPONENTS="${PLATFORM_COMPONENTS}" \
	VENDOR_COMPONENTS="${VENDOR_COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-platform

.PHONY: push-platform
push-platform: check-env
	for component in ${PLATFORM_COMPONENTS} ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-$${component} \
		PUSH_TAGS="${ASTRONOMER_VERSION} latest" \
		bin/push-image; \
	done;
	for component in ${VENDOR_COMPONENTS} ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-$${component} \
		PUSH_TAGS="${ASTRONOMER_VERSION} latest" \
		bin/push-image; \
	done;

.PHONY: push-platform-ref
push-platform-ref:
	for component in ${PLATFORM_COMPONENTS} ; do \
		PUSH_IMAGE="${REPOSITORY}/ap-$${component}" \
		PUSH_TAGS="${ASTRONOMER_REF}" \
		bin/push-image; \
	done;
	for component in ${VENDOR_COMPONENTS} ; do \
		PUSH_IMAGE="${REPOSITORY}/ap-$${component}" \
		PUSH_TAGS="${ASTRONOMER_REF}" \
		bin/push-image; \
	done;

#
# Airflow build/push
#
.PHONY: build-airflow
build-airflow: check-env
	AIRFLOW_VERSIONS="${AIRFLOW_VERSIONS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-airflow

# TODO: Fix me for multiple airflow version support
.PHONY: push-airflow
push-airflow: check-env
	for version in "${AIRFLOW_VERSIONS}" ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-airflow \
		PUSH_TAGS="${ASTRONOMER_VERSION} ${ASTRONOMER_VERSION}-onbuild" \
		bin/push-image; \
	done;

.PHONY: push-airflow-ref
push-airflow-ref:
	for version in "${AIRFLOW_VERSIONS}" ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-airflow \
		PUSH_TAGS="${ASTRONOMER_REF} ${ASTRONOMER_REF}-onbuild" \
		bin/push-image; \
	done;

#
# Clean
#
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

.PHONY: clean-pre-release-images
clean-pre-release-images:
	for image in `docker images -q -f label=io.astronomer.docker.pre-release=true` ; do \
		docker rmi -f $${image} ; \
	done

.PHONY: clean
clean: clean-containers clean-images clean-pre-release-images

# Update the version (tag) that we grab from github from the platform repos
.PHONY: update-platform-tags
update-platform-tags: check-env
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/ARG VERSION=(.*)/ARG VERSION="v${ASTRONOMER_VERSION}"/g' {} \;

.PHONY: check-env
check-env:
ifndef ASTRONOMER_VERSION
	$(error ASTRONOMER_VERSION is not set)
endif
