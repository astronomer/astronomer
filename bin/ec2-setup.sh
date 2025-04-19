#!/bin/bash
# ec2-setup.sh - Setup script for EC2 instance

# Update system packages
yum update -y

# Install Python 3.11 (if needed beyond the CircleCI image)
amazon-linux-extras install python3.11 -y

# Install Docker (often needed for integration tests)
amazon-linux-extras install docker -y
systemctl start docker
systemctl enable docker
usermod -a -G docker ec2-user

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
mv kubectl /usr/local/bin/

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install mkcert
# First install dependencies
yum install -y golang nss-tools
# Then install mkcert
go install filippo.io/mkcert@latest
cp ~/go/bin/mkcert /usr/local/bin/

# Install your application dependencies
pip install -r /path/to/requirements.txt

echo "EC2 instance setup complete!"