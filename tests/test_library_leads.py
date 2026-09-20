import pytest
from archive.document_library import DocumentLibrary
from archive.library_leads import LeadInbox
from historical_engine.ai.fakes import FakeDecisionProvider


@pytest.fixture
def archive(tmp_path):
    lib = DocumentLibrary(tmp_path / 'test.sqlite', tmp_path / 'objects')
    yield lib
    lib.close()


def add(lib, key, text, public=True):
    identifier = lib.ingest(dict(collection='wikileaks', release_id='test', source_item_id=key,
        source_url='https://example.org/' + key, title=key, format='text'), payload=text.encode())
    if public:
        lib.publish(identifier, True, 'test', 'Source review')
    return identifier


def test_leads_keep_late_correction_deduplicate_and_do_not_scan_private(archive):
    text = 'Containers with UNKNOWN CONTENTS. ' + ('Context. ' * 2000) + ' UPDATE: Investigation found vitamins or supplements.'
    add(archive, 'report', text)
    add(archive, 'copy', text)
    add(archive, 'private', 'Suspected incident. UPDATE: corrected account.', public=False)
    inbox = LeadInbox(archive)
    assert inbox.scan()['created'] == 1
    assert inbox.scan()['created'] == 0
    lead = inbox.list()[0]
    assert 'vitamins or supplements' in lead['passages'][1]['text']
    assert lead['source_count'] == 1 and not lead['independent_corroboration']
    assert lead['assessment'] is None


def test_assessment_cached_cited_and_withdrawal_hides_lead(archive):
    identifier = add(archive, 'report', 'Suspected chemical equipment. UPDATE: Found vitamins or supplements.')
    inbox = LeadInbox(archive)
    inbox.scan()
    lead = inbox.list()[0]
    provider = FakeDecisionProvider()
    result = inbox.assess(lead['id'], provider)
    assert result['response']['answer'] == 'unknown'
    assert result['passages'][1]['text'].endswith('supplements.')
    assert inbox.assess(lead['id'], provider) == result
    assert len(provider.calls) == 1
    assert provider.calls[0].context['claim'].startswith('The later passage')
    inbox.review(lead['id'], 'investigating', 'Check chronology against incident log')
    inbox.review(lead['id'], 'dismissed', 'No material change established')
    assert len(inbox.get(lead['id'])['reviews']) == 2
    archive.publish(identifier, False, 'test', 'Withdraw source')
    assert inbox.list() == []
    with pytest.raises(ValueError):
        inbox.assess(lead['id'], provider)
    assert len(provider.calls) == 1


def test_invalid_review_and_unsupplied_citations_rejected(archive):
    add(archive, 'report', 'Initially unknown. CORRECTION: resolved.')
    inbox = LeadInbox(archive)
    inbox.scan()
    lead = inbox.list()[0]
    with pytest.raises(ValueError):
        inbox.review(lead['id'], 'verified', 'Cannot verify automatically')
    with pytest.raises(ValueError):
        inbox.review(lead['id'], 'dismissed', '')
    class Bad(FakeDecisionProvider):
        def decide(self, request):
            result = super().decide(request)
            result.evidence_ids = ['invented']
            return result
    with pytest.raises(ValueError):
        inbox.assess(lead['id'], Bad())
    assert not archive.db.execute('SELECT * FROM library_lead_assessments').fetchall()


def test_scan_batch_limit_and_resume(archive):
    for n in range(28):
        add(archive, str(n), f'Suspected incident {n}. UPDATE: corrected assessment {n}.')
    inbox = LeadInbox(archive)
    assert inbox.scan()['created'] == 25
    assert inbox.scan()['created'] == 3
    assert inbox.scan()['created'] == 0


def test_bot_budget_skips_reviewed_and_assessed_leads(archive):
    for n in range(6):
        add(archive, str(n), f'Unknown incident {n}. UPDATE: resolved {n}.')
    inbox = LeadInbox(archive)
    inbox.scan()
    inbox.review(inbox.list()[0]['id'], 'dismissed', 'Not a reporting priority')
    provider = FakeDecisionProvider()
    assert len(inbox.run(provider)['results']) == 3
    assert len(provider.calls) == 3
    assert len(inbox.run(provider)['results']) == 2
    assert len(provider.calls) == 5
    assert not inbox.run(provider)['results']
