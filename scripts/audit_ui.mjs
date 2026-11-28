#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

const args = process.argv.slice(2);
if (args.length < 1 || args.includes('-h') || args.includes('--help')) {
  console.error('Usage: node scripts/audit_ui.mjs <url> [out_dir]');
  process.exit(args.length < 1 ? 2 : 0);
}

const targetUrl = args[0];
const outDir = args[1] ? path.resolve(args[1]) : null;

function findEdge() {
  const candidates = [
    process.env.EDGE_PATH,
    String.raw`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
    String.raw`C:\Program Files\Microsoft\Edge\Application\msedge.exe`,
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error('Microsoft Edge not found; set EDGE_PATH.');
}

function findAxe() {
  if (process.env.AXE_JS_PATH && fs.existsSync(process.env.AXE_JS_PATH)) {
    return process.env.AXE_JS_PATH;
  }
  const npmNpxCache = path.join(
    process.env.LOCALAPPDATA || '',
    'npm-cache',
    '_npx',
  );
  if (fs.existsSync(npmNpxCache)) {
    for (const entry of fs.readdirSync(npmNpxCache)) {
      const candidate = path.join(npmNpxCache, entry, 'node_modules', 'axe-core', 'axe.min.js');
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  throw new Error(
    'axe.min.js not found in npm _npx cache. Warm it with: npx -y @axe-core/cli --version',
  );
}

const EDGE_PATH = findEdge();
const AXE_PATH = findAxe();
const port = 9230 + (process.pid % 500);
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ekm-edge-audit-'));

const edge = spawn(
  EDGE_PATH,
  [
    '--headless=new',
    '--disable-gpu',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank',
  ],
  { stdio: 'ignore' },
);

async function getWsUrl() {
  for (let i = 0; i < 40; i++) {
    try {
      const resp = await fetch(`http://127.0.0.1:${port}/json/list`);
      const pages = await resp.json();
      const page = pages.find((p) => p.type === 'page');
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {}
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error('Edge CDP did not start in time.');
}

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}

const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

async function auditViewport(cdp, axeSrc, { name, width, height, mobile }) {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
  });
  await new Promise((r) => setTimeout(r, 350));

  const layout = await cdp.send('Runtime.evaluate', {
    returnByValue: true,
    expression: `({ vw: window.innerWidth, sw: document.documentElement.scrollWidth })`,
  });

  await cdp.send('Runtime.evaluate', { expression: axeSrc });
  const axe = await cdp.send('Runtime.evaluate', {
    awaitPromise: true,
    returnByValue: true,
    expression: `axe.run(document, { runOnly: { type: 'tag', values: ${JSON.stringify(AXE_TAGS)} } }).then(r => ({
      passes: r.passes.length,
      violations: r.violations.map(v => ({
        id: v.id,
        impact: v.impact,
        help: v.help,
        targets: v.nodes.map(n => n.target.join(' ')),
      }))
    }))`,
  });

  if (outDir) {
    fs.mkdirSync(outDir, { recursive: true });
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(
      path.join(outDir, `${name}_${width}.png`),
      Buffer.from(shot.data, 'base64'),
    );
  }

  return { name, width, height, ...layout.result.value, ...axe.result.value };
}

try {
  const wsUrl = await getWsUrl();
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve);
    ws.addEventListener('error', reject);
  });

  const cdp = new CDP(ws);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', { url: targetUrl });
  await new Promise((r) => setTimeout(r, 700));

  const axeSrc = fs.readFileSync(AXE_PATH, 'utf8');
  const mobileRes = await auditViewport(cdp, axeSrc, {
    name: 'mobile',
    width: 390,
    height: 844,
    mobile: true,
  });
  const desktopRes = await auditViewport(cdp, axeSrc, {
    name: 'desktop',
    width: 1440,
    height: 900,
    mobile: false,
  });

  ws.close();
  const results = [mobileRes, desktopRes];
  console.log(JSON.stringify(results, null, 2));

  const bad = results.some(
    (r) =>
      r.sw > r.vw ||
      r.violations.some((v) => v.impact === 'critical' || v.impact === 'serious'),
  );
  if (bad) process.exitCode = 1;
} finally {
  edge.kill();
  try {
    fs.rmSync(userDataDir, { recursive: true, force: true });
  } catch {}
}
