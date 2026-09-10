/* 光隙前端：阶段编排 + 后端联调。
   文案均为占位，策划终稿直接改本文件顶部常量或 backend/config/。 */

'use strict';

// ================= 占位文案（策划可直接修改） =================
const WELCOME_MONOLOGUE =
  '嘘……你终于穿过那道沉重的光缝走过来了。\n' +
  '在外面披着铠甲、照顾别人的情绪、迎合所有期待，很累吧？\n' +
  '把那些贴在你身上的标签都在门槛上抖落掉吧。在这里，只有微光和我，没有人会给你打分。\n' +
  '来，坐下来，先让我替你接住这份疲惫……';

const SPLASH_LINES = [
  '他们说你应该情绪稳定。',
  '他们说你应该懂事、合群、随叫随到。',
  '于是你把真实的自己，折叠进了很多个不为人知的角落。',
  '直到今晚——有一道光，只为你留了一道缝。',
];

const SPLASH_LABELS = ['情绪稳定', '懂事', '合群', '随叫随到', '好脾气', '上进', '识大体', '不给人添麻烦'];

const GEN_MIN_MS = 2200; // 凝光页最短停留，保证体感

// ================= 工具 =================
const $ = (id) => document.getElementById(id);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let activeTyper = null;

function typewriter(el, text, speed = 26) {
  // 返回 { skip(), finished }；同一时间只保留一个打字机
  if (activeTyper) activeTyper.skip();
  el.textContent = '';
  let i = 0;
  let skipped = false;
  let resolveDone;
  const finished = new Promise((resolve) => { resolveDone = resolve; });
  const timer = setInterval(() => {
    if (i < text.length) {
      el.textContent += text[i];
      i += 1;
    } else {
      clearInterval(timer);
      activeTyper = null;
      resolveDone();
    }
  }, speed);
  const instance = {
    skip() {
      if (skipped) return;
      skipped = true;
      clearInterval(timer);
      el.textContent = text;
      activeTyper = null;
      resolveDone();
    },
    finished,
  };
  activeTyper = instance;
  return instance;
}

function showToast(message, kind = 'info') {
  const toast = $('toast');
  toast.textContent = message;
  toast.className = `toast show ${kind === 'error' ? 'error' : ''}`;
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toast.className = 'toast';
  }, 3200);
}

// ================= API 客户端 =================
async function api(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw { code: 'NETWORK_ERROR', message: '联不上向导的光……请检查网络后重试', retryable: true };
  }
  let data = null;
  try { data = await response.json(); } catch (err) { data = null; }

  if (!response.ok) {
    const error = (data && data.error) || {};
    throw {
      code: error.code || 'INTERNAL_ERROR',
      message: error.message || '出了点小差错，稍后再试试',
      retryable: Boolean(error.retryable),
      status: response.status,
    };
  }
  return data;
}

const apiCreateSession = () => api('POST', '/api/sessions', {});
const apiGetSession = (id) => api('GET', `/api/sessions/${id}`);
const apiSubmitAnswer = (id, round, answer) => api('POST', `/api/sessions/${id}/answers`, { round, answer });
const apiSwitchQuestion = (id) => api('POST', `/api/sessions/${id}/questions/switch`, {});
const apiRetry = (id) => api('POST', `/api/sessions/${id}/retry`, {});

// ================= 全局状态 =================
const state = {
  sessionId: null,
  round: 1,
  question: null, // {key,title,text,options,allowFreeText,sceneExample}
  quote: null,    // {id,content}
  busy: false,
};

const STORAGE_KEY = 'guangxi_session_id';
const SEEN_KEY = 'guangxi_splash_seen';

function saveSession(id) {
  state.sessionId = id;
  try { localStorage.setItem(STORAGE_KEY, id); } catch (err) { /* 隐私模式忽略 */ }
}

function clearSession() {
  state.sessionId = null;
  state.quote = null;
  try { localStorage.removeItem(STORAGE_KEY); } catch (err) { /* ignore */ }
}

