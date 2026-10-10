// spot-a-vibe: presence detection with OpenCV.js.
//
// Each frame is run through MobileNet-SSD (a Caffe object detector trained on
// PASCAL VOC) via OpenCV's DNN module, keeping only "person" detections. Unlike a
// face detector, this finds people facing away, looking down or partly in frame.
// Inference lives in detector.worker.js so the page stays responsive.
// Raw detections are noisy, so presence is debounced: a few consecutive hits are
// needed to switch to "present", and "away" only kicks in after a grace period
// with nobody detected.

const NET_SIZE = 300;         // MobileNet-SSD input resolution (must match the worker)
const OVERLAY_WIDTH = 640;    // resolution boxes are drawn at
const TARGET_FPS = 10;        // upper bound; in practice inference speed is the limit
const CONFIRM_FRAMES = 3;     // consecutive detections required before declaring presence
const COUNTDOWN_SECONDS = 3;  // delay between someone arriving and the snapshot

const $ = (id) => document.getElementById(id);
const els = {
  video: $('video'),
  overlay: $('overlay'),
  placeholder: $('placeholder'),
  loadStatus: $('loadStatus'),
  startBtn: $('startBtn'),
  presence: $('presence'),
  presenceText: $('presenceText'),
  personCount: $('personCount'),
  fps: $('fps'),
  presentFor: $('presentFor'),
  awayFor: $('awayFor'),
  sensitivity: $('sensitivity'),
  sensOut: $('sensOut'),
  grace: $('grace'),
  graceOut: $('graceOut'),
  boxes: $('boxes'),
  notify: $('notify'),
  log: $('log'),
  countdown: $('countdown'),
  flash: $('flash'),
  snapshots: $('snapshots'),
  noSnapshots: $('noSnapshots'),
};

let procCanvas, procCtx, overlayCtx;
let running = false;
let frameStartedAt = 0;
let countdownTimer = null;

const presence = {
  state: 'unknown',       // 'unknown' | 'present' | 'away'
  since: performance.now(),
  lastSeen: 0,
  hitStreak: 0,
};

const detector = new Worker('detector.worker.js');
detector.onmessage = ({ data }) => {
  if (data.type === 'ready') {
    els.loadStatus.textContent = 'Ready. Only snapshots are sent to the server, for genre detection.';
    els.startBtn.disabled = false;
  } else if (data.type === 'result') {
    onDetections(data.people);
  } else if (data.type === 'error') {
    console.error('detector:', data.message);
    if (running) scheduleNextFrame();
    else els.loadStatus.textContent = `Failed to initialise: ${data.message}`;
  }
};
els.loadStatus.textContent = 'Loading OpenCV and person detector (~33 MB)…';
els.startBtn.addEventListener('click', startCamera);

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

  // Match the container to the camera's aspect ratio so the overlay lines up.
  els.video.parentElement.style.aspectRatio = `${vw} / ${vh}`;

  // The network takes a square input; squashing the frame is how it was trained.
  procCanvas = document.createElement('canvas');
  procCanvas.width = NET_SIZE;
  procCanvas.height = NET_SIZE;
  procCtx = procCanvas.getContext('2d', { willReadFrequently: true });

  els.overlay.width = OVERLAY_WIDTH;
  els.overlay.height = Math.round((OVERLAY_WIDTH * vh) / vw);
  overlayCtx = els.overlay.getContext('2d');

  els.placeholder.hidden = true;
  presence.since = performance.now();
  running = true;
  sendFrame();
}

// Only one frame is in flight at a time; the next is sent once results come back.
function sendFrame() {
  frameStartedAt = performance.now();
  procCtx.drawImage(els.video, 0, 0, NET_SIZE, NET_SIZE);
  const image = procCtx.getImageData(0, 0, NET_SIZE, NET_SIZE);
  // Slider 1..8 maps to a confidence threshold of 90%..20%.
  const threshold = 1 - Number(els.sensitivity.value) / 10;
  detector.postMessage({ type: 'detect', image, threshold }, [image.data.buffer]);
}

function scheduleNextFrame() {
  const elapsed = performance.now() - frameStartedAt;
  setTimeout(sendFrame, Math.max(0, 1000 / TARGET_FPS - elapsed));
}

let lastFrameAt = 0;
let fpsSmoothed = 0;

