// spot-a-vibe: presence detection with OpenCV.js Haar cascades.
//
// Each frame is downscaled, converted to grayscale and run through a frontal-face
// cascade (plus an optional profile cascade on both the frame and its mirror).
// Raw detections are noisy, so presence is debounced: a few consecutive hits are
// needed to switch to "present", and "away" only kicks in after a grace period
// with no faces.

const PROC_WIDTH = 320;       // detection runs on a frame this wide; smaller = faster
const TARGET_FPS = 12;
const CONFIRM_FRAMES = 3;     // consecutive detections required before declaring presence
const MIN_FACE_FRACTION = 0.12; // ignore faces smaller than this fraction of frame width

const CASCADES = {
  frontal: 'models/haarcascade_frontalface_default.xml',
  profile: 'models/haarcascade_profileface.xml',
};

const $ = (id) => document.getElementById(id);
const els = {
  video: $('video'),
  overlay: $('overlay'),
  placeholder: $('placeholder'),
  loadStatus: $('loadStatus'),
  startBtn: $('startBtn'),
  presence: $('presence'),
  presenceText: $('presenceText'),
  faceCount: $('faceCount'),
  fps: $('fps'),
  presentFor: $('presentFor'),
  awayFor: $('awayFor'),
  sensitivity: $('sensitivity'),
  sensOut: $('sensOut'),
  grace: $('grace'),
  graceOut: $('graceOut'),
  profile: $('profile'),
  boxes: $('boxes'),
  notify: $('notify'),
  log: $('log'),
};

// opencv.js picks up a global `Module` object and calls onRuntimeInitialized
// once the WASM runtime is ready. The same object becomes the cv namespace.
var Module = {
  onRuntimeInitialized() {
    window.cv = Module;
    init().catch((err) => {
      console.error(err);
      els.loadStatus.textContent = `Failed to initialise: ${err.message}`;
    });
  },
};

function onOpenCvError() {
  els.loadStatus.textContent = 'Could not load OpenCV.js — check your internet connection.';
}

const classifiers = {};
let mats = null;          // reusable Mats, allocated once the frame size is known
let procCanvas, procCtx, overlayCtx;
let running = false;

const presence = {
  state: 'unknown',       // 'unknown' | 'present' | 'away'
  since: performance.now(),
  lastSeen: 0,
  hitStreak: 0,
};

async function init() {
  els.loadStatus.textContent = 'Loading face models…';
  for (const [name, url] of Object.entries(CASCADES)) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`could not fetch ${url} (${res.status})`);
    const data = new Uint8Array(await res.arrayBuffer());
    const file = `${name}.xml`;
    cv.FS_createDataFile('/', file, data, true, false, false);
    const clf = new cv.CascadeClassifier();
    if (!clf.load(file)) throw new Error(`could not parse ${file}`);
    classifiers[name] = clf;
  }

  els.loadStatus.textContent = 'Ready. Your video never leaves this device.';
  els.startBtn.disabled = false;
  els.startBtn.addEventListener('click', startCamera);
}

async function startCamera() {
  els.startBtn.disabled = true;
  els.loadStatus.textContent = 'Requesting camera…';
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: false,
    });
    els.video.srcObject = stream;
    await els.video.play();
  } catch (err) {
    els.loadStatus.textContent = `Camera unavailable: ${err.message}`;
    els.startBtn.disabled = false;
    return;
  }

  const vw = els.video.videoWidth;
  const vh = els.video.videoHeight;
  const w = PROC_WIDTH;
  const h = Math.round((PROC_WIDTH * vh) / vw);

  // Match the container to the camera's aspect ratio so the overlay lines up.
  els.video.parentElement.style.aspectRatio = `${vw} / ${vh}`;

  procCanvas = document.createElement('canvas');
  procCanvas.width = w;
  procCanvas.height = h;
  procCtx = procCanvas.getContext('2d', { willReadFrequently: true });

  els.overlay.width = w;
  els.overlay.height = h;
  overlayCtx = els.overlay.getContext('2d');

  mats = {
    rgba: new cv.Mat(h, w, cv.CV_8UC4),
    gray: new cv.Mat(),
    mirrored: new cv.Mat(),
  };

  els.placeholder.hidden = true;
  presence.since = performance.now();
  running = true;
  loop();
}

function detect(classifier, img, minNeighbors) {
  const rects = new cv.RectVector();
  const minSize = Math.round(img.cols * MIN_FACE_FRACTION);
  classifier.detectMultiScale(img, rects, 1.1, minNeighbors, 0, new cv.Size(minSize, minSize), new cv.Size(0, 0));
  const out = [];
  for (let i = 0; i < rects.size(); i++) {
    const r = rects.get(i);
    out.push({ x: r.x, y: r.y, width: r.width, height: r.height });
  }
  rects.delete();
  return out;
}

