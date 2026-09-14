/* 光隙前端：阶段编排 + 后端联调。
   文案均为占位，策划终稿直接改本文件顶部常量或 backend/config/。 */

'use strict';

// ================= 占位文案（策划可直接修改） =================
const OPENING_SEEN_KEY = 'guangxi_opening_seen';
// 默认每次刷新都播开场片（便于录视频）；URL 加 ?opening=once 恢复「只播一次」
const OPENING_PLAY_ONCE = new URLSearchParams(location.search).has('opening-once');
const GEN_MIN_MS = 2200; // 凝光页最短停留，保证体感

// ================= 工具 =================
const $ = (id) => document.getElementById(id);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let activeTyper = null;

function typewriter(el, text, speed = 26) {
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

let apiCreateSession = () => api('POST', '/api/sessions', {});
let apiGetSession = (id) => api('GET', `/api/sessions/${id}`);
let apiSubmitMessage = (id, content) => api('POST', `/api/sessions/${id}/messages`, { message: { content } });
let apiEndConversation = (id, endKind) => api('POST', `/api/sessions/${id}/end`, { endKind });
let apiRegenerateQuote = (id, tone) => api('POST', `/api/sessions/${id}/regenerate`, { tone });

// ================= Mock 测试模式 =================
// 默认 mock（脚本化回复，录视频/快速演示用）；URL 加 ?real=1 切到真实模型
const MOCK_MODE = !new URLSearchParams(location.search).has('real');
const MOCK_REPLIES = [
  '嗯，我在听。',
  '听到了。',
  '最近睡得还好吗？',
  '那是从什么时候开始的？',
  '你有没有哪一句，一直没跟别人说过？',
  '说不出的那句，就让它留在这里也行。',
  '不着急，我们可以先不说事。',
  '我陪你坐一会儿。',
];
const MOCK_QUOTES = [
  '那就先停一停。路不会跑，灯还亮着。',
  '想不清楚就先放一放，出门走走。',
  '雨已经落下，那就让它停一会儿。',
  '两难不是错误，只是需要时间。',
];

if (MOCK_MODE) {
  console.log('[mock mode] 前端模拟，不依赖后端模型 — 加 ?real=1 切回真实模式');
  let mockSeq = 1;
  let mockMessages = [];  // mock 也要保存消息列表，不然跨调用丢失
  let mockEndKind = null;
  let mockQuote = null;
  const realCreateSession = apiCreateSession;
  apiCreateSession = async () => {
    const sid = 'mock-' + Math.random().toString(36).slice(2, 10);
    mockSeq = 2;
    mockMessages = [{
      seq: 1, role: 'guide',
      content: '最近，有什么事一直挂在心上吗？不用组织得很完整，想到哪里说到哪里。',
    }];
    return {
      sessionId: sid,
      status: 'OPEN_CHAT',
      endKind: null,
      messages: mockMessages,
    };
  };
  apiSubmitMessage = async (sid, content) => {
    await sleep(400 + Math.random() * 400);
    mockSeq += 1;
    const reply = MOCK_REPLIES[Math.floor(Math.random() * MOCK_REPLIES.length)];
    mockMessages.push({ seq: mockSeq - 1, role: 'user', content });
    mockMessages.push({ seq: mockSeq, role: 'guide', content: reply });
    return {
      sessionId: sid, status: 'OPEN_CHAT', endKind: null,
      messages: mockMessages,
    };
  };
  apiEndConversation = async (sid, endKind) => {
    await sleep(300);
    mockEndKind = endKind;
    mockQuote = MOCK_QUOTES[Math.floor(Math.random() * MOCK_QUOTES.length)];
    return { sessionId: sid, status: 'GENERATING', endKind };
  };
  apiGetSession = async (sid) => {
    return {
      sessionId: sid,
      status: mockQuote ? 'COMPLETED' : 'OPEN_CHAT',
      endKind: mockEndKind,
      quote: mockQuote ? { id: 'mock-q', content: mockQuote } : null,
      messages: mockMessages,
    };
  };
  apiRegenerateQuote = async (sid, tone) => {
    await sleep(500);
    const prefix = tone === 'softer' ? '那就' : tone === 'stronger' ? '站稳了' : '想一想';
    mockQuote = `${prefix}，${MOCK_QUOTES[Math.floor(Math.random() * MOCK_QUOTES.length)].replace(/^[^，]+，/, '')}`;
    return {
      sessionId: sid, status: 'COMPLETED', endKind: mockEndKind,
      quote: { id: 'mock-q', content: mockQuote },
      messages: mockMessages,
    };
  };
}

// ================= 全局状态 =================
const state = {
  sessionId: null,
  round: 1,
  question: null,
  quote: null,
  busy: false,
};

const STORAGE_KEY = 'guangxi_session_id';

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
  // 进行中的会话不保留：刷新 = 重新走完整流程（开场 → 剥瓣 → 房间 → 对话）
  // 只有 COMPLETED 会话才持久化（让用户能回去看远行鼓励）
  let stored = null;
  try { stored = localStorage.getItem(STORAGE_KEY); } catch (err) { stored = null; }

  if (stored) {
    try {
      const snapshot = await apiGetSession(stored);
      if (snapshot.status === 'COMPLETED' && snapshot.quote) {
        // 已完成：恢复到结果页
        saveSession(snapshot.sessionId);
        routeByStatus(snapshot);
        return;
      }
      // 进行中（OPEN_CHAT / GENERATING / FAILED）：清掉，从头开始
      clearSession();
    } catch (err) {
      clearSession();
    }
  }
  enterOpening();
}

function routeByStatus(snapshot) {
  if (snapshot.status === 'COMPLETED') {
    state.quote = snapshot.quote;
    enterResult();
  } else if (snapshot.status === 'GENERATING') {
    showStage('generating-stage');
    pollGenerating();
  } else if (snapshot.status === 'FAILED') {
    enterDialogFailed();
  } else {
    // OPEN_CHAT 或兜底
    enterDialog(snapshot);
  }
}

// ================= 视频声音切换 =================
function bindSoundToggle(videoId, btnId) {
  const video = $(videoId);
  const btn = $(btnId);
  if (!video || !btn) return;
  const updateIcon = () => {
    btn.textContent = video.muted ? '🔇' : '🔊';
    btn.title = video.muted ? '打开声音' : '关闭声音';
  };
  btn.addEventListener('click', () => {
    video.muted = !video.muted;
    updateIcon();
  });
  video.addEventListener('volumechange', updateIcon);
  updateIcon();
}

