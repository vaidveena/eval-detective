const $ = id => document.getElementById(id);
const fields = ['task', 'expected', 'baseline', 'candidate'];
let examples = [], currentResult = null;
function node(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}
function clearResult() { $('result').hidden = true; currentResult = null; }
function show(result, mode) {
  currentResult = result;
  $('mode').textContent = mode;
  $('verdict').textContent = ({baseline:'Baseline preferred',candidate:'Candidate preferred',tie:'No meaningful difference',insufficient_evidence:'Insufficient evidence'})[result.verdict];
  $('summary').textContent = result.summary;
  $('checks').replaceChildren();
  for (const check of result.checks) {
    const card = node('article', '', 'check');
    card.append(node('h3', check.criterion), node('p', check.explanation));
    for (const side of ['baseline', 'candidate']) {
      card.append(node('div', `${side} / ${check[side]}`, 'outcome'));
      card.append(node('blockquote', check[side + '_quote'] || 'No quoted evidence — see the explanation for the omission or uncertainty.'));
    }
    $('checks').append(card);
  }
  $('limitations').textContent = result.limitations;
  $('result').hidden = false;
}
$('examples').onchange = () => {
  const example = examples[Number($('examples').value)];
  if ($('examples').value === '' || !example) return;
  fields.forEach(field => $(field).value = example.input[field]);
  clearResult(); $('status').textContent = 'Sample loaded. View its authored verdict or compare with AI.';
};
fields.forEach(field => $(field).addEventListener('input', clearResult));
$('sample').onclick = () => {
  const example = examples.find(e => fields.every(field => e.input[field] === $(field).value));
  if (!example) { $('status').textContent = 'Choose an unchanged sample to view its authored verdict. Edited inputs require a live comparison.'; return; }
  show(example.result, 'AUTHORED SAMPLE · NO MODEL CALL');
  $('status').textContent = 'This is a teaching example, not a live model judgment.';
};
$('form').onsubmit = async event => {
  event.preventDefault(); clearResult();
  const input = Object.fromEntries(fields.map(field => [field, $(field).value]));
  const snapshot = JSON.stringify(input);
  $('live').disabled = true; $('sample').disabled = true;
  $('status').textContent = 'Comparing against the rubric and checking evidence…';
  try {
    const response = await fetch('/api/compare', {method:'POST',headers:{'Content-Type':'application/json'},body:snapshot});
    if (!(response.headers.get('content-type') || '').includes('application/json')) throw Error('For live AI, run python3 server.py locally and configure OPENAI_API_KEY.');
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Comparison failed.');
    if (snapshot !== JSON.stringify(Object.fromEntries(fields.map(f => [f, $(f).value])))) throw Error('Inputs changed during comparison. Compare again to review the current text.');
    show(result, 'LIVE MODEL · QUOTES VERIFIED'); $('status').textContent = 'Comparison ready for your review.';
  } catch (error) { $('status').textContent = error.message; }
  finally { $('live').disabled = false; $('sample').disabled = false; }
};
$('download').onclick = () => {
  if (!currentResult) return;
  const r = currentResult;
  const text = [`# Eval Detective`, `${$('mode').textContent}`, `Verdict: ${r.verdict}`, r.summary,
    ...r.checks.flatMap(c => [`## ${c.criterion}`, c.explanation, `Baseline (${c.baseline}): ${JSON.stringify(c.baseline_quote)}`, `Candidate (${c.candidate}): ${JSON.stringify(c.candidate_quote)}`]), `Limitations: ${r.limitations}`].join('\n\n');
  const url = URL.createObjectURL(new Blob([text], {type:'text/markdown'}));
  const link = node('a',''); link.href = url; link.download = 'eval-detective.md'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
fetch('./examples.json').then(r => {if (!r.ok) throw Error('Could not load samples.'); return r.json();}).then(data => {
  examples = data;
  data.forEach((e,i) => { const option = node('option', e.title); option.value = i; $('examples').append(option); });
  $('examples').value = '0'; $('examples').onchange();
}).catch(error => $('status').textContent = error.message);
