MAKEFLAGS += --silent

AIRFLOW_IMAGE_NAME ?= astronomerio/airflow-saas

build-airflow:
	docker build -f images/airflow/Dockerfile -t $(AIRFLOW_IMAGE_NAME) images/airflow

clean-containers:
	for container in `docker ps -aq -f label=io.astronomer.docker=true` ; do \
		docker rm -f $${container} ; \
	done

clean-images:
	for image in `docker images -q -f label=io.astronomer.docker=true` ; do \
		docker rmi -f $${image} ; \
	done

clean: clean-containers clean-images
