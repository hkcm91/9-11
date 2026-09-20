import csv
import hashlib
import io
import json
import pytest
from archive.document_library import DocumentLibrary
from archive.library_wikileaks_bulk import import_full, download, valid_afghan_row, fetch_afghan
from archive.library_wikileaks_catalog import release_scopes
from evidence_collections.wikileaks.remote_sources import WAR_DIARY_FIELDS


def source(tmp_path):
    path = tmp_path / 'cables.csv'
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, escapechar='\\', doublequote=False)
        writer.writerow(['1','1966','66TEST1','origin','secret','','','SUBJECT: Test\nFull "quoted" body\nEND'])
        writer.writerow(['2','1966','invalid','origin','secret','','','Bad reference retained in original'])
        writer.writerow(['3','1966','66TEST2','origin','secret','','','Second body'])
    return path, dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), source_url='https://example.org/cables.csv')


def test_resume_rejections_and_complete_bodies(tmp_path):
    path, receipt = source(tmp_path)
    library = DocumentLibrary(tmp_path/'test.sqlite', tmp_path/'objects')
    first = import_full(library, path, receipt, max_records=2, progress=lambda _: None)
    assert first['rows'] == 2 and first['rejected'] == 1 and not first['complete']
    result = import_full(library, path, receipt, progress=lambda _: None)
    assert result['rows'] == 3 and result['complete'] and result['imported'] == 2
    assert library.db.execute('SELECT count(*) FROM library_documents').fetchone()[0] == 2
    assert library.db.execute('SELECT text FROM library_pages ORDER BY rowid').fetchone()[0].endswith('END')
    assert library.db.execute('SELECT count(*) FROM library_bulk_rejections').fetchone()[0] == 1
    assert import_full(library, path, receipt)['rows'] == 3
    assert library.search() == []  # importing does not invent a publication review
    library.close()


def test_changed_transport_cannot_resume(tmp_path):
    path, receipt = source(tmp_path)
    library = DocumentLibrary(tmp_path/'test.sqlite', tmp_path/'objects')
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='receipt'):
        import_full(library, path, receipt)
    library.close()


def test_publisher_catalog_shared_portals_and_untrusted_links():
    tiles = ''.join(f'<li class="tile"><a href="{url}"><h2>{title}</h2></a></li>' for title,url in
        [('Iraq','https://wardiaries.wikileaks.org/'),('Afghan','https://wardiaries.wikileaks.org/'),
         ('Foreign','https://evil.example/'),('Broken','javascript:alert(1)')])
    scopes = release_scopes(tiles)
    assert len(scopes) == 2
    assert scopes[0]['release_id'] != scopes[1]['release_id']
    assert all(s['expected_files'] is None and s['inventory_status'] == 'not_started' for s in scopes)


def test_download_resumes_and_checks_source_hash(tmp_path, monkeypatch):
    payload = b'complete transport bytes'
    (tmp_path/'source-metadata.json').write_text(json.dumps({'files':[dict(name='cables.csv',size=str(len(payload)),sha1=hashlib.sha1(payload).hexdigest())]}))
    (tmp_path/'cables.csv.part').write_bytes(payload[:8])
    class Response(io.BytesIO):
        status = 206
        headers = {'Content-Range': f'bytes 8-{len(payload)-1}/{len(payload)}'}
    def request(req, **kwargs):
        assert req.get_header('Range') == 'bytes=8-'
        return Response(payload[8:])
    monkeypatch.setattr('archive.library_wikileaks_bulk.urlopen', request)
    path, receipt = download(tmp_path)
    assert path.read_bytes() == payload
    assert receipt['sha256'] == hashlib.sha256(payload).hexdigest()
    path.write_bytes(b'x' * len(payload))
    with pytest.raises(ValueError, match='catalog'):
        download(tmp_path)


def test_ignored_range_never_appends_wrong_bytes(tmp_path, monkeypatch):
    (tmp_path/'source-metadata.json').write_text(json.dumps({'files':[dict(name='cables.csv',size='20',sha1='a'*40)]}))
    partial = tmp_path/'cables.csv.part'
    partial.write_bytes(b'partial')
    class Response(io.BytesIO):
        status = 200
        headers = {}
    monkeypatch.setattr('archive.library_wikileaks_bulk.urlopen', lambda *a,**k: Response(b'incorrect response'))
    with pytest.raises(ValueError, match='resume range'):
        download(tmp_path)
    assert partial.read_bytes() == b'partial'


def test_afghan_dialect_preserves_full_narrative_and_resume(tmp_path):
    path = tmp_path/'afg.csv'
    row = {f:'' for f in WAR_DIARY_FIELDS}
    row.update(ReportKey='D92871CA-D217-4124-B8FB-89B9A2CFFCB4',Summary='Initial "quoted" report\nUPDATE: corrected C:\\path. ',Title='Report',DateOccurred='2004-01-01')
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=WAR_DIARY_FIELDS)
        writer.writerow(row)
    receipt=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_url='https://example.org/afghan')
    library=DocumentLibrary(tmp_path/'test.sqlite',tmp_path/'objects')
    result=import_full(library,path,receipt,kind='afghan')
    assert result['complete'] and result['rows']==1
    assert library.db.execute('SELECT text FROM library_pages').fetchone()[0]==row['Summary']
    assert import_full(library,path,receipt,kind='afghan')['rows']==1
    library.close()


def test_afghan_legacy_numeric_ids_are_real_records():
    row={f:'' for f in WAR_DIARY_FIELDS}
    row.update(ReportKey='1009075',Summary='Complete narrative')
    assert valid_afghan_row(row)
    row['ReportKey']='77980224-2219-0B3F-9F3AAB156E5ED8F9'
    assert valid_afghan_row(row)
    row['Summary']=' '
    assert not valid_afghan_row(row)


def test_deduplication_preserves_trailing_whitespace(tmp_path):
    path,receipt=source(tmp_path)
    library=DocumentLibrary(tmp_path/'test.sqlite',tmp_path/'objects')
    import_full(library,path,receipt)
    # Simulate losing a checkpoint after ingestion: exact source bodies are reused.
    with library.db: library.db.execute('DELETE FROM library_bulk_jobs')
    result=import_full(library,path,receipt)
    assert result['duplicates']==2 and result['imported']==0
    assert library.db.execute('SELECT count(*) FROM library_documents').fetchone()[0]==2
    library.close()


def test_afghan_archive_rejects_unexpected_members(tmp_path, monkeypatch):
    import py7zr
    source=tmp_path/'unexpected.txt'; source.write_text('Not the CSV')
    compressed=tmp_path/'source.7z'
    with py7zr.SevenZipFile(compressed,'w') as archive:
        archive.write(source,arcname='unexpected.txt')
    monkeypatch.setattr('archive.library_wikileaks_bulk.download',lambda *a,**k:(compressed,{}))
    library=DocumentLibrary(tmp_path/'test.sqlite',tmp_path/'objects')
    with pytest.raises(ValueError,match='member layout'):
        fetch_afghan(library,tmp_path)
    assert not (tmp_path/'afg.csv').exists()
    library.close()
