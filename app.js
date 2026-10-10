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
  captureBtn: $('captureBtn'),
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
  vibe: $('vibe'),
  vibeTime: $('vibeTime'),
  vibeMessage: $('vibeMessage'),
  vibeResult: $('vibeResult'),
  vibeGenre: $('vibeGenre'),
  vibeConfidence: $('vibeConfidence'),
  vibeBars: $('vibeBars'),
  scanAgain: $('scanAgain'),
  spotify: $('spotify'),
  spotifyAccount: $('spotifyAccount'),
  spotifyConnect: $('spotifyConnect'),
  spotifyDisconnect: $('spotifyDisconnect'),
  songs: $('songs'),
  songsMessage: $('songsMessage'),
  songList: $('songList'),
  spotifySave: $('spotifySave'),
};

let procCanvas, procCtx, overlayCtx;
let running = false;
let frameStartedAt = 0;
let countdownTimer = null;
let latestGenreRequest = 0;  // ignore responses for snapshots older than the newest one
let lastVibe = null;         // { answer, takenAt } of the most recent result
let spotifyConfigured = false;
let spotifyConnected = false;
let pendingPlaylist = null;  // { genre, songs, requestId } shown in the card, ready to save

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
  els.captureBtn.disabled = false;
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
  if (state === 'present') {
    startCountdown();
  } else {
    cancelCountdown();
    // Leaving mid-countdown: go back to whatever the card showed before.
    if (els.vibe.dataset.state === 'countdown') {
      if (lastVibe) showVibeResult(lastVibe.answer, lastVibe.takenAt);
      else showVibeStatus('idle', 'Step in front of the camera, or press Capture.');
    }
  }

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
  showVibeStatus('countdown', 'Someone’s here. Hold still for a snapshot…');
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

  const requestId = ++latestGenreRequest;
  showVibeStatus('loading', 'Reading the vibe…');

  classifyGenre(blob, stamp).then(
    (answer) => {
      if (requestId === latestGenreRequest) {
        lastVibe = { answer, takenAt };
        showVibeResult(answer, takenAt);
        findSongs(answer, requestId);
      }
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
      if (requestId === latestGenreRequest) {
        showVibeStatus('error', `Couldn’t read the vibe: ${err.message}`);
      }
    },
  );
}

// Vibe card: idle / countdown / loading / error show a message; result shows the genre,
// its breakdown and, when Spotify is set up, songs for it.
function showVibeStatus(state, message) {
  els.vibe.dataset.state = state;
  els.vibeMessage.textContent = message;
  els.vibeMessage.hidden = false;
  els.vibeResult.hidden = true;
  els.songs.hidden = true;
  els.scanAgain.hidden = true;
}

function showVibeResult(answer, takenAt) {
  els.vibe.dataset.state = 'result';
  els.vibeMessage.hidden = true;
  els.vibeResult.hidden = false;
  els.songs.hidden = !spotifyConfigured;
  els.scanAgain.hidden = !running;
  els.vibeGenre.textContent = answer.choice;
  els.vibeConfidence.textContent = `${Math.round(answer.confidence * 100)}% confident`;
  els.vibeTime.textContent = `from ${takenAt.toLocaleTimeString()}`;

  const ranked = Object.entries(answer.probabilities).sort((a, b) => b[1] - a[1]);
  els.vibeBars.replaceChildren(...ranked.map(([name, p]) => {
    const li = document.createElement('li');
    if (name === answer.choice) li.className = 'top';
    const label = document.createElement('span');
    label.className = 'name';
    label.textContent = name;
    const track = document.createElement('span');
    track.className = 'track';
    const fill = document.createElement('span');
    fill.className = 'fill';
    fill.style.width = `${p * 100}%`;
    track.append(fill);
    const value = document.createElement('span');
    value.className = 'value';
    value.textContent = `${Math.round(p * 100)}%`;
    li.append(label, track, value);
    return li;
  }));
}

// Spotify: the account bar and song list stay hidden unless the server has Spotify set
// up. Once the user connects, each new vibe shows songs from its top genre, which they
// can save as a playlist on their account. Signing in leaves the page, so the current
// vibe is kept in sessionStorage and shown again (with songs) on the way back.
const RESTORE_KEY = 'spot-a-vibe:vibe';

async function initSpotify() {
  let restored = null;
  try {
    restored = JSON.parse(sessionStorage.getItem(RESTORE_KEY));
    sessionStorage.removeItem(RESTORE_KEY);
  } catch {}
  try {
    const res = await fetch('/api/spotify/status');
    const status = await res.json();
    if (!status.configured) {
      showSpotifyUnavailable('Spotify isn’t set up on this server, so songs and playlists are off.');
      return;
    }
    spotifyConfigured = true;
    setSpotifyConnected(status.connected);
  } catch (err) {
    console.error('spotify:', err);
    showSpotifyUnavailable('Couldn’t reach the server to check Spotify.');
    return;
  }
  // Only restore if nothing newer has been detected while the status was loading.
  if (restored && !lastVibe) {
    lastVibe = { answer: restored.answer, takenAt: new Date(restored.takenAt) };
    showVibeResult(lastVibe.answer, lastVibe.takenAt);
    findSongs(lastVibe.answer, latestGenreRequest);
  }
}

// Shown instead of the Connect button, so a missing setup isn't mistaken for a missing feature.
function showSpotifyUnavailable(text) {
  els.spotify.hidden = false;
  els.spotifyConnect.hidden = true;
  els.spotifyDisconnect.hidden = true;
  els.spotifyAccount.textContent = text;
}

