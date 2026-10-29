async (page) => {
  const BASE = 'http://localhost:5173';
  const DIR = 'C:/Users/KausikGH/Documents/Projects/UniTask/docs/guide/shots';
  const shots = [];
  const wait = (ms) => page.waitForTimeout(ms);
  await page.setViewportSize({ width: 1440, height: 900 });

  const login = async (email, password) => {
    await page.goto(BASE + '/login');
    await page.evaluate(async ([email, password]) => {
      const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
      const d = await r.json();
      localStorage.setItem('unitask.token', d.token);
      localStorage.setItem('unitask.theme', 'light');
    }, [email, password]);
  };
  const api = (path) => page.evaluate(async (path) => {
    const r = await fetch(path, { headers: { Authorization: 'Bearer ' + localStorage.getItem('unitask.token') } });
    return r.ok ? r.json() : null;
  }, path);
  const post = (path, body) => page.evaluate(async ([path, body]) => {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('unitask.token') }, body: JSON.stringify(body || {}) });
    return r.ok ? r.json() : null;
  }, [path, body]);
  const go = async (path, ms = 1800) => { await page.goto(BASE + path); await wait(ms); };
  const view = async (name, opts = {}) => {
    await page.screenshot({ path: `${DIR}/${name}.png`, fullPage: !!opts.full, clip: opts.clip });
    shots.push(name);
  };
  // Screenshot the card/section that contains a heading or label with this text.
  const crop = async (name, text, opts = {}) => {
    const target = page.locator(opts.selector || `:is(.panel, section, .next-action, .col, .planner, aside, form, .with-aside > div):has(:text-is("${text}"))`).last();
    try {
      await target.scrollIntoViewIfNeeded({ timeout: 2000 });
      await wait(250);
      await target.screenshot({ path: `${DIR}/${name}.png`, timeout: 4000 });
      shots.push(name);
    } catch (e) {
      shots.push(name + ' (MISSING)');
    }
  };

  // ---------------- Sign in
  await page.goto(BASE + '/login');
  await page.evaluate(() => { localStorage.clear(); localStorage.setItem('unitask.theme', 'light'); });
  await go('/login', 1500);
  await view('00-signin');

  // ---------------- Student
  await login('riya.sharma@example.edu', 'demo-student-2026');
  await page.goto(BASE + '/');
  // Leave no focus session running from an earlier capture, so Today shows its real next action.
  const open = (await api('/api/sessions')) || [];
  for (const s of (open.items || open.sessions || open)) {
    if (s && (s.state === 'active' || s.state === 'paused')) await post('/api/sessions/' + s.id + '/abandon', {});
  }
  await go('/', 2500);
  await view('01-today');
  await view('01-today-full', { full: true });
  await crop('01a-next-action', '', { selector: '.next-action' });
  await crop('01b-timeline', 'Today');
  await crop('01c-exams', 'Exams coming up');
  await crop('01d-study-queue', 'Study queue');
  await crop('01e-progress', 'This week, so far');

  // Command palette
  await page.keyboard.press('Control+k');
  await wait(600);
  await page.keyboard.type('normal');
  await wait(1500);
  await crop('02-command', '', { selector: 'dialog.palette' });
  await page.keyboard.press('Escape');
  await wait(300);

  // Recovery
  await page.getByRole('button', { name: "I'm behind" }).click();
  await wait(1200);
  await page.getByRole('button', { name: '6h', exact: true }).click();
  await wait(1800);
  await crop('03-recovery', '', { selector: 'dialog.sheet[open]' });
  await page.keyboard.press('Escape');

  await go('/inbox');
  await view('04-inbox');
  await go('/work', 2200);
  await view('05-deadlines');
  await crop('05a-load', 'Next 14 days');

  const work = (await api('/api/work')) || [];
  const lab = work.find((w) => /Lab 4/.test(w.title)) || work[0];
  if (lab) {
    await go('/work/' + lab.id, 2200);
    await view('06-workspace');
    await view('06-workspace-full', { full: true });
  }

  await go('/planner', 2200);
  await view('07-planner');
  for (const tab of ['Timetable', 'Attendance']) {
    const t = page.getByRole('tab', { name: tab }).or(page.getByRole('button', { name: tab })).first();
    if (await t.count()) { await t.click(); await wait(1200); await view('07-planner-' + tab.toLowerCase()); }
  }

  const exams = (await api('/api/exams')) || [];
  await go('/exams');
  await view('08-exams');
  const exam = (exams.items || exams)[0];
  if (exam) {
    await go('/exams/' + exam.id, 2500);
    const build = page.getByRole('button', { name: /build my rescue plan/i });
    if (await build.count()) { await build.click(); await wait(3500); }
    await view('08-rescue');
    await view('08-rescue-full', { full: true });
  }

  const subjects = (await api('/api/subjects')) || [];
  await go('/subjects');
  await view('09-subjects');
  const cd = subjects.find((s) => /Compiler/.test(s.name)) || subjects[0];
  if (cd) {
    await go('/subjects/' + cd.id, 2200);
    await view('10-syllabus');
    await view('10-syllabus-full', { full: true });
    const pyq = page.getByRole('tab', { name: /past|question/i }).or(page.getByRole('button', { name: /past papers|questions/i })).first();
    if (await pyq.count()) { await pyq.click(); await wait(1500); await view('10-pyq'); await view('10-pyq-full', { full: true }); }
    const syl = await api('/api/subjects/' + cd.id + '/syllabus');
    const topic = syl && (syl.modules || []).flatMap((m) => m.topics || m.children || []).find((t) => /automata/i.test(t.title));
    if (topic) { await go('/topics/' + topic.id, 2000); await view('11-topic'); await view('11-topic-full', { full: true }); }
  }

  await go('/library', 2000);
  await view('12-library');
  await go('/library?tab=search&q=FIRST%20FOLLOW', 2200);
  await view('12-search');
  const materials = (await api('/api/materials')) || [];
  const mat = (materials.items || materials).find((m) => m.kind === 'notes') || (materials.items || materials)[0];
  if (mat) { await go('/library/' + mat.id + '?page=2', 2000); await view('13-material'); }

  // Grounded answer with citations (real model call when an LLM is configured)
  await go('/library?tab=ask&q=' + encodeURIComponent('How do I compute FIRST and FOLLOW sets?'), 1500);
  const ask = page.getByRole('button', { name: /^ask/i }).first();
  if (await ask.count()) { await ask.click(); await page.waitForSelector('.citation, [class*="cite"]', { timeout: 60000 }).catch(() => null); await wait(800); await view('14-ask'); await view('14-ask-full', { full: true }); }

  await go('/revision', 2000);
  await view('15-revision');

  // Keep only the newest "ask" thread from repeated captures.
  const before = (await api('/api/tutor/conversations')) || [];
  for (const c of before.filter((c) => /How do I compute/i.test(c.title)).slice(1)) {
    await page.evaluate(async (id) => { await fetch('/api/tutor/conversations/' + id, { method: 'DELETE', headers: { Authorization: 'Bearer ' + localStorage.getItem('unitask.token') } }); }, c.id);
  }
  await go('/tutor', 2200);
  await view('16-tutor');
  const convs = (await api('/api/tutor/conversations')) || [];
  const conv = convs.find((c) => /subset/i.test(c.title)) || convs[0];
  if (conv) { await go('/tutor?conversation=' + conv.id, 2200); await view('16-tutor-chat'); await view('16-tutor-chat-full', { full: true }); }
  const mem = page.getByRole('button', { name: 'What it knows about me' });
  if (await mem.count()) { await mem.click(); await wait(1200); await crop('16-tutor-memory', '', { selector: 'dialog.sheet[open]' }); await page.keyboard.press('Escape'); }

  // Study desk: start (or resume) a session on a topic
  const home = await api('/api/home');
  const weak = home && home.study && home.study.weak_topics && home.study.weak_topics[0];
  const session = weak ? await post('/api/sessions', { kind: 'topic', topic_id: weak.topic_id, planned_minutes: 25 }) : null;
  if (session && session.id) { await go('/study/' + session.id, 2500); await view('17-study-desk'); await view('17-study-desk-full', { full: true }); }

  await go('/insights', 2200);
  await view('18-insights');
  await view('18-insights-full', { full: true });
  await go('/connections', 1800);
  await view('19-connections');
  await view('19-connections-full', { full: true });
  await go('/settings', 1800);
  await view('20-settings');
  await view('20-settings-full', { full: true });
  await go('/classes', 1800);
  await view('21-classes');

  // Mobile
  await page.setViewportSize({ width: 390, height: 844 });
  await go('/', 2200);
  await view('22-mobile-today');
  await page.setViewportSize({ width: 1440, height: 900 });

  // ---------------- Teacher
  await login('meera.iyer@example.edu', 'demo-teacher-2026');
  await go('/', 2000);
  await view('30-teacher-home');
  const courses = (await api('/api/courses')) || [];
  const tc = courses.find((c) => c.my_role === 'teacher');
  if (tc) {
    await go('/classes/' + tc.id, 2000);
    await view('31-teacher-class');
    const cw = (await api('/api/courses/' + tc.id + '/coursework')) || [];
    const withSubs = cw.find((w) => w.turned_in > 0) || cw[0];
    if (withSubs) {
      await go('/coursework/' + withSubs.id, 2000);
      const row = page.locator('button[aria-label*="open submission"]').first();
      if (await row.count()) { await row.click(); await wait(600); }
      await view('32-teacher-grading');
    }
  }
  return shots;
}
