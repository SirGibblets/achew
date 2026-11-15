# Project-local toolchain, sourced by run.sh and dev.sh.
#
# Downloads the uv and Node.js versions pinned in toolchain.env into .toolchain/,
# verifies them against the pinned SHA-256, and points this process (and its
# children) at them. uv's Python, the uv cache and the npm cache live there too. The
# user's PATH, shell profiles and any existing uv/Node/Python installs are never
# touched; deleting .toolchain/ undoes everything.
#
# Set ACHEW_SYSTEM_TOOLS=1 to skip all of this and use uv/npm from PATH instead.

ACHEW_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLCHAIN_DIR="$ACHEW_ROOT/.toolchain"

# shellcheck source-path=SCRIPTDIR/.. source=toolchain.env
. "$ACHEW_ROOT/toolchain.env"

_tc_info() {
    echo -e "\033[0;96m $1\033[0m"
}

_tc_error() {
    echo -e "\033[0;31m $1\033[0m" >&2
}

# For failures of the bundled toolchain, where the user's own tools are the way out.
_tc_fail() {
    _tc_error "$1"
    _tc_error "Install uv and Node.js yourself, then run again with ACHEW_SYSTEM_TOOLS=1."
    exit 1
}

# Whether a version such as 13.4.1 is older than MAJOR.MINOR (only call it as a condition).
_tc_older_than() {
    local major="${1%%.*}" minor="${1#*.}"
    [ "$minor" != "$1" ] || minor=0
    minor="${minor%%.*}"
    [ "$major" -lt "$2" ] || { [ "$major" -eq "$2" ] && [ "$minor" -lt "$3" ]; }
}

# Sets _TC_OS (darwin|linux) and _TC_ARCH (arm64|x64).
_tc_detect_platform() {
    case "$(uname -s)" in
        Darwin) _TC_OS=darwin ;;
        Linux) _TC_OS=linux ;;
        *) _tc_fail "No bundled toolchain for $(uname -s)." ;;
    esac
    case "$(uname -m)" in
        arm64 | aarch64) _TC_ARCH=arm64 ;;
        x86_64 | amd64) _TC_ARCH=x64 ;;
        *) _tc_fail "No bundled toolchain for $(uname -m) CPUs." ;;
    esac
    # A Terminal running under Rosetta reports x86_64 on Apple Silicon; use the native
    # tools so uv picks arm64 wheels (MLX transcription is arm64-only).
    if [ "$_TC_OS" = darwin ] && [ "$_TC_ARCH" = x64 ] &&
        [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = 1 ]; then
        _TC_ARCH=arm64
    fi
    # The official Node.js builds need glibc 2.28+ (no musl builds, so no Alpine).
    if [ "$_TC_OS" = linux ]; then
        local glibc
        glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null | cut -d' ' -f2)"
        [ -n "$glibc" ] || _tc_fail "The bundled Node.js needs glibc, which this system doesn't use."
        if _tc_older_than "$glibc" 2 28; then
            _tc_fail "The bundled Node.js needs glibc 2.28 or newer, but this system has $glibc."
        fi
    fi
    # Node.js 24's macOS builds need macOS 13.5+ (the minos in bin/node); check again when
    # moving to a newer Node.js major.
    if [ "$_TC_OS" = darwin ]; then
        local macos
        macos="$(sw_vers -productVersion 2>/dev/null)"
        if [ -n "$macos" ] && _tc_older_than "$macos" 13 5; then
            _tc_fail "The bundled Node.js needs macOS 13.5 or newer, but this Mac has macOS $macos."
        fi
    fi
}

_tc_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        _tc_fail "Neither sha256sum nor shasum is available to verify downloads."
    fi
}

