import pytest
from archive.document_library import DocumentLibrary
from archive.library_workbench import Workbench
from archive.library_digest import decorate


@pytest.fixture
def setup(tmp_path):
    lib=DocumentLibrary(tmp_path/'test.sqlite',tmp_path/'objects')
    identifier=lib.ingest(dict(collection='wikileaks',release_id='test',source_item_id='1',title='Original title',source_url='https://example.org/source',format='text'),payload=b'Exact source quotation.\fLater correction.')
    desk=Workbench(lib)
    yield lib,identifier,desk
    lib.close()


def test_review_audit_optimistic_concurrency_and_originals(setup):
    lib,identifier,desk=setup
    values=dict(id=identifier,title='Readable title',summary='Human wording',note='Checked source page',status='reviewed',revision=0)
    assert desk.queue('publication')['total']==1
    doc=desk.review(values)
    assert doc['review']['title']=='Readable title' and len(doc['history'])==1
    assert lib.document(identifier) is None
    with pytest.raises(ValueError,match='Another review'): desk.review(values)
    lib.publish(identifier,True,'test','Approved publication separately')
    decorated=decorate(lib,lib.document(identifier))
    assert decorated['display_title']=='Readable title'
    assert decorated['summary_status']=='Human-edited brief'
    assert lib.document(identifier)['title']=='Original title'
    assert lib.page(identifier,1)['text']=='Exact source quotation.'


def test_exact_quote_citation_withdrawal_and_export(setup):
    lib,identifier,desk=setup
    lib.publish(identifier,True,'test','Approved')
    folder=desk.create_folder(dict(title='Investigation',question='What changed?'))
    values=dict(folder_id=folder['id'],kind='quote',text='Exact source quotation.',document_id=identifier,page=1,note='Compare later account')
    saved=desk.add(values)['items'][0]
    assert saved['start']==0 and saved['source_sha256']==lib.document(identifier)['sha256']
    with pytest.raises(ValueError,match='exactly'): desk.add({**values,'text':'Invented quote'})
    assert 'page 1' in desk.markdown(folder['id'])
    lib.publish(identifier,False,'test','Withdraw source')
    result=desk.folder(folder['id'])['items'][0]
    assert result['unavailable'] and 'source_sha256' not in result
    assert 'Exact source quotation.' not in desk.markdown(folder['id'])


def test_folder_notes_events_and_cross_folder_status(setup):
    lib,identifier,desk=setup
    folder=desk.create_folder(dict(title='Research'))
    item=desk.add(dict(folder_id=folder['id'],kind='hypothesis',text='An alternative explanation'))['items'][0]
    assert desk.item_status(dict(folder_id=folder['id'],id=item['id'],status='done'))['items'][0]['status']=='done'
    with pytest.raises(ValueError): desk.item_status(dict(folder_id='wrong',id=item['id'],status='open'))
    with pytest.raises(ValueError): desk.add(dict(folder_id=folder['id'],kind='event',text='Incident',event_date='2025-02-30'))
    result=desk.add(dict(folder_id=folder['id'],kind='event',text='Incident',event_date='2025-02-28'))
    assert result['items'][-1]['event_date']=='2025-02-28'
    with pytest.raises(ValueError): desk.add(dict(folder_id=folder['id'],kind='document',document_id=identifier))
