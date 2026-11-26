const $ = selector => document.querySelector(selector);
const loginView = $('#loginView');
const appView = $('#appView');
const loginForm = $('#loginForm');
const showAuthor = $('#showAuthor');
const showComment = $('#showComment');
const filters = {
  tracker: $('#filterTracker'), status: $('#filterStatus'), version: $('#filterVersion'),
  priority: $('#filterPriority'), comment: $('#filterComment')
};
const startDateOperator = $('#startDateOperator');
const startDateFrom = $('#startDateFrom');
const startDateTo = $('#startDateTo');
const startDateDays = $('#startDateDays');
const dateInputOperators = new Set(['on', 'onOrAfter', 'onOrBefore', 'between']);
const dayInputOperators = new Set(['futureLess', 'futureMore', 'futureWithin', 'futureExact', 'pastLess', 'pastMore', 'pastWithin', 'pastExact']);
const shanghaiDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' });
const millisecondsPerDay = 86400000;
let activeProject = null;
let availableProjects = [];
let issues = [];
const selectedCommentAuthors = new Set();
const selectedIssueAuthors = new Set();
const selectedAssignees = new Set();
const peopleFilters = { commentAuthors: selectedCommentAuthors, authors: selectedIssueAuthors, assignees: selectedAssignees };
const viewStateKey = 'redmine-dashboard-view';
let highlightedProjectIndex = -1;
let commentsLoaded = false;
let loadGeneration = 0;
let toastTimer;
let connectedUser = '';
let connectedBaseUrl = '';
const issuePageSize = 100;
let visibleIssueLimit = issuePageSize;
const statusOrder = ['新建', '进行中', '验证不通过', '已挂起', '待验证', '已拒绝', '确认拒绝'];
const priorityOrder = ['A', 'B', 'C', 'D'];
const statusColors = new Map([
  ['新建', 'teal'],
  ['进行中', 'blue'],
  ['待验证', 'amber'],
  ['验证不通过', 'red'],
  ['验证通过', 'green'],
  ['已挂起', 'purple'],
  ['已拒绝', 'rose'],
  ['确认拒绝', 'brown'],
  ['已解决', 'green'],
  ['resolved', 'green']
]);

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || '请求失败');
    error.status = response.status;
    throw error;
  }
  return data;
}

function escapeHtml(text = '') {
  return String(text).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

function toast(message) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('show'), 2600);
}

function setView(connected) {
  $('#sessionLoading').hidden = true;
  loginView.hidden = connected;
  appView.hidden = !connected;
}

function readViewState() {
  try { return JSON.parse(sessionStorage.getItem(viewStateKey)) || {}; }
  catch { return {}; }
}

function currentViewState() {
  return {
    user: connectedUser,
    baseUrl: connectedBaseUrl,
    projectId: activeProject?.id,
    filters: Object.fromEntries(Object.entries(filters).map(([key, field]) => [key, field.value])),
    people: Object.fromEntries(Object.entries(peopleFilters).map(([key, values]) => [key, [...values]])),
    startDate: { operator: startDateOperator.value, from: startDateFrom.value, to: startDateTo.value, days: startDateDays.value },
    showAuthor: showAuthor.checked,
    showComment: showComment.checked
  };
}

function saveViewState(filtersToSave) {
  try {
    if (!connectedBaseUrl) {
      sessionStorage.removeItem(viewStateKey);
      return;
    }
    const state = currentViewState();
    if (filtersToSave) state.filters = filtersToSave;
    sessionStorage.setItem(viewStateKey, JSON.stringify(state));
  } catch { /* The dashboard still works when browser storage is disabled. */ }
}

function openDashboard(result, state = {}) {
  connectedUser = result.user ?? state.user ?? '';
  connectedBaseUrl = result.baseUrl || state.baseUrl || $('#baseUrl').value.trim();
  $('#connectedUser').textContent = connectedUser;
  $('#baseUrl').value = connectedBaseUrl;
  $('#password').value = '';
  initProjects(result.projects);
  $('#projectSelect').value = '';
  showAuthor.checked = state.showAuthor === true;
  showComment.checked = state.showComment === true;
  startDateOperator.value = state.startDate?.operator || '';
  startDateFrom.value = state.startDate?.from || '';
  startDateTo.value = state.startDate?.to || '';
  startDateDays.value = state.startDate?.days || '';
  syncStartDateFields();
  for (const [key, field] of Object.entries(filters)) field.value = state.filters?.[key] || '';
  setView(true);
  if (availableProjects.some(project => project.id === state.projectId)) {
    loadIssues(state.projectId, state);
  } else {
    populateFilters();
    updateAnalytics();
    render();
    saveViewState();
  }
}

