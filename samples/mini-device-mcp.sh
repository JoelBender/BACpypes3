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
#     ./mini-device-mcp.sh who_is                   # single tool
#     ./mini-device-mcp.sh read_property 192.168.1.10 analog-input,1 present-value
# ---------------------------------------------------------------------------

set -euo pipefail

MCP_URL="${MCP_URL:-http://127.0.0.1:8765/mcp}"

# Temp files created below are cleaned up on any exit path.
_TMPFILES=()
cleanup() {
    local f
    for f in "${_TMPFILES[@]:-}"; do
        [[ -n "$f" ]] && rm -f "$f"
    done
}
trap cleanup EXIT

# curl arg list shared by every request.
CURL_COMMON=(
    --silent
    --show-error
    --fail-with-body
    -H "Content-Type: application/json"
    -H "Accept: application/json, text/event-stream"
)

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
    local headers_file body_file
    headers_file=$(mktemp)
    body_file=$(mktemp)
    _TMPFILES+=("$headers_file" "$body_file")

    curl "${CURL_COMMON[@]}" \
        -D "$headers_file" \
        -o "$body_file" \
        -X POST "$MCP_URL" \
        --data '{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "mini-device-mcp.sh", "version": "1"}
            }
        }'

    # Header name is case-insensitive per RFC 7230; server returns lowercase.
    SID=$(awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/ { sub(/\r$/, "", $2); print $2 }' \
        "$headers_file")
    if [[ -z "$SID" ]]; then
        echo "error: server did not return Mcp-Session-Id header" >&2
        cat "$headers_file" >&2
        exit 1
    fi
    echo "[init] session id: $SID"
    echo "[init] server info:"
    sse_body < "$body_file" | pp
}

# ---------------------------------------------------------------------------
# 2. initialized — a fire-and-forget JSON-RPC notification (no id, no
#    response body). MCP requires this before tool calls.
# ---------------------------------------------------------------------------
initialized() {
    curl "${CURL_COMMON[@]}" \
        -H "Mcp-Session-Id: $SID" \
        -X POST "$MCP_URL" \
        --data '{"jsonrpc": "2.0", "method": "notifications/initialized"}' \
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
    curl "${CURL_COMMON[@]}" \
        -H "Mcp-Session-Id: $SID" \
        -X POST "$MCP_URL" \
        --data '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
    | sse_body | pp
}

# ---------------------------------------------------------------------------
# 4. call_tool NAME ARGUMENTS_JSON — invoke a tool by name.
#    ARGUMENTS_JSON is a JSON object (use '{}' for no arguments). The tool's
#    structured return is at result.structuredContent.result in the reply.
# ---------------------------------------------------------------------------
call_tool() {
    local name="$1"
    local arguments="${2:-{\}}"
    local payload
    payload=$(printf '{"jsonrpc":"2.0","id":%d,"method":"tools/call","params":{"name":"%s","arguments":%s}}' \
        "$RANDOM" "$name" "$arguments")

    echo
    echo "[call] $name $arguments"
    curl "${CURL_COMMON[@]}" \
        -H "Mcp-Session-Id: $SID" \
        -X POST "$MCP_URL" \
        --data "$payload" \
    | sse_body | pp
}

# ---------------------------------------------------------------------------
# Convenience wrappers around the three demo tools.
# ---------------------------------------------------------------------------
who_is() {
    # Local broadcast, no instance range — discovers every device that
    # responds within the ~3-second default timeout.
    call_tool who_is '{}'
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

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
    init
    initialized

    if [[ $# -eq 0 ]]; then
        # Default demo: list the tools the server advertises (with their
        # descriptions), discover devices, announce this side, then read a
        # property from the embedded server's own commandable-av (which the
        # mini-device-with-mcp.py sample registers as analog-value,2).
        list_tools
        who_is
        i_am
        # Read from the embedded server itself. Adjust ADDRESS to any host
        # discovered by who_is above.
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
        who_is|i_am)
            "$tool"
            ;;
        read_property)
            if [[ $# -ne 3 ]]; then
                echo "usage: $0 read_property ADDRESS OBJECT_IDENTIFIER PROPERTY_IDENTIFIER" >&2
                exit 2
            fi
            read_property "$@"
            ;;
        *)
            # Fallback: raw tool call with a JSON argument object.
            call_tool "$tool" "${1:-{\}}"
            ;;
    esac
}

main "$@"