// ================= 阶段 0: 开场品牌片（首次访问播放） =================
async function enterOpening() {
  if (OPENING_PLAY_ONCE) {
    let seen = false;
    try { seen = localStorage.getItem(OPENING_SEEN_KEY) === '1'; } catch (err) { /* ignore */ }
    if (seen) { enterPortal(); return; }
  }

  showStage('opening-stage');
  const video = $('opening-video');
  const startBtn = $('opening-start');
  const skipBtn = $('opening-skip');

  // 浏览器策略：必须先有用户手势才能解除静音自动播。点击「点亮光隙」就是手势。
  const finishOpening = () => {
    try { video.pause(); } catch (err) { /* ignore */ }
    video.currentTime = 0;
    if (OPENING_PLAY_ONCE) {
      try { localStorage.setItem(OPENING_SEEN_KEY, '1'); } catch (err) { /* ignore */ }
    }
    enterPortal();
  };

  skipBtn.onclick = finishOpening;
  video.onended = finishOpening;

  startBtn.onclick = async () => {
    startBtn.classList.add('hidden');
    skipBtn.classList.add('visible');
    try {
      video.currentTime = 0;
      video.muted = false;       // 默认开声
      await video.play();
    } catch (err) {
      // 极少数浏览器连手势都不让放音 → 退回静音
      video.muted = true;
      try { await video.play(); } catch (e2) { finishOpening(); }
    }
  };

  // 视频对象预热（不播放），让后续 play() 更快
  try { video.load(); } catch (err) { /* ignore */ }
}

// ================= 阶段 1: 4 瓣剥开入口 =================
// 每瓣的 3D peel 旋转分量（向外翻起时，rotateX/Y 的符号决定朝哪边翻）
const PETAL_DEFS = {
  'petal-tl': { rx: +1, ry: -1, fallDx: -18, fallDy: -18 },  // 左上：向前+向左翻
  'petal-tr': { rx: +1, ry: +1, fallDx: +18, fallDy: -18 },  // 右上：向前+向右翻
  'petal-bl': { rx: -1, ry: -1, fallDx: -18, fallDy: +18 },  // 左下
  'petal-br': { rx: -1, ry: +1, fallDx: +18, fallDy: +18 },  // 右下
};

const portal = {
  active: null,
  progress: { 'petal-tl': 0, 'petal-tr': 0, 'petal-bl': 0, 'petal-br': 0 },
  fallStart: {},
  dragging: false,
  entered: false,
  hints: [
    { at: 0,    text: '✦ 手指轻触缝隙中心 ✦' },
    { at: 0.25, text: '✦ 顺势撕开「他人期待」 ✦' },
    { at: 0.55, text: '✦ 别放手，外壳正在脱离 ✦' },
    { at: 0.85, text: '✦ 最后一片，即将与真我相见 ✦' },
  ],
};

function enterPortal() {
  portal.active = null;
  portal.progress = { 'petal-tl': 0, 'petal-tr': 0, 'petal-bl': 0, 'petal-br': 0 };
  portal.fallStart = {};
  portal.dragging = false;
  portal.entered = false;
  document.querySelectorAll('.petal').forEach((el) => {
    el.style.transform = '';
    el.classList.remove('peiling', 'peeling', 'fallen');
  });
  $('portal-shell').style.opacity = '';
  $('portal-reveal').classList.remove('glowing');
  const hint = $('portal-hint');
  hint.classList.remove('visible', 'dismissed');
  hint.textContent = portal.hints[0].text;
  showStage('portal-stage');
  setTimeout(() => hint.classList.add('visible'), 500);
}

function setPortalHint(progress) {
  let text = portal.hints[0].text;
  for (const h of portal.hints) if (progress >= h.at) text = h.text;
  const hint = $('portal-hint');
  if (hint.textContent !== text) hint.textContent = text;
}

