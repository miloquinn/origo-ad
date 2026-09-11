"""Curated splash endpoints: literal hosts, bounded paths, no remote code."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

HOST_RE = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PATH_RE = re.compile(r"/[A-Za-z0-9_./{}-]+$")
ENTRY_KEYS = {"id", "app", "host", "path", "match", "source_line"}
OPTIONAL_KEYS = {"query", "response", "rewrite", "source_url"}
RESPONSES = {
    "empty-json": ("{}", "application/json"),
    "empty": ("", "text/plain"),
}
# Native Egern filters keep the rest of each startup response intact. These are
# finite, reviewed templates, not arbitrary code supplied by the manifest.
BODY_REWRITES = {
    'bilibili-preload': (
        'if type != "object" then . elif (.data | type) != "object" then . '
        'else .data |= del(.show, .event_list, .preload) end'
    ),
    'jd-start': (
        'if type != "object" then . else '
        '(if (.images | type) == "array" then .images = [] else . end) | '
        '(if (.showTimesDaily | type) == "number" then .showTimesDaily = 0 else . end) end'
    ),
    'xhs-splash': (
        'def defer_ad: if type == "object" then '
        '.start_time = 3818332800 | .end_time = 3818419199 else . end; '
        'if type != "object" then . elif (.data | type) != "object" then . '
        'elif (.data.ads_groups | type) != "array" then . else '
        '.data.ads_groups |= map(if type == "object" then defer_ad | '
        'if (.ads | type) == "array" then .ads |= map(defer_ad) else . end '
        'else . end) end'
    ),
    'bevol-launch': (
        'if type != "object" then . elif (.result | type) != "object" then . else '
        '(if (.result.openAppAdvert | type) != "object" then . '
        'elif (.result.openAppAdvert.openAdvertOnline | type) == "array" '
        'then .result.openAppAdvert.openAdvertOnline = [] else . end) | '
        '(if (.result.openAdKeepTime | type) == "number" '
        'then .result.openAdKeepTime = 0 else . end) end'
    ),
}
REWRITE_ROUTES = {
    'bilibili-preload': {
        (host, '/x/v2/splash/' + path, '')
        for host in ('app.bilibili.com', 'app.biliapi.net')
        for path in ('list', 'show', 'brand/list', 'event/list2')
    },
    'jd-start': {('api.m.jd.com', '/client.action', 'functionId=start')},
    'xhs-splash': {('edith.xiaohongshu.com', '/api/sns/v{version}/system_service/splash_config', '')},
    'bevol-launch': {('api.bevol.com', '/appmain/app/home/launch', '')},
}
REVIEWED_LOCAL_ROUTES = {
    ('wmapi.meituan.com', '/api/v7/loadInfo', ''),
}


def validate_entries(entries: list[dict]) -> None:
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError("splash entries must be a list of at most 100 reviewed endpoints")
    ids, routes = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or not ENTRY_KEYS.issubset(entry) or set(entry) - ENTRY_KEYS - OPTIONAL_KEYS:
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
        route = (entry['host'], path, query)
        rewrite = entry.get('rewrite')
        if 'rewrite' in entry and (not isinstance(rewrite, str) or rewrite not in BODY_REWRITES):
            raise ValueError('splash rewrite must be a reviewed native template')
        if rewrite and (route not in REWRITE_ROUTES[rewrite] or entry['match'] != 'exact' or 'response' in entry):
            raise ValueError('splash rewrite must keep its reviewed route and response shape')
        reviewed_route = (rewrite and route in REWRITE_ROUTES[rewrite]) or (
            route in REVIEWED_LOCAL_ROUTES and entry.get('response') == 'empty-json' and entry['match'] == 'exact'
        )
        if '..' in path or path == '/' or (not reviewed_route and not re.search(r'splash|launchad|loading_ad|startpageads|getstartad|getappstartad|kaiping|boot_ad|newopenad|open_ad|launchscreen|start/ads|startup_ad|startpage_ad|start_screen_ads|getstartpictureadvertising|adpmobile/launch|launch_v2|openscreen|startpicture', path + query, re.I)):
            raise ValueError("splash path must identify a dedicated opening advertisement endpoint")
        if not isinstance(entry.get('response', 'reject'), str) or entry.get('response', 'reject') not in {'reject', *RESPONSES}:
            raise ValueError('splash response must be a reviewed local template')
        if 'source_url' in entry and (not isinstance(entry['source_url'], str) or not re.fullmatch(
            r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/blob/[a-f0-9]{40}/[^\s?#]+(?:#L[0-9]+(?:-L[0-9]+)?)?', entry['source_url']
        )):
            raise ValueError('splash source URL must reference a pinned source revision')
        if entry["match"] not in {"exact", "subtree"}:
            raise ValueError("invalid splash path matching mode")
        if entry["match"] == "subtree" and not path.endswith('/'):
            raise ValueError("splash subtree must end at a slash boundary")
        if type(entry["source_line"]) is not int or entry["source_line"] < 1:
            raise ValueError("splash endpoint needs a source line")
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


def other_query_parameter(key: str) -> str:
    """Match an ASCII parameter whose name differs from the dispatcher key.

    Egern's linear regex engine cannot compile look-around. Enumerate shorter,
    first-differing and longer names instead. Percent-encoded parameter names
    are intentionally excluded because they could hide a duplicate key.
    """
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-'
    name_char = r'[A-Za-z0-9_.-]'
    alternatives = [re.escape(key[:i]) for i in range(len(key))]
    for i, char in enumerate(key):
        different = '[' + re.escape(alphabet.replace(char, '')) + ']'
        alternatives.append(re.escape(key[:i]) + different + name_char + '*')
    alternatives.append(re.escape(key) + name_char + '+')
    return '(?:' + '|'.join(alternatives) + r')(?:=[^&#]*)?'


def pattern(entry: dict) -> str:
    # Escape literal punctuation; numeric versions cannot escape their path segment.
    path = re.escape(entry['path']).replace(r'\{version\}', '[0-9]+')
    if entry.get('query'):
        # API dispatch parameters may move within the query string. Match one
        # exact value and refuse ambiguous duplicate dispatcher keys.
        key = entry['query'].split('=', 1)[0]
        other = other_query_parameter(key)
        ending = r'\?(?:' + other + '&)*' + re.escape(entry['query'])
        ending += '(?:&' + other + ')*$'
    else:
        ending = '' if entry['match'] == 'subtree' else r'(?:\?|$)'
    return '^https?://' + re.escape(entry['host']) + path + ending


def render_sections(entries: list[dict]) -> str:
    validate_entries(entries)
    # Surge has no response_jq. Never degrade a partial JSON edit into rejecting
    # the entire startup response on the compatibility module.
    entries = [e for e in entries if not e.get('rewrite')]
    if not entries:
        return ''
    ordered = sorted(entries, key=lambda e: (e['host'], e['path'], e['id']))
    rejects = [e for e in ordered if e.get('response', 'reject') == 'reject']
    replies = [e for e in ordered if e.get('response', 'reject') != 'reject']
    lines = ['', '[URL Rewrite]'] if rejects else []
    for entry in rejects:
        lines.extend([f"# Splash: {entry['id']}", f"{pattern(entry)} _ reject"])
    if replies:
        lines.extend(['', '[Map Local]'])
        for entry in replies:
            body, content_type = RESPONSES[entry['response']]
            encoded = base64.b64encode(body.encode('utf-8')).decode('ascii')
            lines.extend([
                f"# Splash: {entry['id']}",
                f'{pattern(entry)} data-type=base64 data="{encoded}" status-code=200 header="Content-Type:{content_type}"',
            ])
    lines.extend(['', '[MITM]', 'hostname = %APPEND% ' + ','.join(sorted({e['host'] for e in entries}))])
    return '\n'.join(lines) + '\n'


def native_sections(entries: list[dict]) -> dict:
    """Egern fields with inline responses, avoiding third-party format conversion."""
    validate_entries(entries)
    if not entries:
        return {}
    rewrites, maps, body_rewrites = [], [], []
    for entry in sorted(entries, key=lambda e: (e['host'], e['path'], e['id'])):
        if entry.get('rewrite'):
            body_rewrites.append({'response_jq': {'match': pattern(entry), 'filter': BODY_REWRITES[entry['rewrite']]}})
            continue
        response = entry.get('response', 'reject')
        if response == 'reject':
            rewrites.append({'match': pattern(entry), 'location': 'http://reject/'})
        else:
            body, content_type = RESPONSES[response]
            maps.append({'match': pattern(entry), 'status_code': 200,
                         'headers': {'Content-Type': content_type}, 'body': body})
    result = {'mitm': {'hostnames': {'includes': sorted({e['host'] for e in entries})}}}
    if rewrites:
        result['url_rewrites'] = rewrites
    if maps:
        result['map_locals'] = maps
    if body_rewrites:
        result['body_rewrites'] = body_rewrites
    return result
