#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# mini-device-mcp.sh — drive an embedded BACpypes3 MCP server with curl.
#
# Pair this with ``samples/mini-device-mcp.py``: start that program in
# one terminal (it runs an embedded MCP HTTP server on 127.0.0.1:8765 in
# addition to the BACnet server), then run this script from another. The
# script performs the MCP handshake once and issues three tool calls —
# who_is, i_am, and read_property — via curl.
#
# The MCP transport is JSON-RPC 2.0 over Streamable HTTP. Two things about
# it that are easy to get wrong:
#
#   1. Every request must Accept both application/json AND text/event-stream.
#      Responses are SSE-framed (event: message\ndata: <json>\n\n) — the
#      helper below unwraps the data line.
#   2. The very first call is an ``initialize`` request. The server picks a
#      session ID and returns it in the ``Mcp-Session-Id`` response header;
#      every subsequent request must echo that header back. Follow the
#      initialize with a ``notifications/initialized`` notification (fire
#      and forget, gets 202 Accepted) before making tool calls.
#
# Requirements: bash, curl. jq is optional — pretty-prints the JSON if
# present, otherwise the raw JSON body is echoed.
#
# Usage:
#     ./mini-device-mcp.sh                          # default host/port + demo
#     MCP_URL=http://host:port/mcp ./mini-device-mcp.sh
#     ./mini-device-mcp.sh list_tools               # dump advertised tools
#     ./mini-device-mcp.sh who_is 999               # single device (instance)
#     ./mini-device-mcp.sh who_is 1000 1999          # instance range
#     ./mini-device-mcp.sh get_config                # local app identity + objects
#     ./mini-device-mcp.sh read_property 192.168.1.10 analog-input,1 present-value
#     ./mini-device-mcp.sh read_broadcast_distribution_table 192.168.1.10
#     ./mini-device-mcp.sh read_foreign_device_table 192.168.1.10
#
# Debugging:
#     MCP_TRACE=1 (the default) prints each outgoing JSON-RPC payload and
#     shows the raw response body when the HTTP call returns non-2xx. Set
#     MCP_TRACE=0 to silence once things are working.
# ---------------------------------------------------------------------------

set -euo pipefail

MCP_URL="${MCP_URL:-http://127.0.0.1:8765/mcp}"

# MCP_TRACE=1 prints each outgoing JSON-RPC payload to stderr before it is
# sent, and each raw response body before SSE unwrapping. Turn this on when
# a call fails with an HTTP-level error (400/406/…): the response body
# usually carries the reason (e.g. "Validation error: params.arguments must
# be an object") but the SSE unwrap step throws away non-event-stream
# bodies. On by default so you always see what the wire looks like — set
# MCP_TRACE=0 to suppress once things are working.
MCP_TRACE="${MCP_TRACE:-1}"

# Temp files created below are cleaned up on any exit path.
_TMPFILES=()
cleanup() {
    local f
    for f in "${_TMPFILES[@]:-}"; do
        [[ -n "$f" ]] && rm -f "$f"
    done
}
trap cleanup EXIT

# curl arg list shared by every request. NOTE: no --fail / --fail-with-body
# here — we want the response body on 4xx/5xx so we can print the reason.
# HTTP status is captured separately via --write-out below.
CURL_COMMON=(
    --silent
    --show-error
    -H "Content-Type: application/json"
    -H "Accept: application/json, text/event-stream"
)

# Log a JSON blob to stderr (labeled), pretty-printed if jq is available.
trace() {
    [[ "$MCP_TRACE" != "1" ]] && return 0
    local label="$1"
    shift
    printf '  [trace] %s: ' "$label" >&2
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$*" | jq -c . >&2 2>/dev/null \
            || printf '%s\n' "$*" >&2
    else
        printf '%s\n' "$*" >&2
    fi
}

# POST a JSON-RPC payload and print the reply. On 2xx, unwrap SSE framing
# and pretty-print the JSON. On any other status, dump the raw body so the
# reason for a 400 (e.g. "Validation error: ...") is visible instead of
# being silently eaten by the SSE unwrap step.
#
# Args: PAYLOAD [extra curl args...]
post() {
    local payload="$1"; shift
    local body_file status
    body_file=$(mktemp)
    _TMPFILES+=("$body_file")

    trace "POST $MCP_URL" "$payload"
    status=$(curl "${CURL_COMMON[@]}" \
        -o "$body_file" \
        -w '%{http_code}' \
        -X POST "$MCP_URL" \
        --data "$payload" \
        "$@")

    if [[ "$status" =~ ^2 ]]; then
        sse_body < "$body_file" | pp
        return 0
    fi

    echo "  [http $status] response body:" >&2
    cat "$body_file" >&2
    echo >&2
    return 22   # match curl's --fail exit for scripts that check $?
}

