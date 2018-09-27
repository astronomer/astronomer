# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds
BUILD_NUMBER ?= 1

# Astronomer build version
# ASTRONOMER_MAJOR_VERSION ?= 0
# ASTRONOMER_MINOR_VERSION ?= 5
# ASTRONOMER_PATCH_VERSION ?= 1
# ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of all components and order to build
PLATFORM_COMPONENTS := base cli-install commander db-bootstrapper default-backend houston-api orbit-ui

# Airflow versions
AIRFLOW_VERSIONS := 1.9.0

# Vendor components
VENDOR_COMPONENTS := cadvisor grafana nginx pgbouncer pgbouncer-exporter prometheus redis registry statsd-exporter

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
build-platform: check-env update-base-tag
	PLATFORM_COMPONENTS="${PLATFORM_COMPONENTS}" \
	VENDOR_COMPONENTS="${VENDOR_COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-platform

.PHONY: push-platform
push-platform: check-env
	for component in ${PLATFORM_COMPONENTS} ; do \
		echo "Pushing ap-$${component}:${ASTRONOMER_VERSION} ======================"; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
	done;
	for component in ${VENDOR_COMPONENTS} ; do \
		echo "Pushing ap-$${component}:${ASTRONOMER_VERSION} ======================"; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
	done;

#
# Airflow build/push
#
.PHONY: build-airflow
build-airflow: check-env update-airflow-tag
	AIRFLOW_VERSIONS="${AIRFLOW_VERSIONS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-airflow

# TODO: Fix me for multiple airflow version support
# docker push ${REPOSITORY}/ap-airflow:${ASTRONOMER_VERSION}-$${version} || exit 1; \
# docker push ${REPOSITORY}/ap-airflow:${ASTRONOMER_VERSION}-$${version}-onbuild || exit 1; \
.PHONY: push-airflow
push-airflow: check-env
	for version in "${AIRFLOW_VERSIONS}" ; do \
		echo "Pushing ap-airflow:${ASTRONOMER_VERSION} ======================"; \
		docker push ${REPOSITORY}/ap-airflow:${ASTRONOMER_VERSION} || exit 1; \
		echo "Pushing ap-airflow:${ASTRONOMER_VERSION}-onbuild ======================"; \
		docker push ${REPOSITORY}/ap-airflow:${ASTRONOMER_VERSION}-onbuild || exit 1; \
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

.PHONY: update-tags
update-tags: check-env update-base-tag update-airflow-tag

# Update the base image version
.PHONY: update-base-tag
update-base-tag: check-env
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/FROM astronomerinc\/ap-base:(.*)/FROM astronomerinc\/ap-base:${ASTRONOMER_VERSION}/g' {} \;

# Update the base image version
.PHONY: update-airflow-tag
update-airflow-tag: check-env
	find docker/airflow -name 'Dockerfile' -exec sed -i -E 's/FROM astronomerinc\/ap-airflow:(.*)/FROM astronomerinc\/ap-airflow:${ASTRONOMER_VERSION}/g' {} \;

# Update the version (tag) that we grab from github from the platform repos
.PHONY: update-version
update-version: check-env
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/ARG VERSION=(.*)/ARG VERSION="v${ASTRONOMER_VERSION}"/g' {} \;

.PHONY: check-env
check-env:
ifndef ASTRONOMER_VERSION
	$(error ASTRONOMER_VERSION is not set)
endif
