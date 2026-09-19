const $ = id => document.getElementById(id);
let offset = 0;
let searchGeneration = 0;
let readerGeneration = 0;

function el(tag, text, cls) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}

async function api(url) {
  const response = await fetch(url);
  if (!response.ok) throw Error(response.status === 404
    ? 'This document or page is unavailable.' : 'The library could not complete this request.');
  return response.json();
}

function link(text, url) {
  const anchor = el('a', text);
  anchor.href = url;
  return anchor;
}

function highlighted(text, className = 'excerpt') {
  const paragraph = el('p', undefined, className);
  const terms = $('query').value.match(/\w+/g) || [];
  if (!terms.length) {
    paragraph.textContent = text;
    return paragraph;
  }
  const escaped = terms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp('(' + escaped.join('|') + ')', 'gi');
  text.split(pattern).forEach((part, index) => paragraph.append(index % 2
    ? el('mark', part) : document.createTextNode(part)));
  return paragraph;
}

async function search(reset = true) {
  const generation = ++searchGeneration;
  if (reset) {
    offset = 0;
    $('results').replaceChildren();
  }
  $('status').textContent = 'Searching…';
  $('more').hidden = true;
  try {
    const rows = await api('/api/search?' + new URLSearchParams({
      q: $('query').value, collection: $('collection').value, offset,
    }));
    if (generation !== searchGeneration) return;
    for (const row of rows) {
      const card = el('div', undefined, 'card');
      card.append(el('div', row.collection.replaceAll('_', ' ') + ' / ' + row.release_id, 'eyebrow'));
      const heading = el('h2');
      heading.append(link(row.title, '#doc=' + row.id + '&page=' + row.page));
      card.append(heading, el('div', 'Page ' + row.page + ' · ' + row.extraction_status.replaceAll('_', ' '), 'meta'), highlighted(row.excerpt));
      $('results').append(card);
    }
    offset += rows.length;
    $('status').textContent = offset ? offset + ($('query').value ? ' matching pages loaded' : ' documents loaded')
      : 'No published documents match this search.';
    $('more').hidden = rows.length < 30;
  } catch (error) {
    if (generation === searchGeneration) $('status').textContent = error.message;
  }
}

function pageLink(id, number) {
  return '#doc=' + id + '&page=' + number;
}

async function read() {
  const params = new URLSearchParams(location.hash.slice(1));
  if (!params.has('doc')) return;
  const generation = ++readerGeneration;
  const number = Number(params.get('page') || 1);
  const id = params.get('doc');
  const box = $('reader');
  box.replaceChildren(el('p', 'Loading source page…', 'meta'));
  try {
    if (!Number.isInteger(number) || number < 1) throw Error('Choose a valid page number.');
    const [doc, page] = await Promise.all([
      api('/api/documents/' + encodeURIComponent(id)),
      api('/api/documents/' + encodeURIComponent(id) + '/pages/' + number),
    ]);
    if (generation !== readerGeneration) return;
    box.replaceChildren(el('div', doc.collection.replaceAll('_', ' '), 'eyebrow'), el('h2', doc.title),
      el('p', 'Release: ' + doc.release_id + ' · ' + doc.page_count + ' pages · Retrieved ' + doc.retrieved_at.slice(0, 10), 'meta'));
    const source = link('Original source', doc.source_url);
    source.target = '_blank';
    source.rel = 'noopener noreferrer';
    if (doc.format === 'record') box.append(el('p', 'Normalized source record: this may contain only metadata, not the full original document.', 'warning'));
    box.append(source, document.createTextNode(' · '), link('Download preserved file', '/api/documents/' + doc.id + '/original'));
    const details = el('details');
    details.append(el('summary', 'Source integrity'), el('p', 'SHA-256: ' + doc.sha256, 'meta'));
    box.append(details);
    const navigation = el('form', undefined, 'page-nav');
    navigation.setAttribute('aria-label', 'Page navigation');
    const previous = el('button', 'Previous');
    previous.type = 'button';
    previous.disabled = number <= 1;
    previous.onclick = () => { location.hash = pageLink(id, number - 1); };
    const next = el('button', 'Next');
    next.type = 'button';
    next.disabled = number >= doc.page_count;
    next.onclick = () => { location.hash = pageLink(id, number + 1); };
    const input = el('input');
    input.type = 'number';
    input.min = 1;
    input.max = doc.page_count;
    input.value = number;
    input.setAttribute('aria-label', 'Page number');
    const go = el('button', 'Go');
    navigation.append(previous, input, el('span', 'of ' + doc.page_count), go, next);
    navigation.onsubmit = event => {
      event.preventDefault();
      if (input.checkValidity()) location.hash = pageLink(id, Number(input.value));
    };
    box.append(navigation);
    const section = el('section', undefined, 'page');
    section.append(el('h3', 'Page ' + number));
    const cite = el('button', 'Copy page citation');
    cite.onclick = async () => {
      const url = location.origin + '/' + pageLink(id, number);
      try {
        await navigator.clipboard.writeText(doc.title + ', p. ' + number + '. ' + doc.source_url + ' — ' + url);
        cite.textContent = 'Copied';
      } catch {
        cite.textContent = 'Copy this page URL from the address bar';
      }
    };
    section.append(cite);
    section.append(page.needs_ocr
      ? el('p', 'No text was extracted from this page. It may be blank or require OCR; consult the preserved original.', 'warning')
      : highlighted(page.text, 'page-body'));
    box.append(section);
    box.scrollIntoView({block: 'start'});
  } catch (error) {
    if (generation === readerGeneration) box.replaceChildren(el('p', error.message));
  }
}

async function coverage() {
  try {
    const [published, inventory] = await Promise.all([api('/api/coverage'), api('/api/inventory')]);
    const total = published.reduce((sum, row) => sum + row.versions, 0);
    const pages = published.reduce((sum, row) => sum + row.pages, 0);
    const summary = el('p', total + ' published document versions · ' + pages.toLocaleString() + ' pages', 'coverage-total');
    const rows = inventory.map(row => el('div', row.collection.replaceAll('_', ' ') + ': '
      + row.processed + ' / ' + row.discovered + ' source items imported'
      + ' · ' + row.published + ' published'
      + (row.processed > row.published ? ' · ' + (row.processed - row.published) + ' awaiting review' : '')
      + (row.pending ? ' · ' + row.pending + ' pending' : '')
      + (row.failed ? ' · ' + row.failed + ' failed' : ''), 'meta'));
    $('coverage').replaceChildren(summary, ...rows);
  } catch {
    $('coverage').textContent = 'Coverage is temporarily unavailable.';
  }
}

$('search').onsubmit = event => { event.preventDefault(); search(); };
$('more').onclick = () => search(false);
window.addEventListener('hashchange', read);
search();
read();
coverage();
