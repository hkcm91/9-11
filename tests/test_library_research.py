import pytest
from archive.document_library import DocumentLibrary
from archive.library_research import ResearchDesk
from historical_engine.ai.fakes import FakeDecisionProvider


@pytest.fixture
def desk(tmp_path):
    lib = DocumentLibrary(tmp_path / 'test.sqlite', tmp_path / 'objects')
    yield ResearchDesk(lib)
    lib.close()


def add(desk, name, text, public=True, collection='wikileaks'):
    lib = desk.library
    identifier = lib.ingest(dict(collection=collection, release_id='test', source_item_id=name,
        title=name, source_url='https://example.org/' + name, format='text'), payload=text.encode())
    if public:
        lib.publish(identifier, True, 'test', 'Source reviewed')
    return identifier


def test_question_retrieval_dedup_budget_cache_and_withdrawal(desk):
    ids = [add(desk, str(n), f'Chemical equipment in Baghdad. Update {n}: vitamins.') for n in range(5)]
    add(desk, 'copy', 'Chemical equipment in Baghdad. Update 0: vitamins.')
    add(desk, 'secret', 'Chemical equipment in Baghdad. Unpublished.', public=False)
    provider = FakeDecisionProvider()
    result = desk.run('What happened with chemical equipment in Baghdad?', provider, budget=3)
    assert result['assessed_pages'] == result['model_calls'] == 3
    assert len(provider.calls) == 3
    assert len({finding['passages'][0]['text'] for finding in result['findings']}) == 3
    again = desk.run(result['question'], provider, budget=3)
    assert again['cached'] == 3 and again['model_calls'] == 0
    first = result['findings'][0]['document_id']
    desk.library.publish(first, False, 'test', 'Withdraw')
    saved = desk.get(result['id'])
    assert saved['withdrawn_findings'] == 1
    assert all(f['document_id'] != first for f in saved['findings'])
    assert desk.history()[0]['question'] == result['question']


def test_modes_collections_no_matches_and_validation(desk):
    add(desk, 'cable', 'Aircraft deliveries to Iran.')
    provider = FakeDecisionProvider()
    result = desk.run('Aircraft', provider, collection='snowden')
    assert not result['findings'] and not provider.calls
    for mode, kind in [('support','supports_claim'), ('contradiction','contradicts_claim'), ('relevance','relevant_to_thread')]:
        desk.run('Aircraft deliveries to Iran', provider, mode=mode)
        assert provider.calls[-1].question == kind
    for args in [{'budget': 7}, {'budget': True}, {'mode': 'invent'}, {'collection': 'private'}]:
        with pytest.raises(ValueError):
            desk.run('Aircraft', provider, **args)
    with pytest.raises(ValueError):
        desk.run('what is it', provider)


def test_long_page_preserves_matching_passage_and_late_correction(desk):
    text = 'Chemical equipment discovered. ' + 'Context. ' * 2000 + 'UPDATE: These were vitamins.'
    add(desk, 'long', text)
    result = desk.run('Chemical equipment', FakeDecisionProvider())
    finding = result['findings'][0]
    assert finding['excerpted']
    assert finding['passages'][-1]['text'].endswith('These were vitamins.')
    for p in finding['passages']:
        assert text[p['start']:p['end']] == p['text']


def test_partial_failure_preserves_completed_findings(desk):
    for n in range(3):
        add(desk, str(n), f'Aircraft report {n}')
    class Failing(FakeDecisionProvider):
        def decide(self, request):
            if self.calls:
                raise RuntimeError('private upstream detail')
            return super().decide(request)
    result = desk.run('Aircraft', Failing())
    assert result['status'] == 'partial' and result['assessed_pages'] == 1
    assert result['model_calls'] == 2
    assert 'private upstream detail' not in str(result)
    assert desk.get(result['id'])['findings'][0]['assessment']


def test_out_of_scope_citation_never_saved_as_assessment(desk):
    add(desk, 'one', 'Aircraft report')
    class Bad(FakeDecisionProvider):
        def decide(self, request):
            answer = super().decide(request)
            answer.evidence_ids = ['made-up-source']
            return answer
    result = desk.run('Aircraft', Bad())
    assert result['status'] == 'partial'
    assert not desk.db.execute('SELECT * FROM library_research_cache').fetchall()
