# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds
BUILD_NUMBER ?= 1

# List of all components and order to build
PLATFORM_COMPONENTS := base cli-install commander db-bootstrapper default-backend houston-api orbit-ui

# List of drone repositories to create secrets for
DRONE_REPOSITORIES := astronomer commander db-bootstrapper default-backend houston-api orbit-ui
# HELM_REPOSITORY := helm.astronomer.io
GITHUB_ORG := astronomer

# Airflow versions
AIRFLOW_VERSIONS := 1.10.5

# Vendor components
VENDOR_COMPONENTS := alertmanager cadvisor curator elasticsearch elasticsearch-exporter fluentd grafana kibana kubed kube-state nginx nginx-es pgbouncer pgbouncer-exporter prisma prometheus redis registry statsd-exporter

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
	for version in ${AIRFLOW_VERSIONS} ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-airflow \
		PUSH_TAGS="${ASTRONOMER_VERSION}-$${version} ${ASTRONOMER_VERSION}-$${version}-onbuild" \
		bin/push-image; \
	done;

.PHONY: push-airflow-ref
push-airflow-ref:
	for version in ${AIRFLOW_VERSIONS} ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-airflow \
		PUSH_TAGS="${ASTRONOMER_REF}-$${version} ${ASTRONOMER_REF}-$${version}-onbuild" \
		bin/push-image; \
	done;

.PHONY: scan-platform
scan-platform: check-env
	for component in ${PLATFORM_COMPONENTS} ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-$${component} \
		PUSH_TAGS="${ASTRONOMER_REF}" \
		bin/clair-scan || exit 1 ; \
	done;
	for component in ${VENDOR_COMPONENTS} ; do \
		PUSH_IMAGE=${REPOSITORY}/ap-$${component} \
		PUSH_TAGS="${ASTRONOMER_REF}" \
		bin/clair-scan || exit 1 ; \
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

# Update all tags
.PHONY: update-tags
update-tags: update-platform-git-tags update-platform-docker-tags update-airflow-onbuild-docker-tags

# Update the version (tag) that we grab from github from the platform repos
.PHONY: update-platform-git-tags
update-platform-git-tags: check-env
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/ARG VERSION=(.*)/ARG VERSION="v${ASTRONOMER_VERSION}"/g' {} +

# Update the base image version
.PHONY: update-platform-docker-tags
update-platform-docker-tags: check-env
	find docker/platform -name 'Dockerfile' -exec sed -i -E 's/FROM astronomerinc\/ap-base:(.*)/FROM astronomerinc\/ap-base:${ASTRONOMER_VERSION}/g' {} +

# Update the base image version
.PHONY: update-airflow-onbuild-docker-tags
update-airflow-onbuild-docker-tags: check-env
	for version in ${AIRFLOW_VERSIONS} ; do \
		find docker/airflow/$${version} -name 'Dockerfile' -exec sed -i -E "s/FROM astronomerinc\/ap-airflow:(.*)/FROM astronomerinc\/ap-airflow:${ASTRONOMER_VERSION}-$${version}/g" {} + ;\
	done;

.PHONY: check-env
check-env:
ifndef ASTRONOMER_VERSION
	$(error ASTRONOMER_VERSION is not set)
endif

# Configure common drone secrets
# TODO: Automate gcp_token and git_push_ssh_keys for astronomer and helm
.PHONY: drone
drone:
ifndef DOCKER_USERNAME
	$(error DOCKER_USERNAME is not set)
endif
ifndef DOCKER_PASSWORD
	$(error DOCKER_PASSWORD is not set)
endif
ifndef GITHUB_TOKEN
	$(error GITHUB_TOKEN is not set)
endif
ifndef DRONE_TOKEN
	$(error DRONE_TOKEN is not set)
endif
ifndef GCP_TOKEN
	$(error GCP_TOKEN is not set)
endif
	for repo in ${DRONE_REPOSITORIES} ; do \
		drone secret add --repository "${GITHUB_ORG}/$${repo}" --name docker_username --value ${DOCKER_USERNAME}; \
		drone secret add --repository "${GITHUB_ORG}/$${repo}" --name docker_password --value ${DOCKER_PASSWORD}; \
		drone secret add --repository "${GITHUB_ORG}/$${repo}" --name github_api_key --value ${GITHUB_TOKEN}; \
		drone secret add --repository "${GITHUB_ORG}/$${repo}" --name downstream_token --value ${DRONE_TOKEN}; \
	done;
	# $(eval TOKEN := $(shell cat $(GCP_TOKEN))); \
	# drone secret add --repository ${HELM_REPOSITORY} --name gcp_token --value ${TOKEN}
