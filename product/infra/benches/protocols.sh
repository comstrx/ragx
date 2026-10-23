#!/usr/bin/env bash
set -Eeuo pipefail

bench-cpu () {

    local line=""

    while IFS= read -r line; do
        [[ "${line}" != usage_usec* ]] || { printf '%s\n' "${line#usage_usec }"; return; }
    done < <(docker exec "${1}" cat /sys/fs/cgroup/cpu.stat)

    return 1

}
bench-protocol () {

    local protocol="${1}" flag="" index=0 started=0 ended=0 before=0 after=0 config="" results=""

    case "${protocol}" in
        h1) flag=--http1.1 ;;
        h2) flag=--http2 ;;
        h3) flag=--http3-only ;;
        *)  printf '[-] Unknown protocol: %s\n' "${protocol}" >&2; return 1 ;;
    esac

    config="$(mktemp)"
    results="$(mktemp)"

    for (( index = 0; index < REQUESTS; index++ )); do
        printf 'url = "https://%s%s"\noutput = "/dev/null"\n' "${HOST}" "${URL_PATH}" >> "${config}"
    done

    chmod 644 "${config}"
    before="$(bench-cpu "${EDGE}")"
    started="$(date +%s%N)"

    docker run --rm --network "${NETWORK}" -v "${CA}:/ca.pem:ro" -v "${config}:/bench.cfg:ro" "${IMAGE}" \
        "${flag}" --parallel --parallel-max "${PARALLEL}" --cacert /ca.pem --connect-to "${HOST}:443:${TARGET}" \
        -sS -K /bench.cfg -w '%{http_code} %{time_total}\n' > "${results}" || true

    ended="$(date +%s%N)"
    after="$(bench-cpu "${EDGE}")"

    awk '$1 == 200 { printf "%.3f\n", $2 * 1000 }' "${results}" | sort -n | awk -v protocol="${protocol}" -v total="$(wc -l < "${results}")" \
        -v wall="$(( (ended - started) / 1000000 ))" -v cpu="$(( (after - before) / 1000 ))" '
        { times[NR] = $1 }
        END {
            p50 = times[int(NR * 0.50) > 0 ? int(NR * 0.50) : 1]
            p95 = times[int(NR * 0.95) > 0 ? int(NR * 0.95) : 1]
            p99 = times[int(NR * 0.99) > 0 ? int(NR * 0.99) : 1]
            printf "{\"protocol\":\"%s\",\"requests\":%d,\"ok\":%d,\"wall_ms\":%d,\"rps\":%.1f,\"p50_ms\":%.2f,\"p95_ms\":%.2f,\"p99_ms\":%.2f,\"edge_cpu_ms\":%d}\n",
                protocol, total, NR, wall, (wall > 0 ? NR * 1000 / wall : 0), p50, p95, p99, cpu
        }'

    rm -f -- "${config}" "${results}"

}
bench-main () {

    local protocol=""

    NETWORK="${1:?network}" CA="${2:?ca}" HOST="${3:?host}" TARGET="${4:?edge:port}" EDGE="${5:?edge container}"
    REQUESTS="${6:-2000}" PARALLEL="${7:-16}" URL_PATH="${8:-/health}" IMAGE="${BENCH_IMAGE:-infra-bench/curl:8.23.0-h3}"

    for protocol in h2 h3 h2 h3; do
        bench-protocol "${protocol}"
    done

}

bench-main "$@"
