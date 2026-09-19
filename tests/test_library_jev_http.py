import json
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from archive.document_library import DocumentLibrary
from archive.library_cli import handler_for
from historical_engine.ai.fakes import FakeDecisionProvider
from historical_engine.ai.providers import AiProviderError


@contextmanager
def serving(tmp_path, provider=None):
    library = DocumentLibrary(tmp_path / 'test.sqlite', tmp_path / 'objects')
    identifier = library.ingest(dict(collection='wikileaks', release_id='test',
        source_item_id='one', source_url='https://example.org/one', title='Source', format='text'),
        payload=b'First original passage\fSecond original passage')
    library.publish(identifier, True, 'test', 'Approved')
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(library.store.path, library.objects,
        jev_factory=(lambda: provider) if provider else None))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def post(values=None, **headers):
        body = dict(left=identifier, right=identifier, left_page=1, right_page=2, question='same_event')
        body.update(values or {})
        request = Request(base + '/api/compare', data=json.dumps(body).encode(), headers={
            'Content-Type': 'application/json', 'Origin': base, 'X-Archive-Request': '1', **headers})
        with urlopen(request) as response:
            return json.load(response)
    try:
        yield library, identifier, base, post
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        library.close()


def test_http_comparison_citations_cache_and_publication_gate(tmp_path):
    provider = FakeDecisionProvider()
    with serving(tmp_path, provider) as (lib, identifier, base, post):
        record = lib.document(identifier)['record_id']
        provider.script('same_event', record, 'same', .95, object_id=record)
        result = post()
        assert result['review_status'] == 'proposed'
        assert [p['text'] for p in result['passages']] == ['First original passage', 'Second original passage']
        assert post() == result
        assert len(provider.calls) == 1
        lib.publish(identifier, False, 'test', 'Withdraw')
        with pytest.raises(HTTPError) as exc:
            post()
        assert exc.value.code == 400
        assert len(provider.calls) == 1


def test_http_rejects_cross_origin_and_invalid_input_without_calling_jev(tmp_path):
    provider = FakeDecisionProvider()
    with serving(tmp_path, provider) as (_, _, _, post):
        for headers in ({'Origin': 'https://evil.example'}, {'X-Archive-Request': ''}, {'Host': 'evil.example'}):
            with pytest.raises(HTTPError) as exc:
                post(**headers)
            assert exc.value.code == 403
        for body in ({'question': 'invented'}, {'left_page': True}, {'right_page': -1}):
            with pytest.raises(HTTPError) as exc:
                post(body)
            assert exc.value.code == 400
        assert not provider.calls


def test_missing_credentials_and_secret_safe_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    with serving(tmp_path) as (_, _, base, post):
        with urlopen(base + '/api/jev/status') as response:
            assert json.load(response)['configured'] is False
        with pytest.raises(HTTPError) as exc:
            post()
        assert exc.value.code == 503
        (tmp_path / '.env').write_text('TYPESAFE_API_KEY=never-expose-this\n')
        with urlopen(base + '/api/jev/status') as response:
            text = response.read().decode()
            assert json.loads(text)['configured'] is True
            assert 'never-expose-this' not in text


def test_provider_error_does_not_expose_transport_details(tmp_path):
    class Broken(FakeDecisionProvider):
        def decide(self, request):
            raise AiProviderError('secret-provider-response')
    with serving(tmp_path, Broken()) as (_, _, _, post):
        with pytest.raises(HTTPError) as exc:
            post()
        assert exc.value.code == 502
        assert b'secret-provider-response' not in exc.value.read()


def test_lead_routes_scan_assess_and_review_with_origin_gate(tmp_path):
    provider = FakeDecisionProvider()
    with serving(tmp_path, provider) as (lib, _, base, _):
        identifier = lib.ingest(dict(collection='wikileaks', release_id='test', source_item_id='update',
            source_url='https://example.org/update', title='Update', format='text'),
            payload=b'Unknown chemicals. UPDATE: Found supplements.')
        lib.publish(identifier, True, 'test', 'Source reviewed')
        def call(path, values, origin=base):
            request = Request(base + '/api/leads/' + path, data=json.dumps(values).encode(),
                headers={'Content-Type': 'application/json', 'Origin': origin, 'X-Archive-Request': '1'})
            with urlopen(request) as response:
                return json.load(response)
        with pytest.raises(HTTPError) as exc:
            call('run', {}, 'https://other.example')
        assert exc.value.code == 403
        assert call('scan', {})['created'] == 1
        assert not provider.calls
        result = call('run', {})
        assert len(result['results']) == 1 and len(provider.calls) == 1
        lead_id = result['results'][0]['id']
        assert call('review', dict(id=lead_id, status='investigating', note='Verify final update'))['status'] == 'investigating'
        with urlopen(base + '/api/leads') as response:
            assert json.load(response)[0]['reviews'][0]['note'] == 'Verify final update'
