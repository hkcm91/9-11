import pytest
from archive.document_library import DocumentLibrary
from archive.library_digest import DocumentDigest, readable_title, file_stem, decorate
from historical_engine.ai.fakes import FakeDecisionProvider


@pytest.fixture
def source(tmp_path):
    lib = DocumentLibrary(tmp_path / 'test.sqlite', tmp_path / 'objects')
    text = 'SUBJECT: SUSPECTED CHEMICAL EQUIPMENT\nREF: RECORD 1\n\nOpening account. ' + 'Context. ' * 1700 + '\nUPDATE: Chemicals were vitamins or supplements.'
    identifier = lib.ingest(dict(collection='wikileaks', release_id='test', source_item_id='CABLE1',
        source_url='https://example.org/one', title='CABLE1', format='text'), payload=text.encode())
    lib.publish(identifier, True, 'test', 'Approved')
    yield lib, identifier, text
    lib.close()


def test_subject_title_and_safe_filename():
    assert readable_title('72TEHRAN1164', 'SUBJECT: AIRCRAFT FOR IRAN\nREF: 1') == 'Aircraft For Iran'
    assert readable_title('Original title', 'No subject header') == 'Original title'
    assert readable_title('85CODE123', 'SUBJ: BUSINESS IN BRUNEI\n1. First paragraph') == 'Business In Brunei'
    name = file_stem('../../bad\r\n"title', 'abcdef123456')
    assert '/' not in name and '\r' not in name and '"' not in name and name.endswith('abcdef1234')


def test_brief_keeps_late_update_exact_citations_and_original_bytes(source):
    lib, identifier, text = source
    doc = lib.document(identifier)
    original = (lib.objects / doc['sha256']).read_bytes()
    provider = FakeDecisionProvider()
    provider.script('supports_claim', doc['record_id'], 'supports', .9, object_id='reading-brief:' + identifier)
    briefs = DocumentDigest(lib)
    result = briefs.build(identifier, provider)
    assert result['title_supported']
    assert any('vitamins or supplements' in p['text'] for p in result['passages'])
    for p in result['passages']:
        assert text[p['start']:p['end']] == p['text']
    assert briefs.build(identifier, provider) == result and len(provider.calls) == 1
    assert 'SHA-256:' in briefs.markdown(identifier)
    assert 'vitamins or supplements' in briefs.markdown(identifier)
    assert (lib.objects / doc['sha256']).read_bytes() == original
    assert lib.document(identifier)['title'] == 'CABLE1'
    assert decorate(lib, doc)['display_title'] == 'Suspected Chemical Equipment'


def test_uncertain_title_keeps_original_and_withdrawal_blocks_exports(source):
    lib, identifier, _ = source
    briefs = DocumentDigest(lib)
    result = briefs.build(identifier, FakeDecisionProvider())
    assert not result['title_supported'] and result['title'] == 'CABLE1'
    lib.publish(identifier, False, 'test', 'Withdraw')
    with pytest.raises(ValueError):
        briefs.get(identifier)
    with pytest.raises(ValueError):
        briefs.markdown(identifier)


def test_fabricated_evidence_rejected(source):
    lib, identifier, _ = source
    class Bad(FakeDecisionProvider):
        def decide(self, request):
            response = super().decide(request)
            response.evidence_ids = ['invented']
            return response
    briefs = DocumentDigest(lib)
    with pytest.raises(ValueError):
        briefs.build(identifier, Bad())
    assert briefs.get(identifier) is None
