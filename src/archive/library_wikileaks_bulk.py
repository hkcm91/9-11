"""Checksum-verified bulk transport and restartable, full-body Cablegate import."""
import csv
import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

from archive.document_library import now
from archive.library_cablegate import valid_cable_row
from archive.library_completion import CompletionDesk
from evidence_collections.wikileaks.adapters import WikiLeaksPlusDAdapter
from evidence_collections.wikileaks.remote_sources import CABLEGATE_FIELDS, USER_AGENT

ITEM = 'wikileaks-cables-csv'
RELEASE = 'cablegate-ia-bulk-v1'


def hashes(path):
    sha1, sha256 = hashlib.sha1(), hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha1.update(chunk)
            sha256.update(chunk)
    return sha1.hexdigest(), sha256.hexdigest()


def download(output, progress=print):
    """Resume only against a pinned size and checksum; never parse partial files."""
    output.mkdir(parents=True, exist_ok=True)
    metadata_path = output / 'source-metadata.json'
    if not metadata_path.exists():
        with urlopen(Request(f'https://archive.org/metadata/{ITEM}', headers={'User-Agent': USER_AGENT}), timeout=60) as response:
            metadata = json.load(response)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    entry = next(f for f in metadata['files'] if f['name'] == 'cables.csv')
    size, checksum = int(entry['size']), entry['sha1']
    if size <= 0 or size > 5 * 1024**3 or len(checksum) != 40:
        raise ValueError('Unexpected bulk source size or checksum')
    target, partial = output / 'cables.csv', output / 'cables.csv.part'
    if not target.exists():
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > size:
            raise ValueError('Partial file exceeds catalog size')
        if shutil.disk_usage(output).free < size - offset + 10 * 1024**3:
            raise ValueError('Download requires a 10 GiB free-space reserve')
        if offset < size:
            headers = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            with urlopen(Request(f'https://archive.org/download/{ITEM}/cables.csv', headers=headers), timeout=120) as response:
                if offset and (response.status != 206 or response.headers.get('Content-Range') != f'bytes {offset}-{size-1}/{size}'):
                    raise ValueError('Server did not honor the exact resume range; partial file retained')
                with partial.open('ab' if offset else 'wb') as handle:
                    reported = offset
                    while chunk := response.read(1024 * 1024):
                        if offset + len(chunk) > size:
                            raise ValueError('Download exceeds catalog size')
                        handle.write(chunk)
                        offset += len(chunk)
                        if offset - reported >= 32 * 1024**2:
                            progress(dict(stage='downloading', bytes=offset, expected_bytes=size))
                            reported = offset
        if partial.stat().st_size != size or hashes(partial)[0] != checksum:
            raise ValueError('Bulk download size/checksum mismatch; not imported')
        partial.replace(target)
    actual_sha1, sha256 = hashes(target)
    if target.stat().st_size != size or actual_sha1 != checksum:
        raise ValueError('Preserved bulk file does not match source catalog')
    receipt = dict(source_url=f'https://archive.org/download/{ITEM}/cables.csv',
        bytes=size, sha1=actual_sha1, sha256=sha256, verified_at=now())
    (output / 'transport.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return target, receipt


class Lines:
    """CSV consumes physical lines; binary tell preserves exact restart offsets."""
    def __init__(self, handle):
        self.handle = handle

    def __iter__(self):
        return self

    def __next__(self):
        line = self.handle.readline()
        if not line:
            raise StopIteration
        return line.decode('utf-8', errors='replace')


def import_full(library, path, receipt, *, max_records=None, progress=print):
    if max_records is not None and max_records < 1:
        raise ValueError('max_records must be positive')
    # A receipt is not a substitute for checking the bytes on disk.
    if path.stat().st_size != receipt['bytes'] or hashes(path)[1] != receipt['sha256']:
        raise ValueError('Import file does not match verified transport receipt')
    db = library.db
    db.executescript('''CREATE TABLE IF NOT EXISTS library_bulk_jobs (
        source_sha256 TEXT PRIMARY KEY, state_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS library_bulk_rejections (
        source_sha256 TEXT, row_number INTEGER, byte_start INTEGER, byte_end INTEGER,
        reason TEXT NOT NULL, PRIMARY KEY(source_sha256,row_number));
        CREATE INDEX IF NOT EXISTS library_documents_source ON library_documents(source_url);
        CREATE INDEX IF NOT EXISTS library_attempts_source ON library_attempts(collection,release_id,source_item_id,id);''')
    saved = db.execute('SELECT state_json FROM library_bulk_jobs WHERE source_sha256=?', (receipt['sha256'],)).fetchone()
    state = json.loads(saved[0]) if saved else dict(offset=0, rows=0, imported=0, rejected=0, duplicates=0, complete=False)
    desk = CompletionDesk(library)
    desk.register([dict(collection='wikileaks', release_id=RELEASE, title='Cablegate — full CSV mirror import',
        inventory_status='partial_catalog', expected_files=None, catalog_url=f'https://archive.org/metadata/{ITEM}',
        scope_note='Full transport preserved. Import and rejected-row accounting are separate from publisher completeness and publication review.')])
    adapter = WikiLeaksPlusDAdapter()
    old_limit = csv.field_size_limit(16 * 1024**2)
    processed = 0

    def checkpoint():
        state['updated_at'] = now()
        with db:
            db.execute('INSERT OR REPLACE INTO library_bulk_jobs VALUES (?,?)', (receipt['sha256'], json.dumps(state)))

    try:
        with path.open('rb') as stream:
            stream.seek(state['offset'])
            reader = csv.DictReader(Lines(stream), fieldnames=CABLEGATE_FIELDS, escapechar='\\', strict=True)
            while max_records is None or processed < max_records:
                start = stream.tell()
                try:
                    row = next(reader)
                except StopIteration:
                    state['complete'] = True
                    checkpoint()
                    break
                except csv.Error as exc:
                    state['error'] = f'CSV parsing stopped at byte {start}: {exc}'
                    checkpoint()
                    raise ValueError(state['error']) from exc
                number = state['rows'] + 1
                if not valid_cable_row(row):
                    with db:
                        db.execute('INSERT OR REPLACE INTO library_bulk_rejections VALUES (?,?,?,?,?)',
                            (receipt['sha256'], number, start, stream.tell(), 'Invalid reference, field count, missing body or damaged UTF-8; original bytes retained'))
                    state['rejected'] += 1
                else:
                    item = adapter.normalize(row)
                    reference = row['reference'].strip().removesuffix('_a')
                    item.source_url = f'https://wikileaks.org/plusd/cables/{reference}_a.html'
                    item.metadata_raw.update(content_kind='full_mirror_text', transport_url=receipt['source_url'],
                        transport_sha256=receipt['sha256'], transport_byte_start=start, transport_byte_end=stream.tell())
                    record = adapter.serialize_source_item(item)
                    record.pop('ingested_at', None)
                    entry = dict(collection='wikileaks', release_id=RELEASE, source_item_id=reference,
                        title=item.title_raw or reference, source_url=item.source_url, format='record',
                        content_kind='full_mirror_text', document_date=item.date_raw,
                        provenance_note='Full mirrored cable body; original bulk bytes retained. Publisher completeness unverified.')
                    library.register_inventory([entry])
                    # Reuse existing complete bodies, including the earlier sample, without changing publication decisions.
                    existing = db.execute('''SELECT d.id FROM library_documents d JOIN library_pages p ON p.document_id=d.id
                        WHERE d.source_url=? AND d.extraction_status!='quarantined' AND p.number=1 AND p.text=? LIMIT 1''',
                        (item.source_url, row['body'].strip())).fetchone()
                    if existing:
                        identifier = existing[0]
                        state['duplicates'] += 1
                    else:
                        identifier = library.ingest(entry, payload=(json.dumps(record, ensure_ascii=False)+'\n').encode('utf-8'))
                        state['imported'] += 1
                    library.record_attempt(entry, dict(status='processed', document_id=identifier, error=None))
                state.update(offset=stream.tell(), rows=number)
                state.pop('error', None)
                checkpoint()
                processed += 1
                if processed % 500 == 0:
                    progress(dict(stage='importing', **state))
                    if shutil.disk_usage(path.parent).free < 10 * 1024**3:
                        raise ValueError('Import paused to retain 10 GiB free space')
    finally:
        csv.field_size_limit(old_limit)
    return dict(**state, source_sha256=receipt['sha256'], publication='New records await review; complete means CSV consumed, not all WikiLeaks archived')


def fetch_full(library, output, max_records=None, progress=print):
    path, receipt = download(output, progress)
    return import_full(library, path, receipt, max_records=max_records, progress=progress)


def bulk_status(library, output):
    """Read persisted progress; never infer a running worker from a partial file."""
    result = dict(expected_bytes=None, preserved_bytes=0, transport_verified=False, jobs=[])
    metadata = output / 'source-metadata.json'
    if metadata.exists():
        try:
            entry = next(f for f in json.loads(metadata.read_text(encoding='utf-8'))['files'] if f['name']=='cables.csv')
            result['expected_bytes'] = int(entry['size'])
        except (ValueError, KeyError, StopIteration):
            pass
    for name in ('cables.csv', 'cables.csv.part'):
        path = output / name
        if path.exists():
            result['preserved_bytes'] = path.stat().st_size
            result['last_file_write'] = path.stat().st_mtime
            break
    receipt_path = output / 'transport.json'
    if receipt_path.exists() and (output / 'cables.csv').exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        result['transport_verified'] = receipt['bytes'] == result['preserved_bytes']
        result['verified_at'] = receipt['verified_at']
    if library.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_bulk_jobs'").fetchone():
        result['jobs'] = [json.loads(row[0]) for row in library.db.execute('SELECT state_json FROM library_bulk_jobs')]
    return result