function totalProgress() {
  const vals = Object.values(portal.progress);
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function pickActivePetal(x, y) {
  const cx = window.innerWidth / 2;
  const cy = window.innerHeight / 2;
  const left = x < cx;
  const top = y < cy;
  const primary = (left && top) ? 'petal-tl'
    : (!left && top) ? 'petal-tr'
    : (left && !top) ? 'petal-bl'
    : 'petal-br';
  const order = {
    'petal-tl': ['petal-tl', 'petal-bl', 'petal-tr', 'petal-br'],
    'petal-tr': ['petal-tr', 'petal-br', 'petal-tl', 'petal-bl'],
    'petal-bl': ['petal-bl', 'petal-tl', 'petal-br', 'petal-tr'],
    'petal-br': ['petal-br', 'petal-tr', 'petal-bl', 'petal-tl'],
  }[primary];
  for (const id of order) {
    if (!portal.fallStart[id] && (portal.progress[id] || 0) < 0.95) return id;
  }
  return null;
}

function applyPetal(petalId, progress) {
  const el = $(petalId);
  if (!el) return;
  const p = Math.max(0, Math.min(1, progress));
  const def = PETAL_DEFS[petalId];
  // 3D 卷边：rotateX 让外侧边沿抬离屏幕，rotateY 让外侧角滑向外
  // 进度映射到 ~120° 总旋转，背面在 ~90° 时开始显露
  const angle = p * 110;
  el.style.transform = `rotateX(${def.rx * angle}deg) rotateY(${def.ry * angle}deg)`;
}

function fallPetal(petalId) {
  if (portal.fallStart[petalId]) return;
  portal.fallStart[petalId] = performance.now();
  const el = $(petalId);
  el.classList.remove('peiling', 'peeling');
  el.classList.add('fallen');
  const def = PETAL_DEFS[petalId];
  // 叠加掉落位移（在原有旋转之上）；CSS transition 已配置在 .fallen
  const baseTransform = el.style.transform || '';
  el.style.transform = `${baseTransform} translate(${def.fallDx}vw, ${def.fallDy}vh)`;
  setTimeout(maybeEnterWelcome, 700);
}

function maybeEnterWelcome() {
  const fallenCount = Object.keys(portal.fallStart).length;
  if (fallenCount >= 4 && !portal.entered) {
    portal.entered = true;
    enterWelcome();
  }
}

function bindPortal() {
  const stage = $('portal-stage');

  const onDown = (e) => {
    if (portal.entered) return;
    const t = e.touches ? e.touches[0] : e;
    const id = pickActivePetal(t.clientX, t.clientY);
    if (!id) return;
    portal.active = id;
    portal.dragging = true;
    stage.classList.add('peeling');
    const g = $(id);
    g.classList.remove('fallen');
    g.classList.add('peiling');
    e.preventDefault();
  };

  const onMove = (e) => {
    if (!portal.dragging || portal.entered) return;
    const t = e.touches ? e.touches[0] : e;
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    const dx = t.clientX - cx;
    const dy = t.clientY - cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const fullDist = Math.min(window.innerWidth, window.innerHeight) * 0.18;
    let progress = Math.min(dist / fullDist, 1);
    portal.progress[portal.active] = progress;
    // 当 progress 突破 0.15 才开始 peeling 视觉
    const g = $(portal.active);
    if (progress > 0.15 && !g.classList.contains('peeling')) {
      g.classList.add('peeling');
    }
    applyPetal(portal.active, progress);
    setPortalHint(totalProgress());
    if (progress >= 0.95) {
      portal.dragging = false;
      stage.classList.remove('peeling');
      fallPetal(portal.active);
      portal.active = null;
    }
  };

  const onUp = () => {
    if (!portal.dragging) return;
    portal.dragging = false;
    stage.classList.remove('peiling', 'peeling');
    if (portal.active && portal.progress[portal.active] < 0.5) {
      portal.progress[portal.active] = 0;
      applyPetal(portal.active, 0);
      const g = $(portal.active);
      g.classList.remove('peeling');
    }
    portal.active = null;
  };

  stage.addEventListener('pointerdown', onDown);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onUp);

  // 键盘兜底：1/2/3/4 直接撕对应瓣（调试用，也方便桌面访问）
  window.addEventListener('keydown', (e) => {
    if (portal.entered) return;
    if (!$('portal-stage').classList.contains('active')) return;
    const map = { '1': 'petal-tl', '2': 'petal-tr', '3': 'petal-bl', '4': 'petal-br' };
    const id = map[e.key];
    if (id && !portal.fallStart[id]) {
      portal.progress[id] = 1;
      applyPetal(id, 1);
      $(id).classList.add('peiling', 'peeling');
      setPortalHint(totalProgress());
      fallPetal(id);
    }
  });
}

// ================= 阶段 2: 向导迎候（视频 + 留声机光圈） =================
let welcomeEnded = false;

function enterWelcome() {
  // 4 瓣都掉光了，shell 淡出，reveal 亮起，再切到 welcome
  $('portal-reveal').classList.add('glowing');
  $('portal-shell').style.opacity = '0';
  $('portal-hint').classList.add('dismissed');
  $('portal-stage').classList.remove('peiling', 'peeling');
  setTimeout(() => {
    showStage('welcome-stage');
    playWelcomeVideo();
  }, 1100);
}

function pauseAllVideos() {
  ['welcome-video', 'opening-video'].forEach((id) => {
    const v = $(id);
    if (v) { try { v.pause(); } catch (err) { /* ignore */ } }
  });
}

// 留声机音乐单独控制：进聊天/回房间不打断，只在离开房间流程时停
function pauseRoomAudio() {
  const audio = $('room-audio');
  if (audio) { try { audio.pause(); } catch (err) { /* ignore */ } }
}

function playWelcomeVideo() {
  const video = $('welcome-video');
  const ring = $('welcome-ring');
  welcomeEnded = false;
  if (ring) { ring.hidden = true; ring.onclick = null; }
  try {
    video.currentTime = 0;
    video.muted = false;
    video.play().catch(() => {
      video.muted = true;
      video.play().catch(() => { showWelcomeRingFallback(); });
    });
  } catch (err) { showWelcomeRingFallback(); }
  // 兜底：视频 7.1s，10s 兜底必触发
  const fallback = setTimeout(() => {
    if (!welcomeEnded) showWelcomeRing();
  }, 10000);
  video.onended = () => {
    welcomeEnded = true;
    clearTimeout(fallback);
    showWelcomeRing();
  };
}

function showWelcomeRingFallback() {
  if (!welcomeEnded) showWelcomeRing();
}

function showWelcomeRing() {
  const ring = $('welcome-ring');
  if (!ring || !ring.hidden) return;
  ring.hidden = false;
  ring.onclick = () => {
    pauseAllVideos();
    enterRoom();
  };
}

// ================= 阶段 2.5: 房间配置 =================
// 网易云 outer URL 模式（演示/Demo 用，ToS 上是灰色，公开上线需自审）
const ROOM_SONGS = [
  { id: '1954343972', name: '夜林',         mood: 'ambient' },
  { id: '225305',     name: '夜雨',         mood: 'ambient' },
  { id: '109187',     name: '微光',         mood: 'ambient' },
  { id: '29775505',   name: '缓步',         mood: 'piano' },
  { id: '27890308',   name: '暮色',         mood: 'cinematic' },
  { id: '209725',     name: '海与星',       mood: 'ambient' },
  { id: '86211',      name: '灯下',         mood: 'acoustic' },
  { id: '1308058076', name: '鹿鸣',         mood: 'piano' },
  { id: '28907026',   name: '夜航',         mood: 'cinematic' },
  { id: '1456319983', name: '港湾',         mood: 'acoustic' },
];
const ROOM_STORAGE_KEY = 'guangxi_room_v1';
const ROOM_DEFAULTS = { brightness: 50, music: 60, temp: 68, curtain: 1 };

let roomConfig = { ...ROOM_DEFAULTS };
let roomSongId = null;

function loadRoomConfig() {
  try {
    const raw = localStorage.getItem(ROOM_STORAGE_KEY);
    if (raw) roomConfig = { ...ROOM_DEFAULTS, ...JSON.parse(raw) };
    // 旧存档可能是三态（0/1/2），收敛到两态（0=关上 1=打开）
    if (roomConfig.curtain !== 0 && roomConfig.curtain !== 1) roomConfig.curtain = ROOM_DEFAULTS.curtain;
  } catch (err) { /* ignore */ }
}
function saveRoomConfig() {
  try { localStorage.setItem(ROOM_STORAGE_KEY, JSON.stringify(roomConfig)); } catch (err) { /* ignore */ }
}

