#!/usr/bin/env bash

assert_eq () {

    local actual="${1:-}" expected="${2:-}" message="${3:-}"

    [[ "${actual}" == "${expected}" ]] && return 0

    err "${message:-expected [${expected}], got [${actual}]}"
    return 1

}
assert_ne () {

    local actual="${1:-}" expected="${2:-}" message="${3:-}"

    [[ "${actual}" != "${expected}" ]] && return 0

    err "${message:-expected anything but [${expected}]}"
    return 1

}
assert_contains () {

    local haystack="${1:-}" needle="${2:-}" message="${3:-}"

    [[ "${haystack}" == *"${needle}"* ]] && return 0

    err "${message:-expected to find [${needle}]}"
    return 1

}
assert_ok () {

    local message="${1:-}"
    shift

    "$@" >/dev/null 2>&1 && return 0

    err "${message:-expected success: $*}"
    return 1

}
assert_fails () {

    local message="${1:-}"
    shift

    ! "$@" >/dev/null 2>&1 && return 0

    err "${message:-expected failure: $*}"
    return 1

}
