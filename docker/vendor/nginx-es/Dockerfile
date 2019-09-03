#
# Copyright 2018 Astronomer Inc.
#
# Licensed under the Apache License, Version 3.0 (the "License");
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

FROM alpine:3.10.2
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="default-backend"
LABEL io.astronomer.docker.component="default-backend"

ENV SERVER_ROOT="/usr/share/nginx/html"

# Install NGINX
RUN apk add --no-cache nginx

# Run mkdir to create nginx directory
RUN mkdir -p /run/nginx

# NGINX is configured to listen on 9200
EXPOSE 9200

# Run NGINX
ENTRYPOINT ["nginx", "-g", "daemon off;"]
