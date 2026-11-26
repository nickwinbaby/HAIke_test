const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const PORT = Number(process.env.PORT || 4173);
const ROOT = __dirname;
const sessions = new Map();
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };

function send(res, status, data, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store' });
  res.end(type.startsWith('application/json') ? JSON.stringify(data) : data);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; if (body.length > 1_000_000) reject(new Error('请求过大')); });
    req.on('end', () => { try { resolve(JSON.parse(body || '{}')); } catch { reject(new Error('请求格式无效')); } });
    req.on('error', reject);
  });
}

function decode(value = '') {
  return value
    .replace(/<br\s*\/?\s*>/gi, '\n').replace(/<\/(p|div|li|tr|h[1-6])\s*>/gi, '\n')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;|&#160;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>').replace(/&quot;/gi, '"').replace(/&#39;|&apos;/gi, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([\da-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/[\t\r ]+/g, ' ').replace(/ *\n */g, '\n').trim();
}

function htmlAttr(value = '') { return decode(value.replace(/\+/g, '%2B')); }
function cells(row) {
  const output = {};
  for (const match of row.matchAll(/<td\b[^>]*class="([^"]*)"[^>]*>([\s\S]*?)<\/td>/gi)) {
    const classes = match[1].split(/\s+/);
    const key = classes.find(name => ['id', 'tracker', 'status', 'priority', 'subject', 'assigned_to', 'version', 'fixed_version', 'cf_2', 'start_date'].includes(name));
    if (key) output[key] = match[2];
  }
  return output;
}

function issueDate(cell = '') {
  const source = cell.match(/\bdatetime="(\d{4}-\d{2}-\d{2})"/i)?.[1] || decode(cell);
  const parts = source.match(/^(\d{4})(?:[-/.]|\s*年\s*)(\d{1,2})(?:[-/.]|\s*月\s*)(\d{1,2})日?$/);
  if (!parts) return '';
  const [, year, month, day] = parts;
  const date = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
  const parsed = new Date(date);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().startsWith(date) ? date : '';
}

