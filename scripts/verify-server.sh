#!/usr/bin/env bash
set -euo pipefail

systemctl is-active --quiet hill175.service
systemctl --no-pager --full status hill175.service
ss -ltnp | grep -E '(:25566)([[:space:]]|$)'
journalctl -u hill175.service -n 120 --no-pager | grep -E 'Hill175|Done \(|ERROR|WARN'
