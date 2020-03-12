#!/usr/bin/env bash
set -eou pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT="$DIR/../.."

# Get the code on the VM (you can use scp too)
git clone https://github.com/astronomer/astronomer
pushd astronomer

# Prep and start Kind
$ROOT/bin/install-ci-tools
$ROOT/bin/setup-kind

# Astronomer Install
$ROOT/bin/install-platform
$ROOT/bin/waitfor-platform

