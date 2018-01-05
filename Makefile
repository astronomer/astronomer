# You can override vars like REPOSITORY in a local.make file
-include local.make

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds.
BUILD_NUMBER ?= 1

ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 0
ASTRONOMER_PATCH_VERSION ?= 11
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of all components and order to build.
PLATFORM_COMPONENTS := base event-api event-router airflow
PLATFORM_ONBUILD_COMPONENTS := airflow
VENDOR_COMPONENTS := cadvisor grafana prometheus statsd-exporter
ALL_COMPONENTS := ${PLATFORM_COMPONENTS} ${VENDOR_COMPONENTS}

# Public repository for images.
REPOSITORY ?= astronomerinc

build:
	PLATFORM_COMPONENTS="${PLATFORM_COMPONENTS}" \
	VENDOR_COMPONENTS="${VENDOR_COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-images

push-public: clean build
	for component in ${ALL_COMPONENTS} ; do \
		echo "Pushing ap-$${component} ========================================"; \
		docker push ${REPOSITORY}/ap-$${component}:latest || exit 1; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
	done; \
	for component in ${PLATFORM_ONBUILD_COMPONENTS} ; do \
		docker push ${REPOSITORY}/ap-$${component}:latest-onbuild || exit 1; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION}-onbuild || exit 1; \
	done

clean-containers:
	for container in `docker ps -aq -f label=io.astronomer.docker=true` ; do \
		docker rm -f -v $${container} ; \
	done

clean-images:
	for image in `docker images -q -f label=io.astronomer.docker=true` ; do \
		docker rmi -f $${image} ; \
	done

clean: clean-containers clean-images
