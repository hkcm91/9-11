const $ = id => document.getElementById(id);
let offset = 0;
let searchGeneration = 0;
let readerGeneration = 0;
let jevReady = false;
let jevBusy = false;
const comparisonPages = {left: null, right: null};

function showView(view) {
  if (!['archive', 'leads', 'jev'].includes(view)) view = 'archive';
  document.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== view; });
  document.querySelectorAll('[data-view]').forEach(button => {
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('view-name').textContent = {archive: 'Document archive', leads: 'Lead inbox', jev: 'Jev comparisons'}[view];
  window.scrollTo(0, 0);
}
document.querySelectorAll('[data-view]').forEach(button => {
  button.onclick = () => { location.hash = 'view=' + button.dataset.view; };
});

function updateComparison() {
  for (const side of ['left', 'right']) {
    const page = comparisonPages[side];
    const label = side === 'left' ? 'First page: ' : 'Second page: ';
    $('jev-' + side).replaceChildren(document.createTextNode(label));
    $('jev-' + side).append(page ? link(page.title + ', page ' + page.number, pageLink(page.id, page.number))
      : document.createTextNode('not selected'));
  }
  $('jev-run').disabled = jevBusy || !jevReady || !comparisonPages.left || !comparisonPages.right;
  $('jev-clear').disabled = jevBusy;
  $('jev-question').disabled = jevBusy;
}

async function checkJev() {
  try {
    const status = await api('/api/jev/status');
    jevReady = status.configured;
    $('jev-status').textContent = status.message;
  } catch {
    jevReady = false;
    $('jev-status').textContent = 'Could not check Jev settings. Try again.';
  }
  updateComparison();
}

async function comparePages(event) {
  event.preventDefault();
  if (jevBusy || !jevReady || !comparisonPages.left || !comparisonPages.right) return;
  jevBusy = true;
  updateComparison();
  $('jev-result').replaceChildren(el('p', 'Comparing selected source passages…'));
  const selected = {left: {...comparisonPages.left}, right: {...comparisonPages.right}};
  try {
    const response = await fetch('/api/compare', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Archive-Request': '1'},
      body: JSON.stringify({left: selected.left.id, left_page: selected.left.number,
        right: selected.right.id, right_page: selected.right.number, question: $('jev-question').value}),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Comparison unavailable.');
    const answer = result.response;
    $('jev-result').replaceChildren(el('h3', 'Suggested result: ' + answer.answer.replaceAll('_', ' ')),
      el('p', 'Model confidence: ' + Math.round(answer.confidence * 100) + '% · '
        + (result.proposal_id ? 'Awaiting review' : 'No review proposal created')),
      el('p', answer.rationale), el('p', 'Model: ' + answer.model, 'meta'));
    for (const [index, passage] of result.passages.entries()) {
      const page = index === 0 ? selected.left : selected.right;
      const details = el('details');
      details.append(el('summary', page.title + ', page ' + passage.page + ' — text supplied to Jev'),
        link('Read source page', pageLink(passage.document_id, passage.page)));
      const text = el('p', passage.text);
      text.style.whiteSpace = 'pre-wrap';
      details.append(text);
      if (passage.truncated) details.append(el('p', 'Only the first 12,000 characters of this page were supplied.', 'warning'));
      $('jev-result').append(details);
    }
  } catch (error) {
    $('jev-result').replaceChildren(el('p', error.message, 'warning'));
  } finally {
    jevBusy = false;
    updateComparison();
  }
}

function el(tag, text, cls) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}

function releaseLabel(row) {
  return {'cablegate-ia-fulltext-v2': 'Cablegate', 'nara-2011': 'Pentagon Papers',
    'war-diary-published-text': 'War Diaries'}[row.release_id] || row.release_id.replaceAll('-', ' ');
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
      card.append(el('div', releaseLabel(row), 'eyebrow'));
      const heading = el('h2');
      heading.append(link(row.title, '#doc=' + row.id + '&page=' + row.page));
      card.append(heading, el('div', 'Page ' + row.page + ' · ' + (row.extraction_status === 'indexed' ? 'Preserved text' : row.extraction_status.replaceAll('_', ' ')), 'meta'), highlighted(row.excerpt));
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
  if (!params.has('doc')) {
    ++readerGeneration;
    showView(params.get('view') || 'archive');
    return;
  }
  showView('archive');
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
      el('p', releaseLabel(doc) + ' · ' + doc.page_count + ' pages · Retrieved ' + doc.retrieved_at.slice(0, 10), 'meta'));
    const source = link('Original source', doc.source_url);
    if (doc.format === 'warlog_html') box.append(el('p', 'Published War Diary narrative. Redactions in the publisher’s text are preserved.', 'meta'));
    source.target = '_blank';
    source.rel = 'noopener noreferrer';
    if (doc.format === 'record') box.append(el('p', doc.metadata.content_kind === 'full_mirror_text'
      ? 'Full cable text from the Internet Archive mirror. The preserved file contains the normalized source record; completeness against every publisher page has not been independently verified.'
      : 'Metadata only: this record is not the full original document.', 'warning'));
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
    for (const side of ['left', 'right']) {
      const choose = el('button', side === 'left' ? 'Use as first comparison page' : 'Use as second comparison page');
      choose.disabled = Boolean(page.needs_ocr);
      choose.onclick = () => {
        if (jevBusy) return;
        comparisonPages[side] = {id, number, title: doc.title};
        $('jev-result').replaceChildren();
        updateComparison();
        location.hash = 'view=jev';
      };
      section.append(choose);
    }
    if (doc.format === 'pdf') {
      const scan = el('details');
      scan.append(el('summary', 'View original page'));
      const picture = el('img');
      picture.alt = 'Preserved original, page ' + number;
      picture.style.maxWidth = '100%';
      picture.loading = 'lazy';
      picture.src = '/api/documents/' + encodeURIComponent(id) + '/pages/' + number + '/image';
      picture.onerror = () => picture.replaceWith(el('p', 'Page image unavailable. Download the preserved original to view this page.', 'warning'));
      scan.append(picture);
      section.append(scan);
    }
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
    const rows = inventory.map(row => el('div', releaseLabel(row) + ': '
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
$('jev-form').onsubmit = comparePages;
$('jev-clear').onclick = () => {
  comparisonPages.left = comparisonPages.right = null;
  $('jev-result').replaceChildren();
  updateComparison();
};
$('jev-refresh').onclick = checkJev;
$('jev-question').onchange = () => $('jev-result').replaceChildren();
checkJev();

let leadBusy = false;
const botButton = el('button', 'Find and assess up to 3 leads with Jev');
$('leads-scan').after(botButton);
botButton.onclick = () => runLeadAction(async () => {
  const result = await leadAction('run', {});
  const completed = result.results.filter(row => row.status === 'assessed').length;
  const failed = result.results.some(row => row.status === 'failed');
  return result.scan.created + ' new candidates; ' + completed + ' Jev assessments saved.'
    + (failed ? ' A provider request failed; completed assessments were retained. Retry the remaining lead individually.' : ' All remain unverified leads.');
});
async function leadAction(path, values) {
  const response = await fetch('/api/leads/' + path, {method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Archive-Request': '1'}, body: JSON.stringify(values)});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Lead action failed.');
  return result;
}

async function runLeadAction(action) {
  if (leadBusy) return;
  leadBusy = true;
  $('leads-scan').disabled = true;
  botButton.disabled = true;
  $('leads-status').textContent = 'Working…';
  try {
    const message = await action();
    await loadLeads();
    $('leads-status').textContent = message;
  } catch (error) {
    $('leads-status').textContent = error.message;
  } finally {
    leadBusy = false;
    $('leads-scan').disabled = false;
    botButton.disabled = false;
  }
}

async function loadLeads() {
  try {
    const leads = await api('/api/leads');
    const visible = leads.filter(lead => $('leads-filter').value === 'all' || lead.status === $('leads-filter').value);
    $('leads-list').replaceChildren();
    if (!visible.length) $('leads-list').append(el('p', 'No leads in this view. Run a scan to find candidates in published text.'));
    for (const lead of visible) {
      const shell = el('details', undefined, 'card');
      shell.append(el('summary', lead.title));
      const card = el('div', undefined, 'lead-content');
      card.append(el('div', lead.status + ' · 1 source · Unverified', 'eyebrow'), el('h3', lead.question),
        el('p', lead.title), el('p', lead.why_it_matters));
      for (const passage of lead.passages) {
        card.append(el('h4', passage.role), el('blockquote', passage.text),
          link('Read full source, page ' + passage.page, pageLink(passage.document_id, passage.page)));
      }
      card.append(el('p', lead.limitations, 'meta'));
      const steps = el('ol');
      lead.next_steps.forEach(step => steps.append(el('li', step)));
      card.append(el('h4', 'Next reporting steps'), steps);
      if (lead.assessment) {
        const answer = lead.assessment.response;
        card.append(el('h4', 'Jev assessment: ' + answer.answer.replaceAll('_', ' ')),
          el('p', lead.assessment.claim), el('p', answer.rationale),
          el('p', 'Model confidence: ' + Math.round(answer.confidence * 100) + '% · ' + answer.model
            + ' · Unverified; editorial review required', 'meta'));
      } else card.append(el('p', lead.discovery, 'meta'));
      const assess = el('button', lead.assessment ? 'Recheck with Jev (cached when unchanged)' : 'Assess this lead with Jev');
      assess.onclick = () => runLeadAction(async () => {
        await leadAction('assess', {id: lead.id});
        return 'Jev assessment saved with exact source passages. This remains an unverified lead.';
      });
      card.append(assess);
      const review = el('form');
      const state = el('select');
      state.setAttribute('aria-label', 'Review status for ' + lead.title);
      for (const value of ['inbox', 'investigating', 'dismissed']) {
        const option = el('option', value); option.value = value; state.append(option);
      }
      state.value = lead.status;
      const note = el('input'); note.placeholder = 'Editorial note or reason for dismissal';
      note.setAttribute('aria-label', 'Review note for ' + lead.title);
      note.required = true; note.maxLength = 2000;
      review.append(state, note, el('button', 'Save review'));
      review.onsubmit = event => {
        event.preventDefault();
        runLeadAction(async () => {
          await leadAction('review', {id: lead.id, status: state.value, note: note.value});
          return 'Editorial review saved.';
        });
      };
      card.append(review);
      for (const entry of lead.reviews) card.append(el('p', entry.status + ': ' + entry.note, 'meta'));
      shell.append(card);
      $('leads-list').append(shell);
    }
  } catch (error) { $('leads-status').textContent = error.message; }
}
$('leads-filter').onchange = loadLeads;
$('leads-scan').onclick = () => runLeadAction(async () => {
  const result = await leadAction('scan', {});
  return result.created + ' new leads; ' + result.pages_examined + ' pages examined. No model calls used.';
});
loadLeads();