// ================= 阶段切换 =================
function showStage(id) {
  document.querySelectorAll('.stage-view').forEach((el) => el.classList.remove('active'));
  $(id).classList.add('active');
}

// ================= 启动路由：新用户 / 刷新恢复 =================
async function boot() {
  let stored = null;
  try { stored = localStorage.getItem(STORAGE_KEY); } catch (err) { stored = null; }

  if (stored) {
    try {
      const snapshot = await apiGetSession(stored);
      saveSession(snapshot.sessionId);
      routeByStatus(snapshot);
      return;
    } catch (err) {
      clearSession(); // 会话已失效，走新用户流程
    }
  }
  enterSplash();
}

function routeByStatus(snapshot) {
  state.round = snapshot.currentRound;
  state.question = snapshot.question;
  if (snapshot.status === 'COMPLETED') {
    state.quote = snapshot.quote;
    enterResult(false);
  } else if (snapshot.status === 'GENERATING') {
    showStage('generating-stage');
    pollGenerating();
  } else if (snapshot.status === 'FAILED') {
    enterDialogFailed();
  } else {
    enterDialog(snapshot);
  }
}

// ================= 阶段 1: 开屏 =================
let splashTimers = [];

function enterSplash() {
  showStage('splash-stage');
  splashTimers.forEach(clearTimeout);
  splashTimers = [];

  const seen = (() => { try { return localStorage.getItem(SEEN_KEY) === '1'; } catch (err) { return false; } })();
  const lineDelay = seen ? 420 : 1500;
  const startDelay = seen ? 500 : 1600;

  const labelsEl = $('splash-labels');
  labelsEl.innerHTML = '';
  const count = seen ? 4 : SPLASH_LABELS.length;
  for (let i = 0; i < count; i += 1) {
    const label = document.createElement('span');
    label.className = 'splash-label';
    label.textContent = SPLASH_LABELS[i % SPLASH_LABELS.length];
    label.style.left = `${8 + ((i * 37) % 70)}%`;
    label.style.top = `${10 + ((i * 53) % 68)}%`;
    label.style.animationDelay = `${(i * 0.7) % 3}s`;
    labelsEl.appendChild(label);
  }

  const linesEl = $('splash-lines');
  linesEl.innerHTML = '';
  SPLASH_LINES.forEach((text) => {
    const line = document.createElement('div');
    line.className = 'splash-line';
    line.textContent = text;
    linesEl.appendChild(line);
  });

  splashTimers.push(setTimeout(() => {
    linesEl.querySelectorAll('.splash-line').forEach((line, idx) => {
      splashTimers.push(setTimeout(() => line.classList.add('show'), idx * lineDelay));
    });
  }, startDelay));

  const btn = $('splash-enter-btn');
  btn.classList.remove('show');
  splashTimers.push(setTimeout(() => btn.classList.add('show'), startDelay + SPLASH_LINES.length * lineDelay + 500));

  markSeen();
}

function markSeen() {
  try { localStorage.setItem(SEEN_KEY, '1'); } catch (err) { /* ignore */ }
}

function leaveSplash() {
  splashTimers.forEach(clearTimeout);
  splashTimers = [];
  markSeen();
  enterPortal();
}

// ================= 阶段 2: 拉开光隙（带阻尼） =================
const portal = { target: 0, rendered: 0, dragging: false, moved: false, entered: false, startX: 0, raf: 0 };

function enterPortal() {
  portal.target = 0;
  portal.rendered = 0;
  portal.entered = false;
  applyPortal(0);
  const hint = $('portal-hint');
  hint.textContent = '✦ 按住并向两侧拉开光缝 ✦';
  hint.style.color = '';
  showStage('portal-stage');
  if (!portal.raf) portalLoop();
}

