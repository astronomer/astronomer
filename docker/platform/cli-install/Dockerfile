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

FROM astronomerinc/ap-base:0.10.0-alpha.1
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER
LABEL io.astronomer.docker.module="astronomer"
LABEL io.astronomer.docker.component="install"

# Install packages
RUN apk update \
	&& apk add --no-cache \
		nginx \
	&& mkdir -p /run/nginx

# Copy NGINX configuration to default location
COPY include/nginx.conf /etc/nginx/nginx.conf

# Copy install.sh to server root
COPY include/install.sh /usr/share/nginx/html/

# Expose HTTP
EXPOSE 80 443

# Run NGINX
ENTRYPOINT ["nginx", "-g", "daemon off;"]
