// Runs MobileNet-SSD person detection off the main thread. A forward pass takes
// several hundred milliseconds in WASM, which would otherwise freeze the page.
//
// Messages in:  { type: 'detect', image: ImageData (NET_SIZE square), threshold }
// Messages out: { type: 'ready' } | { type: 'error', message } | { type: 'result', people }

const NET_SIZE = 300;         // MobileNet-SSD input resolution
const PERSON_CLASS_ID = 15;   // index of "person" in the VOC label set
const MIN_PERSON_AREA = 0.04; // ignore people covering less of the frame than this (far-off passers-by)

const MODEL = {
  config: 'models/MobileNetSSD_deploy.prototxt',
  weights: 'models/MobileNetSSD_deploy.caffemodel',
};

let net = null;
let rgba = null;
let rgb = null;

// opencv.js picks up a global `Module` object and calls onRuntimeInitialized
// once the WASM runtime is ready. The same object becomes the cv namespace.
var Module = {
  onRuntimeInitialized() {
    self.cv = Module;
    loadModel().then(
      () => postMessage({ type: 'ready' }),
      (err) => postMessage({ type: 'error', message: err.message }),
    );
  },
};

try {
  importScripts('https://docs.opencv.org/4.9.0/opencv.js');
} catch (err) {
  postMessage({ type: 'error', message: 'Could not load OpenCV.js — check your internet connection.' });
}

async function loadModel() {
  // OpenCV reads models from its in-memory filesystem, so copy them there first.
  for (const url of Object.values(MODEL)) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`could not fetch ${url} (${res.status})`);
    const data = new Uint8Array(await res.arrayBuffer());
    cv.FS_createDataFile('/', url.split('/').pop(), data, true, false, false);
  }
  net = cv.readNetFromCaffe(MODEL.config.split('/').pop(), MODEL.weights.split('/').pop());
  rgba = new cv.Mat(NET_SIZE, NET_SIZE, cv.CV_8UC4);
  rgb = new cv.Mat();
}

// Returns people as boxes in normalised [0, 1] coordinates.
function findPeople(image, threshold) {
  rgba.data.set(image.data);
  cv.cvtColor(rgba, rgb, cv.COLOR_RGBA2RGB);

  // MobileNet-SSD expects BGR scaled to [-1, 1]: (pixel - 127.5) / 127.5.
  const blob = cv.blobFromImage(rgb, 1 / 127.5, new cv.Size(NET_SIZE, NET_SIZE),
    new cv.Scalar(127.5, 127.5, 127.5), true, false);
  net.setInput(blob);
  const out = net.forward();

  // Output is [1, 1, N, 7]; each row is [batch, class, confidence, x1, y1, x2, y2].
  const people = [];
  const d = out.data32F;
  for (let i = 0; i < d.length; i += 7) {
    if (d[i + 1] !== PERSON_CLASS_ID || d[i + 2] < threshold) continue;
    const x1 = clamp01(d[i + 3]);
    const y1 = clamp01(d[i + 4]);
    const x2 = clamp01(d[i + 5]);
    const y2 = clamp01(d[i + 6]);
    if ((x2 - x1) * (y2 - y1) < MIN_PERSON_AREA) continue;
    people.push({ x: x1, y: y1, width: x2 - x1, height: y2 - y1, confidence: d[i + 2] });
  }

  blob.delete();
  out.delete();
  return people;
}

function clamp01(v) {
  return Math.min(1, Math.max(0, v));
}

onmessage = ({ data }) => {
  if (data.type !== 'detect') return;
  try {
    postMessage({ type: 'result', people: findPeople(data.image, data.threshold) });
  } catch (err) {
    postMessage({ type: 'error', message: err.message ?? String(err) });
  }
};