# Pretty-print JSON if jq is available; otherwise echo the raw body.
pp() {
    if command -v jq >/dev/null 2>&1; then
        jq .
    else
        cat
    fi
}

# Extract the JSON body from an SSE-framed response. Streamable-HTTP MCP
# replies with a `text/event-stream` payload whose data line carries the
# JSON-RPC message; strip the SSE framing so downstream can parse it.
sse_body() {
    sed -n 's/^data: //p'
}

# ---------------------------------------------------------------------------
# 1. initialize — first request; captures Mcp-Session-Id into $SID
# ---------------------------------------------------------------------------
init() {
    local headers_file
    headers_file=$(mktemp)
    _TMPFILES+=("$headers_file")

    local payload='{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "mini-device-mcp.sh", "version": "1"}
        }
    }'

    echo "[init] initialize"
    # -D captures response headers so we can pluck Mcp-Session-Id.
    post "$payload" -D "$headers_file"

    # Header name is case-insensitive per RFC 7230; server returns lowercase.
    SID=$(awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/ { sub(/\r$/, "", $2); print $2 }' \
        "$headers_file")
    if [[ -z "$SID" ]]; then
        echo "error: server did not return Mcp-Session-Id header" >&2
        cat "$headers_file" >&2
        exit 1
    fi
    echo "[init] session id: $SID"
}

# ---------------------------------------------------------------------------
# 2. initialized — a fire-and-forget JSON-RPC notification (no id, no
#    response body). MCP requires this before tool calls.
# ---------------------------------------------------------------------------
initialized() {
    local payload='{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    trace "POST $MCP_URL" "$payload"
    curl "${CURL_COMMON[@]}" \
        -H "Mcp-Session-Id: $SID" \
        -X POST "$MCP_URL" \
        --data "$payload" \
        -o /dev/null
}

# ---------------------------------------------------------------------------
# 3. list_tools — dump the tools the server is advertising, including the
#    description text the model would see. Useful for sanity-checking that
#    the server you're talking to is the version you think it is (e.g. after
#    a docstring change to bacpypes3/mcp.py).
# ---------------------------------------------------------------------------
list_tools() {
    echo
    echo "[list] tools/list"
    post '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
        -H "Mcp-Session-Id: $SID"
}

# ---------------------------------------------------------------------------
# 4. call_tool NAME ARGUMENTS_JSON — invoke a tool by name.
#    ARGUMENTS_JSON is a JSON object (use '{}' for no arguments). The tool's
#    structured return is at result.structuredContent.result in the reply.
# ---------------------------------------------------------------------------
call_tool() {
    local name="$1"
    local arguments="${2:-{\}}"

    # Guard against the classic mistake: passing a bare scalar (an address,
    # a number) where a JSON object is required. The streamable-http
    # transport rejects such a payload with 400 "Validation error";
    # catching it here gives a clearer message and avoids a wasted round
    # trip.
    if [[ "$arguments" != "{"*"}" && "$arguments" != "["*"]" ]]; then
        echo "error: tool arguments must be a JSON object, got: $arguments" >&2
        echo "hint:  wrap it, e.g. '{\"address\":\"$arguments\"}'" >&2
        return 2
    fi

    local payload
    payload=$(printf '{"jsonrpc":"2.0","id":%d,"method":"tools/call","params":{"name":"%s","arguments":%s}}' \
        "$RANDOM" "$name" "$arguments")

    echo
    echo "[call] $name $arguments"
    post "$payload" -H "Mcp-Session-Id: $SID"
}