function tempText(v) {
  if (v >= 70) return '暖';
  if (v >= 30) return '中性';
  return '冷';
}
const CURTAIN_TEXT = ['关上', '打开'];

function applyRoomPreview() {
  const overlay = $('room-light-overlay');
  if (!overlay) return;
  // 亮度：叠加层不透明度
  const b = roomConfig.brightness;
  overlay.style.opacity = String(0.12 + (b / 100) * 0.55);
  // 色温：hue-rotate + 整体偏色
  const t = roomConfig.temp;
  const hue = -25 + (t / 100) * 60;  // -25(冷蓝) → 35(暖橙)
  overlay.style.filter = `hue-rotate(${hue}deg) saturate(${0.9 + (t / 100) * 0.4})`;
  // 向导剪影光晕随亮度
  const halo = $('room-figure-halo');
  if (halo) halo.style.setProperty('--halo-strength', String(0.35 + (b / 100) * 0.65));
  // 留声机边缘高光
  const gram = $('room-gramophone');
  if (gram) gram.style.filter = `drop-shadow(0 0 ${3 + b / 12}px rgba(245, 166, 35, ${0.3 + b / 200}))`;
  // 窗帘图：关上 / 打开（打开图为带窗景完整图）
  const curtainImg = $('room-curtain-img');
  if (curtainImg) {
    curtainImg.src = roomConfig.curtain === 0 ? 'img/curtain-closed.png' : 'img/curtain-open.png';
    curtainImg.style.opacity = '1';
  }
}

function applyAudioVolume() {
  const audio = $('room-audio');
  if (!audio) return;
  audio.volume = Math.min(1, Math.max(0, roomConfig.music / 100));
}

// 一次性挂 audio 错误监听（详细诊断 + 友好提示）
(function bindAudioDiagnostics() {
  const audio = $('room-audio');
  if (!audio || audio.__diagnosticsBound) return;
  audio.__diagnosticsBound = true;
  audio.addEventListener('error', () => {
    const err = audio.error;
    const codeMap = {
      1: '用户中止',
      2: '网络错误',
      3: '解码失败',
      4: '资源不可用 / 网易云 CDN 在当前网络拉不到',
    };
    const msg = err ? (codeMap[err.code] || `错误码 ${err.code}`) : '未知错误';
    console.warn('[audio] error:', err ? `code=${err.code} (${msg})` : 'unknown');
    showToast(`♪ 这首播不出来 — ${msg}`, 'error');
  });
  audio.addEventListener('stalled', () => console.warn('[audio] stalled — 网络可能慢'));
  audio.addEventListener('waiting', () => console.warn('[audio] waiting — 缓冲中'));
  audio.addEventListener('canplay', () => console.log('[audio] canplay'));
})();

function playRoomSong(id) {
  const audio = $('room-audio');
  if (!audio) {
    showToast('音频元素缺失（#room-audio），请刷新页面', 'error');
    return;
  }
  const song = ROOM_SONGS.find((s) => s.id === id);
  const name = song ? song.name : id;
  const url = `https://music.163.com/song/media/outer/url?id=${id}.mp3`;
  roomSongId = id;
  audio.src = url;
  audio.muted = false;
  applyAudioVolume();
  showToast(`已点播《${name}》，加载中…`);
  // 加载 + 播放；详细错误已在 bindAudioDiagnostics 里捕获
  const playPromise = audio.play();
  if (playPromise && playPromise.then) {
    playPromise.then(() => {
      console.log('[audio] playing:', id);
    }).catch((err) => {
      console.warn('[audio] play() rejected:', err && err.message);
      showToast('播放被浏览器拦截，点页面任意位置后再试', 'error');
    });
  }
  // 3 秒自检：若还没真正出声，弹具体原因
  setTimeout(() => {
    if (roomSongId !== id) return;
    if (audio.paused) {
      showToast('音频仍未开始播放 — 可能被 Edge 安全策略拦截，按 F12 看控制台红字', 'error');
    } else if (audio.volume === 0 || audio.muted) {
      showToast('在播放但音量为 0 — 把房间面板「音乐」滑块调高', 'error');
    } else if (audio.currentTime <= 0.1) {
      showToast('已连接但缓冲中，网络较慢，再等几秒', 'info');
    }
  }, 3000);
  updateSongListUI();
  showNowPlaying(id);
}

function toggleRoomSong() {
  const audio = $('room-audio');
  if (!audio) return;
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
  updateSongListUI();
}

function showNowPlaying(id) {
  const np = $('room-now-playing');
  if (!np) return;
  const song = ROOM_SONGS.find((s) => s.id === id);
  if (!song) { np.hidden = true; return; }
  np.querySelector('span').textContent = song.name;
  np.hidden = false;
}

function updateSongListUI() {
  const list = $('room-songs-list');
  if (!list) return;
  const audio = $('room-audio');
  list.querySelectorAll('.room-song').forEach((el) => {
    const id = el.dataset.id;
    el.classList.toggle('playing', id === roomSongId && audio && !audio.paused);
    const stateEl = el.querySelector('.room-song-state');
    if (stateEl) {
      if (id === roomSongId && audio && !audio.paused) stateEl.textContent = '播放中';
      else if (id === roomSongId && audio && audio.paused) stateEl.textContent = '已暂停';
      else stateEl.textContent = '';
    }
  });
}

let quoteDebounce = null;
function getContextualQuote() {
  const c = roomConfig;
  if (c.brightness < 12 && c.curtain === 0) return '黑暗里也不怕，我陪着你。';
  if (c.brightness < 15) return '再暗一点也行，藏得住心事。';
  if (c.brightness > 78) return '亮得太满了，反而看不清自己。';
  if (c.curtain === 0) return '关上窗，外面再吵也进不来。';
  if (c.curtain === 1 && c.brightness > 55) return '打开窗，外面的风可以进来了。';
  if (c.temp < 25) return '冷一点也好，思绪更清楚。';
  if (c.temp > 85) return '太暖会犯困，就在这儿眯一会儿吧。';
  if (c.music > 75) return '声音再大一点就把安静也盖住了。';
  return null;
}
function maybeUpdateQuote() {
  if (quoteDebounce) clearTimeout(quoteDebounce);
  quoteDebounce = setTimeout(() => {
    const q = getContextualQuote();
    const el = $('room-quote');
    if (!el) return;
    if (q) {
      el.style.opacity = '0';
      setTimeout(() => {
        el.textContent = '向导：「' + q + '」';
        el.style.opacity = '1';
      }, 250);
    }
  }, 1100);
}

