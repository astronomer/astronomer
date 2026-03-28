# cert_check.sh

This script validates TLS certificates, checks SANs, expiration, and verifies CA trust on macOS and Linux systems.

## Requirements

The following tools must be installed and available:

- bash
- openssl

OS support:
- macOS
- Linux

## Usage

```bash
Usage: ./cert_check.sh <certificate.crt> <values.yaml> [rootCA.pem]

Arguments:
  <certificate.crt> - Required
  <values.yaml>     - Required
  [rootCA.pem]      - Optional
