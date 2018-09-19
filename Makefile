# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds
BUILD_NUMBER ?= 1

# Astronomer build version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 5
ASTRONOMER_PATCH_VERSION ?= 1
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of all components and order to build
PLATFORM_COMPONENTS := base airflow cli-install commander db-bootstrapper default-backend houston-api orbit-ui

# Airflow versions
AIRFLOW_VERSIONS := 1.9.0 #1.10.0

# Vendor components
VENDOR_COMPONENTS := cadvisor grafana nginx pgbouncer pgbouncer-exporter prometheus redis registry statsd-exporter

# Set default for make
.DEFAULT_GOAL := build

#
# Main build/push
#
.PHONY: build
build:
	$(MAKE) build-platform
	$(MAKE) build-airflow

.PHONY: push
push: clean-images build
	$(MAKE) push-platform
	$(MAKE) push-airflow

#
# Platform build/push
#
.PHONY: build-platform
build-platform: clean-master-images update-base-tag
	PLATFORM_COMPONENTS="${PLATFORM_COMPONENTS}" \
	VENDOR_COMPONENTS="${VENDOR_COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-platform

.PHONY: push-platform
push-platform:
	for component in ${PLATFORM_COMPONENTS} ; do \
		echo "Pushing ap-$${component}:${ASTRONOMER_VERSION} ======================"; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
	done;

#
# Airflow build/push
#
.PHONY: build-airflow
build-airflow:
	AIRFLOW_VERSIONS="${AIRFLOW_VERSIONS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-airflow

.PHONY: push-airflow
push-airflow:
	for version in "${AIRFLOW_VERSIONS}" ; do \
		echo "Pushing ap-$${component}:${AIRFLOW_VERSION}-${AIRFLOW_BUILD} ======================"; \
		docker push ${REPOSITORY}/ap-$${component}:${AIRFLOW_VERSION}-${version} || exit 1; \
		docker push ${REPOSITORY}/ap-$${component}:${AIRFLOW_VERSION}-${version}-onbuild || exit 1; \
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

.PHONY: clean-master-images
clean-master-images:
	for image in `docker images -q -f label=io.astronomer.docker.master=true` ; do \
		docker rmi -f $${image} ; \
	done

.PHONY: clean
clean: clean-containers clean-images clean-master-images

# Update the base image version
.PHONY: update-base-tag
update-base-tag:
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/FROM astronomerinc\/ap-base:(.*)/FROM astronomerinc\/ap-base:${ASTRONOMER_VERSION}/g' {} \;

# Update the version (tag) that we grab from github from the platform repos
.PHONY: update-version
update-version:
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/ARG VERSION=(.*)/ARG VERSION="v${ASTRONOMER_VERSION}"/g' {} \;
