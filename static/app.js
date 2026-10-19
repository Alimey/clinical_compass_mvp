'use strict';
const $ = (q) => document.querySelector(q);
let role = 'patient', page = 'checkin', patientId = '', generation = 0, pendingInstall;
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = v => new Date(v).toLocaleString('ru-RU', {dateStyle:'medium', timeStyle:'short'});
function status(message, error=false) { $('#status').className = error ? 'error' : 'success'; $('#status').textContent = message; }
async function api(path, body) {
  const response = await fetch(path, {cache:'no-store', ...(body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Не удалось выполнить запрос');
  return result;
}
function showPage(next) {
  page = next;
  for (const id of ['checkin','history','doctor','about']) $('#'+id).hidden = id !== next;
  document.querySelectorAll('[data-page]').forEach(b => {
    b.dataset.page === next ? b.setAttribute('aria-current','page') : b.removeAttribute('aria-current');
  });
}
function history(reports) {
  if (!reports.length) return '<p class="empty">Пока нет самоотчётов.<br>Заполните первый в разделе «Самоотчёт».</p>';
  return reports.map(r => `<article class="card"><time class="report-date">${escapeHTML(date(r.created_at))}</time><div class="report-values"><b>Настроение ${r.mood}/10</b><b>Тревога ${r.anxiety}/10</b></div><div class="report-copy">Рекомендации: ${escapeHTML(r.adherence)}${r.adverse_effects ? '<br>Самочувствие: '+escapeHTML(r.adverse_effects) : ''}${r.note ? '<br>Комментарий: '+escapeHTML(r.note) : ''}</div>${r.safety_signal ? '<p class="badge">Отмечены опасения за безопасность</p>' : ''}</article>`).join('');
}
function chart(reports) {
  if (!reports.length) return '';
  const values = reports.slice(0,14).reverse();
  const x = i => values.length === 1 ? 160 : 25+i*270/(values.length-1);
  const y = n => 140-n*12;
  const lines = [['mood','#17695f'],['anxiety','#a56a2a']].map(([key,color]) => `<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${values.map((r,i)=>`${x(i)},${y(r[key])}`).join(' ')}"/>${values.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r[key])}" r="3" fill="${color}"/>`).join('')}`).join('');
  return `<div class="card"><h2>Динамика · последние ${values.length}</h2><div class="legend"><span>● Настроение</span><span>● Тревога</span></div><svg class="trend" viewBox="0 0 320 170" role="img" aria-label="Настроение и тревога от 0 до 10, от старых к новым отчётам"><path d="M25 20H295M25 80H295M25 140H295" stroke="#dce6df" fill="none"/><g font-size="10" fill="#71837b"><text x="3" y="24">10</text><text x="9" y="84">5</text><text x="9" y="144">0</text><text x="25" y="163">Раньше</text><text x="260" y="163">Позже</text></g>${lines}</svg><small>Точные значения и даты — в карточках ниже.</small></div>`;
}
async function refresh() {
  const version = ++generation, selected = patientId;
  try {
    const [patients, data] = await Promise.all([api('/api/patients'), api('/api/patients/'+selected)]);
    if (version !== generation || selected !== patientId) return;
    $('#patient-history').innerHTML = chart(data.reports)+history(data.reports);
    $('#doctor-history').innerHTML = history(data.reports);
    const latest = data.reports[0];
    $('#doctor-summary').innerHTML = latest ? `<div class="metric">Настроение<strong>${latest.mood}<small>/10</small></strong></div><div class="metric">Тревога<strong>${latest.anxiety}<small>/10</small></strong></div>` : '';
    $('#unread').textContent = `Непросмотренных сигналов: ${data.alerts.filter(a=>a.status==='new').length} у пациента · ${patients.reduce((s,p)=>s+p.unread,0)} всего`;
    $('#alerts').innerHTML = data.alerts.length ? data.alerts.map(a => `<article class="card alert"><span class="badge ${a.status === 'new' ? '' : 'reviewed'}">${a.status === 'new' ? 'Новый сигнал' : 'Просмотрен'}</span><p class="report-date">${escapeHTML(date(a.created_at))}</p><p class="report-copy">${escapeHTML(a.explanation)}</p>${a.status === 'new' ? `<button data-review="${a.id}">Отметить просмотренным</button>` : ''}</article>`).join('') : '<p class="empty">Сигналов безопасности нет.</p>';
    $('#decisions').innerHTML = data.decisions.length ? data.decisions.map(d=>`<article class="card"><time class="report-date">${escapeHTML(date(d.created_at))}</time><h3>${escapeHTML(d.decision)}</h3><p class="report-copy">${escapeHTML(d.note)}</p></article>`).join('') : '<p class="empty">Решения пока не зафиксированы.</p>';
  } catch (error) {
    if (version !== generation) return;
    for (const id of ['patient-history','doctor-history','alerts','decisions']) $('#'+id).replaceChildren();
    $('#doctor-summary').replaceChildren(); $('#unread').textContent = '';
    status('Не удалось обновить данные. Проверьте соединение и повторите. '+error.message, true);
  }
}
function setRole(next) {
  role = next;
  $('#patient-role').setAttribute('aria-pressed', String(role==='patient'));
  $('#doctor-role').setAttribute('aria-pressed', String(role==='doctor'));
  const first = document.querySelector('[data-page]');
  first.dataset.page = role==='doctor' ? 'doctor' : 'checkin';
  first.innerHTML = role==='doctor' ? '<span aria-hidden="true">▤</span>Обзор' : '<span aria-hidden="true">＋</span>Самоотчёт';
  document.querySelector('[data-page="history"]').hidden = role==='doctor';
  showPage(role==='doctor' ? 'doctor' : 'checkin');
  $('#status').textContent = ''; $('#status').className = '';
  if (patientId) refresh();
}
$('#patient-role').onclick = () => setRole('patient');
$('#doctor-role').onclick = () => setRole('doctor');
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{showPage(b.dataset.page);if(patientId)refresh();window.scrollTo({top:0,behavior:'smooth'});});
$('#patient').onchange = () => {
  patientId = $('#patient').value;
  $('#report-form').reset(); $('#decision-form').reset(); updateRanges(); $('#urgent').hidden = true;
  $('#status').textContent=''; $('#status').className=''; refresh();
};
function updateRanges() { for (const id of ['mood','anxiety']) $('#'+id+'-value').textContent = $('#'+id).value+' / 10'; }
for (const id of ['mood','anxiety']) $('#'+id).oninput = updateRanges;
$('#safety').onchange = () => { $('#urgent').hidden = !$('#safety').checked; };
async function submit(form, task) {
  const controls = [...form.elements], picker = $('#patient');
  controls.forEach(c=>c.disabled=true); picker.disabled=true;
  try { await task(); } catch(error) { status('Не удалось сохранить. Проверьте соединение. Если ответ сервера потерян, проверьте историю перед повторной отправкой. '+error.message,true); }
  finally { controls.forEach(c=>c.disabled=false); picker.disabled=false; }
}
$('#report-form').onsubmit = event => {
  event.preventDefault();
  const safety = $('#safety').checked;
  const data = {mood:Number($('#mood').value),anxiety:Number($('#anxiety').value),adherence:$('#adherence').value,adverse_effects:$('#adverse').value,note:$('#note').value,safety_signal:safety};
  submit(event.target, async()=>{
    await api('/api/patients/'+patientId+'/reports',data);
    event.target.reset(); updateRanges(); $('#urgent').hidden=!safety;
    status(safety ? 'Самоотчёт сохранён. При непосредственной опасности обратитесь за экстренной помощью; не ждите ответа в приложении.' : 'Самоотчёт сохранён и доступен в демо-кабинете врача.');
    await refresh();
  });
};
$('#decision-form').onsubmit = event => {
  event.preventDefault();
  const data = {decision:$('#decision').value,note:$('#decision-note').value};
  submit(event.target,async()=>{await api('/api/patients/'+patientId+'/decisions',data);event.target.reset();status('Решение врача сохранено.');await refresh();});
};
$('#alerts').onclick = async event => {
  const button = event.target.closest('[data-review]'); if(!button)return;
  button.disabled=true;
  try {await api('/api/alerts/'+button.dataset.review+'/review',{});status('Сигнал отмечен просмотренным.');await refresh();}
  catch(error){status(error.message,true);button.disabled=false;}
};
function connectivity(){ $('#connection').hidden=navigator.onLine; }
window.addEventListener('offline',connectivity);
window.addEventListener('online',()=>{connectivity();patientId ? refresh() : init();});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();pendingInstall=event;$('#install').hidden=false;});
$('#install').onclick=async()=>{if(pendingInstall){await pendingInstall.prompt();pendingInstall=null;$('#install').hidden=true;}};
window.addEventListener('appinstalled',()=>{$('#install').hidden=true;});
async function init(){
  try {
    const patients=await api('/api/patients');
    $('#patient').innerHTML=patients.map(p=>`<option value="${p.id}">${escapeHTML(p.name)}</option>`).join('');
    patientId=$('#patient').value;
    if(!patientId)throw new Error('Нет демо-пациентов');
    await refresh();
  }catch(error){status('Не удалось загрузить пациентов. Подключитесь к серверу и обновите страницу. '+error.message,true);}
}
connectivity();init();
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
