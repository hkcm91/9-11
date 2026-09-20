const $ = id => document.getElementById(id);
let offset = 0;
let searchGeneration = 0;
let readerGeneration = 0;
let jevReady = false;
let jevBusy = false;
const comparisonPages = {left: null, right: null};

function showView(view) {
  if (!['archive', 'leads', 'jev', 'research', 'completion'].includes(view)) view = 'archive';
  document.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== view; });
  document.querySelectorAll('[data-view]').forEach(button => {
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('view-name').textContent = {archive: 'Document archive', leads: 'Lead inbox', jev: 'Jev comparisons', research: 'Jev investigator', completion: 'Collection coverage'}[view];
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
      heading.append(link(row.display_title || row.title, '#doc=' + row.id + '&page=' + row.page));
      if (row.display_title && row.display_title !== row.title) card.append(el('div', row.title, 'meta'));
      if (row.brief_summary) {
        const brief=el('details'); brief.append(el('summary','Brief summary'),el('p',row.brief_summary),el('div',row.summary_status,'meta')); card.append(brief);
      }
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
    box.replaceChildren(el('div', doc.collection.replaceAll('_', ' '), 'eyebrow'), el('h2', doc.display_title || doc.title),
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
    if (doc.display_title && doc.display_title !== doc.title) box.append(el('p', 'Reading title · Original identifier: ' + doc.title, 'meta'));
    if (doc.brief_summary) {
      const brief = el('section', undefined, 'card');
      brief.append(el('h3', 'Brief summary'), el('p', doc.brief_summary), el('p', doc.summary_status + ' · Quoted source passages; claims remain unverified.', 'meta'));
      for (const passage of doc.editorial?.summary_passages || []) brief.append(link('Source passage · page ' + passage.page, pageLink(doc.id,passage.page)));
      if (doc.editorial) brief.append(el('p', 'Pages assessed: ' + doc.editorial.sampled_pages.join(', ') + ' of ' + doc.editorial.total_pages, 'meta'));
      box.append(brief);
    }
    const digestPanel = el('details');
    digestPanel.append(el('summary', 'Reading brief & noteworthy passages'));
    const digestBody = el('div'); digestPanel.append(digestBody); box.append(digestPanel);
    mountDigest(doc, digestBody);
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

let researchBusy = false;
function renderResearch(result) {
  const box = $('research-result');
  box.replaceChildren(el('h2', result.question), el('p', result.scope, 'meta'),
    el('p', result.candidate_pages + ' candidate pages · ' + result.assessed_pages
      + ' assessed in this run · ' + result.model_calls + ' model calls · ' + result.cached + ' cached assessments'));
  box.append(el('p', 'Search terms: ' + result.search_terms.join(', '), 'meta'));
  if (result.withdrawn_findings) box.append(el('p', result.withdrawn_findings + ' findings hidden because their sources were withdrawn.', 'warning'));
  if (result.status === 'partial') box.append(el('p', 'This investigation stopped early. Completed evidence is saved; rerun to retry.', 'warning'));
  if (!result.findings.length) box.append(el('p', 'No evidence is available for this pass. Try another name, spelling, date, or collection. This is not proof that no evidence exists.'));
  for (const finding of result.findings) {
    const card = el('article', undefined, 'card');
    card.append(el('h3', finding.title), link('Read full source · page ' + finding.page, pageLink(finding.document_id, finding.page)));
    if (finding.assessment) {
      const answer = finding.assessment.response;
      card.append(el('h4', answer.answer.replaceAll('_', ' ')), el('p', answer.rationale),
        el('p', 'Model confidence: ' + Math.round(answer.confidence * 100) + '% · ' + answer.model
          + ' · Unverified assessment', 'meta'));
    } else card.append(el('p', finding.error, 'warning'));
    const evidence = el('details');
    evidence.append(el('summary', 'Exact evidence supplied to Jev'));
    for (const passage of finding.passages) {
      const quote = el('blockquote', passage.text); quote.style.whiteSpace = 'pre-wrap';
      evidence.append(quote);
    }
    if (finding.excerpted) evidence.append(el('p', 'Excerpts only. Intervening text may be omitted; read the full page.', 'warning'));
    card.append(evidence);
    box.append(card);
  }
  const limitations = el('ul');
  result.limitations.forEach(item => limitations.append(el('li', item)));
  const steps = el('ol'); result.next_steps.forEach(item => steps.append(el('li', item)));
  box.append(el('h3', 'Limits of this search'), limitations, el('h3', 'Next reporting steps'), steps);
  const download = el('button', 'Export evidence sheet');
  download.onclick = async () => {
    try {
      // Recheck publication before exporting an older view.
      const current = await api('/api/research/' + encodeURIComponent(result.id));
      const url = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2)], {type: 'application/json'}));
      const anchor = link('Export', url); anchor.download = 'investigation-' + current.id.slice(0, 10) + '.json';
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { $('research-status').textContent = error.message; }
  };
  box.append(download);
}