function portalLoop() {
  portal.raf = requestAnimationFrame(portalLoop);
  if (Math.abs(portal.target - portal.rendered) < 0.0005) {
    if (portal.rendered === portal.target) return;
    portal.rendered = portal.target;
  } else {
    portal.rendered += (portal.target - portal.rendered) * 0.14;
  }
  applyPortal(portal.rendered);
}

function applyPortal(progress) {
  const p = Math.min(Math.max(progress, 0), 1);
  const offset = p * 48;
  $('door-left').style.transform = `translateX(-${offset}vw)`;
  $('door-right').style.transform = `translateX(${offset}vw)`;
  const slit = $('light-slit');
  slit.style.transform = `scaleX(${1 + p * 30})`;
  slit.style.opacity = `${0.7 + p * 0.3}`;

  const hint = $('portal-hint');
  if (p > 0.45 && p < 0.75) {
    hint.textContent = '✦ 别放手，向导正在光缝另一端等候你 ✦';
    hint.style.color = '#F5A623';
  } else if (p >= 0.75) {
    hint.textContent = '✦ 光缝后是只属于你的夜晚 ✦';
  }

  if (p >= 0.8 && !portal.entered) {
    portal.entered = true;
    enterWelcome();
  }
}

function bindPortal() {
  const area = $('portal-touch-area');

  area.addEventListener('pointerdown', (e) => {
    portal.dragging = true;
    portal.moved = false;
    portal.startX = e.clientX;
  });

  window.addEventListener('pointermove', (e) => {
    if (!portal.dragging) return;
    const delta = Math.abs(e.clientX - portal.startX);
    if (delta > 6) portal.moved = true;
    portal.target = delta / (window.innerWidth * 0.35);
    if (portal.target >= 0.8 && !portal.entered) enterWelcome(); // 进入不依赖动画帧
  });

  window.addEventListener('pointerup', () => {
    if (!portal.dragging) return;
    portal.dragging = false;
    if (portal.entered) return;
    if (!portal.moved && portal.target < 0.2) {
      portal.target = 1; // 点击兜底：光缝自动拉开
      setTimeout(() => { if (!portal.entered) applyPortal(1); }, 900);
      return;
    }
    if (portal.target < 0.8) portal.target = portal.target > 0.3 ? 0.35 : 0;
  });
}

// ================= 阶段 3: 向导迎候 =================
let welcomeTyper = null;

function enterWelcome() {
  showStage('welcome-stage');
  const textEl = $('welcome-text');
  const btn = $('welcome-action-btn');
  btn.classList.remove('show');
  textEl.textContent = '';
  welcomeTyper = typewriter(textEl, WELCOME_MONOLOGUE, 38);
  welcomeTyper.finished.then(() => btn.classList.add('show'));
}

async function welcomeContinue() {
  const btn = $('welcome-action-btn');
  if (!state.sessionId) {
    btn.classList.add('loading');
    btn.textContent = '向导点起了灯……';
    try {
      const created = await apiCreateSession();
      saveSession(created.sessionId);
      state.round = created.currentRound;
      state.question = created.question;
    } catch (err) {
      btn.classList.remove('loading');
      btn.textContent = '「 终于能松一口气了，坐下歇歇 ☕ 」';
      showToast(err.message, 'error');
      return;
    }
  }
  btn.classList.remove('loading');
  btn.textContent = '「 终于能松一口气了，坐下歇歇 ☕ 」';
  enterDialog();
}

// ================= 阶段 4: 三轮对话 =================
let questionTyper = null;

function enterDialog(snapshot) {
  showStage('dialog-stage');
  $('failed-view').hidden = true;
  $('answer-area').style.display = '';
  if (snapshot && snapshot.question) {
    state.round = snapshot.currentRound;
    state.question = snapshot.question;
  }
  updateDots(state.round);
  renderQuestion(state.question);
}