function parseIssues(html) {
  const issues = [];
  for (const match of html.matchAll(/<tr\b[^>]*id="issue-(\d+)"[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const td = cells(match[2]);
    const id = match[1];
    const value = key => decode(td[key] || '');
    issues.push({
      id,
      tracker: value('tracker'),
      status: value('status'),
      version: value('cf_2') || value('version') || value('fixed_version'),
      priority: value('priority'),
      subject: value('subject'),
      assignee: value('assigned_to'),
      startDate: issueDate(td.start_date),
      author: '',
      url: `/issues/${id}`,
      note: null,
      commentAt: '',
      commentAuthor: ''
    });
  }
  return issues;
}

function parseProjects(html, base) {
  const found = new Map();
  const projectPrefix = `${base.pathname.replace(/\/$/, '')}/projects/`;
  for (const match of html.matchAll(/<a\b([^>]*href="([^"]+)"[^>]*)>([\s\S]*?)<\/a>/gi)) {
    let url;
    try { url = new URL(match[2].replace(/&amp;/g, '&'), base); } catch { continue; }
    if (url.origin !== base.origin || !url.pathname.startsWith(projectPrefix)) continue;
    const id = url.pathname.slice(projectPrefix.length).split('/')[0];
    if (!id || ['autocomplete.js'].includes(id)) continue;
    const name = decode(match[3]);
    if (!name || name === '项目') continue;
    const previous = found.get(id);
    if (!previous || name.length < previous.name.length) found.set(id, { id, name, url: `${projectPrefix}${id}` });
  }
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
}

function parseLatestComment(html) {
  const issueAuthorHtml = (html.match(/<p\b[^>]*class="author"[^>]*>[\s\S]*?<a\b[^>]*class="user[^\"]*"[^>]*>([\s\S]*?)<\/a>/i) || [])[1] || '';
  const issueAuthor = decode(issueAuthorHtml);
  const journals = [...html.matchAll(/<div\b[^>]*class="journal\b[^>]*>/gi)];
  for (let i = journals.length - 1; i >= 0; i--) {
    const start = journals[i].index;
    const end = i + 1 < journals.length ? journals[i + 1].index : html.length;
    const block = html.slice(start, end);
    const note = [...block.matchAll(/<div\b[^>]*class="wiki"[^>]*>([\s\S]*?)<\/div>/gi)]
      .map(match => decode(match[1])).filter(Boolean).pop();
    if (!note) continue;
    const heading = (block.match(/<h4\b[^>]*>([\s\S]*?)<\/h4>/i) || [])[1] || '';
    const date = heading.match(/<a\b[^>]*title="(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})"/i);
    const authorHtml = (heading.match(/<a\b[^>]*class="user[^\"]*"[^>]*>([\s\S]*?)<\/a>/i) || [])[1] || '';
    return { note, commentAt: date?.[1] || '', commentAuthor: decode(authorHtml), author: issueAuthor };
  }
  return { note: '', commentAt: '', commentAuthor: '', author: issueAuthor };
}

function cookieHeader(cookieMap) { return [...cookieMap].map(([key, value]) => `${key}=${value}`).join('; '); }
function rememberCookies(cookieMap, response) {
  const values = response.headers.getSetCookie?.() || [response.headers.get('set-cookie')].filter(Boolean);
  for (const value of values) {
    const pair = value.split(';', 1)[0];
    const split = pair.indexOf('=');
    if (split > 0) cookieMap.set(pair.slice(0, split), pair.slice(split + 1));
  }
}

async function redmineFetch(session, target, options = {}) {
  const url = new URL(target, session.base);
  if (url.origin !== session.base.origin) throw new Error('Redmine 重定向到了其他站点');
  const headers = new Headers(options.headers || {});
  const cookie = cookieHeader(session.cookies);
  if (cookie) headers.set('cookie', cookie);
  let response = await fetch(url, { ...options, headers, redirect: 'manual' });
  rememberCookies(session.cookies, response);
  if ([301, 302, 303, 307, 308].includes(response.status)) {
    const location = response.headers.get('location');
    if (!location) throw new Error('Redmine 返回了无效重定向');
    const next = new URL(location, url);
    if (next.origin !== session.base.origin) throw new Error('Redmine 重定向到了其他站点');
    const nextHeaders = new Headers();
    const nextCookie = cookieHeader(session.cookies);
    if (nextCookie) nextHeaders.set('cookie', nextCookie);
    response = await fetch(next, { headers: nextHeaders, redirect: 'manual' });
    rememberCookies(session.cookies, response);
  }
  return response;
}

function route(base, pathname, query = '') {
  const prefix = base.pathname.replace(/\/$/, '');
  return `${prefix}${pathname}${query}`;
}

async function api(req, res, url) {
  if (url.pathname === '/api/login' && req.method === 'POST') {
    const body = await readBody(req);
    let base;
    try { base = new URL(body.baseUrl); } catch { return send(res, 400, { error: 'Redmine 地址无效' }); }
    if (!['http:', 'https:'].includes(base.protocol)) return send(res, 400, { error: '仅支持 HTTP 或 HTTPS 地址' });
    base.pathname = `${base.pathname.replace(/\/$/, '')}/`;
    base.search = '';
    base.hash = '';
    const session = { base, user: body.username || '', cookies: new Map(), projects: [] };
    const loginPage = await redmineFetch(session, route(base, '/login'));
    const loginHtml = await loginPage.text();
    const token = (loginHtml.match(/name="authenticity_token"\s+value="([^"]+)"/) || [])[1];
    if (!token) return send(res, 502, { error: '无法读取 Redmine 登录页' });
    const form = new URLSearchParams({ username: body.username || '', password: body.password || '', authenticity_token: token, utf8: '✓', login: '登录' });
    const login = await redmineFetch(session, route(base, '/login'), { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: form.toString() });
    const loginResult = await login.text();
    if (loginResult.includes('controller-account action-login') || !cookieHeader(session.cookies)) {
      return send(res, 401, { error: '登录失败，请检查账号和密码' });
    }
    const projectsPage = await redmineFetch(session, route(base, '/projects'));
    session.projects = parseProjects(await projectsPage.text(), base);
    if (!session.projects.length) return send(res, 403, { error: '登录成功，但没有读取到可访问的项目' });
    const id = crypto.randomBytes(24).toString('hex');
    sessions.set(id, session);
    setTimeout(() => sessions.delete(id), 12 * 60 * 60 * 1000).unref();
    res.setHeader('set-cookie', `dashboardSession=${id}; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200`);
    return send(res, 200, { user: session.user, baseUrl: base.href, projects: session.projects });
  }

  const sid = (req.headers.cookie || '').match(/(?:^|;\s*)dashboardSession=([a-f\d]+)/)?.[1];
  const session = sid && sessions.get(sid);
  if (url.pathname === '/api/logout') {
    if (sid) sessions.delete(sid);
    res.setHeader('set-cookie', 'dashboardSession=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0');
    return send(res, 200, { ok: true });
  }
  if (!session) return send(res, 401, { error: '连接已失效，请重新登录' });
  if (url.pathname === '/api/projects') {
    return send(res, 200, { user: session.user, baseUrl: session.base.href, projects: session.projects });
  }

  const projectId = url.searchParams.get('projectId');
  if (url.pathname === '/api/issues' && req.method === 'GET') {
    if (!session.projects.some(project => project.id === projectId)) return send(res, 403, { error: '无法访问这个项目' });
    const listUrl = route(session.base, `/projects/${encodeURIComponent(projectId)}/issues`);
    const allIssuesQuery = new URLSearchParams({ set_filter: '1', 'f[]': 'status_id', 'op[status_id]': '*', per_page: '100' });
    for (const column of ['tracker', 'status', 'priority', 'subject', 'assigned_to', 'fixed_version', 'cf_2', 'start_date']) {
      allIssuesQuery.append('c[]', column);
    }
    const first = await redmineFetch(session, `${listUrl}?${allIssuesQuery}`);
    if (!first.ok) return send(res, first.status, { error: '读取故障列表失败' });
    const firstHtml = await first.text();
    if (firstHtml.includes('controller-account action-login')) {
      sessions.delete(sid);
      return send(res, 401, { error: 'Redmine 登录已失效，请重新登录' });
    }
    const issues = parseIssues(firstHtml);
    const itemCount = Number((firstHtml.match(/class="items">\((?:\d+-\d+\/)?(\d+)\)/) || [])[1]) || issues.length;
    const pages = Math.ceil(itemCount / 100);
    const pageResults = new Array(Math.max(0, pages - 1));
    let nextPage = 2;
    const workers = Array.from({ length: Math.min(4, pageResults.length) }, async () => {
      while (nextPage <= pages) {
        const page = nextPage++;
        const response = await redmineFetch(session, `${listUrl}?${allIssuesQuery}&page=${page}`);
        if (!response.ok) throw new Error(`读取故障列表第 ${page} 页失败`);
        const html = await response.text();
        if (html.includes('controller-account action-login')) throw new Error('Redmine 登录已失效，请重新登录');
        pageResults[page - 2] = parseIssues(html);
      }
    });
    await Promise.all(workers);
    for (const pageIssues of pageResults) issues.push(...pageIssues);
    return send(res, 200, { project: session.projects.find(project => project.id === projectId), issues, total: itemCount });
  }

  if (url.pathname === '/api/comments' && req.method === 'POST') {
    const body = await readBody(req);
    const ids = [...new Set((body.ids || []).map(String).filter(id => /^\d+$/.test(id)))].slice(0, 200);
    const output = {};
    const failedIds = [];
    let index = 0;
    const workers = Array.from({ length: Math.min(8, ids.length) }, async () => {
      while (index < ids.length) {
        const id = ids[index++];
        try {
          const response = await redmineFetch(session, route(session.base, `/issues/${id}`));
          if (response.ok) output[id] = parseLatestComment(await response.text());
          else failedIds.push(id);
        } catch { failedIds.push(id); }
      }
    });
    await Promise.all(workers);
    return send(res, 200, { comments: output, failedIds });
  }
  return send(res, 404, { error: '接口不存在' });
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    if (url.pathname.startsWith('/api/')) return await api(req, res, url);
    const relative = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname.slice(1));
    const file = path.resolve(ROOT, relative);
    if (!file.startsWith(ROOT + path.sep)) return send(res, 403, 'Forbidden', 'text/plain');
    const data = fs.readFileSync(file);
    return send(res, 200, data, MIME[path.extname(file)] || 'application/octet-stream');
  } catch (error) {
    return send(res, 500, { error: error.message || '服务器错误' });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  const url = `http://127.0.0.1:${PORT}`;
  console.log(`Redmine 故障看板运行于 ${url}`);
  if (process.env.AUTO_OPEN_BROWSER === '1' && process.platform === 'win32') {
    require('node:child_process').execFile('cmd.exe', ['/c', 'start', '', url], { windowsHide: true });
  }
});
