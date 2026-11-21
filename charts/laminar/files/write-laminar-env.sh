#!/bin/sh
# Write laminar's settings file: the chart's laminar.env, then the JWKS as a laminar_jwks
# setting. laminar has no file setting for its JWKS, so with secretsFromFiles on this init
# container is what keeps the certificate out of its environment. laminar loads laminar.env
# from its working directory, and gives it precedence over its environment variables.
#
# Usage: write-laminar-env.sh <laminar.env> <jwks-file> <output-file>
#
# The certificate is written last, so it wins over a laminar_jwks line in the chart's file. It
# goes in a double-quoted value, in which python-dotenv expands backslash escapes and ${...},
# so a double quote, backslash or dollar sign would not arrive intact. A PEM certificate never
# contains one, so the script refuses them rather than write a value laminar would misread.
# Nothing read from the certificate file is printed.
set -eu
umask 077

fail() {
  echo "write-laminar-env: $*" >&2
  exit 1
}

[ "$#" -eq 3 ] || fail "usage: write-laminar-env.sh <laminar.env> <jwks-file> <output-file>"
[ -r "$1" ] || fail "cannot read the settings file $1"
[ -s "$2" ] || fail "the JWKS certificate file $2 is missing or empty"
jwks=$(cat "$2")
case "$jwks" in
  *[\"\\\$]*) fail "the JWKS certificate file $2 holds a double quote, backslash or dollar sign, so it is not a PEM certificate" ;;
esac

{
  cat "$1"
  printf '\nlaminar_jwks="%s"\n' "$jwks"
} >"$3"
echo "write-laminar-env: wrote $3 with the JWKS from $2"