async function researchHistory() {
  try {
    const rows = await api('/api/research');
    $('research-history').replaceChildren();
    for (const row of rows) {
      const button = el('button', row.question);
      button.style.margin = '8px';
      button.onclick = async () => {
        if (researchBusy) return;
        try { renderResearch(await api('/api/research/' + encodeURIComponent(row.id))); }
        catch (error) { $('research-status').textContent = error.message; }
      };
      $('research-history').append(button);
    }
  } catch { $('research-history').textContent = 'Investigation history unavailable.'; }
}

$('research-form').onsubmit = async event => {
  event.preventDefault();
  if (researchBusy) return;
  researchBusy = true;
  $('research-run').disabled = true;
  $('research-status').textContent = 'Searching archived text and assessing source passages. This may take a few minutes…';
  $('research-result').replaceChildren();
  try {
    const response = await fetch('/api/research', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Archive-Request': '1'},
      body: JSON.stringify({question: $('research-question').value, mode: $('research-mode').value,
        collection: $('research-collection').value, budget: Number($('research-budget').value)})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Investigation unavailable.');
    renderResearch(result);
    $('research-status').textContent = result.status === 'partial' ? 'Partial investigation saved.' : 'Investigation saved. Review the source evidence before drawing conclusions.';
    await researchHistory();
  } catch (error) { $('research-status').textContent = error.message; }
  finally { researchBusy = false; $('research-run').disabled = false; }
};
researchHistory();

async function mountDigest(doc, box) {
  const content = el('div');
  const status = el('p', '', 'meta');
  const build = el('button', 'Create reading brief with Jev');
  box.append(el('p', 'A readable title and exact source excerpts, including updates and conclusions. Jev checks the title; excerpts are not a generated whole-document summary.', 'meta'), build, status, content);
  function render(brief) {
    if (!brief) return;
    build.textContent = 'Recheck reading brief (cached when unchanged)';
    content.replaceChildren(el('h3', brief.title), el('p', brief.summary_kind, 'meta'),
      el('p', 'Pages sampled: ' + brief.coverage.sampled_pages.join(', ') + ' of ' + brief.coverage.total_pages, 'meta'),
      el('p', 'Jev title assessment: ' + brief.assessment.response.answer.replaceAll('_', ' ')
        + ' · Model confidence: ' + Math.round(brief.assessment.response.confidence * 100) + '%'
        + (brief.title_supported ? ' · Suggested reading title' : ' · Original title retained'), 'meta'),
      link('Download formatted reading brief', '/api/documents/' + doc.id + '/brief'));
    for (const passage of brief.passages) {
      const quote = el('blockquote', passage.text); quote.style.whiteSpace = 'pre-wrap';
      content.append(el('h4', passage.label), quote,
        link('Read source · page ' + passage.page, pageLink(doc.id, passage.page)));
    }
    content.append(el('p', brief.limitations, 'meta'));
  }
  build.onclick = async () => {
    build.disabled = true; status.textContent = 'Preparing source excerpts and checking the title with Jev…';
    try {
      const response = await fetch('/api/digest', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Archive-Request': '1'}, body: JSON.stringify({id: doc.id})});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Reading brief unavailable.');
      render(result); status.textContent = 'Reading brief saved. The preserved original is unchanged.';
    } catch (error) { status.textContent = error.message; }
    finally { build.disabled = false; }
  };
  try { render(await api('/api/documents/' + doc.id + '/digest')); }
  catch { status.textContent = 'Saved brief could not be loaded. You can try creating it again.'; }
}

let completionReleases = [], completionOffset = 0, completionGeneration = 0, completionBusy = false;
function currentRelease() { return completionReleases[Number($('completion-release').value)]; }
async function loadCompletion(keep = false) {
  await showBulkProgress();
  const previous = currentRelease();
  completionReleases = await api('/api/completion');
  $('completion-release').replaceChildren();
  completionReleases.forEach((row, index) => {
    const option = el('option', row.title || row.release_id); option.value = index;
    $('completion-release').append(option);
  });
  if (keep && previous) {
    const index = completionReleases.findIndex(row => row.collection === previous.collection && row.release_id === previous.release_id);
    if (index >= 0) $('completion-release').value = index;
  }
  await completionItems();
}
async function completionItems() {
  const generation = ++completionGeneration;
  const row = currentRelease(); if (!row) return;
  const box = $('completion-summary');
  box.replaceChildren(el('h2', row.title || row.release_id),
    el('p', row.inventory_status.replaceAll('_', ' ') + ' · Expected files: ' + (row.expected_files ?? 'unknown')),
    el('p', row.scope_note || '', 'meta'), el('p', row.complete ? 'Complete within this documented catalog scope.' : 'Incomplete or not fully verified.', 'warning'));
  box.append(el('p', ['discovered','downloaded','extracted','reviewed','searchable','verified'].map(key => row.counts[key] + ' ' + key).join(' → ')));
  box.append(el('p', row.counts.ocr_pages + ' pages need OCR · ' + row.counts.attention + ' items need attention'
    + (row.unlisted_expected ? ' · ' + row.unlisted_expected + ' expected items not yet enumerated' : ''), 'meta'));
  if (row.catalog_url) box.append(link('Source catalog', row.catalog_url));
  if (row.snapshot_sha256) box.append(el('p', 'Catalog snapshot SHA-256: ' + row.snapshot_sha256, 'meta'));
  const result = await api('/api/completion/items?' + new URLSearchParams({collection:row.collection,
    release_id:row.release_id, stage:$('completion-stage').value, offset:completionOffset}));
  if (generation !== completionGeneration) return;
  $('completion-items').replaceChildren(); $('completion-expected').replaceChildren();
  $('completion-count').textContent = result.total ? (completionOffset+1) + '–' + (completionOffset+result.items.length) + ' of ' + result.total : 'No files in this view';
  $('completion-prev').disabled = completionOffset === 0;
  $('completion-next').disabled = completionOffset + result.items.length >= result.total;
  for (const item of result.items) {
    const card = el('details', undefined, 'card');
    card.append(el('summary', item.title + ' · ' + item.stage.replaceAll('_',' ')),
      el('p', item.source_item_id, 'meta'), link('Catalog file link', item.source_url),
      el('p', item.pages + ' pages · ' + item.ocr_pages + ' need OCR · Integrity: ' + item.integrity));
    if (item.sha256) card.append(el('p', 'SHA-256: ' + item.sha256, 'meta'));
    if (item.checked_at) card.append(el('p', 'Last integrity check: ' + item.checked_at, 'meta'));
    if (item.reason) card.append(el('p', item.reason, 'warning'));
    if (item.document_id) card.append(link('Read archived document', pageLink(item.document_id, 1)));
    $('completion-items').append(card);
    const option = el('option', item.title); option.value = item.source_item_id; $('completion-expected').append(option);
  }
}
async function completionAction(path, extra = {}) {
  if (completionBusy) return;
  const row = currentRelease(); if (!row) return;
  completionBusy = true; $('completion-verify').disabled = true;
  $('completion-status').textContent = 'Working…';
  try {
    const response = await fetch('/api/completion/' + path, {method:'POST',
      headers:{'Content-Type':'application/json','X-Archive-Request':'1'},
      body:JSON.stringify({collection:row.collection,release_id:row.release_id,...extra})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Unable to complete action');
    if (path === 'verify') {
      $('completion-status').textContent = result.checked + ' files checked · ' + result.failed + ' failed.';
      await loadCompletion(true);
    } else {
      $('completion-status').textContent = 'Source-match proposal saved. Inventory unchanged.';
      $('completion-match-result').replaceChildren(el('h3', result.response.answer.replaceAll('_',' ')),
        el('p', 'Expected: ' + result.expected.title), el('p', 'Candidate: ' + result.candidate.title),
        el('p', result.response.rationale), el('p', result.note, 'meta'));
      $('completion-match-result').append(link('Read candidate source', pageLink(result.candidate.document_id, 1)));
    }
  } catch (error) { $('completion-status').textContent = error.message; }
  finally { completionBusy = false; $('completion-verify').disabled = false; }
}
function refreshCompletionItems() { completionItems().catch(error => { $('completion-status').textContent = error.message; }); }
$('completion-release').onchange = () => { completionOffset = 0; $('completion-match-result').replaceChildren(); refreshCompletionItems(); };
$('completion-stage').onchange = () => { completionOffset = 0; refreshCompletionItems(); };
$('completion-prev').onclick = () => { completionOffset = Math.max(0, completionOffset-50); refreshCompletionItems(); };
$('completion-next').onclick = () => { completionOffset += 50; refreshCompletionItems(); };
$('completion-verify').onclick = () => completionAction('verify');
$('completion-find').onsubmit = async event => {
  event.preventDefault();
  try {
    const rows = await api('/api/search?' + new URLSearchParams({q:$('completion-query').value}));
    $('completion-candidate').replaceChildren();
    for (const row of rows) {
      const option = el('option', row.display_title || row.title); option.value = row.id; $('completion-candidate').append(option);
    }
    if (!rows.length) $('completion-status').textContent = 'No published candidate found.';
  } catch (error) { $('completion-status').textContent = error.message; }
};
$('completion-match').onsubmit = event => { event.preventDefault(); completionAction('match',
  {source_item_id:$('completion-expected').value, candidate:$('completion-candidate').value}); };
async function showBulkProgress() {
  const status = await api('/api/wikileaks/bulk');
  let panel = $('wikileaks-bulk-progress');
  if (!panel) {
    panel = el('section', undefined, 'card'); panel.id = 'wikileaks-bulk-progress';
    $('completion-summary').before(panel);
  }
  const gb = bytes => (bytes / 1000000000).toFixed(2) + ' GB';
  panel.replaceChildren(el('h2', 'WikiLeaks bulk acquisition'),
    el('p', 'Cablegate: ' + gb(status.preserved_bytes) + ' preserved of ' + (status.expected_bytes ? gb(status.expected_bytes) : 'unknown size')),
    el('p', status.transport_verified ? 'Full transport checksum checked. Record extraction and review are tracked separately.' : 'Partial transport. Contents will be imported after the complete file passes its checksum.', 'meta'));
  for (const job of status.jobs) panel.append(el('p', (job.title || 'Cablegate') + ': ' + job.rows.toLocaleString() + ' rows processed · '
    + job.imported.toLocaleString() + ' new records · ' + job.duplicates.toLocaleString() + ' reused · '
    + job.rejected.toLocaleString() + ' rejected · ' + (job.complete ? 'end of CSV reached' : 'import incomplete')
    + (job.error ? ' · ' + job.error : '')));
  for (const inventory of status.inventories || []) panel.append(el('p', inventory.title + ' source scan: '
    + inventory.rows.toLocaleString() + ' total rows · ' + inventory.unique_valid_ids.toLocaleString()
    + ' distinct usable records · ' + inventory.rejected.toLocaleString() + ' rejected rows preserved in the source file.', 'meta'));
  if (status.editorial) panel.append(el('h3','Jev titles and briefs'),el('p',status.editorial.processed.toLocaleString()
    + ' documents assessed · ' + status.editorial.reviewed.toLocaleString() + ' title-and-brief selections accepted · '
    + status.editorial.pending_imported.toLocaleString() + ' imported documents pending assessment'));
  const refresh = el('button', 'Refresh acquisition progress');
  refresh.onclick = () => showBulkProgress().catch(error => { $('completion-status').textContent = error.message; });
  panel.append(el('p', 'Saved progress only; this does not confirm a worker is currently running. Other releases are listed below.', 'meta'), refresh);
}
loadCompletion().catch(error => { $('completion-status').textContent = error.message; });
