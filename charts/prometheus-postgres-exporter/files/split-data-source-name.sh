#!/bin/sh
# Split the exporter's connection string into the files postgres_exporter reads through
# DATA_SOURCE_USER_FILE, DATA_SOURCE_PASS_FILE and DATA_SOURCE_URI_FILE. It has no
# DATA_SOURCE_NAME_FILE, so with secretsFromFiles on, this init container is what keeps the
# default connectionSecret form out of the exporter's environment.
#
# Usage: split-data-source-name.sh <connection-string-file> <output-dir>
#
# The URL is split the way postgres_exporter's parser (Go's net/url) splits DATA_SOURCE_NAME:
# the fragment, then the query, then the path, then the user info up to the last "@", and the
# user up to the first ":". The user and password are percent-decoded, because postgres_exporter
# encodes them again; the host, path and query are kept as written, because it puts them back
# into a URL. Nothing read from the file is ever printed.
set -eu
umask 077

fail() {
  echo "split-data-source-name: $*" >&2
  exit 1
}

# Percent-decode $1 byte by byte. An invalid escape, or %00, fails, as it does in Go.
pct_decode() {
  printf '%s' "$1" | LC_ALL=C awk '
    BEGIN { for (i = 1; i < 256; i++) byte[sprintf("%02x", i)] = sprintf("%c", i) }
    {
      s = $0
      out = ""
      while ((i = index(s, "%")) > 0) {
        h = tolower(substr(s, i + 1, 2))
        if (!(h in byte)) { bad = 1; exit }
        out = out substr(s, 1, i - 1) byte[h]
        s = substr(s, i + 3)
      }
      printf "%s", out s
    }
    END { exit bad }'
}

[ "$#" -eq 2 ] || fail "usage: split-data-source-name.sh <connection-string-file> <output-dir>"
[ -s "$1" ] || fail "the connection string file $1 is missing or empty"
dsn=$(cat "$1")

[ "$(printf '%s' "$dsn" | LC_ALL=C tr -d '\000-\037\177')" = "$dsn" ] || fail "the connection string has a control character"
case "$dsn" in
  postgres://* | postgresql://*) ;;
  *) fail "the connection string is not a postgres:// or postgresql:// URL" ;;
esac
case "$dsn" in
  *,*) fail "the connection string has a comma, which postgres_exporter reads as a list of connection strings; percent-encode it as %2C" ;;
esac

rest=${dsn#*://}
rest=${rest%%#*}
query=
case "$rest" in
  *\?*)
    query=${rest#*\?}
    rest=${rest%%\?*}
    ;;
esac
authority=${rest%%/*}
path=${rest#"$authority"}
case "$authority" in
  *@*) ;;
  *) fail "the connection string has no user" ;;
esac
userinfo=${authority%@*}
host=${authority##*@}
[ -n "$host" ] || fail "the connection string has no host"
user=${userinfo%%:*}
password=
case "$userinfo" in
  *:*) password=${userinfo#*:} ;;
esac

# The trailing x keeps a decoded trailing newline from being dropped by the command substitution.
user=$(pct_decode "$user" && printf x) || fail "the user has an invalid percent-escape"
user=${user%x}
password=$(pct_decode "$password" && printf x) || fail "the password has an invalid percent-escape"
password=${password%x}
for value in "$user" "$password"; do
  case "$value" in
    [[:space:]]* | *[[:space:]]) fail "the user or password starts or ends with whitespace, which postgres_exporter trims from its files" ;;
  esac
done

printf '%s' "$user" >"$2/data_source_user"
printf '%s' "$password" >"$2/data_source_password"
printf '%s%s%s' "$host" "$path" "${query:+?$query}" >"$2/data_source_uri"
echo "split-data-source-name: wrote the user, password and URI files for postgres_exporter"
