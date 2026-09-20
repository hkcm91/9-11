"""Checksum-verified bulk transport and restartable, full-body Cablegate import."""
import csv
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from archive.document_library import now
from archive.library_cablegate import valid_cable_row
from archive.library_completion import CompletionDesk
from evidence_collections.wikileaks.adapters import WikiLeaksPlusDAdapter, WikiLeaksWarDiariesAdapter
from evidence_collections.wikileaks.remote_sources import CABLEGATE_FIELDS, WAR_DIARY_FIELDS, USER_AGENT

ITEM = 'wikileaks-cables-csv'
RELEASE = 'cablegate-ia-bulk-v1'


def valid_afghan_row(row):
    # Report keys are opaque: GUIDs, shorter hexadecimal forms and numeric IDs.
    return (None not in row and all(isinstance(row.get(f), str) for f in WAR_DIARY_FIELDS)
        and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', row['ReportKey']))
        and bool(row['Summary'].strip()) and '\ufffd' not in row['Summary'])


def hashes(path):
    sha1, sha256 = hashlib.sha1(), hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha1.update(chunk)
            sha256.update(chunk)
    return sha1.hexdigest(), sha256.hexdigest()


def download(output, progress=print, *, item=ITEM, filename='cables.csv'):
    """Resume only against a pinned size and checksum; never parse partial files."""
    if Path(filename).name != filename or '/' in filename or '\\' in filename:
        raise ValueError('Transport must be a plain filename')
    output.mkdir(parents=True, exist_ok=True)
    metadata_path = output / 'source-metadata.json'
    if not metadata_path.exists():
        with urlopen(Request(f'https://archive.org/metadata/{item}', headers={'User-Agent': USER_AGENT}), timeout=60) as response:
            metadata = json.load(response)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    entry = next(f for f in metadata['files'] if f['name'] == filename)
    size, checksum = int(entry['size']), entry['sha1']
    if size <= 0 or size > 5 * 1024**3 or len(checksum) != 40:
        raise ValueError('Unexpected bulk source size or checksum')
    target, partial = output / filename, output / (filename + '.part')
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
            with urlopen(Request(f'https://archive.org/download/{item}/{filename}', headers=headers), timeout=120) as response:
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
    receipt = dict(source_url=f'https://archive.org/download/{item}/{filename}',
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


def import_full(library, path, receipt, *, max_records=None, progress=print, kind='cablegate'):
    if kind not in {'cablegate', 'afghan'}:
        raise ValueError('Unsupported bulk dialect')
    war = kind == 'afghan'
    fields = WAR_DIARY_FIELDS if war else CABLEGATE_FIELDS
    release = 'afghan-ia-bulk-v1' if war else RELEASE
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
    if war and state.get('validation') != 'afghan-v3':
        # Replay earlier strict-GUID attempts; immutable objects are reused.
        state = dict(offset=0, rows=0, imported=0, rejected=0, duplicates=0, complete=False, validation='afghan-v3')
        with db:
            db.execute('DELETE FROM library_bulk_rejections WHERE source_sha256=?', (receipt['sha256'],))
    state.update(release_id=release, title='Afghan War Diary' if war else 'Cablegate')
    desk = CompletionDesk(library)
    scope = dict(collection='wikileaks', release_id=release, title=state['title'] + ' — full CSV mirror import',
        inventory_status='partial_catalog', expected_files=None, catalog_url=receipt['source_url'],
        scope_note='Full transport preserved. Import and rejected-row accounting are separate from publisher completeness and publication review.')
    previous_scope = db.execute('SELECT scope_json FROM library_release_scopes WHERE collection=? AND release_id=?', ('wikileaks',release)).fetchone()
    if previous_scope:
        scope = json.loads(previous_scope[0])
    desk.register([scope])
    adapter = WikiLeaksWarDiariesAdapter() if war else WikiLeaksPlusDAdapter()
    old_limit = csv.field_size_limit(16 * 1024**2)
    processed = 0
    old_sync = db.execute('PRAGMA synchronous').fetchone()[0]
    # WAL keeps transactions consistent; NORMAL avoids a disk flush per row.
    # After power loss, any lost tail is recovered by replaying the checkpoint.
    db.execute('PRAGMA synchronous=NORMAL')

    def checkpoint():
        state['updated_at'] = now()
        with db:
            db.execute('INSERT OR REPLACE INTO library_bulk_jobs VALUES (?,?)', (receipt['sha256'], json.dumps(state)))

    try:
        with path.open('rb') as stream:
            stream.seek(state['offset'])
            reader = csv.DictReader(Lines(stream), fieldnames=fields, escapechar=None if war else '\\', strict=True)
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
                valid = valid_afghan_row(row) if war else valid_cable_row(row)
                if not valid:
                    with db:
                        db.execute('INSERT OR REPLACE INTO library_bulk_rejections VALUES (?,?,?,?,?)',
                            (receipt['sha256'], number, start, stream.tell(), 'Invalid reference, field count, missing body or damaged UTF-8; original bytes retained'))
                    state['rejected'] += 1
                else:
                    item = adapter.normalize(row)
                    reference = row['ReportKey'] if war else row['reference'].strip().removesuffix('_a')
                    body = row['Summary'] if war else row['body']
                    item.source_url = f'https://warlogs.wikileaks.org/id/{reference}/' if war else f'https://wikileaks.org/plusd/cables/{reference}_a.html'
                    item.metadata_raw['body'] = body
                    item.metadata_raw.update(content_kind='full_mirror_text', transport_url=receipt['source_url'],
                        transport_sha256=receipt['sha256'], transport_byte_start=start, transport_byte_end=stream.tell())
                    record = adapter.serialize_source_item(item)
                    record.pop('ingested_at', None)
                    entry = dict(collection='wikileaks', release_id=release, source_item_id=reference,
                        title=item.title_raw or reference, source_url=item.source_url, format='record',
                        content_kind='full_mirror_text', document_date=item.date_raw,
                        provenance_note='Full mirrored narrative; original bulk bytes retained. Publisher completeness and redaction equivalence unverified.')
                    library.register_inventory([entry])
                    # Reuse existing complete bodies, including the earlier sample, without changing publication decisions.
                    existing = db.execute('''SELECT d.id FROM library_documents d JOIN library_pages p ON p.document_id=d.id
                        WHERE d.source_url=? AND d.extraction_status!='quarantined' AND p.number=1 AND p.text=? LIMIT 1''',
                        (item.source_url, body)).fetchone()
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
        db.execute(f'PRAGMA synchronous={old_sync}')
    return dict(**state, source_sha256=receipt['sha256'], publication='New records await review; complete means CSV consumed, not all WikiLeaks archived')


def fetch_full(library, output, max_records=None, progress=print):
    path, receipt = download(output, progress)
    return import_full(library, path, receipt, max_records=max_records, progress=progress)


def fetch_afghan(library, output, max_records=None, progress=print):
    import py7zr
    archive, transport = download(output, progress, item='WikileaksWarDiaryCsv', filename='afg-war-diary.csv.7z')
    # Extract only the known regular CSV in an isolated directory. Never execute
    # content, follow archive paths, or trust a pre-existing extracted file.
    with py7zr.SevenZipFile(archive) as compressed:
        entries = compressed.list()
        if len(entries) != 1 or entries[0].filename != 'afg.csv' or entries[0].is_directory:
            raise ValueError('Unexpected Afghan archive member layout')
        if not 0 < entries[0].uncompressed <= 512 * 1024**2:
            raise ValueError('Afghan CSV exceeds extraction budget')
        if any(member.is_symlink or member.is_directory for member in compressed.files):
            raise ValueError('Archive links or directories are not supported')
        with tempfile.TemporaryDirectory(dir=output) as scratch:
            compressed.extract(path=scratch, targets=['afg.csv'])
            extracted = Path(scratch) / 'afg.csv'
            if extracted.stat().st_size != entries[0].uncompressed:
                raise ValueError('Extracted CSV size differs from archive directory')
            sha1, sha256 = hashes(extracted)
            receipt = dict(source_url=transport['source_url'], bytes=extracted.stat().st_size,
                sha1=sha1, sha256=sha256, archive_sha256=transport['sha256'], verified_at=now())
            extracted.replace(output / 'afg.csv')
    (output/'csv-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return import_full(library, output/'afg.csv', receipt, kind='afghan', max_records=max_records, progress=progress)


def bulk_status(library, output):
    """Read persisted progress; never infer a running worker from a partial file."""
    result = dict(expected_bytes=None, preserved_bytes=0, transport_verified=False, jobs=[], inventories=[])
    for inventory in (output/'cables.csv.inventory.json', output/'afghan'/'afg.csv.inventory.json'):
        if inventory.exists():
            result['inventories'].append(json.loads(inventory.read_text(encoding='utf-8')))
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
    if library.db.execute("SELECT 1 FROM sqlite_master WHERE name='library_editorial'").fetchone():
        from archive.library_editorial import VERSION
        counts=library.db.execute('''SELECT count(DISTINCT e.document_id),
            count(DISTINCT CASE WHEN json_extract(e.result_json,'$.summary_reviewed')=1 AND json_extract(e.result_json,'$.title_supported')=1 THEN e.document_id END)
            FROM library_editorial e JOIN library_documents d ON d.id=e.document_id WHERE e.version=? AND d.collection='wikileaks' ''',(VERSION,)).fetchone()
        total=library.db.execute("SELECT count(*) FROM library_documents WHERE collection='wikileaks' AND extraction_status!='quarantined'").fetchone()[0]
        result['editorial']=dict(processed=counts[0],reviewed=counts[1],pending_imported=max(0,total-counts[0]))
    return result
