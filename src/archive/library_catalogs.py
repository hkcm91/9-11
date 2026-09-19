"""Snapshot-based discovery: pinned Snowden mirror and bounded DOJ catalogs."""
import json
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import quote, urljoin, urlsplit
from archive.document_library import digest


def snowden_manifest(tree, commit):
    if tree.get('truncated') or not re.fullmatch('[0-9a-f]{40}', commit.get('sha', '')):
        raise ValueError('A complete tree and pinned commit are required')
    if commit['commit']['tree']['sha'] != tree.get('sha'):
        raise ValueError('Tree does not match the pinned commit')
    revision = commit['sha']
    rows = []
    for blob in tree['tree']:
        path = blob['path']
        if blob.get('type') != 'blob' or not path.startswith('documents/') or not path.endswith('.pdf'):
            continue
        if '..' in PurePosixPath(path).parts or not re.fullmatch('[0-9a-f]{40}', blob['sha']):
            raise ValueError('Invalid mirror path or blob identity')
        rows.append(dict(collection='snowden', release_id='published-mirror-' + revision[:12],
            source_item_id=path, title=PurePosixPath(path).stem.replace('__', ' — ').replace('_', ' '),
            source_url=f'https://raw.githubusercontent.com/iamcryptoki/snowden-archive/{revision}/{quote(path)}',
            format='pdf', git_blob_sha1=blob['sha'], advertised_bytes=blob['size'],
            inventory_url=f'https://github.com/iamcryptoki/snowden-archive/tree/{revision}',
            provenance_note='Third-party mirror of published documents; complete relative to this repository snapshot only. Not the entire Snowden cache.'))
    if not rows or len({r['source_item_id'] for r in rows}) != len(rows):
        raise ValueError('Empty or duplicate mirror inventory')
    return rows


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs).get('href', ''))


def doj_manifest(html, catalog_url, dataset):
    if not re.fullmatch(r'\d{1,2}', str(dataset)) or not 1 <= int(dataset) <= 12:
        raise ValueError('Dataset must be 1–12')
    if urlsplit(catalog_url).hostname != 'www.justice.gov':
        raise ValueError('Expected official DOJ catalog')
    parser = Links()
    parser.feed(html)
    rows = {}
    for link in parser.links:
        url = urljoin(catalog_url, link)
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'www.justice.gov':
            continue
        name = PurePosixPath(parsed.path).name
        if not re.fullmatch(r'EFTA\d+\.pdf', name, re.I):
            continue
        rows[name] = dict(collection='epstein', release_id='doj-data-set-' + str(dataset),
            source_item_id=name, title=name[:-4], source_url=url, format='pdf',
            inventory_url=catalog_url,
            provenance_note='Official DOJ catalog link. Partial catalog capture; source access and publication review remain separate steps.')
    if not rows:
        raise ValueError('No document links found; source may require access or layout review')
    return list(rows.values())