# _tc_install NAME URL SHA256 DEST: downloads a .tar.gz, verifies it, and moves its
# single top-level directory to DEST. Extracts into a temp dir first so an
# interrupted run never leaves a half-installed DEST behind.
_tc_install() {
    local name="$1" url="$2" sha="$3" dest="$4" tmp actual
    [ -n "$sha" ] || _tc_fail "toolchain.env has no checksum for $name on $_TC_OS-$_TC_ARCH."
    mkdir -p "$TOOLCHAIN_DIR"
    tmp="$(mktemp -d "$TOOLCHAIN_DIR/.download.XXXXXX")"
    _tc_info "Downloading $name..."
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --progress-bar -o "$tmp/archive.tar.gz" "$url" ||
            { rm -rf "$tmp"; _tc_fail "Failed to download $url"; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$tmp/archive.tar.gz" "$url" ||
            { rm -rf "$tmp"; _tc_fail "Failed to download $url"; }
    else
        rm -rf "$tmp"
        _tc_fail "Neither curl nor wget is available to download $name."
    fi
    actual="$(_tc_sha256 "$tmp/archive.tar.gz")"
    if [ "$actual" != "$sha" ]; then
        rm -rf "$tmp"
        _tc_fail "Checksum mismatch for $name (expected $sha, got $actual)."
    fi
    mkdir "$tmp/x"
    tar -xzf "$tmp/archive.tar.gz" -C "$tmp/x" || { rm -rf "$tmp"; _tc_fail "Failed to extract $name."; }
    rm -rf "$dest"
    mv "$tmp/x/"* "$dest"
    rm -rf "$tmp"
}

# _tc_prune KEEP GLOB: removes other versions of a tool once the pinned one is in place.
_tc_prune() {
    local keep="$1" old
    # shellcheck disable=SC2086 # GLOB must expand
    for old in "$TOOLCHAIN_DIR"/$2; do
        if [ -e "$old" ] && [ "$old" != "$keep" ]; then
            rm -rf "$old"
        fi
    done
}

_tc_ensure_uv() {
    local target sha_var
    case "$_TC_OS-$_TC_ARCH" in
        darwin-arm64) target=aarch64-apple-darwin ;;
        darwin-x64) target=x86_64-apple-darwin ;;
        # The musl builds are static, so they run on any distro. uv still detects the
        # system's libc itself and downloads a matching Python.
        linux-arm64) target=aarch64-unknown-linux-musl ;;
        linux-x64) target=x86_64-unknown-linux-musl ;;
    esac
    # Per-platform directories, so a checkout shared with WSL or a container keeps both.
    UV_HOME="$TOOLCHAIN_DIR/uv-$UV_VERSION-$target"
    if [ ! -x "$UV_HOME/uv" ]; then
        sha_var="UV_SHA256_${target//-/_}"
        _tc_install "uv $UV_VERSION" \
            "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz" \
            "${!sha_var}" "$UV_HOME"
        _tc_prune "$UV_HOME" "uv-[0-9]*-$target"
    fi
}

_tc_ensure_node() {
    local dist="node-v$NODE_VERSION-$_TC_OS-$_TC_ARCH" sha_var
    NODE_HOME="$TOOLCHAIN_DIR/$dist"
    if [ ! -x "$NODE_HOME/bin/node" ]; then
        sha_var="NODE_SHA256_${_TC_OS}_${_TC_ARCH}"
        _tc_install "Node.js $NODE_VERSION" \
            "https://nodejs.org/dist/v$NODE_VERSION/$dist.tar.gz" \
            "${!sha_var}" "$NODE_HOME"
        _tc_prune "$NODE_HOME" "node-v[0-9]*-$_TC_OS-$_TC_ARCH"
    fi
}

if [ "${ACHEW_SYSTEM_TOOLS:-}" = 1 ]; then
    if ! command -v npm >/dev/null 2>&1; then
        _tc_error "ACHEW_SYSTEM_TOOLS=1 is set, but npm is not installed. Install Node.js (which includes npm) first."
        _tc_error "For installation instructions, visit: https://nodejs.org/en/download/"
        exit 1
    fi
    if ! command -v uv >/dev/null 2>&1; then
        _tc_error "ACHEW_SYSTEM_TOOLS=1 is set, but uv is not installed. Install uv first."
        _tc_error "For installation instructions, visit: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
else
    _tc_detect_platform
    _tc_ensure_uv
    _tc_ensure_node

    export PATH="$UV_HOME:$NODE_HOME/bin:$PATH"

    # Keep uv's Python, cache and any tool installs inside the project, and never use
    # (or register) a system Python.
    export UV_CACHE_DIR="$TOOLCHAIN_DIR/cache/uv"
    export UV_PYTHON_INSTALL_DIR="$TOOLCHAIN_DIR/python"
    export UV_TOOL_DIR="$TOOLCHAIN_DIR/uv-tools"
    export UV_MANAGED_PYTHON=1
    export UV_PYTHON="$PYTHON_VERSION"
    export UV_PYTHON_INSTALL_BIN=0
    export UV_PYTHON_INSTALL_REGISTRY=0

    # npm's cache and logs (otherwise ~/.npm), and no update or funding notices.
    export npm_config_cache="$TOOLCHAIN_DIR/cache/npm"
    export npm_config_update_notifier=false
    export npm_config_fund=false
fi
