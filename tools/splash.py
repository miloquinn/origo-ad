"""Curated splash endpoints: literal hosts, bounded paths, no remote code."""
from __future__ import annotations

import json
import re
from pathlib import Path

HOST_RE = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PATH_RE = re.compile(r"/[A-Za-z0-9_./{}-]+$")
ENTRY_KEYS = {"id", "app", "host", "path", "match", "source_line"}


def validate_entries(entries: list[dict]) -> None:
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError("splash entries must be a list of at most 100 reviewed endpoints")
    ids, routes = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in (ENTRY_KEYS, ENTRY_KEYS | {"query"}):
            raise ValueError("invalid splash entry fields")
        for key in ("id", "app", "host", "path", "match"):
            if not isinstance(entry[key], str) or not entry[key] or any(c in entry[key] for c in '\r\n'):
                raise ValueError(f"invalid splash {key}")
        if not re.fullmatch(r"[a-z0-9-]+", entry["id"]):
            raise ValueError("invalid splash ID")
        if not HOST_RE.fullmatch(entry["host"]):
            raise ValueError("splash host must be one literal DNS hostname")
        path = entry["path"]
        if not PATH_RE.fullmatch(path) or any(c in path.replace('{version}', '') for c in '{}'):
            raise ValueError("splash path must be literal except for {version}")
        query = entry.get('query', '')
        if 'query' in entry and (not isinstance(query, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*=[A-Za-z0-9_]+', query)):
            raise ValueError('splash query must be one literal key=value discriminator')
        if query and entry['match'] != 'exact':
            raise ValueError('query-selected splash endpoint must use exact path matching')
        if '..' in path or path == '/' or not re.search(r'splash|launchad|loading_ad|startpageads|getstartad|getappstartad|kaiping|boot_ad|newopenad|open_ad|launchscreen|start/ads|startup_ad|startpage_ad|start_screen_ads|getstartpictureadvertising|adpmobile/launch', path + query, re.I):
            raise ValueError("splash path must identify a dedicated opening advertisement endpoint")
        if entry["match"] not in {"exact", "subtree"}:
            raise ValueError("invalid splash path matching mode")
        if entry["match"] == "subtree" and not path.endswith('/'):
            raise ValueError("splash subtree must end at a slash boundary")
        if type(entry["source_line"]) is not int or entry["source_line"] < 1:
            raise ValueError("splash endpoint needs a source line")
        route = (entry['host'], path, entry.get('query', ''))
        if entry['id'] in ids or route in routes:
            raise ValueError("duplicate splash endpoint")
        ids.add(entry['id'])
        routes.add(route)
    for entry in entries:
        if entry['match'] == 'subtree' and any(
            other is not entry and other['host'] == entry['host'] and other['path'].startswith(entry['path'])
            for other in entries
        ):
            raise ValueError("overlapping splash endpoints")


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise ValueError("unsupported splash manifest")
    validate_entries(manifest.get('entries'))
    if not manifest['entries']:
        raise ValueError("reviewed splash manifest must not be empty")
    return manifest


def select_entries(manifest: dict, blocked_domains) -> list[dict]:
    """Already blocked hosts need neither URL processing nor extra TLS interception."""
    validate_entries(manifest['entries'])
    exact, suffix = set(), set()
    for rule in blocked_domains:
        if rule.kind == 'DOMAIN':
            exact.add(rule.domain)
        elif rule.kind == 'DOMAIN-SUFFIX':
            suffix.add(rule.domain)
    selected = []
    for entry in manifest['entries']:
        host = entry['host']
        if host in exact or any('.'.join(host.split('.')[i:]) in suffix for i in range(len(host.split('.')))):
            continue
        selected.append(entry)
    return sorted(selected, key=lambda e: (e['host'], e['path'], e['id']))


def pattern(entry: dict) -> str:
    # Escape literal punctuation; numeric versions cannot escape their path segment.
    path = re.escape(entry['path']).replace(r'\{version\}', '[0-9]+')
    if entry.get('query'):
        ending = r'\?' + re.escape(entry['query']) + r'(?:&|$)'
    else:
        ending = '' if entry['match'] == 'subtree' else r'(?:\?|$)'
    return '^https?://' + re.escape(entry['host']) + path + ending


def render_sections(entries: list[dict]) -> str:
    validate_entries(entries)
    if not entries:
        return ''
    lines = ['', '[URL Rewrite]']
    for entry in sorted(entries, key=lambda e: (e['host'], e['path'], e['id'])):
        lines.extend([f"# Splash: {entry['id']}", f"{pattern(entry)} _ reject"])
    lines.extend(['', '[MITM]', 'hostname = %APPEND% ' + ','.join(sorted({e['host'] for e in entries}))])
    return '\n'.join(lines) + '\n'