function onDetections(people) {
  const now = performance.now();
  updatePresence(people.length > 0, now);
  drawOverlay(people);
  renderStats(people.length, now);

  if (lastFrameAt) {
    const fps = 1000 / (now - lastFrameAt);
    fpsSmoothed = fpsSmoothed ? fpsSmoothed * 0.8 + fps * 0.2 : fps;
  }
  lastFrameAt = now;

  scheduleNextFrame();
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

  addLogEntry(state === 'present' ? 'Arrived' : 'Left', state === 'present' ? 'in' : 'out');
  if (state === 'present') startCountdown();
  else cancelCountdown();

  if (prev !== 'unknown' && els.notify.checked && Notification.permission === 'granted') {
    new Notification('spot-a-vibe', {
      body: state === 'present' ? 'Someone sat down in front of the camera.' : 'Nobody is in front of the camera.',
      silent: true,
    });
  }
}

function addLogEntry(text, className) {
  const li = document.createElement('li');
  li.className = className;
  const t = document.createElement('span');
  t.className = 't';
  t.textContent = new Date().toLocaleTimeString();
  li.append(t, text);
  els.log.prepend(li);
  while (els.log.children.length > 50) els.log.lastChild.remove();
}

// Counts down once per arrival, then snaps a photo. Leaving cancels it.
function startCountdown() {
  cancelCountdown();
  let remaining = COUNTDOWN_SECONDS;
  showCountdown(remaining);
  countdownTimer = setInterval(() => {
    remaining--;
    if (remaining > 0) {
      showCountdown(remaining);
    } else {
      cancelCountdown();
      takeSnapshot();
    }
  }, 1000);
}

function cancelCountdown() {
  clearInterval(countdownTimer);
  countdownTimer = null;
  els.countdown.hidden = true;
}

function showCountdown(n) {
  els.countdown.textContent = n;
  els.countdown.hidden = false;
  // Restart the CSS animation for each tick.
  els.countdown.classList.remove('tick');
  void els.countdown.offsetWidth;
  els.countdown.classList.add('tick');
}

// Captures the full-resolution camera frame (without boxes), mirrored to match the preview.
function takeSnapshot() {
  const { videoWidth: w, videoHeight: h } = els.video;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.translate(w, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(els.video, 0, 0, w, h);

  els.flash.classList.remove('go');
  void els.flash.offsetWidth;
  els.flash.classList.add('go');

  const takenAt = new Date();
  canvas.toBlob((blob) => addSnapshot(blob, takenAt), 'image/png');
  addLogEntry('Snapshot taken', 'snap');
}

function addSnapshot(blob, takenAt) {
  const url = URL.createObjectURL(blob);
  const stamp = takenAt.toISOString().replace(/[:.]/g, '-');

  const fig = document.createElement('figure');
  const link = document.createElement('a');
  link.href = url;
  link.download = `spot-a-vibe-${stamp}.png`;
  link.title = 'Download';
  const img = document.createElement('img');
  img.src = url;
  img.alt = `Snapshot taken at ${takenAt.toLocaleTimeString()}`;
  link.append(img);
  const caption = document.createElement('figcaption');
  caption.textContent = `${takenAt.toLocaleTimeString()} · click to download`;
  const genre = document.createElement('p');
  genre.className = 'genre';
  genre.textContent = 'Reading the vibe…';
  fig.append(link, genre, caption);

  els.noSnapshots.hidden = true;
  els.snapshots.prepend(fig);

  classifyGenre(blob, stamp).then(
    (answer) => {
      genre.textContent = `${answer.choice} · ${Math.round(answer.confidence * 100)}%`;
      genre.title = Object.entries(answer.probabilities)
        .sort((a, b) => b[1] - a[1])
        .map(([name, p]) => `${name}: ${Math.round(p * 100)}%`)
        .join('\n');
      addLogEntry(`Vibe: ${answer.choice}`, 'snap');
    },
    (err) => {
      console.error('genre:', err);
      genre.textContent = 'Genre unavailable';
      genre.classList.add('failed');
    },
  );
}

// Sends a snapshot to the Flask server, which runs it through Clef-Flash.
async function classifyGenre(blob, stamp) {
  const form = new FormData();
  form.append('image', blob, `snapshot-${stamp}.png`);
  const res = await fetch('/api/genre', { method: 'POST', body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body.answers.genre;
}

function drawOverlay(people) {
  const ctx = overlayCtx;
  const { width: w, height: h } = els.overlay;
  ctx.clearRect(0, 0, w, h);
  if (!els.boxes.checked) return;
  ctx.lineWidth = 3;
  ctx.strokeStyle = '#2ecc71';
  for (const p of people) {
    ctx.strokeRect(p.x * w, p.y * h, p.width * w, p.height * h);
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

function renderStats(personCount, now) {
  els.personCount.textContent = personCount;
  els.fps.textContent = fpsSmoothed ? fpsSmoothed.toFixed(1) : '–';
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
