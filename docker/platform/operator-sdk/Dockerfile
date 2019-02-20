FROM alpine:3.6

ARG operator_sdk_version=0.5.0

ADD https://github.com/operator-framework/operator-sdk/releases/download/v${operator_sdk_version}/operator-sdk-v${operator_sdk_version}-x86_64-linux-gnu /usr/bin/operator-sdk

RUN chmod +x /usr/bin/operator-sdk

RUN apk add --update alpine-sdk docker