#!/bin/bash
# ec2-setup.sh - Setup script for EC2 instance

# Update system packages
sudo yum update -y

sudo yum install -y git

# Install Python 3.11 (if needed beyond the CircleCI image)
sudo yum install python3 -y

# Install Docker (often needed for integration tests)
sudo amazon-linux-extras install docker -y
systemctl start docker
systemctl enable docker
usermod -a -G docker ec2-user

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# For AMD64 / x86_64
[ $(uname -m) = x86_64 ] && curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-amd64
# For ARM64
[ $(uname -m) = aarch64 ] && curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-arm64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install mkcert
# First install dependencies
sudo yum install -y golang nss-tools
# Then install mkcert
go install filippo.io/mkcert@latest
sudo cp ~/go/bin/mkcert /usr/local/bin/

echo "EC2 instance setup complete!"