function bindSlider(id, key, valueEl, isTemp) {
  const el = $(id);
  const out = $(valueEl);
  if (!el) return;
  el.value = roomConfig[key];
  if (out) out.textContent = isTemp ? tempText(roomConfig[key]) : roomConfig[key];
  el.addEventListener('input', () => {
    roomConfig[key] = parseInt(el.value, 10);
    if (out) out.textContent = isTemp ? tempText(roomConfig[key]) : roomConfig[key];
    applyRoomPreview();
    if (key === 'music') applyAudioVolume();
    saveRoomConfig();
    maybeUpdateQuote();
  });
}

function showPreviewTip(el, msg) {
  document.querySelectorAll('.preview-tip').forEach((t) => t.remove());
  const tip = document.createElement('div');
  tip.className = 'preview-tip';
  tip.textContent = msg;
  document.body.appendChild(tip);
  const rect = el.getBoundingClientRect();
  tip.style.left = `${rect.left + rect.width / 2}px`;
  tip.style.top = `${rect.top - 8}px`;
  setTimeout(() => { tip.style.opacity = '0'; }, 2400);
  setTimeout(() => { tip.remove(); }, 2900);
}

// ================= 房间：点击物件 → 直接调整 / 弹浮窗 =================
let roomScene = null;
let candleLit = false;
let activeFloatingPanel = null;

function closeFloatingPanel() {
  if (activeFloatingPanel && activeFloatingPanel.parentElement) {
    activeFloatingPanel.remove();
  }
  activeFloatingPanel = null;
}

function showFloatingPanel(targetEl, contentHTML) {
  closeFloatingPanel();
  const panel = document.createElement('div');
  panel.className = 'room-floating-panel';
  panel.innerHTML = `<button class="room-floating-panel-close" title="关闭">×</button>${contentHTML}`;
  // 定位在物件上方
  const rect = targetEl.getBoundingClientRect();
  const canvasRect = $('room-canvas').getBoundingClientRect();
  panel.style.left = `${rect.left + rect.width / 2 - canvasRect.left}px`;
  panel.style.top = `${rect.top - canvasRect.top - 8}px`;
  panel.style.transform = 'translate(-50%, -100%)';
  $('room-canvas').appendChild(panel);
  activeFloatingPanel = panel;
  panel.querySelector('.room-floating-panel-close').addEventListener('click', closeFloatingPanel);
  // 外部点击关闭（点 hotspot 不关，让新面板接管）
  setTimeout(() => {
    document.addEventListener('pointerdown', (e) => {
      if (activeFloatingPanel && !activeFloatingPanel.contains(e.target) && !e.target.closest('[data-hotspot]')) {
        closeFloatingPanel();
      }
    }, { once: true });
  }, 50);
  return panel;
}

function bindRoomItems() {
  // 窗户 → 切换窗帘（两态：关上 ⇄ 打开）
  document.querySelector('.room-window-area')?.addEventListener('click', () => {
    const next = (roomConfig.curtain + 1) % 2;
    roomConfig.curtain = next;
    $('val-curtain').textContent = CURTAIN_TEXT[next];
    document.querySelectorAll('.room-toggle').forEach((b) => {
      b.classList.toggle('active', parseInt(b.dataset.curtain, 10) === next);
    });
    applyRoomPreview();
    saveRoomConfig();
    maybeUpdateQuote();
    showPreviewTip(document.querySelector('.room-window-area'), `窗帘${CURTAIN_TEXT[next]}`);
  });

  // 蜡烛 → 点亮/熄灭
  const candle = document.querySelector('.room-candle');
  candle?.addEventListener('click', () => {
    candleLit = !candleLit;
    candle.classList.toggle('lit-on', candleLit);
    candle.classList.toggle('lit-off', !candleLit);
    // 点亮 → 拉高亮度；熄灭 → 拉低亮度
    const newBrightness = candleLit ? Math.max(roomConfig.brightness, 60) : Math.min(roomConfig.brightness, 25);
    roomConfig.brightness = newBrightness;
    $('ctrl-brightness').value = newBrightness;
    $('val-brightness').textContent = newBrightness;
    applyRoomPreview();
    saveRoomConfig();
    maybeUpdateQuote();
    showPreviewTip(candle, candleLit ? '烛光点亮了' : '烛火熄了');
  });

  // 台灯 → 浮窗弹亮度滑块
  const lamp = document.querySelector('.room-lamp-img');
  lamp?.addEventListener('click', () => {
    showFloatingPanel(lamp, `
      <div style="font-size:11px;color:#F5A623;letter-spacing:1.5px;margin-bottom:6px;">调节亮度</div>
      <input type="range" min="0" max="100" value="${roomConfig.brightness}"
             class="room-slider" id="popup-brightness"
             style="width:100%;">
      <div style="text-align:right;font-size:11px;color:rgba(245,230,200,0.6);margin-top:4px;">
        <span id="popup-brightness-val">${roomConfig.brightness}</span>
      </div>
    `);
    const slider = $('popup-brightness');
    slider.addEventListener('input', () => {
      roomConfig.brightness = parseInt(slider.value, 10);
      $('val-brightness').textContent = slider.value;
      $('ctrl-brightness').value = slider.value;
      $('popup-brightness-val').textContent = slider.value;
      applyRoomPreview();
      saveRoomConfig();
      maybeUpdateQuote();
    });
  });

  // 留声机 → 浮窗弹曲目列表（id 在 PNG 图元素上）
  const gram = $('room-gramophone');
  gram?.addEventListener('click', () => {
    const list = ROOM_SONGS.map(song => {
      const isPlaying = song.id === roomSongId;
      const audio = $('room-audio');
      const stateLabel = isPlaying && audio && !audio.paused ? '播放中' : (isPlaying ? '已暂停' : '');
      return `<div class="room-fp-song${isPlaying ? ' playing' : ''}" data-id="${song.id}">
        <span>♪ ${song.name}</span>
        <span class="room-fp-song-state">${stateLabel}</span>
      </div>`;
    }).join('');
    const panel = showFloatingPanel(gram, `
      <div style="font-size:11px;color:#F5A623;letter-spacing:1.5px;margin-bottom:6px;">🎵 留声机曲目</div>
      <div class="room-fp-list">${list}</div>
    `);
    // 事件委托：面板内任意歌曲行点击都接管，防绑定丢失
    panel.addEventListener('click', (e) => {
      const row = e.target.closest('.room-fp-song');
      if (!row) return;
      const id = row.dataset.id;
      if (roomSongId === id) {
        toggleRoomSong();
      } else {
        playRoomSong(id);
      }
      closeFloatingPanel();
    });
  });

  // 向导剪影 → 提示
  document.querySelector('.room-figure')?.addEventListener('click', () => {
    showPreviewTip(document.querySelector('.room-figure'), '向导坐在那里，没打扰你。');
  });
}

