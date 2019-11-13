# Based off https://github.com/andyshinn/docker-alpine-abuild but for apline 3.5
FROM alpine:3.10
RUN apk --no-cache add alpine-sdk coreutils \
  && adduser -G abuild -g "Alpine Package Builder" -s /bin/ash -D builder \
  && echo "builder ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
  && mkdir /packages \
  && chown builder:abuild /packages
COPY /abuilder /bin/
USER builder
ENTRYPOINT ["abuilder", "-r"]
WORKDIR /home/builder/package
ENV RSA_PRIVATE_KEY_NAME ssh.rsa
ENV PACKAGER_PRIVKEY /home/builder/${RSA_PRIVATE_KEY_NAME}
ENV REPODEST /packages

ENV PACKAGER Astronomer <humans@astronomer.io>
ENV PACKAGER_PRIVKEY /home/builder/.abuild/keys/humans@astronomer.io.rsa

USER root
# Since we are building python3 deps.
RUN apk --no-cache add python3-dev py3-setuptools
USER builder