# ---------------------------------------------------------------------------
# Convenience wrappers around the three demo tools.
# ---------------------------------------------------------------------------
who_is() {
    # Usage: who_is LOW_LIMIT [HIGH_LIMIT]
    #
    # An unqualified who_is (no arguments) is a global broadcast that every
    # BACnet device on the network answers to. On a large site that means
    # a burst of hundreds or thousands of I-Am replies — a broadcast storm
    # that can drop other traffic and briefly overwhelm the collector. This
    # wrapper refuses that shape and requires a device-instance floor
    # (``low_limit``) so the query reaches a bounded subset. If
    # ``high_limit`` is omitted the MCP tool defaults it to ``low_limit``,
    # so ``who_is 1234`` targets exactly instance 1234; pass an explicit
    # ``high_limit`` for a range.
    if [[ $# -lt 1 ]]; then
        echo "error: who_is requires at least a low_limit argument" >&2
        echo "hint:  an unqualified who_is broadcasts to every device on" >&2
        echo "       the network and can cause a reply storm on large" >&2
        echo "       sites. Pass a device-instance floor to bound it:" >&2
        echo "         $0 who_is 999            # instance 999 only" >&2
        echo "         $0 who_is 1000 1999      # range 1000..1999" >&2
        return 2
    fi

    local low_limit="$1"
    local high_limit="${2:-}"
    local args
    if [[ -n "$high_limit" ]]; then
        args=$(printf '{"low_limit":%s,"high_limit":%s}' "$low_limit" "$high_limit")
    else
        args=$(printf '{"low_limit":%s}' "$low_limit")
    fi
    call_tool who_is "$args"
}

i_am() {
    # Fire-and-forget I-Am broadcast. Returns {"ok": true}.
    call_tool i_am '{}'
}

read_property() {
    # Usage: read_property ADDRESS OBJECT_IDENTIFIER PROPERTY_IDENTIFIER
    # e.g.   read_property 192.168.1.10 analog-input,1 present-value
    local address="$1"
    local object_identifier="$2"
    local property_identifier="$3"
    call_tool read_property "$(printf '{"address":"%s","object_identifier":"%s","property_identifier":"%s"}' \
        "$address" "$object_identifier" "$property_identifier")"
}

read_broadcast_distribution_table() {
    # Usage: read_broadcast_distribution_table ADDRESS
    local address="$1"
    call_tool read_broadcast_distribution_table \
        "$(printf '{"address":"%s"}' "$address")"
}

read_foreign_device_table() {
    # Usage: read_foreign_device_table ADDRESS
    local address="$1"
    call_tool read_foreign_device_table \
        "$(printf '{"address":"%s"}' "$address")"
}

get_config() {
    # No arguments. Returns the running application's own identity
    # (bound address, device instance, vendor, etc.) plus every locally-
    # registered BACnet object. Unlike every other tool in this script,
    # get_config does NOT send a BACnet PDU — it reads the local
    # application state directly — so it works even when the stack
    # cannot talk to itself over the wire, and is a good end-to-end
    # sanity check that the MCP transport is up.
    call_tool get_config '{}'
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
    init
    initialized

    if [[ $# -eq 0 ]]; then
        # Default demo, in order of increasing "how much of the stack is
        # this really exercising":
        #   1. list_tools — pure MCP transport, no application code.
        #   2. get_config — MCP → application, no network. This is the
        #      most robust end-to-end sanity check that both the MCP
        #      server and the injected app are wired up.
        #   3. who_is 999 — MCP → application → network layer, bounded
        #      to a single instance (defaulting high_limit to low_limit)
        #      to avoid a broadcast storm on a large site.
        #   4. i_am — fire-and-forget broadcast.
        #   5. read_property against 127.0.0.1 — MCP → application →
        #      network → back up. IPv4DatagramServer.indication() has a
        #      loopback shortcut for self-addressed unicasts (including
        #      any 127.x.x.x on the app's port), so this reaches the
        #      embedded server's own analog-value,2 in-process without
        #      going on the wire. Adjust ADDRESS to any host discovered
        #      by who_is above to exercise a real remote read.
        list_tools
        get_config
        who_is 999
        i_am
        read_property "127.0.0.1" "analog-value,2" "present-value"
        return
    fi

    # Manual mode: first arg is the tool name, remaining args are passed
    # positionally to the wrapper if one is defined, otherwise treated as a
    # JSON arguments object.
    local tool="$1"; shift
    case "$tool" in
        list_tools|tools|tools/list)
            list_tools
            ;;
        who_is)
            # Pass through positional args (low_limit [high_limit]); the
            # wrapper refuses a bare who_is with a broadcast-storm warning.
            who_is "$@"
            ;;
        i_am)
            i_am
            ;;
        get_config)
            get_config
            ;;
        read_property)
            if [[ $# -ne 3 ]]; then
                echo "usage: $0 read_property ADDRESS OBJECT_IDENTIFIER PROPERTY_IDENTIFIER" >&2
                exit 2
            fi
            read_property "$@"
            ;;
        read_broadcast_distribution_table|read_foreign_device_table)
            if [[ $# -ne 1 ]]; then
                echo "usage: $0 $tool ADDRESS" >&2
                exit 2
            fi
            "$tool" "$@"
            ;;
        *)
            # Fallback: raw tool call with a JSON argument object. call_tool
            # rejects a non-JSON-object argument before the round trip.
            call_tool "$tool" "${1:-{\}}"
            ;;
    esac
}

main "$@"
