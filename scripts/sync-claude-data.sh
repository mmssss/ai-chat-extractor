#!/bin/bash

set -euo pipefail

# SSH options for connection multiplexing
mkdir -p ~/.ssh/sockets 2>/dev/null || true
SSH_OPTS="-o ControlMaster=auto -o ControlPath=~/.ssh/sockets/%r@%h-%p -o ControlPersist=600"

REMOTE_HOST=""
REMOTE_USER=""
IDENTITY_KEY=""
OUTPUT_DIR=""

usage() {
    echo "Sync Claude Code data from a remote server"
    echo
    echo "Rsyncs ~/.claude.json and ~/.claude/ from the remote host into a local"
    echo "directory, under a subdirectory named after the host."
    echo
    echo "Usage: $0 -H HOST -u USER -o OUTPUT_DIR [-i IDENTITY_KEY] [-s SSH_OPTS]"
    echo
    echo "Options:"
    echo "  -H, --host HOST           Remote host, as defined in ~/.ssh/config (required)"
    echo "  -u, --user USER           Remote SSH user (required)"
    echo "  -o, --output DIR          Local output directory (required)"
    echo "  -i, --identity KEY        Path to SSH identity key (optional)"
    echo "  -s, --ssh-opts OPTS       SSH options (default: multiplexing options)"
    echo "  -h, --help                Show this help message"
    echo
    echo "Examples:"
    echo "  $0 -H myserver -u john -o ./backup"
    echo "  $0 --host devbox --user admin --identity ~/.ssh/id_ed25519 --output /tmp/claude-sync"
    exit 1
}

# Parse command line options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -H|--host)
            REMOTE_HOST="$2"
            shift 2
            ;;
        --host=*)
            REMOTE_HOST="${1#*=}"
            shift
            ;;
        -u|--user)
            REMOTE_USER="$2"
            shift 2
            ;;
        --user=*)
            REMOTE_USER="${1#*=}"
            shift
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --output=*)
            OUTPUT_DIR="${1#*=}"
            shift
            ;;
        -i|--identity)
            IDENTITY_KEY="$2"
            shift 2
            ;;
        --identity=*)
            IDENTITY_KEY="${1#*=}"
            shift
            ;;
        -s|--ssh-opts)
            SSH_OPTS="$2"
            shift 2
            ;;
        --ssh-opts=*)
            SSH_OPTS="${1#*=}"
            shift
            ;;
        -h|--help)
            usage
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage
            ;;
        *)
            echo "Unexpected argument: $1" >&2
            usage
            ;;
    esac
done

# Validate required parameters
if [[ -z "$REMOTE_HOST" ]]; then
    echo "Error: Remote host is required (-H)" >&2
    usage
fi

if [[ -z "$REMOTE_USER" ]]; then
    echo "Error: Remote user is required (-u)" >&2
    usage
fi

if [[ -z "$OUTPUT_DIR" ]]; then
    echo "Error: Output directory is required (-o)" >&2
    usage
fi

# Build SSH command with identity key and options
SSH_CMD="ssh ${SSH_OPTS}"
if [[ -n "$IDENTITY_KEY" ]]; then
    if [[ ! -f "$IDENTITY_KEY" ]]; then
        echo "Error: identity key not found: $IDENTITY_KEY" >&2
        exit 1
    fi
    SSH_CMD="${SSH_CMD} -i ${IDENTITY_KEY}"
fi

DEST="${OUTPUT_DIR}/${REMOTE_HOST}"
mkdir -p "$DEST"

echo "Syncing Claude data from ${REMOTE_USER}@${REMOTE_HOST} -> ${DEST}"

# Sync ~/.claude.json
echo "  Syncing ~/.claude.json ..."
rc=0
rsync -az --info=progress2,stats2 \
    -e "$SSH_CMD" \
    "${REMOTE_USER}@${REMOTE_HOST}:~/.claude.json" \
    "${DEST}/" || rc=$?
if [[ $rc -eq 23 ]]; then
    echo "  Warning: ~/.claude.json not found on remote (skipping)." >&2
elif [[ $rc -ne 0 ]]; then
    echo "  Error: rsync failed (exit code $rc)." >&2
    exit 1
fi

# Sync ~/.claude/ directory recursively
echo "  Syncing ~/.claude/ ..."
rc=0
rsync -az --info=progress2,stats2 \
    -e "$SSH_CMD" \
    "${REMOTE_USER}@${REMOTE_HOST}:~/.claude/" \
    "${DEST}/.claude/" || rc=$?
if [[ $rc -eq 23 ]]; then
    echo "  Warning: ~/.claude/ not found on remote (skipping)." >&2
elif [[ $rc -ne 0 ]]; then
    echo "  Error: rsync failed (exit code $rc)." >&2
    exit 1
fi

echo "Done. Data saved to: ${DEST}"