function enterDialogFailed() {
  showStage('dialog-stage');
  $('answer-area').style.display = 'none';
  $('failed-view').hidden = false;
  updateDots(3);
  $('mini-guide-cue').textContent = '向导还捧着你那三段回答，等你一句话。';
  const typer = typewriter($('typewriter-text'), '（向导轻声）刚才的光，晃了一下……不过你说过的话，我一个字都没忘。', 26);
  $('cursor').style.display = '';
  typer.finished.then(() => {});
}

function updateDots(current) {
  for (let i = 1; i <= 3; i += 1) {
    const dot = $(`dot-${i}`);
    dot.className = 'step-dot';
    if (i === current) dot.classList.add('active');
    else if (i < current) dot.classList.add('done');
  }
}

function renderQuestion(question) {
  if (!question) return;
  state.question = question;
  const act = state.round;
  $('mini-guide-cue').textContent = question.title
    ? `第${act}幕 · 【${question.title}】`
    : `第${act}幕`;
  $('speaker-name').textContent = '向导轻声问';

  const shelf = $('inspiration-shelf');
  shelf.classList.remove('visible');
  shelf.innerHTML = '<span class="shelf-label">向导隐隐看见的画面：</span>';
  (question.options || []).forEach((option) => {
    const chip = document.createElement('span');
    chip.className = 'inspire-chip';
    chip.textContent = option.label;
    chip.addEventListener('click', () => {
      $('user-custom-input').value = option.label;
      $('user-custom-input').focus();
    });
    shelf.appendChild(chip);
  });

  const assistBtn = $('ai-assist-btn');
  if (question.sceneExample) {
    assistBtn.hidden = false;
    $('ai-btn-text').textContent = '让向导替我显影电影镜头';
  } else {
    assistBtn.hidden = true;
  }

  const input = $('user-custom-input');
  input.value = '';
  input.placeholder = '用自己的话说说看，或点一个画面……';
  setAnswerEnabled(true);
  $('speech-status').textContent = '向导在此守护，绝无任何标签与评判';
  $('speech-status').classList.remove('active');

  questionTyper = typewriter($('typewriter-text'), question.text, 26);
  questionTyper.finished.then(() => shelf.classList.add('visible'));
}

function setAnswerEnabled(enabled) {
  $('user-custom-input').disabled = !enabled;
  $('send-custom-btn').disabled = !enabled;
  $('switch-question-btn').disabled = !enabled;
  $('mic-btn').disabled = !enabled || !speechSupported();
}

async function submitAnswer() {
  if (state.busy) return;
  const input = $('user-custom-input');
  const content = input.value.trim();
  if (!content) {
    showToast('跟向导说点什么吧，哪怕几个词。');
    return;
  }
  state.busy = true;
  setAnswerEnabled(false);
  $('mini-guide-cue').textContent = '向导侧耳倾听着……';
  try {
    const result = await apiSubmitAnswer(state.sessionId, state.round, { type: 'text', content });
    state.round = result.currentRound;
    if (result.status === 'COMPLETED') {
      state.quote = result.quote;
      enterGenerating(() => enterResult(true));
      return;
    }
    if (result.question) {
      state.question = result.question;
      updateDots(state.round);
      renderQuestion(result.question);
    }
  } catch (err) {
    if (err.code === 'ANSWER_ALREADY_EXISTS') {
      await resyncSession();
      return;
    }
    if (err.code === 'GENERATION_FAILED' && err.retryable) {
      enterDialogFailed();
      return;
    }
    if (err.code === 'SESSION_NOT_FOUND') {
      clearSession();
      showToast('会话已失效，重新开始这段旅程吧', 'error');
      enterPortal();
      return;
    }
    showToast(err.message, 'error');
    setAnswerEnabled(true);
    $('mini-guide-cue').textContent = '向导还在这里，随时可以再说一次。';
  } finally {
    state.busy = false;
  }
}

