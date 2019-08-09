#!/usr/bin/env bash

# Make sure you installed and run
# docker run -p 5432:5432 -d --name db arminc/clair-db:latest
# and
# docker run -p 6060:6060 --link db:postgres -d --name clair arminc/clair-local-scan:latest

RELEASE_TAG=master
declare -a TARGET_IMAGES=("ap-base"
                          "ap-airflow"
                          "ap-alertmanager"
                          "ap-cadvisor"
                          "ap-curator"
                          "ap-elasticsearch"
                          "ap-elasticsearch-exporter"
                          "ap-fluentd"
                          "ap-grafana"
                          "ap-kibana"
                          "ap-kube-replicator"
                          "ap-kube-state"
                          "ap-nginx"
                          "ap-nginx-es"
                          "ap-pgbouncer"
                          "ap-pgbouncer-exporter"
                          "ap-prisma"
                          "ap-prometheus"
                          "ap-redis"
                          "ap-registry"
                          "ap-statsd-exporter")


for i in "${TARGET_IMAGES[@]}"
do
   image="astronomerinc/$i:$RELEASE_TAG"
   echo "scanning: $image"
   docker pull $image > results.log
   clair-scanner --ip=192.168.1.199 $image &> "${i}_results.txt"
   high_count=`grep High ${i}_results.txt | wc -l`
   medium_count=`grep Medium ${i}_results.txt | wc -l`
   low_count=`grep Low ${i}_results.txt | wc -l`
   negligible_count=`grep Negligible ${i}_results.txt | wc -l`
   unknown_count=`grep Unknown ${i}_results.txt | wc -l`
   echo "Docker image \"$image\" have: ${high_count//[[:space:]]/} High / ${medium_count//[[:space:]]/} Medium / ${low_count//[[:space:]]/} Low"
done
