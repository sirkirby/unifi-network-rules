"""Utilities for fetching and parsing curated lists from remote repos."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def build_raw_url_candidates(clone_url: str | None, ref: str, filename: str) -> list[str]:
    """Return candidate raw URLs for common providers.

    Supports:
    - GitHub repos: https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file}
    - GitHub Gist: tries multiple patterns using gist id and optional username
    - GitLab: https://gitlab.com/{owner}/{repo}/-/raw/{ref}/{file}
    - Bitbucket.org: https://bitbucket.org/{owner}/{repo}/raw/{ref}/{file}
    - Direct URL in `filename` (http/https) is accepted as-is
    """
    candidates: list[str] = []

    # If filename is itself a URL, prefer it
    if filename.lower().startswith(("http://", "https://")):
        return [filename]

    if not clone_url:
        return candidates

    url = clone_url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path_parts = [p for p in (parsed.path or "").split("/") if p]
    ref = ref or "main"

    # GitHub repo
    if host == "github.com" and len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1]
        candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{filename}")
        return candidates

    # GitHub Gist
    if host == "gist.github.com" and len(path_parts) >= 1:
        # path_parts can be [user, id] or just [id]
        if len(path_parts) == 1:
            gist_id = path_parts[0]
            candidates.append(f"https://gist.github.com/{gist_id}/raw/{filename}")
        else:
            user, gist_id = path_parts[0], path_parts[1]
            candidates.append(f"https://gist.github.com/{gist_id}/raw/{filename}")
            candidates.append(f"https://gist.github.com/{user}/{gist_id}/raw/{filename}")
            candidates.append(f"https://gist.githubusercontent.com/{user}/{gist_id}/raw/{filename}")
        return candidates

    # GitLab.com
    if host == "gitlab.com" and len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1]
        candidates.append(f"https://gitlab.com/{owner}/{repo}/-/raw/{ref}/{filename}")
        return candidates

    # Bitbucket.org
    if host == "bitbucket.org" and len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1]
        candidates.append(f"https://bitbucket.org/{owner}/{repo}/raw/{ref}/{filename}")
        return candidates

    # Unknown provider — caller may provide direct URL via filename instead
    return candidates


def parse_curated_text(content: str) -> dict[str, Any]:
    """Parse curated list text into a payload for firewall group creation.

    Format:
    - Header as comment lines with `# key: value` (name, type, description optional)
    - Blank line separates header from entries
    - Entries are one per line; blank lines and lines starting with `#` ignored

    Supported types: address-group, ipv6-address-group, port-group
    If type is missing, we attempt a basic inference.
    """
    lines = content.splitlines()
    meta: dict[str, str] = {}
    entries: list[str] = []
    in_header = True
    for raw in lines:
        line = raw.strip()
        if not line:
            in_header = False
            continue
        if in_header and line.startswith("#") and ":" in line:
            try:
                key, val = line[1:].split(":", 1)
                meta[key.strip().lower()] = val.strip()
                continue
            except Exception:
                pass
        if line.startswith("#"):
            # ignore other comments
            continue
        in_header = False
        entries.append(line)

    group_type = meta.get("type", "").strip().lower()
    name = meta.get("name") or "UNR: Curated Group"
    description = meta.get("description", "")

    if not group_type:
        # naive inference: colon suggests IPv6, dash or comma suggests port spec, dot or / suggests IPv4/6
        sample = entries[0] if entries else ""
        if ":" in sample and any(ch.isalpha() for ch in sample) is False:
            group_type = "ipv6-address-group"
        elif any(ch.isalpha() for ch in sample):
            # If there are letters, treat as invalid for legacy API. Default to port-group if digits present.
            group_type = "port-group" if any(ch.isdigit() for ch in sample) else "address-group"
        elif "-" in sample:
            group_type = "port-group"
        elif sample.count(".") == 3 or "/" in sample:
            group_type = "address-group"
        else:
            group_type = "address-group"

    if group_type not in {"address-group", "ipv6-address-group", "port-group"}:
        raise ValueError(f"Unsupported group type: {group_type}")

    # Build members with typed records
    if group_type == "port-group":
        members = [{"type": "port", "value": str(e)} for e in entries]
    elif group_type == "ipv6-address-group":
        members = [{"type": "ipv6-address", "value": e} for e in entries]
    else:
        members = [{"type": "ipv4-address", "value": e} for e in entries]

    return {
        "name": name,
        "description": description,
        "type": group_type,
        "members": members,
    }
