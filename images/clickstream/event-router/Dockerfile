#
# Copyright 2016 Astronomer Inc.
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

FROM astronomerio/alpine-librdkafka-golang:1.9-0.11.0-r0 as builder
MAINTAINER Astronomer <humans@astronomer.io>

RUN apk update && apk add git
RUN go get -v github.com/astronomerio/cs-event-router
WORKDIR /go/src/github.com/astronomerio/cs-event-router
RUN make build

FROM alpine:3.4
COPY --from=builder /go/src/github.com/astronomerio/cs-event-router/event-router /event-router
RUN apk update && apk add ca-certificates curl && update-ca-certificates
EXPOSE 9091
ENTRYPOINT ["/event-router"]
