/* Browser smoke checks with installed Chrome; no npm dependencies.
 * Run: node --experimental-websocket website/scripts/test_browser.mjs
 * Screenshots and a machine-readable verdict go to website/preview/.
 */
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, readFile, writeFile, stat, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(site, 'preview');
const profile = await mkdtemp(path.join(tmpdir(), 'segmentsnap-browser-'));
const prefix = '/review/segment-snap/';
const checks = [];
const browserErrors = [];
let browser, socket;

const check = (condition, name, details = null) => {
  checks.push({ name, passed: Boolean(condition), details });
  if (!condition) throw new Error(`${name}: ${JSON.stringify(details)}`);
};
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// An ephemeral nested-path server tests portability to a personal GitHub subpath.
const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png', '.svg': 'image/svg+xml', '.pdf': 'application/pdf', '.bib': 'text/plain; charset=utf-8' };
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (!pathname.startsWith(prefix)) { response.writeHead(404).end(); return; }
    const relative = decodeURIComponent(pathname.slice(prefix.length)) || 'index.html';
    const target = path.resolve(site, relative);
    const extension = path.extname(target);
    if (!target.startsWith(site + path.sep) || !types[extension] || !(await stat(target)).isFile()) {
      response.writeHead(404).end(); return;
    }
    response.writeHead(200, { 'Content-Type': types[extension] });
    response.end(await readFile(target));
  } catch { response.writeHead(404).end(); }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}${prefix}`;
await mkdir(output, { recursive: true });

try {
  if (typeof WebSocket === 'undefined') throw new Error('Use node --experimental-websocket for Node 20.');
  const endpoint = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chrome startup timed out')), 15000);
    browser = spawn('/usr/bin/google-chrome', [
      '--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
      '--disable-background-networking', '--no-first-run', '--no-default-browser-check',
      '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
    ], { stdio: ['ignore', 'ignore', 'pipe'] });
    let stderr = '';
    browser.stderr.on('data', (chunk) => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
    browser.once('error', (error) => { clearTimeout(timer); reject(error); });
  });

  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let nextId = 0;
  const pending = new Map();
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject, timer } = pending.get(message.id);
      pending.delete(message.id); clearTimeout(timer);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
    }
    if (message.method === 'Runtime.exceptionThrown') browserErrors.push(message.params.exceptionDetails);
    if (message.method === 'Network.responseReceived' && message.params.response.status >= 400) {
      browserErrors.push({ url: message.params.response.url, status: message.params.response.status });
    }
  });
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out: ${method}`)); }, 15000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const page = (method, params = {}) => send(method, params, sessionId);
  await page('Page.enable');
  await page('Runtime.enable');
  await page('Network.enable');
  const evaluate = async (expression, extra = {}) => {
    const result = await page('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, ...extra });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const ready = async (url = base) => {
    await page('Page.navigate', { url });
    for (let i = 0; i < 60; i++) {
      if (await evaluate('document.readyState === "complete" && !!document.querySelector("#paper-title")')) break;
      await pause(100);
    }
    await evaluate(`Promise.all([...document.images].filter(img => img.hasAttribute('src')).map(img => {
      img.loading = 'eager'; return img.decode().catch(() => null);
    }))`);
    // The page may use one-time entrance animations. Wait for them before
    // inspecting layout or saving visual review artifacts; this is also safe
    // when reduced motion disables animations entirely.
    await evaluate(`Promise.race([
      Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => null))),
      new Promise(resolve => setTimeout(resolve, 1200))
    ])`);
    await pause(50);
  };
  const viewport = (width, height, mobile = false, scale = 1) => page('Emulation.setDeviceMetricsOverride', { width, height, mobile, deviceScaleFactor: scale });
  const screenshot = async (name, full = false) => {
    const layout = await page('Page.getLayoutMetrics');
    const box = layout.cssContentSize;
    const shot = await page('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: full,
      ...(full ? { clip: { x: 0, y: 0, width: box.width, height: box.height, scale: 1 } } : {}),
    });
    await writeFile(path.join(output, name), Buffer.from(shot.data, 'base64'));
  };

  await viewport(1440, 1000);
  await ready();
  check(await evaluate('document.title.includes("Segment–Snap")'), 'Page loads at a nested project path');
  check(await evaluate('[...document.images].filter(i => i.hasAttribute("src")).every(i => i.complete && i.naturalWidth > 0)'), 'All scientific figures and resource icons load');
  check(await evaluate('document.querySelectorAll("h1").length === 1'), 'One primary heading');
  check(await evaluate('document.querySelectorAll("[data-gallery-panel]:not([hidden])").length === 1'), 'Gallery starts with one selected category');
  check(await evaluate(`document.querySelector('link[rel="canonical"]').href === 'https://hyokong.github.io/segment-snap-page/' && document.querySelector('meta[property="og:url"]').content === 'https://hyokong.github.io/segment-snap-page/'`), 'Canonical and sharing metadata use the project URL');
  check(await evaluate(`['.hero-actions', '.resource-links'].every(selector => {
    const links = [...document.querySelector(selector).querySelectorAll('a[data-resource]')];
    return links.length === 3 && !links.some(link => link.dataset.resource === 'project') && links.every(link => {
      const icon = link.querySelector('img.resource-icon');
      return icon?.complete && icon.naturalWidth > 0 && icon.alt === '' && icon.getAttribute('aria-hidden') === 'true' && link.textContent.trim().length >= 4;
    });
  })`), 'Paper, Code, and Hugging Face have loaded icons and labels, without a project self-link');
  check(await evaluate(`(() => {
    const citation = document.querySelector('#bibtex').textContent;
    return citation.startsWith('@article{kong2026segmentsnap,') &&
      citation.includes('https://arxiv.org/abs/2609.25247') &&
      citation.includes('journal = {arXiv preprint arXiv:2609.25247}');
  })()`), 'Copyable citation uses article format with the verified arXiv identifier');
  check(await evaluate(`[...document.querySelectorAll('.nav-paper, [data-resource="paper"]')].every(link => link.href === 'https://arxiv.org/abs/2609.25247') && document.querySelector('.evidence-details .text-link').href === 'https://arxiv.org/pdf/2609.25247#page=13'`), 'All public Paper buttons and the controls link point to arXiv');
  const citationResponse = await fetch(base + 'assets/citation.bib');
  const citationText = await citationResponse.text();
  check(citationResponse.ok && citationText.trim() === await evaluate('document.querySelector("#bibtex").textContent.trim()') &&
    await evaluate(`document.querySelector('a[href="assets/citation.bib"]').hasAttribute('download')`),
    'Downloadable BibTeX matches the displayed and copyable citation');
  check(await evaluate(`(() => {
    const award = document.querySelector('.award-link');
    return document.querySelectorAll('.award-link').length === 1 &&
      award.href === 'https://art3d-challenge.mooo.com/web/challenges/challenge-page/1/leaderboard/' &&
      award.textContent.includes('1st place') && award.textContent.includes('Articulate3D Challenge') &&
      award.getAttribute('aria-describedby') === 'award-scope' &&
      document.querySelector('#award-scope').textContent.includes('both evaluated outputs') &&
      document.querySelector('#award-scope a').getAttribute('href') === '#challenge';
  })()`), 'Winner callout names the achievement, links to its evidence, and states its scope');
  check(await evaluate(`(() => {
    const luminance = color => {
      const channels = color.match(/[\\d.]+/g).slice(0, 3).map(value => Number(value) / 255)
        .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
      return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
    };
    const contrast = (foreground, background) => {
      const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
      return (values[0] + .05) / (values[1] + .05);
    };
    const surface = getComputedStyle(document.querySelector('.award-link')).backgroundColor;
    return ['.award-rank', '.award-name'].every(selector =>
      contrast(getComputedStyle(document.querySelector(selector)).color, surface) >= 4.5);
  })()`), 'Winner callout text meets 4.5:1 contrast on its warm background');
  await screenshot('desktop.png');
  await screenshot('desktop-full.png', true);
  for (const id of ['method', 'results', 'qualitative', 'citation']) {
    const region = await evaluate(`(() => {
      const box = document.getElementById('${id}').getBoundingClientRect();
      return { x: 0, y: box.top + scrollY, width: document.documentElement.clientWidth,
               height: Math.min(box.height, 1400), scale: 1 };
    })()`);
    const shot = await page('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: region });
    await writeFile(path.join(output, `${id}.png`), Buffer.from(shot.data, 'base64'));
  }

  // A text Range, rather than the heading box, reports actual rendered line
  // fragments and catches a CSS wrap even when the overall h1 still fits.
  for (const width of [1440, 1024, 820, 768]) {
    await viewport(width, 1000);
    await pause(50);
    const titleLayout = await evaluate(`(() => {
      const title = document.querySelector('#paper-title .title-main');
      const range = document.createRange();
      range.selectNodeContents(title);
      const lines = [...range.getClientRects()].filter(rect => rect.width > 0.5);
      const box = title.getBoundingClientRect();
      return { lines: lines.length, left: box.left, right: box.right, viewport: innerWidth,
        text: title.textContent.trim(), forcedBreaks: title.querySelectorAll('br').length };
    })()`);
    check(titleLayout.text === 'Geometric and Semantic Coupling' && titleLayout.forcedBreaks === 0 &&
      titleLayout.lines === 1 && titleLayout.left >= 0 && titleLayout.right <= titleLayout.viewport,
    `Main title is one unforced line at ${width}px`, titleLayout);
  }
  await viewport(1440, 1000);

  const screenshotSection = async (id, name) => {
    const region = await evaluate(`(() => {
      const box = document.getElementById('${id}').getBoundingClientRect();
      return { x: 0, y: box.top + scrollY, width: document.documentElement.clientWidth,
               height: Math.min(box.height, 1400), scale: 1 };
    })()`);
    const shot = await page('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: region });
    await writeFile(path.join(output, name), Buffer.from(shot.data, 'base64'));
  };

  const inspectVisiblePngs = () => evaluate(`(() => [...document.images]
    .filter(image => image.getAttribute('src')?.endsWith('.png'))
    .map(image => {
      const box = image.getBoundingClientRect();
      const source = image.getAttribute('src');
      return { source, width: box.width, height: box.height, naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight, dpr: devicePixelRatio,
        visible: box.width > 0.5 && box.height > 0.5,
        adequate: image.naturalWidth >= box.width * devicePixelRatio && image.naturalHeight >= box.height * devicePixelRatio };
    }).filter(image => image.visible))()`);
  const capturePngDensity = async (dpr, samples) => {
    const rendered = await inspectVisiblePngs();
    check(rendered.every(image => image.dpr === dpr && image.adequate),
      `Visible PNG figures have enough physical pixels at DPR ${dpr}`, rendered);
    rendered.forEach((image) => samples.set(image.source, image));
  };
  const verifyDialogSource = async (extension) => {
    const state = await evaluate(`(async () => {
      const link = [...document.querySelectorAll('a[data-lightbox]')]
        .find(candidate => candidate.getAttribute('href')?.endsWith('${extension}') && candidate.getClientRects().length);
      if (!link) return null;
      link.click();
      const image = document.querySelector('#dialog-image');
      const original = document.querySelector('#dialog-original');
      await image.decode();
      const bounds = image.getBoundingClientRect();
      return { href: link.href, image: image.src, original: original.href, complete: image.complete,
        naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
        requiredWidth: bounds.width * devicePixelRatio, requiredHeight: bounds.height * devicePixelRatio };
    })()`);
    check(state?.href === state?.image && state?.href === state?.original && state.complete &&
      state.naturalWidth > 0 && state.naturalHeight > 0,
    `Dialog loads the highest-resolution ${extension} source, not a thumbnail`, state);
    if (extension === '.png') {
      check(state.naturalWidth >= state.requiredWidth && state.naturalHeight >= state.requiredHeight,
        'Expanded qualitative figure supplies native pixels at DPR 2', state);
    }
    await screenshot(`dialog-${extension === '.svg' ? 'vector' : 'result'}-2x.png`);
    await evaluate('document.querySelector("#image-dialog").close()');
  };

  const comparison = '[data-comparison]';
  check(await evaluate(`!!document.querySelector('#gallery-motion ${comparison}')`), 'Motion gallery includes a before/after comparison');
  check(await evaluate(`document.querySelectorAll('#gallery-motion ${comparison} img').length === 2`), 'Comparison retains both source images');
  check(await evaluate(`(() => {
    const node = document.querySelector('#gallery-motion ${comparison}');
    const before = node.querySelector('[data-compare-set="before"]');
    const after = node.querySelector('[data-compare-set="after"]');
    const status = node.querySelector('[data-compare-status]');
    return node.classList.contains('is-interactive') && node.dataset.view === 'after' &&
      before?.getAttribute('aria-pressed') === 'false' && after?.getAttribute('aria-pressed') === 'true' &&
      status?.getAttribute('aria-live') === 'polite' && status.textContent.trim() === 'Handle-guided origin · 0.05 m error' &&
      node.querySelector('figure[data-compare-view="before"]').hidden && !node.querySelector('figure[data-compare-view="after"]').hidden &&
      getComputedStyle(node).clipPath === 'none';
  })()`), 'Comparison defaults to the full handle-guided image without a spatial crop');
  const comparisonState = (view) => evaluate(`(() => {
    const node = document.querySelector('#gallery-motion ${comparison}');
    const isBefore = '${view}' === 'before';
    const button = node.querySelector('[data-compare-set="${view}"]');
    const other = node.querySelector('[data-compare-set="${view === 'before' ? 'after' : 'before'}"]');
    const expectedStatus = isBefore ? 'Centroid origin · 0.42 m error' : 'Handle-guided origin · 0.05 m error';
    return node.dataset.view === '${view}' && button.getAttribute('aria-pressed') === 'true' &&
      other.getAttribute('aria-pressed') === 'false' && !node.querySelector('figure[data-compare-view="${view}"]').hidden &&
      node.querySelector('figure[data-compare-view="${view === 'before' ? 'after' : 'before'}"]').hidden &&
      node.querySelector('[data-compare-status]').textContent.trim() === expectedStatus;
  })()`);
  await evaluate(`document.querySelector('#gallery-motion [data-compare-set="before"]').click()`);
  check(await comparisonState('before'), 'Comparison before button shows the complete centroid-origin image');
  await evaluate(`document.querySelector('#gallery-motion [data-compare-set="after"]').click()`);
  check(await comparisonState('after'), 'Comparison handle-guided button shows the complete handle-guided image');
  await evaluate(`document.querySelector('#gallery-motion [data-compare-set="after"]').focus()`);
  await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowLeft', code: 'ArrowLeft', windowsVirtualKeyCode: 37 });
  check(await comparisonState('before') && await evaluate('document.activeElement.matches("[data-compare-set=before]")'), 'Comparison supports ArrowLeft and focuses the centroid-origin state');
  await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Home', code: 'Home', windowsVirtualKeyCode: 36 });
  check(await comparisonState('before') && await evaluate('document.activeElement.matches("[data-compare-set=before]")'), 'Comparison supports Home for the centroid-origin state');
  await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
  check(await comparisonState('after') && await evaluate('document.activeElement.matches("[data-compare-set=after]")'), 'Comparison supports ArrowRight and focuses the handle-guided state');
  await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'End', code: 'End', windowsVirtualKeyCode: 35 });
  check(await comparisonState('after') && await evaluate('document.activeElement.matches("[data-compare-set=after]")'), 'Comparison supports End for the handle-guided state');
  await evaluate('document.activeElement.blur()');
  await screenshotSection('gallery-motion', 'hinge-comparison.png');

  check(await evaluate(`(() => ['https://github.com/HyoKong/Segment-Snap', 'https://huggingface.co/imsuperkong/Segment-Snap'].every(url => [...document.querySelectorAll('a')].some(link => link.href === url)))()`), 'Code and checkpoint links use their exact URLs');

  await evaluate('document.querySelector("#tab-motion").focus()');
  await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
  check(await evaluate('document.activeElement.id === "tab-handles" && !document.querySelector("#gallery-handles").hidden'), 'Gallery supports keyboard arrow navigation');
  await screenshotSection('gallery-handles', 'gallery-handles.png');
  await evaluate('document.querySelector("#tab-limits").click()');
  check(await evaluate('!document.querySelector("#gallery-limits").hidden && document.querySelector("#tab-limits").getAttribute("aria-selected") === "true"'), 'Failure category is available');
  await screenshotSection('gallery-limits', 'gallery-limits.png');
  for (const [name, legends] of [
    ['motion', ['motion-legend']],
    ['handles', ['recovery-legend', 'context-legend']],
    ['limits', ['axis-legend', 'extent-legend']],
  ]) {
    await evaluate(`document.querySelector('#tab-${name}').click()`);
    check(await evaluate(`(() => {
      const panel = document.querySelector('#gallery-${name}');
      const intro = panel.querySelector('.gallery-intro');
      const legends = ${JSON.stringify(legends)}.map(id => document.getElementById(id));
      return !panel.hidden && !!intro && intro.querySelector('h3')?.textContent.trim().length >= 8 &&
        intro.querySelector('p')?.textContent.trim().length >= 40 && legends.every(legend =>
          legend && legend.getClientRects().length > 0 && getComputedStyle(legend).display !== 'none');
    })()`), `Active ${name} gallery explains its purpose and visible figure legends`);
  }
  await evaluate('document.querySelector("#tab-limits").click()');
  await evaluate('document.querySelector("#gallery-limits [data-lightbox]").click()');
  check(await evaluate('document.querySelector("#image-dialog").open && document.activeElement.classList.contains("dialog-close")'), 'Image dialog opens with keyboard focus');
  await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await pause(50);
  check(await evaluate('!document.querySelector("#image-dialog").open && document.activeElement === document.querySelector("#gallery-limits [data-lightbox]")'), 'Escape closes the dialog and restores focus');

  // Save review artifacts at physical DPR 2 and prove that every visible PNG
  // has at least one native source pixel per device pixel. SVG diagrams are
  // checked as vector resources by the static validator below.
  await viewport(1440, 1000, false, 2);
  await pause(50);
  check(await evaluate('devicePixelRatio === 2'), 'Desktop high-density capture uses DPR 2');
  await evaluate('scrollTo(0, 0)');
  await screenshot('desktop-2x.png');
  await screenshotSection('method', 'method-2x.png');
  await screenshotSection('qualitative', 'qualitative-2x.png');
  check(await evaluate(`['assets/teaser.svg', 'assets/pipeline.svg'].every(source => {
    const image = [...document.images].find(candidate => candidate.getAttribute('src') === source);
    return image?.currentSrc.endsWith(source) && image.complete && image.naturalWidth > 0;
  })`), 'Method diagrams load source-native SVG resources');
  const desktopPngSamples = new Map();
  await evaluate('document.querySelector("#tab-motion").click(); document.querySelector("[data-compare-set=after]").click()');
  await capturePngDensity(2, desktopPngSamples);
  await evaluate('document.querySelector("[data-compare-set=before]").click()');
  await capturePngDensity(2, desktopPngSamples);
  for (const panel of ['handles', 'limits']) {
    await evaluate(`document.querySelector('#tab-${panel}').click()`);
    await capturePngDensity(2, desktopPngSamples);
  }
  check(new Set(desktopPngSamples.keys()).size === 6,
    'All six qualitative PNG sources meet their DPR-2 display requirements', [...desktopPngSamples.values()]);
  await verifyDialogSource('.svg');
  await evaluate('document.querySelector("#tab-handles").click()');
  await verifyDialogSource('.png');

  await send('Browser.grantPermissions', { origin: new URL(base).origin, permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite'] });
  await evaluate('document.querySelector("[data-copy-citation]").click()', { userGesture: true });
  await pause(100);
  check(await evaluate('document.querySelector("#copy-status").textContent === "Citation copied."'), 'Citation copy reports success');
  check(await evaluate('navigator.clipboard.readText().then(text => text === document.querySelector("#bibtex").textContent)', { userGesture: true }), 'Copied citation matches displayed BibTeX');
  await evaluate('Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true }); document.querySelector("[data-copy-citation]").click()');
  check(await evaluate('document.querySelector("#copy-status").textContent.includes("selected") && getSelection().toString().includes("kong2026segmentsnap")'), 'Clipboard-unavailable fallback selects the citation');

  await ready();
  for (const [width, height, mobile] of [[1440, 1000, false], [820, 1180, false], [390, 844, true], [320, 740, true]]) {
    await viewport(width, height, mobile);
    await evaluate('scrollTo(0, 0)');
    await pause(100);
    check(await evaluate(`(() => {
      const group = document.querySelector('.hero-actions');
      const [paper, code, huggingface] = [...group.querySelectorAll('a')].map(link => link.getBoundingClientRect());
      const same = (first, second) => Math.abs(first - second) < 1;
      if (${width} <= 390) {
        return same(paper.width, group.getBoundingClientRect().width) &&
          paper.bottom <= code.top && same(code.top, huggingface.top) &&
          same(code.width, huggingface.width) && code.right <= huggingface.left &&
          [paper, code, huggingface].every(box => box.height >= 44);
      }
      return same(paper.top, code.top) && same(code.top, huggingface.top) &&
        paper.right <= code.left && code.right <= huggingface.left;
    })()`), `Resource buttons align without overlaps at ${width}px`);
    check(await evaluate(`(() => {
      const award = document.querySelector('.award-link').getBoundingClientRect();
      const recognition = document.querySelector('.hero-recognition').getBoundingClientRect();
      const title = document.querySelector('#paper-title').getBoundingClientRect();
      const header = document.querySelector('.site-header').getBoundingClientRect();
      return award.top >= header.bottom && recognition.bottom < innerHeight &&
        recognition.bottom <= title.top && award.left >= 0 && award.right <= innerWidth &&
        award.height >= 44 && parseFloat(getComputedStyle(document.querySelector('.award-rank')).fontSize) >= 18;
    })()`), `First place is readable above the title and visible without scrolling at ${width}px`);
    const selectedPanels = width <= 390 ? ['motion', 'handles', 'limits'] : ['motion'];
    for (const selected of selectedPanels) {
      await evaluate(`document.querySelector('#tab-${selected}').click()`);
      await pause(25);
      const sizes = await evaluate('({ content: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth })');
      if (sizes.content > sizes.viewport) {
        sizes.overflowingElements = await evaluate(`[...document.body.querySelectorAll('*')].map(element => {
          const box = element.getBoundingClientRect();
          return { tag: element.tagName, class: element.className, left: box.left, right: box.right };
        }).filter(box => box.right > document.documentElement.clientWidth || box.left < 0).slice(0, 20)`);
      }
      check(sizes.content <= sizes.viewport, `No horizontal page overflow at ${width}px (${selected} gallery)`, sizes);
    }
    // Keep mobile review captures on the default hinge example, rather than
    // whichever category was last inspected for overflow.
    await evaluate('document.querySelector("#tab-motion").click()');
    if (width === 390) {
      await screenshotSection('qualitative', 'mobile-qualitative.png');
      await evaluate('scrollTo(0, 0)');
      await screenshot('mobile.png');
      await screenshot('mobile-full.png', true);
      await viewport(390, 844, true, 3);
      await pause(50);
      check(await evaluate('devicePixelRatio === 3'), 'Mobile high-density capture uses DPR 3');
      const mobilePngSamples = new Map();
      await evaluate('document.querySelector("#tab-motion").click(); document.querySelector("[data-compare-set=after]").click()');
      await capturePngDensity(3, mobilePngSamples);
      await evaluate('document.querySelector("[data-compare-set=before]").click()');
      await capturePngDensity(3, mobilePngSamples);
      for (const panel of ['handles', 'limits']) {
        await evaluate(`document.querySelector('#tab-${panel}').click()`);
        await capturePngDensity(3, mobilePngSamples);
      }
      check(new Set(mobilePngSamples.keys()).size === 6,
        'All six qualitative PNG sources meet their DPR-3 display requirements', [...mobilePngSamples.values()]);
      await evaluate('document.querySelector("#tab-motion").click(); scrollTo(0, 0)');
      await screenshot('mobile-3x.png');
    }
    if (width === 820) await screenshot('tablet.png');
  }
  await viewport(720, 600, false, 2);
  check(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), 'Layout reflows at a 200%-scale equivalent viewport');
  await page('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  check(await evaluate('getComputedStyle(document.documentElement).scrollBehavior === "auto"'), 'Reduced-motion preference disables smooth scrolling');

  await viewport(1440, 1000);
  await page('Emulation.setScriptExecutionDisabled', { value: true });
  await ready();
  check(await evaluate('document.querySelector(".award-link").getBoundingClientRect().height >= 44 && document.querySelector(".hero-recognition").getBoundingClientRect().bottom < innerHeight'), 'First-place recognition stays visible without JavaScript');
  check(await evaluate('[...document.querySelectorAll("[data-gallery-panel]")].every(p => !p.hidden)'), 'All gallery content remains available without JavaScript');
  check(await evaluate(`document.querySelector('[data-gallery-tabs]').hidden && document.querySelector('[data-copy-citation]').hidden && document.querySelector('[data-compare-controls]').hidden`), 'Nonfunctional enhancement controls stay hidden without JavaScript');
  check(await evaluate(`(() => { const comparison = document.querySelector('#gallery-motion ${comparison}'); const figures = [...comparison.querySelectorAll('figure[data-compare-view]')]; return !comparison.classList.contains('is-interactive') && !comparison.dataset.view && figures.length === 2 && figures.every(figure => !figure.hidden) && [...comparison.querySelectorAll('img')].every(image => image.complete && image.naturalWidth > 0); })()`), 'Comparison falls back to both complete source images without JavaScript');
  await page('Emulation.setScriptExecutionDisabled', { value: false });
  await ready(`file://${path.join(site, 'index.html')}`);
  check(await evaluate('[...document.images].filter(i => i.hasAttribute("src")).every(i => i.complete && i.naturalWidth > 0)'), 'Direct file preview loads local figures without a server');
  check(browserErrors.length === 0, 'No browser exceptions or failed HTTP resources', browserErrors);
  const paper = await fetch(base + 'assets/paper.pdf');
  check(paper.ok && Buffer.from(await paper.arrayBuffer()).subarray(0, 5).toString() === '%PDF-', 'Offline review PDF remains available as a valid local asset');

  // Preview the README's actual HTML asset blocks with GitHub-like image sizing.
  // This checks our local assets, not GitHub's production Markdown renderer.
  const repository = path.resolve(site, '..', 'opensource');
  const readme = await readFile(path.join(repository, 'README.md'), 'utf8');
  const readmeAssets = [...readme.matchAll(/<p align="center">[\s\S]*?<\/p>/g)].map(match => match[0]).join('\n');
  const { frameTree } = await page('Page.getFrameTree');
  await page('Page.setDocumentContent', {
    frameId: frameTree.frame.id,
    html: `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
      <base href="file://${repository}/"><style>
      * { box-sizing: border-box; } body { margin: 0; color: #1f2328; font: 16px/1.5 Arial, sans-serif; }
      main { max-width: 1012px; margin: 24px auto; padding: 24px; border: 1px solid #d1d9e0; border-radius: 6px; }
      h1 { margin: 0 0 16px; padding-bottom: 8px; font-size: 32px; border-bottom: 1px solid #d1d9e0; }
      img { max-width: 100%; height: auto; vertical-align: middle; } p { margin: 16px 0; }
      </style></head><body><main><h1>Segment–Snap</h1>
      <p><strong>Geometric and Semantic Coupling for Interaction Understanding in 3D Scenes</strong></p>
      ${readmeAssets}</main></body></html>`,
  });
  await evaluate('Promise.all([...document.images].map(image => image.decode()))');
  check(await evaluate('document.images.length === 4 && [...document.images].every(image => image.complete && image.naturalWidth > 0)'), 'README paper/project/Hugging Face buttons and vector teaser render locally');
  for (const width of [1000, 390, 320]) {
    await viewport(width, 820, width < 700);
    check(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), `README asset preview fits at ${width}px`);
    if (width !== 320) await screenshot(width === 1000 ? 'readme.png' : 'readme-mobile.png');
  }
  console.log(`PASS: ${checks.length} browser checks; screenshots in website/preview/.`);
} catch (error) {
  checks.push({ name: 'Browser run completed', passed: false, details: error.message });
  console.error(error);
  process.exitCode = 1;
} finally {
  await writeFile(path.join(output, 'browser-checks.json'), JSON.stringify({ checks, browserErrors }, null, 2) + '\n');
  socket?.close();
  if (browser && browser.exitCode === null) {
    const exited = new Promise((resolve) => browser.once('exit', resolve));
    browser.kill('SIGTERM');
    await Promise.race([exited, pause(2000)]);
  }
  await new Promise((resolve) => server.close(resolve));
  // This exact directory was allocated by mkdtemp above and contains only test Chrome state.
  await rm(profile, { recursive: true, force: true });
}