// ================= 房间：3D 拖动摄像头 =================
function bindRoomCamera() {
  const canvas = $('room-canvas');
  if (!canvas) return;
  roomScene = $('room-scene');
  if (!roomScene) return;

  let dragging = false;
  let startX = 0, startY = 0;
  let baseRotateX = 0, baseRotateY = 0;
  let lastMoveTime = 0;

  const onDown = (e) => {
    // 不抢点击物件的事件（物件热点 / 罗盘 / 浮窗内的按钮和滑块）
    if (e.target.closest('[data-hotspot]') || e.target.closest('.room-compass') || e.target.closest('.room-floating-panel')) return;
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    canvas.classList.add('dragging');
    canvas.setPointerCapture && canvas.setPointerCapture(e.pointerId);
  };
  const onMove = (e) => {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    // 灵敏度
    const ry = Math.max(-25, Math.min(25, baseRotateY + dx * 0.18));
    const rx = Math.max(-12, Math.min(12, baseRotateX - dy * 0.12));
    roomScene.style.transform = `translateZ(0) rotateX(${rx}deg) rotateY(${ry}deg)`;
    lastMoveTime = Date.now();
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    canvas.classList.remove('dragging');
    // 1.5 秒无操作后自动归位（轻柔）
    setTimeout(() => {
      if (!dragging && Date.now() - lastMoveTime > 1400) {
        roomScene.style.transform = '';
      }
    }, 1500);
  };

  canvas.addEventListener('pointerdown', onDown);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onUp);
}

function initRoomStage() {
  // 滑块
  bindSlider('ctrl-brightness', 'brightness', 'val-brightness', false);
  bindSlider('ctrl-music', 'music', 'val-music', false);
  bindSlider('ctrl-temp', 'temp', 'val-temp', true);

  // 窗帘
  document.querySelectorAll('.room-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const v = parseInt(btn.dataset.curtain, 10);
      roomConfig.curtain = v;
      $('val-curtain').textContent = CURTAIN_TEXT[v];
      document.querySelectorAll('.room-toggle').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      applyRoomPreview();
      saveRoomConfig();
      maybeUpdateQuote();
    });
  });

  // 点击物件：浮窗提示 / 直接调整
  bindRoomItems();

  // 3D 拖动：横向转 Y，纵向转 X，松手自动归位
  bindRoomCamera();

  // 罗盘按钮 = 归位
  $('room-compass').addEventListener('click', () => {
    if (roomScene) roomScene.style.transform = '';
  });

  // 底部按钮
  $('room-stay-btn').addEventListener('click', () => {
    showToast('那就先这样待着，听听歌。');
  });
  $('room-chat-btn').addEventListener('click', async () => {
    pauseAllVideos();
    // 没有会话就先建一个（mock 或真实都走 apiCreateSession）
    if (!state.sessionId) {
      try {
        const created = await apiCreateSession();
        saveSession(created.sessionId);
      } catch (err) {
        showToast(err.message || '没法和向导建立连接', 'error');
        return;
      }
    }
    enterDialog();
  });
}

function enterRoom() {
  loadRoomConfig();
  showStage('room-stage');
  // 同步控件值
  $('ctrl-brightness').value = roomConfig.brightness;
  $('ctrl-music').value = roomConfig.music;
  $('ctrl-temp').value = roomConfig.temp;
  $('val-brightness').textContent = roomConfig.brightness;
  $('val-music').textContent = roomConfig.music;
  $('val-temp').textContent = tempText(roomConfig.temp);
  $('val-curtain').textContent = CURTAIN_TEXT[roomConfig.curtain];
  document.querySelectorAll('.room-toggle').forEach((b) => {
    b.classList.toggle('active', parseInt(b.dataset.curtain, 10) === roomConfig.curtain);
  });
  applyRoomPreview();
  applyAudioVolume();
}

// ================= 阶段 3: 开放式聊天 =================

function appendBubble(role, text, opts = {}) {
  // galgame 模式：不显示气泡流，改为更新底部对话框的当前文本
  if (role === 'guide') {
    setCurrentDialog(text, opts.typing);
  }
  // history drawer 还是要完整存（用于抽屉显示）
  if (!window.__chatHistory) window.__chatHistory = [];
  window.__chatHistory.push({ role, text });
  return null;
}

// galgame 主对话区：只显示最新一条向导回复
function setCurrentDialog(text, typing) {
  const el = $('dialog-current-text');
  if (!el) return;
  if (typing) {
    el.textContent = '';
    let i = 0;
    const speed = 30;
    const id = setInterval(() => {
      if (i < text.length) {
        el.textContent += text[i++];
      } else {
        clearInterval(id);
      }
    }, speed);
  } else {
    el.textContent = text;
  }
}

// ================= 历史抽屉 =================
function openHistoryDrawer() {
  console.log('[history] openHistoryDrawer called');
  const drawer = $('chat-history-drawer');
  const list = $('chat-history-list');
  if (!drawer || !list) return;
  list.innerHTML = '';
  const items = window.__chatHistory || [];
  console.log('[history] items count:', items.length, 'roles:', items.map(i => i.role).join(','));
  items.forEach((m) => {
    const div = document.createElement('div');
    div.className = 'history-row ' + (m.role === 'user' ? 'is-user' : m.role === 'guide' ? 'is-guide' : 'is-system');
    div.textContent = m.text;
    list.appendChild(div);
  });
  if (items.length === 0) {
    list.innerHTML = '<div style="text-align:center;color:rgba(255,248,220,0.5);font-size:12px;padding:20px;">还没有对话</div>';
  }
  drawer.hidden = false;
  drawer.style.zIndex = '50';
}

