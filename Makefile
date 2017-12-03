MAKEFLAGS += --silent

ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 0
ASTRONOMER_PATCH_VERSION ?= 1
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

COMPONENTS := base cs-event-api cs-event-router airflow

REPOSITORY ?= astronomerio

build-alpine:
	COMPONENTS="${COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	bin/build-alpine

clean-containers:
	for container in `docker ps -aq -f label=io.astronomer.docker=true` ; do \
		docker rm -f $${container} ; \
	done

clean-images:
	for image in `docker images -q -f label=io.astronomer.docker=true` ; do \
		docker rmi -f $${image} ; \
	done

clean: clean-containers clean-images
