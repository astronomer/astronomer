TOP=$(abspath $(dir $(lastword $(MAKEFILE_LIST))))

APKBUILD_FILES=$(wildcard */APKBUILD)
APK_FILES=$(patsubst %/APKBUILD,%/.built,$(APKBUILD_FILES))

.PHONY: all

all: $(APK_FILES)

# Explict deps: we need our cython and numpy built before we can build these packages
py3-cassandra-driver/.built py3-grpcio/.built py3-numpy: cython/.built
py3-pandas/.built : py3-numpy/.built


keys repo:
	mkdir $@

keys/humans@astronomer.io.rsa: | keys
	openssl genrsa -out $@ 2048
	@# When we re-generate the key we have to remove the index file else abuild will fail with "BAD signature"
	rm repo/x86_64/APKINDEX.tar.gz

keys/%.rsa.pub: keys/%.rsa
	openssl rsa -in $< -pubout -out $@

$(APK_FILES): %/.built: %/APKBUILD apk-builder/.image_id keys/humans@astronomer.io.rsa.pub | repo
	docker run --rm -ti \
		-v $(TOP)/keys/humans@astronomer.io.rsa.pub:/etc/apk/keys/humans@astronomer.io.rsa.pub \
		-v $(TOP)/keys:/home/builder/.abuild/keys \
		-v $(TOP)/repo:/packages/builder \
		-v $(dir $(abspath $<)):/home/builder/package \
		apk-builder
	touch $@

#$(foreach apkbuild,$(APKBUILD_FILES),$(eval $(call define_compile_rules,$(apkbuild))))


apk-builder/.image_id: apk-builder/Dockerfile
	docker build --pull --iidfile $@ -t apk-builder apk-builder/