function closeHistoryDrawer() {
  const drawer = $('chat-history-drawer');
  if (drawer) drawer.hidden = true;
}

async function enterDialog(snapshot) {
  showStage('dialog-stage');
  $('failed-view').hidden = true;
  $('chat-input-area').hidden = false;
  $('end-options-panel').hidden = true;

  // 没有传 snapshot 的话，先去拿一次（从房间直接跳进来时会触发）
  let msgs = (snapshot && snapshot.messages) || [];
  if (!snapshot && state.sessionId) {
    try {
      const snap = await apiGetSession(state.sessionId);
      msgs = snap.messages || [];
      state.round = snap.currentRound;
      state.question = snap.question;
    } catch (err) {
      // 没会话就建一个（mock 或真实）
      try {
        const created = await apiCreateSession();
        saveSession(created.sessionId);
        msgs = created.messages || [];
      } catch (e2) { /* ignore */ }
    }
  }
  msgs.forEach((m) => appendBubble(m.role === 'user' ? 'user' : 'guide', m.content));

  $('chat-input').value = '';
  $('chat-input').focus();
}

function enterDialogFailed() {
  showStage('dialog-stage');
  $('chat-input-area').hidden = true;
  $('end-options-panel').hidden = true;
  $('failed-view').hidden = false;
}

async function sendChatMessage() {
  if (state.busy) return;
  const input = $('chat-input');
  const content = (input.value || '').trim();
  if (!content) {
    showToast('说点什么吧，哪怕几个字。');
    return;
  }
  state.busy = true;
  input.disabled = true;
  $('chat-send-btn').disabled = true;
  try {
    // 第一次发消息后，「差不多了」按钮浮现
    const endBtn = $('chat-end-trigger');
    if (endBtn && endBtn.hidden) {
      endBtn.hidden = false;
      showToast('聊开后可以选「差不多了」收束这段相遇');
    }
    // 立即显示用户气泡（乐观渲染）
    appendBubble('user', content);
    input.value = '';
    lastUserMessageText = content;

    const result = await apiSubmitMessage(state.sessionId, content);
    // 同步消息历史；向导回复（真实模式=模型生成；mock=脚本台词）以打字机效果显示
    rebuildChatThread(result.messages, { typing: true });
  } catch (err) {
    if (err.code === 'SESSION_NOT_FOUND') {
      clearSession();
      showToast('会话已失效，重新开始这段旅程吧', 'error');
      enterPortal();
      return;
    }
    showToast(err.message, 'error');
  } finally {
    state.busy = false;
    input.disabled = false;
    $('chat-send-btn').disabled = false;
    input.focus();
  }
}

function rebuildChatThread(messages, opts = {}) {
  // galgame 模式：清空历史，画廊重置最新对话
  if (!window.__chatHistory) window.__chatHistory = [];
  window.__chatHistory = [];
  (messages || []).forEach((m) => {
    window.__chatHistory.push({ role: m.role, text: m.content });
  });
  // 把最后一条 guide 消息显示到对话框
  const lastGuide = (messages || []).filter((m) => m.role === 'guide').pop();
  if (lastGuide) setCurrentDialog(lastGuide.content, Boolean(opts.typing));
}

function showEndOptions() {
  console.log('[end] showEndOptions called');
  $('chat-input-area').hidden = true;
  $('end-options-panel').hidden = false;
  $('end-options-panel').style.zIndex = '60';
}

function hideEndOptions() {
  $('end-options-panel').hidden = true;
  $('chat-input-area').hidden = false;
  $('chat-input').focus();
}

async function confirmEnd(endKind) {
  console.log('[end] confirmEnd:', endKind);
  if (state.busy) return;
  state.busy = true;
  try {
    const result = await apiEndConversation(state.sessionId, endKind);
    console.log('[end] /end response:', result);
    if (result.status === 'GENERATING') {
      $('end-options-panel').hidden = true;
      enterGenerating(() => enterResult(true));
    } else if (result.status === 'COMPLETED') {
      state.quote = result.quote;
      enterResult(false);
    } else if (result.status === 'FAILED') {
      enterDialogFailed();
    }
  } catch (err) {
    console.error('[end] confirmEnd error:', err);
    if (err.code === 'SESSION_NOT_FOUND') {
      clearSession();
      showToast('会话已失效，重新开始这段旅程吧', 'error');
      enterPortal();
      return;
    }
    showToast(err.message, 'error');
  } finally {
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
    const result = await apiEndConversation(state.sessionId, 'natural_close');
    if (result.status === 'GENERATING') {
      enterGenerating(() => enterResult(true));
    } else if (result.status === 'COMPLETED') {
      state.quote = result.quote;
      enterResult(true);
    } else {
      enterDialogFailed();
    }
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

// ================= 语音输入 =================
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
    if (recording) { recognition.stop(); return; }
    try { recognition.start(); } catch (err) { recognition.stop(); }
  });
}

// ================= 阶段 4: 凝光生成 =================
let generatingEntered = false;

function enterGenerating(onDone) {
  if (generatingEntered) return;
  generatingEntered = true;
  showStage('generating-stage');
  setTimeout(() => {
    generatingEntered = false;
    if (onDone) onDone();
  }, GEN_MIN_MS);
}

async function pollGenerating() {
  $('gen-text').innerHTML = '向导正在把散落的碎光捧在手心...<br>为你凝结一句远行鼓励';
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
      if (snapshot.status === 'OPEN_CHAT') {
        enterDialog(snapshot);
        return;
      }
    } catch (err) { /* 继续轮询 */ }
  }
  $('gen-text').innerHTML = '光凝了很久还没有成形……<br>你可以刷新页面再看看';
}

// ================= 阶段 5: 远行鼓励 =================
let lastUserMessageText = '';

