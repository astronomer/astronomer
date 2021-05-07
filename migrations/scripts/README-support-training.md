# Support training or development of the upgrade script

First, you can deploy an old version of Astronomer on our AWS development account using an old version of the Astronomer Enterprise Terraform module.

```ruby
provider "aws" {
  region = "us-east-1"
}

provider "acme" {
  server_url = "https://acme-v02.api.letsencrypt.org/directory"
}

variable deployment_id {
  description = "The name part of your astro email, for example 'steven' if you email is 'steven@astronomer.io'"
}

variable route53_domain {
  default = "astronomer-development.com"
}

module "astronomer_aws_from_scratch" {
  source          = "astronomer/astronomer-enterprise/aws"

  # If you intended to install Astronomer version 0.11.* or earlier, then use this exact version
  # If you intended to install a version of Astronomer 0.12.* or newer, then use the latest version of the module by deleting this line.
  version         = "1.0.221"

  # you can pick any EKS-supported version here
  cluster_version = "1.18"

  # you can pick any Astronomer version here
  astronomer_version = "0.10.2"

  email = "{var.deployment_id}@astronomer.io"

  # supply your public DNS hosted zone name
  route53_domain = var.route53_domain

  # EKS kubernetes management endpoint
  management_api = "public"

  enable_bastion     = false
  enable_windows_box = false

  # This configuration serves the platform publicly
  allow_public_load_balancers = true

  # You may add additional Astronomer configurations in this YAML block
  astronomer_helm_values      = <<EOF
  global:
    baseDomain: ${var.deployment_id}.${var.route53_domain}
    tlsSecret: astronomer-tls
  nginx:
    privateLoadBalancer: false
  astronomer:
    houston:
      config:
        publicSignups: false
  EOF
  # Choose tags for the AWS resources
  tags = {
    "OWNER" = var.deployment_id
  }
}
```

Then, you can use the old Astronomer version by setting up deployments and so forth. Then follow the directions in the README of this repository to run the upgrade script.
