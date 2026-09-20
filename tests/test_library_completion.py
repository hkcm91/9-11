import hashlib
import pytest
from archive.document_library import DocumentLibrary
from archive.library_completion import CompletionDesk
from archive.library_catalogs import snowden_manifest, doj_manifest
from archive.library_sources import verify_catalog_identity
from historical_engine.ai.fakes import FakeDecisionProvider


@pytest.fixture
def archive(tmp_path):
    lib = DocumentLibrary(tmp_path/'archive.sqlite', tmp_path/'objects')
    yield lib
    lib.close()


def add(lib, text=b'Public source contents'):
    entry = dict(collection='pentagon_papers',release_id='test',source_item_id='1',
        title='Expected volume',source_url='https://example.org/file.txt',format='text')
    lib.register_inventory([entry])
    identifier = lib.ingest(entry,payload=text)
    lib.record_attempt(entry,dict(status='processed',document_id=identifier))
    return entry,identifier


def test_completion_requires_scope_integrity_review_text_and_publication(archive):
    entry,identifier=add(archive)
    desk=CompletionDesk(archive)
    assert not desk.releases()[0]['complete']
    desk.register([dict(collection='pentagon_papers',release_id='test',inventory_status='complete_catalog',expected_files=1)])
    assert desk.items('pentagon_papers','test')[0]['stage']=='awaiting_review'
    archive.publish(identifier,True,'test','Reviewed')
    assert not desk.releases()[0]['complete']
    assert desk.verify('pentagon_papers','test')['failed']==0
    assert desk.releases()[0]['complete']
    path=archive.objects/archive.document(identifier)['sha256']
    path.write_bytes(b'changed')
    assert desk.verify('pentagon_papers','test')['failed']==1
    assert not desk.releases()[0]['complete']
    assert desk.items('pentagon_papers','test')[0]['stage']=='integrity_problem'
    path.unlink()
    assert not desk.items('pentagon_papers','test')[0]['downloaded']


def test_samples_never_complete_and_failed_retry_keeps_preserved_document(archive):
    entry,identifier=add(archive)
    archive.publish(identifier,True,'test','Reviewed')
    desk=CompletionDesk(archive)
    desk.register([dict(collection='pentagon_papers',release_id='test',inventory_status='bounded_sample',expected_files=1)])
    desk.verify('pentagon_papers','test')
    assert not desk.releases()[0]['complete']
    archive.record_attempt(entry,dict(status='failed',error='Refresh failed'))
    row=desk.items('pentagon_papers','test')[0]
    assert row['downloaded'] and row['document_id']==identifier and row['reason']=='Refresh failed'
    assert desk.releases()[0]['counts']['attention']==1


def test_expected_missing_and_ocr_prevent_completion(archive):
    entry,identifier=add(archive,b'First page\f')
    archive.publish(identifier,True,'test','Reviewed')
    desk=CompletionDesk(archive)
    desk.register([dict(collection='pentagon_papers',release_id='test',inventory_status='complete_catalog',expected_files=2)])
    desk.verify('pentagon_papers','test')
    row=desk.releases()[0]
    assert row['unlisted_expected']==1 and row['counts']['ocr_pages']==1 and not row['complete']


def test_jev_match_is_cached_and_cannot_change_inventory(archive):
    entry,identifier=add(archive)
    archive.publish(identifier,True,'test','Reviewed')
    desk=CompletionDesk(archive); provider=FakeDecisionProvider()
    before=desk.releases()
    result=desk.match('pentagon_papers','test','1',identifier,provider)
    assert desk.match('pentagon_papers','test','1',identifier,provider)==result
    assert len(provider.calls)==1 and desk.releases()==before
    archive.publish(identifier,False,'test','Withdraw')
    with pytest.raises(ValueError):
        desk.match('pentagon_papers','test','1',identifier,provider)


def test_catalog_parsers_pin_scope_and_reject_wrong_identity(tmp_path):
    commit=dict(sha='a'*40,commit={'tree':{'sha':'b'*40}})
    data=b'PDF bytes'; sha=hashlib.sha1(b'blob 9\0'+data).hexdigest()
    tree=dict(sha='b'*40,truncated=False,tree=[dict(path='documents/2013/file.pdf',type='blob',sha=sha,size=9)])
    entry=snowden_manifest(tree,commit)[0]
    assert '/'+('a'*40)+'/' in entry['source_url']
    path=tmp_path/'file'; path.write_bytes(data)
    verify_catalog_identity(path,entry)
    path.write_bytes(b'wrong')
    with pytest.raises(ValueError): verify_catalog_identity(path,entry)
    with pytest.raises(ValueError): snowden_manifest({**tree,'truncated':True},commit)
    html='<a href="/epstein/files/DataSet%201/EFTA00000001.pdf">file</a><a href="https://evil.test/EFTA00000002.pdf">bad</a>'
    assert len(doj_manifest(html,'https://www.justice.gov/epstein/doj-disclosures/data-set-1-files',1))==1