async function switchQuestion() {
  if (state.busy) return;
  state.busy = true;
  const btn = $('switch-question-btn');
  btn.disabled = true;
  try {
    const result = await apiSwitchQuestion(state.sessionId);
    if (result.question) {
      state.question = result.question;
      renderQuestion(result.question);
    }
  } catch (err) {
    if (err.code === 'SESSION_NOT_FOUND') {
      clearSession();
      showToast('会话已失效，重新开始这段旅程吧', 'error');
      enterPortal();
      return;
    }
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    state.busy = false;
  }
}

async function retryGeneration() {
  const btn = $('failed-retry-btn');
  if (state.busy) return;
  state.busy = true;
  btn.disabled = true;
  btn.textContent = '向导重新捧起了碎光……';
  try {
    const result = await apiRetry(state.sessionId);
    if (result.status === 'COMPLETED') {
      state.quote = result.quote;
      enterGenerating(() => enterResult(true));
      return;
    }
    enterDialogFailed();
    showToast('还是没能凝成……再试一次？', 'error');
  } catch (err) {
    if (err.code === 'SESSION_NOT_FOUND') {
      clearSession();
      enterPortal();
      return;
    }
    showToast(err.message, 'error');
    enterDialogFailed();
  } finally {
    btn.disabled = false;
    btn.textContent = '再试一次';
    state.busy = false;
  }
}

async function resyncSession() {
  try {
    const snapshot = await apiGetSession(state.sessionId);
    routeByStatus(snapshot);
  } catch (err) {
    clearSession();
    showToast('会话已失效，重新开始这段旅程吧', 'error');
    enterPortal();
  }
}

// 语音输入：支持则用，不支持就禁用（绝不伪造用户输入）
function speechSupported() {
  return 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
}

let recognition = null;
let recording = false;

function bindSpeech() {
  const micBtn = $('mic-btn');
  if (!speechSupported()) {
    micBtn.disabled = true;
    micBtn.title = '当前浏览器不支持语音输入，直接打字就好';
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = 'zh-CN';
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    recording = true;
    micBtn.classList.add('recording');
    $('speech-status').textContent = '向导正在倾听你的声音……说完自动填入';
    $('speech-status').classList.add('active');
  };
  recognition.onresult = (event) => {
    $('user-custom-input').value = event.results[0][0].transcript;
    $('speech-status').textContent = '已听清你的声音，可以修改后交付';
    $('speech-status').classList.remove('active');
  };
  recognition.onerror = () => {
    $('speech-status').textContent = '麦克风没开，直接打字也一样。';
    $('speech-status').classList.remove('active');
  };
  recognition.onend = () => {
    recording = false;
    micBtn.classList.remove('recording');
    if (!$('speech-status').classList.contains('active')) return;
    $('speech-status').classList.remove('active');
  };

  micBtn.addEventListener('click', () => {
    if (recording) {
      recognition.stop();
      return;
    }
    try { recognition.start(); } catch (err) { recognition.stop(); }
  });
}

// ================= 阶段 5: 凝光生成 =================
let generatingEntered = false;

function enterGenerating(onDone) {
  if (generatingEntered) return;
  generatingEntered = true;
  showStage('generating-stage');
  // 后端同步返回很快，凝光页至少停留 GEN_MIN_MS 再浮现卡片，保证体感
  setTimeout(() => {
    generatingEntered = false;
    if (onDone) onDone();
  }, GEN_MIN_MS);
}

async function pollGenerating() {
  $('gen-text').innerHTML = '向导正在把散落的碎光捧在手心...<br>为你凝结一句不被分类的真我';
  for (let i = 0; i < 20; i += 1) {
    await sleep(1500);
    try {
      const snapshot = await apiGetSession(state.sessionId);
      if (snapshot.status === 'COMPLETED') {
        state.quote = snapshot.quote;
        enterResult(false);
        return;
      }
      if (snapshot.status === 'FAILED') {
        enterDialogFailed();
        return;
      }
      if (snapshot.status.startsWith('QUESTION_')) {
        // 后端尚未推进到生成（异常恢复），回到对话
        enterDialog(snapshot);
        return;
      }
    } catch (err) {
      /* 继续轮询 */
    }
  }
  $('gen-text').innerHTML = '光凝了很久还没有成形……<br>你可以刷新页面再看看';
}

