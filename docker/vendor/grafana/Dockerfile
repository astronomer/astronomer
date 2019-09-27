#
# Copyright 2016 Astronomer Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
FROM grafana/grafana:6.3.3
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER

# Copy default dashboards and datasource configuration
COPY include/dashboard.yaml /etc/grafana/provisioning/dashboards/dashboard.yaml
COPY include/nginx-ingress.json /var/lib/grafana/dashboards/nginx-ingress.json
COPY include/airflow-overview.json /var/lib/grafana/dashboards/airflow-overview.json
COPY include/airflow-scheduler.json /var/lib/grafana/dashboards/airflow-scheduler.json
COPY include/airflow-containers.json /var/lib/grafana/dashboards/airflow-containers.json
COPY include/airflow-state.json /var/lib/grafana/dashboards/airflow-state.json
COPY include/airflow-database-activity.json /var/lib/grafana/dashboards/airflow-database-activity.json
COPY include/fluentd.json /var/lib/grafana/dashboards/fluentd.json
COPY include/elasticsearch.json /var/lib/grafana/dashboards/elasticsearch.json
COPY include/prometheus.json /var/lib/grafana/dashboards/prometheus.json
COPY include/docker-registry.json /var/lib/grafana/dashboards/docker-registry.json
COPY include/platform-overview.json /var/lib/grafana/dashboards/platform-overview.json
COPY include/kubernetes-pods-metrics.json /var/lib/grafana/dashboards/kubernetes-pods-metrics.json
