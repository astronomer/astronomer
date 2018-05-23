# You can override vars like REPOSITORY in a local.make file
-include local.make

# Public repository for images.
REPOSITORY ?= astronomerinc

# Bump this on subsequent build, reset on new version or public release. Inherit from env for CI builds.
BUILD_NUMBER ?= 1

ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 2
ASTRONOMER_PATCH_VERSION ?= 1
ASTRONOMER_VERSION ?= "${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}"

# List of all components and order to build.
PLATFORM_COMPONENTS := base default-backend commander houston-api airflow
PLATFORM_ONBUILD_COMPONENTS := airflow
VENDOR_COMPONENTS := nginx registry cadvisor grafana prometheus statsd-exporter
ALL_COMPONENTS := ${PLATFORM_COMPONENTS} ${VENDOR_COMPONENTS}

# Documentation build vars.
DOCS_DOMAIN ?= open.astronomer.io
DOCS_BUCKET ?= gs://${DOCS_DOMAIN}
DOCS_SRC := docs
DOCS_DEST := docs/_site

# Set default for make.
.DEFAULT_GOAL := build

.PHONY: build
build:
	PLATFORM_COMPONENTS="${PLATFORM_COMPONENTS}" \
	VENDOR_COMPONENTS="${VENDOR_COMPONENTS}" \
	REPOSITORY=${REPOSITORY} \
	ASTRONOMER_VERSION=${ASTRONOMER_VERSION} \
	BUILD_NUMBER=${BUILD_NUMBER} \
	bin/build-images

.PHONY: push-images
push-images: clean build
	for component in ${ALL_COMPONENTS} ; do \
		echo "Pushing ap-$${component} ========================================"; \
		docker push ${REPOSITORY}/ap-$${component}:latest || exit 1; \
		docker push ${REPOSITORY}/ap-$${component}:${ASTRONOMER_VERSION} || exit 1; \
	done; \
	for component in ${PLATFORM_ONBUILD_COMPONENTS} ; do \
		docker push ${REPOSITORY}/ap-$${component}:latest-onbuild || exit 1; \
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

.PHONY: clean
clean: clean-containers clean-images

.PHONY: build-docs
build-docs:
	jekyll build --source ${DOCS_SRC} --destination ${DOCS_DEST}

.PHONY: push-docs
push-docs: build-docs
	gsutil \
		-h "Cache-Control:public, max-age=300" \
		-m rsync -a public-read -d -r ${DOCS_DEST} ${DOCS_BUCKET}