// ================= 阶段 6: 金句卡片 =================
function enterResult(withMinWait) {
  const quote = state.quote;
  if (!quote) return;
  showStage('result-stage');

  const idShort = quote.id.replace(/-/g, '').slice(0, 8).toUpperCase();
  $('card-id').textContent = `LG-${idShort}`;
  const now = new Date();
  $('card-date').textContent =
    `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')}`;

  const sentenceEl = $('golden-sentence-text');
  sentenceEl.textContent = '';
  document.querySelectorAll('.result-actions .action-btn').forEach((b) => { b.disabled = true; });

  const reveal = () => {
    const typer = typewriter(sentenceEl, quote.content, 46);
    typer.finished.then(() => {
      document.querySelectorAll('.result-actions .action-btn').forEach((b) => { b.disabled = false; });
    });
  };

  if (withMinWait) {
    // 从凝光页过渡而来：卡片随凝光结束浮现
    setTimeout(reveal, 350);
  } else {
    reveal();
  }
}

async function copyQuote() {
  const text = state.quote ? state.quote.content : '';
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showToast('金句已复制，去分享给懂你的人吧');
  } catch (err) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      showToast('金句已复制，去分享给懂你的人吧');
    } catch (copyErr) {
      showToast('复制没成功，长按卡片文字手动复制吧', 'error');
    }
    document.body.removeChild(textarea);
  }
}

async function downloadCard() {
  const btn = $('save-card-btn');
  if (state.busy) return;
  state.busy = true;
  btn.disabled = true;
  btn.textContent = '正在生成…';
  try {
    const canvas = await html2canvas($('golden-card'), {
      scale: 2,
      backgroundColor: '#ffffff',
      useCORS: true,
    });
    const link = document.createElement('a');
    const idShort = state.quote ? state.quote.id.replace(/-/g, '').slice(0, 8) : 'card';
    link.download = `光隙金句-${idShort}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
    showToast('卡片已保存到下载');
  } catch (err) {
    showToast('生成图片没成功，再试一次？', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '下载卡片';
    state.busy = false;
  }
}

function restartJourney() {
  clearSession();
  state.round = 1;
  state.question = null;
  updateDots(1);
  enterPortal();
}

// ================= 事件绑定与启动 =================
function bindEvents() {
  $('splash-enter-btn').addEventListener('click', leaveSplash);
  $('splash-skip-btn').addEventListener('click', leaveSplash);

  bindPortal();

  $('welcome-text').addEventListener('click', () => {
    if (welcomeTyper) { welcomeTyper.skip(); welcomeTyper = null; }
  });
  $('welcome-action-btn').addEventListener('click', welcomeContinue);

  $('skip-btn').addEventListener('click', () => {
    if (questionTyper) { questionTyper.skip(); questionTyper = null; }
  });
  $('switch-question-btn').addEventListener('click', switchQuestion);
  $('send-custom-btn').addEventListener('click', submitAnswer);
  $('user-custom-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitAnswer();
  });
  $('ai-assist-btn').addEventListener('click', () => {
    if (!state.question || !state.question.sceneExample) return;
    const btn = $('ai-assist-btn');
    btn.classList.add('loading');
    $('ai-btn-text').textContent = '向导提灯显影中...';
    setTimeout(() => {
      $('user-custom-input').value = state.question.sceneExample;
      $('ai-btn-text').textContent = '已显影电影画面（可自由修改）';
      btn.classList.remove('loading');
      $('user-custom-input').focus();
    }, 450);
  });
  $('failed-retry-btn').addEventListener('click', retryGeneration);

  bindSpeech();

  $('copy-quote-btn').addEventListener('click', copyQuote);
  $('save-card-btn').addEventListener('click', downloadCard);
  $('restart-btn').addEventListener('click', restartJourney);
}

bindEvents();
boot();
