import json
import pytest
from archive.library_warlog import extract_warlog


def test_published_summary_decoded_without_executing_script():
    body = 'AT %%%: "Quoted" report.\nFinal update: supplements.'
    html = '<script>throw Error("do not execute"); var summary = ' + json.dumps(body) + ';</script>'
    assert extract_warlog(html.encode()) == body
    with pytest.raises(ValueError):
        extract_warlog(b'<h1>Title without contents</h1>')
    with pytest.raises(ValueError):
        extract_warlog(b'var summary = "";')
