/* Facade — renders the MIT Green Building's 17x9 window grid onto a <canvas>.
 *
 * Usage:
 *   const f = new Facade(document.getElementById('c'), {reflection: true});
 *   f.draw(hexString);          // 153 * "rrggbb", row-major, row 0 = top
 *   f.draw(uint8Array);         // 459 bytes r,g,b,...
 *   f.cellAt(px, py) -> {r, c} | null   (for mouse input)
 *
 * Pure canvas 2D, no dependencies. Row 0 is the top of the tower.
 */
(function (global) {
  'use strict';
  const ROWS = 17, COLS = 9;

  function Facade(canvas, opts) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.opts = Object.assign({ reflection: true, stars: true, glow: 1.0, label: '', dome: true, sky: true }, opts || {});
    this.last = new Uint8Array(ROWS * COLS * 3);
    this.stars = [];
    const rnd = mulberry32(7);
    for (let i = 0; i < 90; i++) this.stars.push([rnd(), rnd() * 0.55, 0.4 + rnd() * 0.8]);
    this.resize();
    this._bg = null;
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  Facade.prototype.resize = function () {
    const c = this.canvas;
    const dpr = Math.min(2, global.devicePixelRatio || 1);
    const w = c.clientWidth || c.width, h = c.clientHeight || c.height;
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.W = w; this.H = h;
    // Building geometry: fit a tower of aspect ~0.46 (w/h) in the canvas.
    const usableH = this.opts.reflection ? h * 0.80 : h * 0.94;
    let bh = usableH * 0.92;
    let bw = bh * 0.46;
    if (bw > w * 0.9) { bw = w * 0.9; bh = bw / 0.46; }
    this.bw = bw; this.bh = bh;
    this.bx = (w - bw) / 2;
    this.by = (this.opts.reflection ? h * 0.80 : h * 0.94) - bh;
    // Window grid occupies the upper part; the base is the open pilotis level.
    const marginX = bw * 0.07, topPad = bh * 0.035, baseH = bh * 0.11;
    this.gx = this.bx + marginX; this.gw = bw - 2 * marginX;
    this.gy = this.by + topPad; this.gh = bh - topPad - baseH;
    this.cw = this.gw / COLS; this.ch = this.gh / ROWS;
    this.ww = this.cw * 0.70; this.wh = this.ch * 0.52; // window pane size within cell
    this._bg = null; // background needs re-render
  };

  Facade.prototype.cellAt = function (px, py) {
    const c = Math.floor((px - this.gx) / this.cw), r = Math.floor((py - this.gy) / this.ch);
    if (r < 0 || r >= ROWS || c < 0 || c >= COLS) return null;
    return { r: r, c: c, nr: (py - this.gy) / this.gh, nc: (px - this.gx) / this.gw };
  };

  Facade.prototype._drawBackground = function () {
    const ctx = this.ctx, W = this.W, H = this.H;
    const off = document.createElement('canvas');
    off.width = this.canvas.width; off.height = this.canvas.height;
    const o = off.getContext('2d');
    const dpr = this.canvas.width / W;
    o.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (this.opts.sky) {
      const sky = o.createLinearGradient(0, 0, 0, H);
      sky.addColorStop(0, '#05070f'); sky.addColorStop(0.55, '#0b1226'); sky.addColorStop(0.8, '#101a33'); sky.addColorStop(1, '#05070f');
      o.fillStyle = sky; o.fillRect(0, 0, W, H);
      if (this.opts.stars) {
        for (const s of this.stars) {
          o.fillStyle = 'rgba(255,255,255,' + (0.25 * s[2]).toFixed(3) + ')';
          o.fillRect(s[0] * W, s[1] * H, 1.2, 1.2);
        }
      }
    } else {
      o.clearRect(0, 0, W, H);
    }
    // ground / river line
    const groundY = this.by + this.bh;
    if (this.opts.reflection) {
      const river = o.createLinearGradient(0, groundY, 0, H);
      river.addColorStop(0, '#0a1020'); river.addColorStop(1, '#03050a');
      o.fillStyle = river; o.fillRect(0, groundY, W, H - groundY);
    }
    // tower body
    o.fillStyle = '#23262c';
    o.fillRect(this.bx, this.by, this.bw, this.bh);
    // subtle concrete texture: vertical mullions between columns
    o.fillStyle = 'rgba(255,255,255,0.035)';
    for (let c = 0; c <= COLS; c++) o.fillRect(this.gx + c * this.cw - 0.5, this.gy, 1, this.gh);
    // floor slabs
    o.fillStyle = 'rgba(0,0,0,0.25)';
    for (let r = 0; r <= ROWS; r++) o.fillRect(this.gx, this.gy + r * this.ch - 0.5, this.gw, 1);
    // top mechanical floor + radome
    o.fillStyle = '#1b1d22';
    o.fillRect(this.bx, this.by, this.bw, this.bh * 0.03);
    if (this.opts.dome) {
      const cx = this.bx + this.bw * 0.5, r = this.bw * 0.12;
      o.beginPath(); o.arc(cx, this.by, r, Math.PI, 0); o.closePath();
      o.fillStyle = '#2d3038'; o.fill();
    }
    // pilotis (open ground level columns)
    const baseY = this.gy + this.gh, baseH = this.by + this.bh - baseY;
    o.fillStyle = '#121418'; o.fillRect(this.bx, baseY, this.bw, baseH);
    o.fillStyle = '#2a2d33';
    for (let i = 0; i < 4; i++) o.fillRect(this.bx + this.bw * (0.12 + i * 0.253), baseY, this.bw * 0.05, baseH);
    // dark window panes (unlit)
    o.fillStyle = '#0d0f13';
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const x = this.gx + c * this.cw + (this.cw - this.ww) / 2, y = this.gy + r * this.ch + (this.ch - this.wh) / 2;
      o.fillRect(x, y, this.ww, this.wh);
    }
    if (this.opts.label) {
      o.fillStyle = 'rgba(255,255,255,0.35)'; o.font = '12px system-ui, sans-serif'; o.textAlign = 'center';
      o.fillText(this.opts.label, W / 2, H - 8);
    }
    this._bg = off;
  };

  Facade.prototype.draw = function (frame) {
    let px;
    if (typeof frame === 'string') {
      px = this.last;
      for (let i = 0; i < ROWS * COLS * 3; i++) px[i] = parseInt(frame.substr(i * 2, 2), 16);
    } else if (frame instanceof Uint8Array) { px = frame; this.last.set(px); }
    else { px = this.last; let k = 0; for (const p of frame) { px[k++] = p[0]; px[k++] = p[1]; px[k++] = p[2]; } }
    const ctx = this.ctx;
    if (!this._bg) this._drawBackground();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(this._bg, 0, 0);
    const dpr = this.canvas.width / this.W;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const glow = this.opts.glow;
    // Glow pass (additive-ish): soft radial halo for each lit window.
    ctx.globalCompositeOperation = 'lighter';
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const i = (r * COLS + c) * 3, R = px[i], G = px[i + 1], B = px[i + 2];
      const lum = (R * 0.3 + G * 0.59 + B * 0.11) / 255;
      if (lum < 0.02) continue;
      const cx = this.gx + c * this.cw + this.cw / 2, cy = this.gy + r * this.ch + this.ch / 2;
      const rad = Math.max(this.cw, this.ch) * (0.75 + 0.75 * lum) * glow;
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
      const a = (0.20 * lum).toFixed(3);
      g.addColorStop(0, 'rgba(' + R + ',' + G + ',' + B + ',' + a + ')');
      g.addColorStop(1, 'rgba(' + R + ',' + G + ',' + B + ',0)');
      ctx.fillStyle = g; ctx.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
    }
    ctx.globalCompositeOperation = 'source-over';
    // Window panes
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const i = (r * COLS + c) * 3, R = px[i], G = px[i + 1], B = px[i + 2];
      if (R + G + B < 6) continue;
      const x = this.gx + c * this.cw + (this.cw - this.ww) / 2, y = this.gy + r * this.ch + (this.ch - this.wh) / 2;
      ctx.fillStyle = 'rgb(' + R + ',' + G + ',' + B + ')';
      ctx.fillRect(x, y, this.ww, this.wh);
      // slight inner highlight so bright colours read as glass
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.fillRect(x, y, this.ww, this.wh * 0.3);
    }
    // Reflection in the Charles
    if (this.opts.reflection) {
      const groundY = this.by + this.bh;
      ctx.save();
      ctx.globalAlpha = 0.14;
      ctx.translate(0, groundY + groundY * 0.45);
      ctx.scale(1, -0.45);
      for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
        const i = (r * COLS + c) * 3, R = px[i], G = px[i + 1], B = px[i + 2];
        if (R + G + B < 24) continue;
        const x = this.gx + c * this.cw + (this.cw - this.ww) / 2, y = this.gy + r * this.ch + (this.ch - this.wh) / 2;
        ctx.fillStyle = 'rgb(' + R + ',' + G + ',' + B + ')';
        ctx.fillRect(x, y, this.ww, this.wh * 1.8);
      }
      ctx.restore();
    }
  };

  /* Player: replays a recording {rows, cols, fps, frames:[hex,...]} on a Facade. */
  function Player(facade, rec, opts) {
    this.f = facade; this.rec = rec; this.i = 0; this.playing = false; this.t0 = 0;
    this.opts = Object.assign({ loop: true, speed: 1 }, opts || {});
    this.onframe = null;
  }
  Player.prototype.play = function () {
    if (this.playing) return; this.playing = true; this.t0 = performance.now() - this.i * 1000 / this.rec.fps / this.opts.speed;
    const step = () => {
      if (!this.playing) return;
      const idx = Math.floor((performance.now() - this.t0) / 1000 * this.rec.fps * this.opts.speed);
      if (idx >= this.rec.frames.length) {
        if (this.opts.loop) { this.i = 0; this.t0 = performance.now(); }
        else { this.playing = false; return; }
      } else if (idx !== this.i) {
        this.i = idx; this.f.draw(this.rec.frames[this.i]);
        if (this.onframe) this.onframe(this.i);
      }
      requestAnimationFrame(step);
    };
    this.f.draw(this.rec.frames[this.i]);
    requestAnimationFrame(step);
  };
  Player.prototype.pause = function () { this.playing = false; };
  Player.prototype.seek = function (i) { this.i = Math.max(0, Math.min(this.rec.frames.length - 1, i)); this.t0 = performance.now() - this.i * 1000 / this.rec.fps / this.opts.speed; this.f.draw(this.rec.frames[this.i]); };

  global.Facade = Facade; global.FacadePlayer = Player;
})(typeof window !== 'undefined' ? window : this);
