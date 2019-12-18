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

FROM registry.access.redhat.com/ubi7/ubi:7.7
LABEL maintainer="Astronomer <humans@astronomer.io>"

ARG BUILD_NUMBER=-1
LABEL io.astronomer.docker=true
LABEL io.astronomer.docker.build.number=$BUILD_NUMBER


ENV PATH=${PATH}:/opt/rh/rh-python36/root/usr/bin
ENV LC_ALL="en_US.UTF-8"
ENV LANG="en_US.UTF-8"

RUN yum --disableplugin=subscription-manager -y update \
    && yum --disableplugin=subscription-manager --setopt=tsflags=noscripts -y install \
        coreutils \
		rh-python36 \
        rh-python36-python-devel \
        rh-python36-python-pip \
        rh-python36-python-setuptools \       
        gcc \
        kernel-headers \
        libffi \
		libffi-devel \
	&& scl enable rh-python36 'pip install --no-cache-dir --upgrade pip && \
		pip install --no-cache-dir --upgrade setuptools && \
		pip install --upgrade pip && \
        pip install wheel && \
        pip install elasticsearch-curator==5.7.6 && \
        pip install boto3==1.9.143 && \
        pip install requests-aws4auth==0.9 && \
        pip install cryptography==2.6.1 && \
        pip install pyOpenSSL ' \
# We can uninstall the packages to save around 150 MB. or to keep the binaries, comment out the below line
#	&& yum  --disableplugin=subscription-manager --setopt=tsflags=noscripts -y history undo last-1 \
	&& yum  --disableplugin=subscription-manager -y clean all \
    && ln -s /opt/rh/rh-python36/root/usr/bin/curator /usr/bin/curator \
    && sed -i '/import sys/a urllib3.contrib.pyopenssl.inject_into_urllib3()' /usr/bin/curator \
    && sed -i '/import sys/a import urllib3.contrib.pyopenssl' /usr/bin/curator \
    && sed -i '/import sys/a import urllib3' /usr/bin/curator

USER nobody:nobody

ENTRYPOINT ["/usr/bin/curator"]