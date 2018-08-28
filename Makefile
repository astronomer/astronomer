# Public repository for charts.
DOMAIN ?= helm.astronomer.io
URL ?= https://${DOMAIN}
BUCKET ?= gs://${DOMAIN}

# Version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 4
ASTRONOMER_PATCH_VERSION ?= 2
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of charts to build
CHARTS := astronomer airflow grafana prometheus nginx

# Output directory
OUTPUT := repository

.PHONY: build
build:
	mkdir -p ${OUTPUT}
	for chart in ${CHARTS} ; do \
		helm package --version ${ASTRONOMER_VERSION} -d ${OUTPUT} charts/$${chart} || exit 1; \
	done; \
	$(MAKE) build-index

.PHONY: build-index
build-index:
	helm repo index ${OUTPUT} --url ${URL}

.PHONY: push
push: build
	@read -p "Are you sure you want to push a production release? Ctrl+c to abort." ans;
	$(MAKE) push-repo

.PHONY: push-repo
push-repo:
	for chart in ${CHARTS} ; do \
		gsutil cp -a public-read ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}.tgz ${BUCKET} || exit 1; \
	done; \
	$(MAKE) push-index

.PHONY: push-index
push-index: build-index
	gsutil cp -a public-read ${OUTPUT}/index.yaml ${BUCKET}

.PHONY: clean
clean:
	for chart in ${CHARTS} ; do \
		rm ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}.tgz || exit 1; \
	done; \

.PHONY: build-rc
build-rc:
ifndef ASTRONOMER_RC_VERSION
	$(error ASTRONOMER_RC_VERSION must be defined)
endif
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} build

.PHONY: push-rc
push-rc: build-rc
	$(MAKE) ASTRONOMER_VERSION=${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION} push-repo

.PHONY: clean-rc
clean-rc:
ifndef ASTRONOMER_RC_VERSION
	$(error ASTRONOMER_RC_VERSION must be defined)
endif
	for chart in ${CHARTS} ; do \
		rm ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}-rc.${ASTRONOMER_RC_VERSION}.tgz || exit 1; \
	done; \
