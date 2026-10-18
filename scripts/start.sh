#!/bin/sh
set -e

# Trust no forwarding headers by default. Set only verified proxy IPs/CIDRs.
case "${FORWARDED_ALLOW_IPS:-}" in
  *\**) echo "FORWARDED_ALLOW_IPS must list explicit trusted proxy IPs/CIDRs, not *" >&2; exit 1 ;;
esac

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-}"