function findFaces() {
  const { rgba, gray, mirrored } = mats;
  procCtx.drawImage(els.video, 0, 0, procCanvas.width, procCanvas.height);
  rgba.data.set(procCtx.getImageData(0, 0, procCanvas.width, procCanvas.height).data);
  cv.cvtColor(rgba, gray, cv.COLOR_RGBA2GRAY);
  cv.equalizeHist(gray, gray);

  // Slider 1..8 maps to minNeighbors 8..1: fewer neighbours = more permissive.
  const minNeighbors = 9 - Number(els.sensitivity.value);

  const faces = detect(classifiers.frontal, gray, minNeighbors).map((f) => ({ ...f, kind: 'frontal' }));
  if (faces.length || !els.profile.checked) return faces;

  // The profile cascade only knows one side, so also run it on a mirrored frame.
  for (const f of detect(classifiers.profile, gray, minNeighbors)) {
    faces.push({ ...f, kind: 'profile' });
  }
  cv.flip(gray, mirrored, 1);
  for (const f of detect(classifiers.profile, mirrored, minNeighbors)) {
    faces.push({ ...f, x: gray.cols - f.x - f.width, kind: 'profile' });
  }
  return faces;
}

let lastFrameAt = 0;
let fpsSmoothed = 0;

function loop() {
  if (!running) return;
  const start = performance.now();

  const faces = findFaces();
  updatePresence(faces.length > 0, start);
  drawOverlay(faces);
  renderStats(faces.length, start);

  if (lastFrameAt) {
    const fps = 1000 / (start - lastFrameAt);
    fpsSmoothed = fpsSmoothed ? fpsSmoothed * 0.9 + fps * 0.1 : fps;
  }
  lastFrameAt = start;

  const elapsed = performance.now() - start;
  setTimeout(loop, Math.max(0, 1000 / TARGET_FPS - elapsed));
}

function updatePresence(detected, now) {
  const graceMs = Number(els.grace.value) * 1000;

  if (detected) {
    presence.hitStreak++;
    presence.lastSeen = now;
  } else {
    presence.hitStreak = 0;
  }

  if (presence.state !== 'present' && presence.hitStreak >= CONFIRM_FRAMES) {
    setPresence('present', now);
  } else if (presence.state !== 'away' && !detected && now - presence.lastSeen > graceMs) {
    // While present, lastSeen marks when the person was last seen, so the away
    // timer starts from there rather than from when the grace period ran out.
    setPresence('away', presence.state === 'present' ? presence.lastSeen : now);
  }
}

function setPresence(state, since) {
  const prev = presence.state;
  presence.state = state;
  presence.since = since;

  els.presence.className = `presence ${state}`;
  els.presenceText.textContent = state === 'present' ? 'Someone’s here' : 'Nobody’s here';
  document.title = `${state === 'present' ? '🟢' : '🔴'} spot-a-vibe`;

  addLogEntry(state);
  if (prev !== 'unknown' && els.notify.checked && Notification.permission === 'granted') {
    new Notification('spot-a-vibe', {
      body: state === 'present' ? 'Someone sat down in front of the camera.' : 'Nobody is in front of the camera.',
      silent: true,
    });
  }
}

function addLogEntry(state) {
  const li = document.createElement('li');
  li.className = state === 'present' ? 'in' : 'out';
  const t = document.createElement('span');
  t.className = 't';
  t.textContent = new Date().toLocaleTimeString();
  li.append(t, state === 'present' ? 'Arrived' : 'Left');
  els.log.prepend(li);
  while (els.log.children.length > 50) els.log.lastChild.remove();
}

function drawOverlay(faces) {
  const ctx = overlayCtx;
  ctx.clearRect(0, 0, els.overlay.width, els.overlay.height);
  if (!els.boxes.checked) return;
  ctx.lineWidth = 2;
  for (const f of faces) {
    ctx.strokeStyle = f.kind === 'frontal' ? '#2ecc71' : '#f1c40f';
    ctx.strokeRect(f.x, f.y, f.width, f.height);
  }
}

function formatDuration(ms) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function renderStats(faceCount, now) {
  els.faceCount.textContent = faceCount;
  els.fps.textContent = fpsSmoothed ? fpsSmoothed.toFixed(0) : '–';
  const elapsed = formatDuration(now - presence.since);
  els.presentFor.textContent = presence.state === 'present' ? elapsed : '–';
  els.awayFor.textContent = presence.state === 'away' ? elapsed : '–';
}

// Settings wiring
function syncOutputs() {
  els.sensOut.textContent = els.sensitivity.value;
  els.graceOut.textContent = `${els.grace.value}s`;
}
els.sensitivity.addEventListener('input', syncOutputs);
els.grace.addEventListener('input', syncOutputs);
syncOutputs();

els.notify.addEventListener('change', async () => {
  if (!els.notify.checked) return;
  if (!('Notification' in window)) {
    els.notify.checked = false;
    return;
  }
  if (Notification.permission !== 'granted') {
    const result = await Notification.requestPermission();
    if (result !== 'granted') els.notify.checked = false;
  }
});
