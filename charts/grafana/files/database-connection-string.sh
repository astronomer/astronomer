#!/bin/sh
# Turn the Postgres URL in GRAFANA_DATABASE_URL into a quoted lib/pq key=value string in
# GF_DATABASE_CONNECTION_STRING, then exec the command in "$@" (grafana's run.sh).
#
# Grafana builds its own key=value string from GF_DATABASE_URL without quoting the values, so
# lib/pq drops a backslash in the password and splits it at a space or a single quote. Grafana
# uses [database] connection_string as given, so every value here is single-quoted, with
# backslash and single quote escaped by a backslash.
#
# The URL is split as Go's net/url splits it: the fragment, then the query, then the path, then
# the user info up to the last "@", and the user up to the first ":". The user, password and
# database name are percent-decoded; query parameters are decoded as Go's url.Query does, and
# are added after sslmode so that a sslmode in the URL wins, as it did with GF_DATABASE_URL.
# A URL that is empty or not postgres:// or postgresql:// goes to Grafana as GF_DATABASE_URL.
# Nothing read from the URL is ever printed.
set -eu

fail() {
  echo "grafana-database-connection-string: $*" >&2
  exit 1
}

# Percent-decode $1 byte by byte; with $2 = 1, decode "+" as a space first, as a query does.
# An invalid escape, or %00, fails, as it does in Go.
pct_decode() {
  printf '%s' "$1" | LC_ALL=C awk -v plus="${2:-0}" '
    BEGIN { for (i = 1; i < 256; i++) byte[sprintf("%02x", i)] = sprintf("%c", i) }
    {
      s = $0
      if (plus) gsub(/\+/, " ", s)
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

# Append " $1='$2'" to conn, with backslash and single quote in $2 escaped by a backslash.
add() {
  rest=$2
  quoted=
  while :; do
    plain=${rest%%[\\\']*}
    [ "$plain" != "$rest" ] || break
    rest=${rest#"$plain"}
    quoted=$quoted$plain\\${rest%"${rest#?}"}
    rest=${rest#?}
  done
  conn="$conn${conn:+ }$1='$quoted$rest'"
}

url=${GRAFANA_DATABASE_URL-}
unset GRAFANA_DATABASE_URL
case "$url" in
  postgres://* | postgresql://*) ;;
  *)
    [ -z "$url" ] || export GF_DATABASE_URL="$url"
    exec "$@"
    ;;
esac
[ "$(printf '%s' "$url" | LC_ALL=C tr -d '\000-\037\177')" = "$url" ] || fail "the database URL has a control character"

rest=${url#*://}
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
path=${path#/}
userinfo=
case "$authority" in
  *@*) userinfo=${authority%@*} ;;
esac
hostport=${authority##*@}
user=${userinfo%%:*}
password=
case "$userinfo" in
  *:*) password=${userinfo#*:} ;;
esac
case "$hostport" in
  \[*\]:*)
    host=${hostport%]:*}
    host=${host#[}
    port=${hostport##*]:}
    ;;
  \[*\])
    host=${hostport#[}
    host=${host%]}
    port=
    ;;
  *:*)
    host=${hostport%:*}
    port=${hostport##*:}
    ;;
  *)
    host=$hostport
    port=
    ;;
esac

# The trailing x keeps a decoded trailing newline from being dropped by the command substitution.
user=$(pct_decode "$user" && printf x) || fail "the user has an invalid percent-escape"
user=${user%x}
password=$(pct_decode "$password" && printf x) || fail "the password has an invalid percent-escape"
password=${password%x}
dbname=$(pct_decode "${path%%/*}" && printf x) || fail "the database name has an invalid percent-escape"
dbname=${dbname%x}

# The same defaults and settings Grafana uses when it builds the string from GF_DATABASE_URL.
conn=
add user "$user"
add host "${host:-127.0.0.1}"
add port "${port:-5432}"
add dbname "$dbname"
add sslmode "${GF_DATABASE_SSL_MODE:-disable}"
[ -z "${GF_DATABASE_CLIENT_CERT_PATH-}" ] || add sslcert "$GF_DATABASE_CLIENT_CERT_PATH"
[ -z "${GF_DATABASE_CLIENT_KEY_PATH-}" ] || add sslkey "$GF_DATABASE_CLIENT_KEY_PATH"
[ -z "${GF_DATABASE_CA_CERT_PATH-}" ] || add sslrootcert "$GF_DATABASE_CA_CERT_PATH"
[ -z "${GF_DATABASE_SSL_SNI-}" ] || add sslsni "$GF_DATABASE_SSL_SNI"
[ -z "$password" ] || add password "$password"

while [ -n "$query" ]; do
  param=${query%%&*}
  case "$query" in
    *\&*) query=${query#*&} ;;
    *) query= ;;
  esac
  key=${param%%=*}
  value=
  case "$param" in
    *=*) value=${param#*=} ;;
  esac
  key=$(pct_decode "$key" 1 && printf x) || fail "a query parameter has an invalid percent-escape"
  key=${key%x}
  value=$(pct_decode "$value" 1 && printf x) || fail "a query parameter has an invalid percent-escape"
  value=${value%x}
  [ -z "$key" ] || add "$key" "$value"
done

export GF_DATABASE_TYPE=postgres
export GF_DATABASE_CONNECTION_STRING="$conn"
exec "$@"
