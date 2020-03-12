#!/usr/bin/env bash
set -euo pipefail

# Adapted from
# https://docs.docker.com/install/linux/docker-ce/ubuntu/

# Dependencies
sudo apt-get update -y
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg-agent \
    software-properties-common

# Docker repo
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo apt-key fingerprint 0EBFCD88
sudo add-apt-repository \
	"deb [arch=amd64] https://download.docker.com/linux/ubuntu \
	$(lsb_release -cs) \
	stable"

# Install Docker
sudo apt-get update -y
sudo apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io

# Test Deocker
sudo docker run hello-world

# Non-sudo
# sudo groupadd docker (already added during install)
sudo usermod -aG docker $USER

