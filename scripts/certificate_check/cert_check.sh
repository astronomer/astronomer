#!/usr/bin/env bash
#set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
VIOLET='\033[0;35m'
NC='\033[0m'

CN_VALID=false
EXPIRATION_VALID=true
CERT_TRUSTED=false
SAN_VALID=false

CERT="$1"
VALUES_YAML="$2"
ROOT_CA="${3:-}"  # optional root CA
WARN_DAYS=90
WARN_SECONDS=$((WARN_DAYS * 86400))
BASE_DOMAIN=$(yq '.global.baseDomain' $VALUES_YAML)
KNOWN_PUBLIC_CAS=(
  "Let's Encrypt"
  "DigiCert"
  "Sectigo"
  "COMODO"
  "GlobalSign"
)

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <certificate.crt> <values.yaml> [rootCA.pem]"
  exit 1
fi

if [[ ! -f "$CERT" ]]; then
  echo "Certificate not found: $CERT"
  exit 1
fi

if [[ ! -f "$VALUES_YAML" ]]; then
  echo "values.yaml not found: $VALUES_YAML"
  exit 1
fi

if [[ -n "$ROOT_CA" && ! -f "$ROOT_CA" ]]; then
  echo "Root CA certificate not found: $ROOT_CA"
  exit 1
fi

echo "Checking certificate: $CERT"
echo "-------------------------------------->"

if openssl x509 -in "$CERT" -noout -checkend 0 >/dev/null; then
  echo -e "${GREEN}Certificate is currently valid${NC}"

else
  echo -e "${RED}Certificate has EXPIRED${NC}"
  exit 1
fi

if ! openssl x509 -in "$CERT" -noout -checkend "$WARN_SECONDS" >/dev/null; then
  echo "Certificate expires within $WARN_DAYS days"
fi

# Expiration date
END_DATE=$(openssl x509 -in "$CERT" -noout -enddate | cut -d= -f2)
echo "Expires on : $END_DATE"
echo

# Common Name (CN)
CN=$(openssl x509 -in "$CERT" -noout -subject \
     | sed -n 's/.*CN *= *\([^,/]*\).*/\1/p')

echo -e "${GREEN}Common Name (CN):${NC} ${CN:-<none>}"
echo
# Compare CN with BASE_DOMAIN from values.yaml
if [[ "$CN" == "$BASE_DOMAIN" ]]; then
  echo -e "${GREEN}CN matches the baseDomain from config file:${NC} $BASE_DOMAIN"
  CN_VALID=true
else
  echo -e "${RED}CN does NOT match the baseDomain from config file!"
  echo -e "CN: $CN"
  echo -e "baseDomain: $BASE_DOMAIN${NC}"
fi

echo
# Extract SANs (DNS only)
echo -e "${GREEN}Subject Alternative Names (SAN):${NC}"
SAN_LIST=$(openssl x509 -in "$CERT" -noout -ext subjectAltName \
  | sed '1d' \
  | tr ',' '\n' \
  | sed 's/^[[:space:]]*DNS://')


echo "$SAN_LIST"
echo

# Wildcard + base domain
if echo "$SAN_LIST" | grep -qx "\*.$BASE_DOMAIN" \
   && echo "$SAN_LIST" | grep -qx "$BASE_DOMAIN"; then
  echo -e "${GREEN}Wildcard and base domain present${NC}"
  SAN_VALID=true
fi

# Full endpoint list
REQUIRED_ENDPOINTS=(
  app
  deployments
  registry
  houston
  grafana
  kibana
  install
  alertmanager
  prometheus
)

MISSING=()

for ep in "${REQUIRED_ENDPOINTS[@]}"; do
  fqdn="$ep.$BASE_DOMAIN"
  if ! echo "$SAN_LIST" | grep -qx "$fqdn"; then
    MISSING+=("$fqdn")
  fi
done

if [[ ${#MISSING[@]} -eq 0 ]]; then
  echo -e "${GREEN}All required endpoints present${NC}"
  SAN_VALID=true
fi

# Decision about SAN
if [[ "$SAN_VALID" == false ]]; then
  echo -e "${RED}INVALID certificate SANs${NC}"
  echo "Missing SAN entries:"
  for m in "${MISSING[@]}"; do
    echo "  - $m"
  done
fi


# Public vs Private CA
ISSUER=$(openssl x509 -in "$CERT" -noout -issuer)
CERT_CLASS="Private CA"
PUBLIC_CA_NAME=""

for ca in "${KNOWN_PUBLIC_CAS[@]}"; do
  if echo "$ISSUER" | grep -qi "$ca"; then
    CERT_CLASS="Public CA"
    PUBLIC_CA_NAME="$ca"
    break
  fi
done

if [[ "$CERT_CLASS" == "Public CA" ]]; then
  echo -e "${GREEN}Certificate signed by Public CA:${NC} $PUBLIC_CA_NAME"
else
  echo -e "${VIOLET}Certificate signed by Private CA${NC}"
fi

# Optional Root CA trust check
if [[ -n "$ROOT_CA" ]]; then
  if [[ "$(uname)" == "Darwin" ]]; then
    if security verify-cert -c "$ROOT_CA" -k /Library/Keychains/System.keychain >/dev/null 2>&1; then
      PRIVATE_CA_TRUSTED=true
      echo -e "${GREEN}Private CA root is trusted in macOS System keychain${NC}"
    else
      PRIVATE_CA_TRUSTED=false
      echo -e "${RED}Private CA root is NOT trusted in macOS System keychain${NC}"
    fi
  else
    # Linux
    if [[ -f /etc/ssl/certs/ca-certificates.crt ]]; then
      TRUST_STORE="/etc/ssl/certs/ca-certificates.crt"
    elif [[ -f /etc/pki/tls/certs/ca-bundle.crt ]]; then
      TRUST_STORE="/etc/pki/tls/certs/ca-bundle.crt"
    else
      echo "Unable to locate system CA trust store"
      exit 1
    fi

    if openssl verify -CAfile "$TRUST_STORE" "$ROOT_CA" >/dev/null 2>&1; then
      PRIVATE_CA_TRUSTED=true
      echo -e "${GREEN}Private CA root is trusted in Linux system trust store${NC}"
    else
      PRIVATE_CA_TRUSTED=false
      echo -e "${RED}Private CA root is NOT trusted in Linux system trust store${NC}"
    fi
  fi
fi

# Summary
echo
echo "================ Certificate Summary ================"
printf "Expiration valid     : "
[[ "$EXPIRATION_VALID" == true ]] && echo -e "${GREEN}YES${NC}" || echo -e "${RED}NO${NC}"

printf "SANs valid           : "
[[ "$SAN_VALID" == true ]] && echo -e "${GREEN}YES${NC}" || echo -e "${RED}NO${NC}"

printf "Domain (CN) valid    : "
[[ "$CN_VALID" == true ]] && echo -e "${GREEN}YES${NC}" || echo -e "${RED}NO${NC}"

printf "Certificate issuer   : "
if [[ "$CERT_CLASS" == "Public CA" ]]; then
  echo -e "${GREEN}Public CA ($PUBLIC_CA_NAME)${NC}"
else
  echo -e "${VIOLET}Private CA${NC}"
fi

if [[ -n "$ROOT_CA" ]]; then
  printf "Private CA trusted   : "
  [[ "$PRIVATE_CA_TRUSTED" == true ]] && echo -e "${GREEN}YES${NC}" || echo -e "${RED}NO${NC}"
fi
echo "===================================================="


