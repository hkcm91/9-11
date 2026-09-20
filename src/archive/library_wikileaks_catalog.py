"""Discover release scopes from the publisher's visible release tiles."""
import hashlib
import re
from html import unescape
from urllib.parse import urljoin, urlsplit, urlunsplit

CATALOG_URL = 'https://wikileaks.org/-Leaks-.html'


def release_scopes(html):
    scopes = []
    seen = set()
    for tile in re.findall(r'<li\b[^>]*class=[\"\']tile[\"\'][^>]*>(.*?)</li>', html, re.S | re.I):
        href = re.search(r'<a\b[^>]*href=[\"\']([^\"\']+)', tile, re.I)
        heading = re.search(r'<h2\b[^>]*>(.*?)</h2>', tile, re.S | re.I)
        if not href or not heading:
            continue
        title = unescape(re.sub('<[^>]+>', '', heading[1])).strip()
        url = urlsplit(urljoin(CATALOG_URL, unescape(href[1])))
        if url.scheme not in {'http', 'https'} or not (url.hostname == 'wikileaks.org' or (url.hostname or '').endswith('.wikileaks.org')):
            continue
        source = urlunsplit((url.scheme, url.netloc, re.sub('/+', '/', url.path), url.query, url.fragment))
        # Iraq and Afghan logs share one portal; their release scopes stay distinct.
        identity = hashlib.sha256((source + '\n' + title).encode()).hexdigest()[:12]
        if identity in seen:
            continue
        seen.add(identity)
        scopes.append(dict(collection='wikileaks', release_id='publisher-' + identity, title=title,
            inventory_status='not_started', expected_files=None, catalog_url=source,
            scope_note='Listed on the publisher release index. File inventory and contents not yet acquired; the index itself may omit historical releases.',
            discovery_url=CATALOG_URL, snapshot_sha256=hashlib.sha256(html.encode()).hexdigest()))
    if not scopes:
        raise ValueError('Publisher page contained no recognized release tiles')
    return scopes