function setSpotifyConnected(connected) {
  spotifyConnected = connected;
  pendingPlaylist = null;
  els.spotify.hidden = false;
  els.spotifyConnect.hidden = connected;
  els.spotifyDisconnect.hidden = !connected;
  els.spotifyAccount.textContent = connected
    ? 'Spotify connected'
    : 'Connect Spotify to get songs for your vibe';
  els.songList.hidden = true;
  els.spotifySave.hidden = true;
  if (connected) {
    showSongsMessage('idle', 'Songs for your vibe will show up here.');
  } else {
    showSongsMessage('idle', 'Connect Spotify above to get songs for this vibe.');
  }
}

function showSongsMessage(state, text, link) {
  els.songs.dataset.state = state;
  els.songsMessage.replaceChildren(text);
  if (link) {
    const a = document.createElement('a');
    a.href = link;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'Open in Spotify';
    els.songsMessage.append(' ', a);
  }
}

async function postSpotify(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

function songCard(song) {
  const li = document.createElement('li');
  const a = document.createElement('a');
  a.className = 'song';
  if (song.spotify_url) {
    a.href = song.spotify_url;
    a.target = '_blank';
    a.rel = 'noopener';
  }
  // Some tracks have no album art; an empty tile keeps the cards aligned.
  const cover = document.createElement(song.album_art ? 'img' : 'span');
  cover.className = 'cover';
  if (song.album_art) {
    cover.src = song.album_art;
    cover.alt = '';
    cover.loading = 'lazy';
  }
  const info = document.createElement('span');
  info.className = 'info';
  const title = document.createElement('span');
  title.className = 'title';
  title.textContent = song.title;
  const artist = document.createElement('span');
  artist.className = 'artist';
  artist.textContent = song.artist;
  info.append(title, artist);
  a.append(cover, info);
  li.append(a);
  return li;
}

// Only called for the newest snapshot; a newer one arriving mid-request wins. The
// server picks artists by how well they match all of Clef's genre probabilities.
async function findSongs(answer, requestId) {
  if (!spotifyConnected) return;
  const genre = answer.choice;
  pendingPlaylist = null;
  els.songList.hidden = true;
  els.spotifySave.hidden = true;
  showSongsMessage('loading', `Finding ${genre} songs…`);
  try {
    const { res, data } = await postSpotify('/api/playlist/songs', {
      genre,
      probabilities: answer.probabilities,
    });
    if (requestId !== latestGenreRequest) return;
    if (res.status === 401) setSpotifyConnected(false);
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    pendingPlaylist = { genre, songs: data.songs, requestId };
    showSongsMessage('idle', `${genre} songs for your vibe`);
    els.songList.replaceChildren(...data.songs.map(songCard));
    els.songList.hidden = false;
    els.spotifySave.disabled = false;
    els.spotifySave.hidden = false;
  } catch (err) {
    console.error('songs:', err);
    if (requestId === latestGenreRequest) {
      showSongsMessage('error', `Couldn’t find songs: ${err.message}`);
    }
  }
}

// Saves exactly the songs on screen, so the playlist matches what was shown.
async function savePlaylist() {
  if (!pendingPlaylist) return;
  const { genre, songs, requestId } = pendingPlaylist;
  els.spotifySave.disabled = true;
  showSongsMessage('loading', `Saving your ${genre} playlist…`);
  try {
    const { res, data } = await postSpotify('/api/playlist', { genre, uris: songs.map((s) => s.uri) });
    if (requestId !== latestGenreRequest) return;
    if (res.status === 401) setSpotifyConnected(false);
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    els.spotifySave.hidden = true;
    showSongsMessage('done', `Saved “${data.playlist.name}” to your Spotify.`, data.playlist.spotify_url);
    addLogEntry(`Playlist saved: ${genre}`, 'snap');
  } catch (err) {
    console.error('playlist:', err);
    if (requestId === latestGenreRequest) {
      els.spotifySave.disabled = false;
      showSongsMessage('error', `Couldn’t save the playlist: ${err.message}`);
    }
  }
}

els.spotifySave.addEventListener('click', savePlaylist);
// Sign-in opens in a popup, so the camera and the current vibe stay put. If the browser
// blocks it, the link navigates as usual and the vibe is restored on the way back.
els.spotifyConnect.addEventListener('click', (event) => {
  const popup = window.open('/spotify/login?popup=1', 'spotify-sign-in', 'popup,width=500,height=760');
  if (popup) {
    event.preventDefault();
    popup.focus();
    return;
  }
  if (!lastVibe) return;
  try {
    sessionStorage.setItem(RESTORE_KEY, JSON.stringify({
      answer: lastVibe.answer,
      takenAt: lastVibe.takenAt.toISOString(),
    }));
  } catch {}
});
// The popup's last page posts this once the server has (or hasn't) stored the tokens.
window.addEventListener('message', async (event) => {
  if (event.origin !== location.origin || event.data !== 'spotify-sign-in-done') return;
  try {
    const status = await (await fetch('/api/spotify/status')).json();
    if (!status.connected) return;
    setSpotifyConnected(true);
    addLogEntry('Spotify connected', 'snap');
    // Skip while a newer snapshot is being read; its result fetches songs itself.
    if (lastVibe && els.vibe.dataset.state === 'result') {
      findSongs(lastVibe.answer, latestGenreRequest);
    }
  } catch (err) {
    console.error('spotify:', err);
  }
});
els.spotifyDisconnect.addEventListener('click', async () => {
  await fetch('/spotify/logout', { method: 'POST' }).catch(() => {});
  setSpotifyConnected(false);
});
initSpotify();

// Capture snaps a photo right away; Scan again runs the countdown first.
els.captureBtn.addEventListener('click', () => {
  if (!running) return;
  cancelCountdown();
  takeSnapshot();
});
els.scanAgain.addEventListener('click', () => {
  if (!running) return;
  els.video.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
  startCountdown();
});

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