async function restoreSession() {
  try {
    const result = await api('/api/projects');
    const state = readViewState();
    const sameSession = (!result.baseUrl || result.baseUrl === state.baseUrl) && (!result.user || result.user === state.user);
    openDashboard(result, sameSession ? state : {});
  } catch (error) {
    if (error.status !== 401) $('#loginError').textContent = error.message;
    setView(false);
  }
}

function initProjects(projects) {
  const excludedProjects = new Set(['后装车联网产品线', '移动通信产品线']);
  availableProjects = projects.filter(project => !excludedProjects.has(project.name.trim()));
  $('#projectOptions').hidden = true;
  $('#projectSelect').setAttribute('aria-expanded', 'false');
}

function renderProjectOptions() {
  const input = $('#projectSelect');
  const options = $('#projectOptions');
  const query = input.value.trim().toLocaleLowerCase('zh-CN');
  const matches = availableProjects.filter(project => project.name.toLocaleLowerCase('zh-CN').includes(query));
  highlightedProjectIndex = matches.length ? 0 : -1;
  options.replaceChildren(...matches.slice(0, 60).map((project, index) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = `project-option${index === highlightedProjectIndex ? ' highlighted' : ''}`;
    option.setAttribute('role', 'option');
    option.setAttribute('aria-selected', String(index === highlightedProjectIndex));
    option.textContent = project.name;
    option.addEventListener('mousedown', event => event.preventDefault());
    option.addEventListener('click', () => chooseProject(project));
    return option;
  }));
  if (matches.length > 60) {
    const remaining = document.createElement('div');
    remaining.className = 'project-options-note';
    remaining.textContent = `还有 ${matches.length - 60} 个结果，请继续输入缩小范围`;
    options.append(remaining);
  }
  options.hidden = matches.length === 0;
  input.setAttribute('aria-expanded', String(!options.hidden));
}

function chooseProject(project) {
  const input = $('#projectSelect');
  input.value = project.name;
  $('#projectOptions').hidden = true;
  input.setAttribute('aria-expanded', 'false');
  if (activeProject?.id !== project.id) loadIssues(project.id);
}

