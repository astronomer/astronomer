# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images.
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds.
BUILD_NUMBER ?= 1

# Astronomer build version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 5
ASTRONOMER_PATCH_VERSION ?= 0
ASTRONOMER_VERSION ?= "${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}"

# List of all components and order to build.
PLATFORM_COMPONENTS := base airflow cli-install commander db-bootstrapper default-backend houston-api orbit-ui

# Airflow versions
AIRFLOW_VERSIONS := 1.9.0

# Vendor components
VENDOR_COMPONENTS := cadvisor grafana nginx pgbouncer pgbouncer-exporter prometheus redis registry statsd-exporter

# Set default for make.
.DEFAULT_GOAL := build

#
# Main build/push
#
.PHONY: build
build:
	$(MAKE) build-platform
	# $(MAKE) build-airflow

.PHONY: push
push: clean-images build
	$(MAKE) push-platform
	$(MAKE) push-airflow

#
# RC build/push
#
.PHONY: build-rc
build-rc: clean-rc-images
ifndef ASTRONOMER_RC_VERSION
	$(error ASTRONOMER_RC_VERSION must be defined)
endif
ifndef ASTRONOMER_EDGE_COMPONENTS
	$(error ASTRONOMER_EDGE_COMPONENTS must be defined)
endif
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} ASTRONOMER_EDGE_COMPONENTS=${ASTRONOMER_EDGE_COMPONENTS} build-platform

.PHONY: push-rc
push-rc: build-rc
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} push-platform
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} push-airflow

#
# Platform build/push
#
.PHONY: build-platform
build-platform:
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
push-airflow: build-airflow
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

.PHONY: clean-rc-images
clean-rc-images:
	for image in `docker images -q -f label=io.astronomer.docker.rc=true` ; do \
		docker rmi -f $${image} ; \
	done

.PHONY: clean
clean: clean-containers clean-images clean-rc-images
