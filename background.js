// The page's background, behind every screen: the eye logo tiled across it, drawn through a
// WebGL shader in one of three modes:
//   matrix    the logo rebuilt from whole dots on a grid, like an LED sign
//   halftone  round dots sized by the logo's tone, trimmed to its outline
//   dither    an ordered (Bayer) dither of the logo's tone, trimmed to its outline
//
// Pick the mode with data-mode on the canvas, or ?bg=matrix / halftone / dither in the address.
// Without WebGL the canvas stays empty and style.css's tiled logo.png shows instead.
// The eyes drift, except on the scan screen, where they hold still so the camera and the
// person detector have the GPU to themselves.

(() => {
  const canvas = document.getElementById('pageBg');
  if (!canvas) return;

  const SETTINGS = {
    tile: 240,       // CSS px; the logo repeats every tile, a second copy offset by half
    matrixTile: 400, // CSS px; matrix mode needs bigger tiles for its dots to stand apart
    columns: 80,     // matrix: dots across the eye; fewer than ~50 and the clef blurs
    pitch: 5,        // halftone: CSS px between dot centres
    angle: 45,       // halftone: screen angle in degrees
    pixel: 1,        // dither: CSS px per dither pixel
    opacity: 0.14,   // how strongly the dots show against the page
    speed: 12,       // CSS px per second each diagonal row of eyes drifts; 0 to stand still
  };
  const mode = new URLSearchParams(location.search).get('bg') || canvas.dataset.mode || 'dither';
  const MODES = { halftone: 0, dither: 1, matrix: 2 };

  // Where the eye sits in logo.svg's square, in fractions of it (centre and half-size),
  // so the tone can fade from the middle of the eye out to its corners.
  const EYE = { cx: 0.530, cy: 0.490, rx: 0.273, ry: 0.161 };

  const TEX = 1024; // texture size for one tile

  const VERT = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

  const FRAG = `#version 300 es
precision highp float;
uniform sampler2D uTex;
uniform vec2 uRes;      // canvas size, device px
uniform float uTile;    // device px
uniform float uPitch;   // device px
uniform float uAngle;   // radians
uniform float uPixel;   // device px
uniform float uOpacity;
uniform int uMode;      // 0 halftone, 1 dither, 2 matrix
uniform vec4 uEye;      // cx, cy, rx, ry in tile units
uniform float uGrid;    // matrix: dots per tile (even, so the offset copy lands on the grid)
uniform float uShift;   // how far the rows have drifted, in tile units (wraps every half tile)
out vec4 outColor;

// The eyes sit in diagonal rows running top-left to bottom-right, both logo copies sharing
// each row. Slide every row along itself, alternating direction from one row to the next.
// Rows never cross, and the pattern repeats every half tile along a row, so it loops cleanly.
vec2 flow(vec2 uv) {
  float row = round(uv.x - uv.y - (uEye.x - uEye.y));
  float dir = mod(row, 2.0) < 0.5 ? 1.0 : -1.0;
  return uv - dir * uShift;
}

// Texture level of detail for averaging the logo over a cell of the given size.
float lodFor(float px) { return log2(max(px * ${TEX}.0 / uTile, 1.0)); }

// Tone (0..1) at a screen point: the logo averaged over a cell, faded toward the eye's
// corners. There are two logo lattices, one offset by half a tile, so use the nearer eye.
float tone(vec2 p, float cell) {
  vec2 uv = flow(p / uTile);
  float logo = textureLod(uTex, uv, lodFor(cell) + 0.5).a;
  vec2 f = fract(uv) - uEye.xy;
  vec2 a = f - round(f);
  vec2 b = (f + 0.5) - round(f + 0.5);
  float t = min(length(a / uEye.zw), length(b / uEye.zw));
  float fall = max(0.12, 1.0 - 0.85 * pow(t, 1.6));
  return logo * fall;
}

// The logo's own crisp edge at screen resolution, so fine detail like the clef survives.
float shape(vec2 p) { return textureLod(uTex, flow(p / uTile), lodFor(1.0)).a; }

float bayer8(ivec2 c) {
  int x = c.x & 7, y = c.y & 7, xr = x ^ y;
  int v = ((x & 1) << 5) | ((xr & 1) << 4) | ((x & 2) << 2) | ((xr & 2) << 1) | ((x & 4) >> 1) | ((xr & 4) >> 2);
  return (float(v) + 0.5) / 64.0;
}

void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y); // top-left origin, like CSS
  float cov = 0.0;

  if (uMode == 2) {
    // A grid fixed to the logo, starting at the eye's top-left corner. Each dot is lit
    // whole if its centre falls on the logo, so the shape is made of dots, not cut out.
    vec2 origin = uEye.xy - uEye.zw;
    vec2 g = (flow(p / uTile) - origin) * uGrid;
    vec2 k = round(g);
    float lit = step(0.5, textureLod(uTex, origin + k / uGrid, 0.0).a);
    float pitch = uTile / uGrid;
    float d = length(g - k) * pitch;
    outColor = vec4(lit * clamp(pitch * 0.4 - d + 0.5, 0.0, 1.0) * uOpacity);
    return;
  }

  if (uMode == 0) {
    mat2 rot = mat2(cos(uAngle), sin(uAngle), -sin(uAngle), cos(uAngle));
    vec2 r = rot * p / uPitch;
    vec2 cell = floor(r);
    // Dots grow past their cell in bright areas, so check the neighbours too.
    for (int j = -1; j <= 1; j++) {
      for (int i = -1; i <= 1; i++) {
        vec2 c = cell + vec2(i, j) + 0.5;
        vec2 centre = transpose(rot) * (c * uPitch);
        float radius = uPitch * 0.62 * sqrt(tone(centre, uPitch));
        float d = length(r - c) * uPitch;
        cov = max(cov, clamp(radius - d + 0.5, 0.0, 1.0));
      }
    }
  } else {
    ivec2 c = ivec2(floor(p / uPixel));
    vec2 centre = (vec2(c) + 0.5) * uPixel;
    cov = step(bayer8(c), tone(centre, uPixel));
  }

  float a = cov * shape(p) * uOpacity;
  outColor = vec4(a, a, a, a); // white, premultiplied
}`;

  let gl, program, uniforms, ready = false;

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }

  // One tile of the pattern: the logo, plus the copy offset by half a tile wrapping round
  // the corners, exactly like the two offset CSS background layers.
  function tileImage(logo) {
    const c = document.createElement('canvas');
    c.width = c.height = TEX;
    const ctx = c.getContext('2d');
    ctx.drawImage(logo, 0, 0, TEX, TEX);
    for (const [x, y] of [[0.5, 0.5], [-0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]]) {
      ctx.drawImage(logo, x * TEX, y * TEX, TEX, TEX);
    }
    return c;
  }

  function init(logo) {
    gl = canvas.getContext('webgl2', { premultipliedAlpha: true, antialias: false });
    if (!gl) return;

    program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);

    // One triangle that covers the whole screen.
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(program, 'aPos');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, tileImage(logo));
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

    uniforms = {};
    for (const name of ['uRes', 'uTile', 'uPitch', 'uAngle', 'uPixel', 'uOpacity', 'uMode', 'uEye', 'uGrid', 'uShift']) {
      uniforms[name] = gl.getUniformLocation(program, name);
    }
    ready = true;
    sized = '';
    document.body.classList.add('has-shader');
    start();
  }

  // Sets the canvas and the uniforms that only change with the window. Returns false before
  // the canvas has a size, since there's nothing to draw into.
  let sized = '';
  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(canvas.clientWidth * dpr);
    const h = Math.round(canvas.clientHeight * dpr);
    if (!w || !h) return false;
    if (sized === `${w}x${h}x${dpr}`) return true;
    sized = `${w}x${h}x${dpr}`;
    canvas.width = w;
    canvas.height = h;
    gl.viewport(0, 0, w, h);
    gl.uniform2f(uniforms.uRes, w, h);
    const tile = mode === 'matrix' ? SETTINGS.matrixTile : SETTINGS.tile;
    gl.uniform1f(uniforms.uTile, tile * dpr);
    gl.uniform1f(uniforms.uGrid, 2 * Math.round(SETTINGS.columns / (4 * EYE.rx)));
    gl.uniform1f(uniforms.uPitch, SETTINGS.pitch * dpr);
    gl.uniform1f(uniforms.uAngle, SETTINGS.angle * Math.PI / 180);
    gl.uniform1f(uniforms.uPixel, Math.max(1, Math.round(SETTINGS.pixel * dpr)));
    gl.uniform1f(uniforms.uOpacity, SETTINGS.opacity);
    gl.uniform1i(uniforms.uMode, MODES[mode] ?? MODES.dither);
    gl.uniform4f(uniforms.uEye, EYE.cx, EYE.cy, EYE.rx, EYE.ry);
    return true;
  }

  const still = matchMedia('(prefers-reduced-motion: reduce)');
  const moving = () => !still.matches && SETTINGS.speed && location.hash !== '#scan';

  // Each row moves along its diagonal, so each axis gets speed / sqrt(2). `elapsed` only
  // counts time spent moving, so the eyes pick up where they stopped rather than jumping.
  function shift(elapsed) {
    const tile = mode === 'matrix' ? SETTINGS.matrixTile : SETTINGS.tile;
    return (elapsed / 1000 * SETTINGS.speed / Math.SQRT2 / tile) % 0.5;
  }

  function draw(elapsed) {
    gl.uniform1f(uniforms.uShift, shift(elapsed));
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  // Animates while the eyes are moving. Otherwise (on the scan screen, with reduced motion,
  // or a speed of 0) it draws one still frame and stops, and a resize, a change of screen
  // or a change of motion setting starts it again.
  let frame = 0, elapsed = 0, last = null;
  function tick(now) {
    frame = 0;
    if (!ready || !resize()) return;
    const move = moving();
    if (move && last !== null) elapsed += now - last;
    last = move ? now : null;
    draw(elapsed);
    if (move) frame = requestAnimationFrame(tick);
  }
  function start() {
    if (!frame) frame = requestAnimationFrame(tick);
  }

  new ResizeObserver(start).observe(canvas);
  still.addEventListener('change', start);
  window.addEventListener('hashchange', start);

  const logo = new Image();
  logo.onload = () => {
    try { init(logo); } catch (err) { console.warn('Background shader failed, using the CSS background.', err); }
  };
  logo.src = 'logo.svg';

  // If the GPU drops the context, fall back to CSS until it comes back, then rebuild.
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    ready = false;
    document.body.classList.remove('has-shader');
  });
  canvas.addEventListener('webglcontextrestored', () => {
    try { init(logo); } catch (err) { console.warn(err); }
  });
})();
