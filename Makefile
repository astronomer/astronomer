# You can override vars like REPOSITORY in a local.make file
-include local.make

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds.
BUILD_NUMBER ?= 1

ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 0
ASTRONOMER_PATCH_VERSION ?= 5
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

COMPONENTS := base event-api event-router airflow
REPOSITORY ?= astronomerinc

build-alpine:
	COMPONENTS="${COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-alpine

push-public: clean build-alpine
	for component in ${COMPONENTS} ; do \
		echo "Pushing ap-$${component} ========================================"; \
		docker push ${REPOSITORY}/ap-$${component}:latest || exit 1; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
  	done

clean-containers:
	for container in `docker ps -aq -f label=io.astronomer.docker=true` ; do \
		docker rm -f $${container} ; \
	done

clean-images:
	for image in `docker images -q -f label=io.astronomer.docker=true` ; do \
		docker rmi -f $${image} ; \
	done

clean: clean-containers clean-images