function enterResult() {
  const quote = state.quote;
  if (!quote || !quote.content) {
    resyncSession();
    return;
  }
  showStage('result-stage');

  const ctx = $('result-context-text');
  if (ctx) {
    if (lastUserMessageText) ctx.textContent = lastUserMessageText;
    else if (state.sessionId) {
      apiGetSession(state.sessionId).then((snap) => {
        const userMsgs = (snap.messages || []).filter((m) => m.role === 'user');
        const last = userMsgs[userMsgs.length - 1];
        if (last) {
          lastUserMessageText = last.content;
          ctx.textContent = last.content;
        }
      }).catch(() => {});
    }
  }

  const ta = $('result-quote-text');
  if (ta) {
    ta.value = quote.content;
    ta.disabled = false;
  }

  const nameInput = $('result-name-input');
  if (nameInput) nameInput.value = '';

  document.querySelectorAll('.result-variant-btn').forEach((b) => {
    b.disabled = false;
    b.classList.remove('loading');
    b.textContent = b.dataset.tone === 'softer' ? '更温柔一点'
                  : b.dataset.tone === 'stronger' ? '更有力量一点'
                  : '重写一句';
  });

  const take = $('result-take-btn');
  if (take) {
    take.disabled = false;
    take.textContent = '带着这句话出发';
    take.style.background = '';
  }
}

async function regenerateWithTone(tone) {
  if (state.busy) return;
  state.busy = true;
  const btns = document.querySelectorAll('.result-variant-btn');
  btns.forEach((b) => { b.disabled = true; });
  const target = document.querySelector(`.result-variant-btn[data-tone="${tone}"]`);
  if (target) {
    target.classList.add('loading');
    target.textContent = '重写中…';
  }
  try {
    const result = await apiRegenerateQuote(state.sessionId, tone);
    if (result.quote && result.quote.content) {
      state.quote = result.quote;
      const ta = $('result-quote-text');
      if (ta) ta.value = result.quote.content;
    }
  } catch (err) {
    showToast(err.message || '这次改写没成，可以再试一次', 'error');
  } finally {
    state.busy = false;
    btns.forEach((b) => {
      b.disabled = false;
      b.classList.remove('loading');
      b.textContent = b.dataset.tone === 'softer' ? '更温柔一点'
                    : b.dataset.tone === 'stronger' ? '更有力量一点'
                    : '重写一句';
    });
  }
}

async function takeQuoteAway() {
  const text = ($('result-quote-text') || {}).value || '';
  const name = (($('result-name-input') || {}).value || '').trim() || '本次相遇·未命名';
  if (!text.trim()) {
    showToast('这句话空了，要么留一句，要么关掉这页。');
    return;
  }
  const btn = $('result-take-btn');
  btn.disabled = true;
  btn.textContent = '正在打包…';
  try {
    await navigator.clipboard.writeText(text);
    showToast(`「${text}」已复制，带着它上路吧`);
  } catch (err) { /* ignore */ }
  setTimeout(() => {
    btn.textContent = `✓ 带走了（${name}）`;
    btn.style.background = 'linear-gradient(135deg, #2a1850, #15082e)';
  }, 600);
}

function restartJourney() {
  pauseAllVideos();
  pauseRoomAudio();
  clearSession();
  state.round = 1;
  state.question = null;
  if (OPENING_PLAY_ONCE) {
    try { localStorage.setItem(OPENING_SEEN_KEY, '1'); } catch (err) { /* ignore */ }
  }
  enterPortal();
}

function backToPortal() {
  pauseAllVideos();
  pauseRoomAudio();
  state.busy = false;
  $('chat-input-area').hidden = false;
  $('end-options-panel').hidden = true;
  $('failed-view').hidden = true;
  $('portal-shell').style.opacity = '';
  $('portal-reveal').classList.remove('glowing');
  $('portal-hint').classList.remove('dismissed');
  enterPortal();
}

// ================= 事件绑定与启动 =================
function bindEvents() {
  bindPortal();
  bindSoundToggle('opening-video', 'opening-sound');
  bindSoundToggle('welcome-video', 'welcome-sound');
  initRoomStage();

  $('welcome-replay-btn').addEventListener('click', () => {
    const v = $('welcome-video');
    try { v.currentTime = 0; v.play().catch(() => {}); } catch (err) { /* ignore */ }
    const ring = $('welcome-ring');
    if (ring) ring.hidden = true;
    welcomeEnded = false;
    setTimeout(() => { if (!welcomeEnded) showWelcomeRing(); }, 10000);
    v.onended = () => {
      welcomeEnded = true;
      showWelcomeRing();
    };
  });

  $('room-back').addEventListener('click', () => {
    pauseAllVideos();
    pauseRoomAudio();
    showStage('welcome-stage');
    welcomeEnded = false;
    playWelcomeVideo();
  });

  // 聊天输入
  $('chat-send-btn').addEventListener('click', sendChatMessage);
  $('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  // 历史抽屉
  $('chat-history-btn').addEventListener('click', openHistoryDrawer);
  $('chat-history-close').addEventListener('click', closeHistoryDrawer);

  // 结束入口
  $('chat-end-trigger').addEventListener('click', showEndOptions);
  $('end-options-cancel').addEventListener('click', hideEndOptions);
  document.querySelectorAll('.end-option[data-end]').forEach((btn) => {
    btn.addEventListener('click', () => confirmEnd(btn.dataset.end));
  });

  // 回房间
  $('chat-back-to-room').addEventListener('click', () => {
    console.log('[nav] back to room');
    pauseAllVideos();
    enterRoom();
  });

  $('failed-retry-btn').addEventListener('click', retryGeneration);

  // 远行鼓励 stage
  document.querySelectorAll('.result-variant-btn').forEach((btn) => {
    btn.addEventListener('click', () => regenerateWithTone(btn.dataset.tone));
  });
  $('result-take-btn').addEventListener('click', takeQuoteAway);

  $('back-to-portal-btn').addEventListener('click', backToPortal);
  $('result-back-btn').addEventListener('click', backToPortal);
}

bindEvents();
boot();

// 模式切换小徽章
(function setupModeBadge() {
  const badge = $('mode-badge');
  if (!badge) return;
  badge.textContent = MOCK_MODE ? '模拟' : '真实';
  badge.classList.toggle('real', !MOCK_MODE);
  badge.addEventListener('click', () => {
    const next = MOCK_MODE ? '?real=1' : location.pathname;
    location.href = next;
  });
})();
