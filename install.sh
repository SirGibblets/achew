#!/bin/sh
# Installs Achew (or updates an existing install), then starts it:
#
#   curl -LsSf https://raw.githubusercontent.com/SirGibblets/achew/main/install.sh | sh
#
# Arguments go to run.sh, e.g. `| sh -s -- --listen` to reach Achew from other machines.
#
# Installs the latest release into ~/achew, or into ACHEW_DIR if set: a git clone checked out at
# the release's tag when git is available, otherwise the release's files, downloaded. Either
# way, run.sh then downloads the tools Achew needs (uv, Node.js and Python) into that folder,
# and nothing outside it changes.
#
# ACHEW_GIT_URL, ACHEW_LATEST_RELEASE_URL and ACHEW_RELEASE_ARCHIVE_URL override where Achew
# comes from (for forks, or testing); the last two are shared with backend/app/core/updater.py.

set -eu

say() {
    printf '\033[0;96m %s\033[0m\n' "$1"
}

die() {
    printf '\033[0;31m %s\033[0m\n' "$1" >&2
    exit 1
}

# Prints a URL's contents, or saves them to a file if one is given.
fetch() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 3 -o "${2:--}" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "${2:--}" "$1"
    else
        die "Installing Achew needs curl or wget."
    fi
}

# macOS ships /usr/bin/git as a stub that pops up the Xcode tools installer when they're
# missing, so only count it once the tools are installed.
have_git() {
    command -v git >/dev/null 2>&1 || return 1
    if [ "$(uname -s)" = Darwin ] && [ "$(command -v git)" = /usr/bin/git ]; then
        xcode-select -p >/dev/null 2>&1 || return 1
    fi
}

latest_release_tag() {
    fetch "$LATEST_RELEASE_URL" | tr ',' '\n' | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1
}

install_release() {
    dir="$1"
    tag="$2"
    say "Downloading Achew $tag into $dir..."
    mkdir -p "$dir/.toolchain"
    archive="$dir/.toolchain/release.tar.gz"
    fetch "$(printf '%s' "$RELEASE_ARCHIVE_URL" | sed "s|{tag}|$tag|g")" "$archive" ||
        die "Couldn't download Achew $tag."
    tar -xzf "$archive" -C "$dir" --strip-components 1
    # Lists the release's files, so updates can remove files that later releases drop
    tar -tzf "$archive" | sed -e 's|^[^/]*/||' -e '/\/$/d' -e '/^$/d' >"$dir/.toolchain/install-manifest.txt"
    rm -f "$archive"
}

main() {
    dir="${ACHEW_DIR:-$HOME/achew}"
    GIT_URL="${ACHEW_GIT_URL:-https://github.com/SirGibblets/achew.git}"
    LATEST_RELEASE_URL="${ACHEW_LATEST_RELEASE_URL:-https://api.github.com/repos/SirGibblets/achew/releases/latest}"
    # Not inline in ${...:-...}, which would end at the first "}"
    default_archive_url='https://github.com/SirGibblets/achew/archive/refs/tags/{tag}.tar.gz'
    RELEASE_ARCHIVE_URL="${ACHEW_RELEASE_ARCHIVE_URL:-$default_archive_url}"

    if [ -f "$dir/run.sh" ]; then
        # Achew 1.13 and earlier have no updater, and their run.sh rejects --update
        [ -f "$dir/backend/app/core/updater.py" ] ||
            die "The Achew in $dir is too old to update itself. Update it once with git: cd \"$dir\" && git checkout main && git pull && ./run.sh"
        say "Achew is already installed in $dir, so updating it."
        exec "$dir/run.sh" --update "$@"
    fi
    if [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
        die "$dir already exists and isn't an Achew install. Set ACHEW_DIR to install somewhere else."
    fi

    say "Looking up the latest Achew release..."
    tag="$(latest_release_tag)"
    [ -n "$tag" ] || die "Couldn't find the latest Achew release."

    if have_git; then
        say "Downloading Achew $tag into $dir..."
        git -c advice.detachedHead=false clone --quiet --branch "$tag" "$GIT_URL" "$dir"
    else
        install_release "$dir" "$tag"
    fi

    say "Installed Achew in $dir. To start it again later, run: $dir/run.sh"
    say "Starting Achew. Once it's ready, open http://localhost:8000 (or the address you chose)."
    exec "$dir/run.sh" "$@"
}

# Last, so a download cut short can't run part of the script
main "$@"