loginForm.addEventListener('submit', async event => {
  event.preventDefault();
  const button = loginForm.querySelector('button');
  button.disabled = true;
  button.textContent = '正在连接…';
  $('#loginError').textContent = '';
  try {
    const result = await api('/api/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ baseUrl: $('#baseUrl').value.trim(), username: $('#username').value.trim(), password: $('#password').value }) });
    openDashboard(result);
  } catch (error) {
    $('#loginError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = '连接 Redmine';
  }
});

$('#logoutButton').addEventListener('click', async () => {
  try {
    await api('/api/logout', { method: 'POST' });
    endSession();
  } catch (error) { toast(error.message); }
});

function endSession(message = '') {
  loadGeneration++;
  issues = [];
  activeProject = null;
  commentsLoaded = false;
  connectedUser = '';
  connectedBaseUrl = '';
  $('#projectIdentifier').textContent = '';
  $('#lastUpdated').textContent = '';
  $('#exportButton').disabled = true;
  $('#loadingNote').hidden = true;
  clearPeopleFilters();
  saveViewState();
  $('#loginError').textContent = message;
  setView(false);
}

$('#projectSelect').addEventListener('change', event => {
  const name = event.target.value.trim();
  const project = availableProjects.find(item => item.name.localeCompare(name, 'zh-CN', { sensitivity: 'accent' }) === 0);
  if (project) chooseProject(project);
});
$('#projectSelect').addEventListener('focus', renderProjectOptions);
$('#projectSelect').addEventListener('input', renderProjectOptions);
$('#projectSelect').addEventListener('keydown', event => {
  const options = $('#projectOptions');
  const optionButtons = [...options.querySelectorAll('.project-option')];
  if (event.key === 'Escape') {
    options.hidden = true;
    event.currentTarget.setAttribute('aria-expanded', 'false');
    return;
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    if (!optionButtons.length) return;
    const direction = event.key === 'ArrowDown' ? 1 : -1;
    highlightedProjectIndex = (highlightedProjectIndex + direction + optionButtons.length) % optionButtons.length;
    optionButtons.forEach((option, index) => {
      option.classList.toggle('highlighted', index === highlightedProjectIndex);
      option.setAttribute('aria-selected', String(index === highlightedProjectIndex));
    });
    optionButtons[highlightedProjectIndex].scrollIntoView({ block: 'nearest' });
    return;
  }
  if (event.key === 'Enter' && optionButtons.length) {
    event.preventDefault();
    optionButtons[Math.max(0, highlightedProjectIndex)]?.click();
  }
});
document.addEventListener('mousedown', event => {
  if (!event.target.closest('.project-picker')) {
    $('#projectOptions').hidden = true;
    $('#projectSelect').setAttribute('aria-expanded', 'false');
  }
  if (!event.target.closest('.author-filter')) {
    document.querySelectorAll('.author-filter[open]').forEach(filter => { filter.open = false; });
  }
});
$('#refreshButton').addEventListener('click', () => activeProject && loadIssues(activeProject.id, currentViewState()));
function applyFilters() {
  visibleIssueLimit = issuePageSize;
  saveViewState();
  updateAnalytics();
  render();
}

Object.values(filters).forEach(select => select.addEventListener('change', applyFilters));

function syncStartDateFields() {
  const operator = startDateOperator.value;
  $('#startDateFromField').hidden = !dateInputOperators.has(operator);
  $('#startDateToField').hidden = operator !== 'between';
  $('#startDateDaysField').hidden = !dayInputOperators.has(operator);
  const reversed = operator === 'between' && startDateFrom.value && startDateTo.value && startDateFrom.value > startDateTo.value;
  $('#startDateError').hidden = !reversed;
  startDateTo.setAttribute('aria-invalid', String(Boolean(reversed)));
}

for (const control of [startDateOperator, startDateFrom, startDateTo, startDateDays]) {
  control.addEventListener('change', () => {
    syncStartDateFields();
    applyFilters();
  });
}

function bindMultiSelect(name, selected, updateSummary) {
  const options = $(`#${name}Options`);
  options.addEventListener('change', event => {
    if (!event.target.matches('input[type="checkbox"]')) return;
    const { value, checked } = event.target;
    if (checked) selected.add(value);
    else selected.delete(value);
    updateSummary();
    applyFilters();
  });
  $(`#${name}Clear`).addEventListener('click', () => {
    if (!selected.size) return;
    selected.clear();
    for (const checkbox of options.querySelectorAll('input:checked')) checkbox.checked = false;
    $(`#${name}Summary`).focus();
    updateSummary();
    applyFilters();
  });
}

bindMultiSelect('commentAuthor', selectedCommentAuthors, updateCommentAuthorSummary);
bindMultiSelect('issueAuthor', selectedIssueAuthors, updateIssueAuthorSummary);
bindMultiSelect('assignee', selectedAssignees, updateAssigneeSummary);
for (const control of [showAuthor, showComment]) {
  control.addEventListener('change', () => {
    saveViewState();
    render();
  });
}
$('#exportButton').addEventListener('click', exportCsv);
$('#loadMoreButton').addEventListener('click', () => {
  visibleIssueLimit += issuePageSize;
  render();
});

function clearPeopleFilters() {
  for (const values of Object.values(peopleFilters)) values.clear();
  $('#commentAuthorOptions').innerHTML = '<span class="muted">加载批注后显示作者</span>';
  $('#issueAuthorOptions').innerHTML = '<span class="muted">加载故障后显示作者</span>';
  $('#assigneeOptions').innerHTML = '<span class="muted">加载故障后显示负责人</span>';
  updateCommentAuthorSummary();
  updateIssueAuthorSummary();
  updateAssigneeSummary();
}

async function loadIssues(projectId, state) {
  const preservedFilters = state?.filters ?? currentViewState().filters;
  if (!projectId) return;
  const project = availableProjects.find(item => item.id === projectId);
  if (!project) return;
  const generation = ++loadGeneration;
  activeProject = { id: projectId, name: project.name };
  $('#projectSelect').value = project.name;
  $('#projectIdentifier').textContent = `Redmine 标识：${project.id}`;
  issues = [];
  visibleIssueLimit = issuePageSize;
  $('#loadMoreContainer').hidden = true;
  clearPeopleFilters();
  for (const [key, values] of Object.entries(peopleFilters)) {
    for (const value of state?.people?.[key] || []) values.add(value);
  }
  updateCommentAuthorSummary();
  updateIssueAuthorSummary();
  updateAssigneeSummary();
  saveViewState(preservedFilters);
  commentsLoaded = false;
  $('#projectIdentifier').textContent = '';
  $('#lastUpdated').textContent = '';
  updateIssueColumns();
  renderIssueMessage('正在读取故障列表…');
  $('#loadingNote').hidden = false;
  $('#loadingNote').textContent = '正在加载故障与最近批注…';
  $('#exportButton').disabled = true;
  try {
    const data = await api(`/api/issues?projectId=${encodeURIComponent(projectId)}`);
    if (generation !== loadGeneration) return;
    activeProject.name = data.project.name;
    issues = data.issues;
    $('#projectIdentifier').textContent = `Redmine 标识：${data.project.id}`;
    $('#lastUpdated').textContent = `更新于 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
    populateFilters(preservedFilters);
    populateAssignees();
    saveViewState();
    updateAnalytics();
    render();
    $('#exportButton').disabled = false;
    loadComments(generation, issues.map(issue => issue.id));
  } catch (error) {
    if (generation !== loadGeneration) return;
    if (error.status === 401) {
      endSession(error.message);
      return;
    }
    renderIssueMessage(error.message);
    $('#loadingNote').hidden = true;
    toast(error.message);
  }
}

function populateFilters(preserved = {}) {
  const mapping = { tracker: 'tracker', status: 'status', version: 'version', priority: 'priority' };
  for (const [filter, field] of Object.entries(mapping)) {
    const select = filters[filter];
    const selected = preserved[filter] ?? select.value;
    const values = [...new Set(issues.map(issue => issue[field]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
    select.replaceChildren(new Option(filter === 'status' ? '全部未关闭' : '全部', ''));
    if (filter === 'status') select.add(new Option('全部', '__all__'));
    values.forEach(value => select.add(new Option(value, value)));
    if (values.includes(selected) || (filter === 'status' && selected === '__all__')) select.value = selected;
  }
}

function updateAnalytics() {
  const total = issues.length;
  const open = issues.filter(issue => !isClosed(issue)).length;
  const closed = total - open;
  $('#statTotal').textContent = total;
  $('#statOpen').textContent = open;
  $('#statClosed').textContent = closed;
  $('#statCommented').textContent = commentsLoaded ? issues.filter(issue => issue.note).length : '…';

  renderStatusChart(issues, '#overviewStatusChart', '#overviewStatusTotal', '项目全部故障');
  renderPriorityChart(issues, '#overviewPriorityChart');

  const selectedIssues = filteredIssues();
  renderStatusChart(selectedIssues, '#statusChart', '#statusTotal', '当前筛选');
  renderPriorityChart(selectedIssues, '#priorityChart');
}

function renderStatusChart(source, chartSelector, totalSelector, totalLabel) {
  const counts = new Map();
  for (const issue of source) counts.set(issue.status || '未设置', (counts.get(issue.status || '未设置') || 0) + 1);
  const statuses = [...statusOrder, ...[...counts.keys()].filter(status => !statusOrder.includes(status))];
  const max = Math.max(1, ...counts.values());
  $(totalSelector).textContent = `${totalLabel} ${source.length} 条`;
  $(chartSelector).innerHTML = statuses.map(name => {
    const value = counts.get(name) || 0;
    const percentage = source.length ? Math.round(value / source.length * 100) : 0;
    return `<div class="bar-item"><div class="bar-label"><span>${escapeHtml(name)}</span><span>${value} <small>${percentage}%</small></span></div><div class="bar-track"><div class="bar-fill" style="width:${value ? Math.max(3, value / max * 100) : 0}%"></div></div></div>`;
  }).join('');
}

function renderPriorityChart(source, chartSelector) {
  const priorities = new Map();
  for (const issue of source) {
    const priority = issue.priority || '未设置';
    priorities.set(priority, (priorities.get(priority) || 0) + 1);
  }
  const priorityNames = [...priorityOrder, ...[...priorities.keys()].filter(priority => !priorityOrder.includes(priority)).sort((a, b) => a.localeCompare(b, 'zh-CN'))];
  $(chartSelector).innerHTML = priorityNames.map(name => {
    const value = priorities.get(name) || 0;
    const percentage = source.length ? Math.round(value / source.length * 100) : 0;
    return `<div class="priority-card priority-${escapeHtml(name.toLowerCase())}" aria-label="优先级 ${escapeHtml(name)}，${value} 条，占 ${percentage}%"><div class="priority-fill" style="width:${percentage}%"></div><span class="priority-name">${escapeHtml(name)}</span><strong>${value}</strong><span class="priority-watermark" aria-hidden="true">${percentage}%</span></div>`;
  }).join('');
}

function isClosed(issue) {
  return ['已关闭', '关闭', '已解决', 'closed', 'resolved'].includes(String(issue.status || '').trim().toLowerCase());
}

function priorityColor(priority = '') {
  const label = priority.trim().toUpperCase();
  if (priorityOrder.includes(label)) return `priority-${label.toLowerCase()}`;
  if (/紧急|高/.test(label)) return 'priority-urgent';
  if (/普通|中|低/.test(label)) return 'priority-high';
  return '';
}

async function loadComments(generation, ids) {
  const batchSize = 25;
  let finished = 0;
  let failed = 0;
  for (let i = 0; i < ids.length; i += batchSize) {
    if (generation !== loadGeneration) return;
    const batch = ids.slice(i, i + batchSize);
    try {
      const data = await api('/api/comments', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ids: batch }) });
      if (generation !== loadGeneration) return;
      failed += data.failedIds?.length || 0;
      for (const issue of issues) if (data.comments[issue.id]) Object.assign(issue, data.comments[issue.id]);
      populateCommentAuthors();
      populateIssueAuthors();
    } catch (error) {
      if (generation !== loadGeneration) return;
      failed += batch.length;
      toast(`批注加载中断：${error.message}`);
    }
    finished += batch.length;
    $('#loadingNote').textContent = `批注读取进度 ${finished}/${ids.length}`;
    commentsLoaded = finished >= ids.length && failed === 0;
    updateAnalytics();
    render();
  }
  commentsLoaded = failed === 0;
  updateAnalytics();
  render();
  if (failed) {
    $('#loadingNote').textContent = `有 ${failed} 条故障详情未能读取，请点击刷新重试`;
  } else {
    $('#loadingNote').hidden = true;
  }
}

function populateCommentAuthors() {
  const authors = [...new Set(issues.map(issue => issue.commentAuthor).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const container = $('#commentAuthorOptions');
  container.replaceChildren();
  if (!authors.length) {
    container.innerHTML = '<span class="muted">暂时没有带文字的批注</span>';
  } else {
    for (const author of authors) {
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = author;
      checkbox.checked = selectedCommentAuthors.has(author);
      label.append(checkbox, document.createTextNode(author));
      container.append(label);
    }
  }
  updateCommentAuthorSummary();
}

function updateCommentAuthorSummary() {
  const count = selectedCommentAuthors.size;
  $('#commentAuthorSummary').textContent = count ? `批注人：已选 ${count} 位` : '批注人：全部';
  $('#commentAuthorClear').disabled = count === 0;
}

function populateIssueAuthors() {
  const authors = [...new Set(issues.map(issue => issue.author).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const container = $('#issueAuthorOptions');
  container.replaceChildren();
  if (!authors.length) {
    container.innerHTML = '<span class="muted">暂时没有读取到作者</span>';
  } else {
    for (const author of authors) {
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = author;
      checkbox.checked = selectedIssueAuthors.has(author);
      label.append(checkbox, document.createTextNode(author));
      container.append(label);
    }
  }
  updateIssueAuthorSummary();
}

function updateIssueAuthorSummary() {
  const count = selectedIssueAuthors.size;
  $('#issueAuthorSummary').textContent = count ? `作者：已选 ${count} 位` : '作者：全部';
  $('#issueAuthorClear').disabled = count === 0;
}

function populateAssignees() {
  const assignees = [...new Set(issues.map(issue => issue.assignee).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const container = $('#assigneeOptions');
  container.replaceChildren();
  if (!assignees.length) {
    container.innerHTML = '<span class="muted">暂无负责人</span>';
  } else {
    for (const assignee of assignees) {
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = assignee;
      checkbox.checked = selectedAssignees.has(assignee);
      label.append(checkbox, document.createTextNode(assignee));
      container.append(label);
    }
  }
  updateAssigneeSummary();
}

function updateAssigneeSummary() {
  const count = selectedAssignees.size;
  $('#assigneeSummary').textContent = count ? `指派给：已选 ${count} 位` : '指派给：全部';
  $('#assigneeClear').disabled = count === 0;
}

function startDatePredicate(now = new Date()) {
  const operator = startDateOperator.value;
  if (!operator) return null;
  if (operator === 'missing') return date => !date;
  if (operator === 'present') return date => Boolean(date);

  if (dateInputOperators.has(operator)) {
    const from = startDateFrom.value;
    const to = startDateTo.value;
    if (!from || !startDateFrom.validity.valid) return null;
    if (operator === 'on') return date => date === from;
    if (operator === 'onOrAfter') return date => date >= from;
    if (operator === 'onOrBefore') return date => Boolean(date) && date <= from;
    if (!to || !startDateTo.validity.valid || from > to) return null;
    return date => date >= from && date <= to;
  }

  // Represent Shanghai calendar dates at UTC midnight so offsets always mean whole days.
  const today = new Date(`${shanghaiDate.format(now)}T00:00:00Z`);
  const weekday = (today.getUTCDay() + 6) % 7;
  const year = today.getUTCFullYear();
  const month = today.getUTCMonth();
  const offset = days => new Date(today.getTime() + days * millisecondsPerDay).toISOString().slice(0, 10);
  const boundary = (month, day) => new Date(Date.UTC(year, month, day)).toISOString().slice(0, 10);
  const days = startDateDays.valueAsNumber;
  if (dayInputOperators.has(operator) && (!startDateDays.validity.valid || !Number.isInteger(days))) return null;

  let first;
  let last;
  switch (operator) {
    case 'today': first = last = offset(0); break;
    case 'yesterday': first = last = offset(-1); break;
    case 'thisWeek': first = offset(-weekday); last = offset(6 - weekday); break;
    case 'lastWeek': first = offset(-weekday - 7); last = offset(-weekday - 1); break;
    case 'lastTwoWeeks': first = offset(-weekday - 14); last = offset(-weekday - 1); break;
    case 'thisMonth': first = boundary(month, 1); last = boundary(month + 1, 0); break;
    case 'lastMonth': first = boundary(month - 1, 1); last = boundary(month, 0); break;
    case 'thisYear': first = boundary(0, 1); last = boundary(12, 0); break;
    case 'futureLess': last = offset(days); break;
    case 'futureMore': first = offset(days); break;
    case 'futureWithin': first = offset(0); last = offset(days); break;
    case 'futureExact': first = last = offset(days); break;
    case 'pastLess': first = offset(-days); break;
    case 'pastMore': last = offset(-days); break;
    case 'pastWithin': first = offset(-days); last = offset(0); break;
    case 'pastExact': first = last = offset(-days); break;
    default: return null;
  }
  return date => Boolean(date) && (!first || date >= first) && (!last || date <= last);
}

function filteredIssues() {
  const match = { tracker: 'tracker', status: 'status', version: 'version', priority: 'priority' };
  const matchesStartDate = startDatePredicate();
  return issues.filter(issue => {
    if (!filters.status.value && isClosed(issue)) return false;
    for (const [key, field] of Object.entries(match)) {
      const value = filters[key].value;
      if (value && !(key === 'status' && value === '__all__') && issue[field] !== value) return false;
    }
    if (filters.comment.value === 'has' && !issue.note) return false;
    if (filters.comment.value === 'none' && issue.note) return false;
    if (selectedCommentAuthors.size && !selectedCommentAuthors.has(issue.commentAuthor)) return false;
    if (selectedIssueAuthors.size && !selectedIssueAuthors.has(issue.author)) return false;
    if (selectedAssignees.size && !selectedAssignees.has(issue.assignee)) return false;
    if (matchesStartDate && !matchesStartDate(issue.startDate)) return false;
    return true;
  });
}

function renderIssueMessage(message) {
  const columnCount = 7 + Number(showAuthor.checked) + Number(showComment.checked);
  $('#issueRows').innerHTML = `<tr><td colspan="${columnCount}" class="empty-state">${escapeHtml(message)}</td></tr>`;
}

function updateIssueColumns() {
  $('#authorHeader').hidden = !showAuthor.checked;
  $('#commentHeader').hidden = !showComment.checked;
}

function render() {
  const list = filteredIssues();
  const displayedCount = Math.min(visibleIssueLimit, list.length);
  $('#loadMoreContainer').hidden = displayedCount >= list.length;
  $('#visibleIssueCount').textContent = `已显示 ${displayedCount} / ${list.length} 条`;
  $('#loadMoreButton').textContent = `加载更多 ${Math.min(issuePageSize, list.length - displayedCount)} 条`;
  $('#issueCount').textContent = issues.length ? `筛选结果 ${list.length} 条 / 项目共 ${issues.length} 条` : '暂无故障';
  updateIssueColumns();
  if (!list.length) {
    renderIssueMessage(issues.length ? '没有符合条件的故障' : '请选择项目以加载故障');
    return;
  }
  $('#issueRows').innerHTML = list.slice(0, visibleIssueLimit).map(issue => {
    const statusColor = statusColors.get(String(issue.status || '').trim().toLowerCase()) || 'gray';
    const cells = [
      `<a class="issue-link" href="${escapeHtml(activeProjectBase())}${escapeHtml(issue.url)}" target="_blank" rel="noreferrer">#${escapeHtml(issue.id)}</a>`,
      `<span class="pill">${escapeHtml(issue.tracker)}</span>`,
      `<span class="pill issue-status status-${statusColor}">${escapeHtml(issue.status || '—')}</span>`,
      escapeHtml(issue.version || '—'),
      `<span class="pill issue-priority ${priorityColor(issue.priority || '')}">${escapeHtml(issue.priority || '—')}</span>`,
      `<span class="subject-cell">${escapeHtml(issue.subject || '—')}</span>`,
      escapeHtml(issue.assignee || '—')
    ];
    if (showAuthor.checked) cells.push(escapeHtml(issue.author || (commentsLoaded ? '—' : '读取中…')));
    if (showComment.checked) cells.push(issue.note ? `<span class="comment-date">${escapeHtml(issue.commentAuthor || '作者未知')} · ${escapeHtml(issue.commentAt)}</span><span class="comment-cell">${escapeHtml(issue.note)}</span>` : commentsLoaded ? '<span class="comment-empty">无批注</span>' : '<span class="comment-empty">读取中…</span>');
    return `<tr>${cells.map(cell => `<td>${cell}</td>`).join('')}</tr>`;
  }).join('');
}

function activeProjectBase() {
  return connectedBaseUrl.replace(/\/$/, '');
}

function exportCsv() {
  const headers = ['故障编号', '跟踪', '状态', '版本号', '优先级', '主题', '指派给'];
  if (showAuthor.checked) headers.push('作者');
  if (showComment.checked) headers.push('最近批注', '批注人');
  const rows = filteredIssues().map(issue => {
    const row = [
      issue.id, issue.tracker, issue.status, issue.version, issue.priority,
      issue.subject, issue.assignee
    ];
    if (showAuthor.checked) row.push(issue.author);
    if (showComment.checked) row.push(issue.note || '', issue.note ? issue.commentAuthor || '' : '');
    return row;
  });
  const csv = [headers, ...rows].map(row => row.map(value => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }));
  const timestampParts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).formatToParts(new Date());
  const { year, month, day, hour, minute, second } = Object.fromEntries(
    timestampParts.map(({ type, value }) => [type, value])
  );
  link.download = `${activeProject?.name || 'issues'}-故障_${year}${month}${day}-${hour}${minute}${second}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

restoreSession();
