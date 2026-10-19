#!/usr/bin/env bash
set -Eeuo pipefail

source "${BASH_SOURCE[0]%/*}/bootstrap/index.sh"

bootstrap-main "$@"
