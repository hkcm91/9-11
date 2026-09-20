import json
import pytest
from archive.document_library import DocumentLibrary
from archive.library_editorial import EditorialDesk,prepare
from archive.library_digest import decorate


class Editor:
    model='test-editor'
    calls=0
    def choose(self,prepared):
        self.calls+=1
        return dict(model=self.model,answers=dict(title=dict(choice='use',confidence=.95),summary=dict(choice='0',confidence=.95)))


@pytest.fixture
def source(tmp_path):
    lib=DocumentLibrary(tmp_path/'test.sqlite',tmp_path/'objects')
    text='SUBJECT: TEST REPORT\n\nSUMMARY: An initial account describes a suspected incident.\nUPDATE: The later investigation corrected the initial account.'
    identifier=lib.ingest(dict(collection='wikileaks',release_id='test',source_item_id='one',title='CABLE1',source_url='https://example.org/one',format='text'),payload=text.encode())
    yield lib,identifier,text
    lib.close()


def test_cited_summary_title_cache_and_original_preservation(source):
    lib,identifier,text=source
    editor=Editor(); desk=EditorialDesk(lib)
    result=desk.build(identifier,editor)
    assert result['title']=='Test Report'
    assert 'corrected' in result['summary']
    for p in result['summary_passages']: assert text[p['start']:p['end']]==p['text']
    assert desk.build(identifier,editor)==result and editor.calls==1
    lib.publish(identifier,True,'test','Approved')
    assert decorate(lib,lib.document(identifier))['brief_summary']==result['summary']
    assert lib.document(identifier)['title']=='CABLE1'


def test_batch_publication_scope_and_resume(source):
    lib,identifier,text=source; desk=EditorialDesk(lib); editor=Editor()
    assert desk.batch(editor,3,progress=lambda _:None)['completed']==0
    assert editor.calls==0
    assert desk.batch(editor,3,True,progress=lambda _:None)['completed']==1
    assert desk.batch(editor,3,True,progress=lambda _:None)['completed']==0


def test_uncertainty_never_claims_approved_title_or_summary(source):
    lib,identifier,text=source
    class Uncertain(Editor):
        def choose(self,prepared):
            return dict(answers=dict(title=dict(choice='uncertain',confidence=.9),summary=dict(choice='insufficient',confidence=.9)))
    result=EditorialDesk(lib).build(identifier,Uncertain())
    assert result['title']=='CABLE1' and not result['summary_reviewed']
    assert result['status']=='Needs editorial review'
