/* Progressive enhancement only: content, figures and paper work without JS. */
(() => {
  const tabList = document.querySelector('[data-gallery-tabs]');
  const tabs = [...document.querySelectorAll('[data-panel]')];
  const panels = [...document.querySelectorAll('[data-gallery-panel]')];

  if (tabList && tabs.length === panels.length) {
    const activate = (index, focus = false) => {
      tabs.forEach((tab, position) => {
        const selected = position === index;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
        const panel = document.getElementById(tab.dataset.panel);
        panel.hidden = !selected;
      });
      if (focus) tabs[index].focus();
    };

    tabList.hidden = false;
    tabList.setAttribute('role', 'tablist');
    tabs.forEach((tab, index) => {
      const panel = document.getElementById(tab.dataset.panel);
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', panel.id);
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', tab.id);
      panel.tabIndex = 0;
      tab.addEventListener('click', () => activate(index));
      tab.addEventListener('keydown', (event) => {
        const positions = {
          ArrowRight: (index + 1) % tabs.length,
          ArrowLeft: (index - 1 + tabs.length) % tabs.length,
          Home: 0,
          End: tabs.length - 1,
        };
        if (Object.hasOwn(positions, event.key)) {
          event.preventDefault();
          activate(positions[event.key], true);
        }
      });
    });
    activate(0);
  }

  // Show complete panels: the source projections are not pixel-registered.
  const comparison = document.querySelector('[data-comparison]');
  if (comparison) {
    const controls = comparison.querySelector('[data-compare-controls]');
    const views = [...comparison.querySelectorAll('[data-compare-view]')];
    const buttons = [...comparison.querySelectorAll('[data-compare-set]')];
    const status = comparison.querySelector('[data-compare-status]');
    const showView = (name, focus = false) => {
      comparison.dataset.view = name;
      views.forEach((view) => { view.hidden = view.dataset.compareView !== name; });
      buttons.forEach((button) => {
        const selected = button.dataset.compareSet === name;
        button.setAttribute('aria-pressed', String(selected));
        if (selected && focus) button.focus({ preventScroll: true });
      });
      status.textContent = name === 'before' ? 'Centroid origin · 0.42 m error' : 'Handle-guided origin · 0.05 m error';
    };
    comparison.classList.add('is-interactive');
    controls.hidden = false;
    showView('after');
    buttons.forEach((button) => {
      button.addEventListener('click', () => showView(button.dataset.compareSet));
      button.addEventListener('keydown', (event) => {
        const next = { ArrowLeft: 'before', Home: 'before', ArrowRight: 'after', End: 'after' }[event.key];
        if (!next) return;
        event.preventDefault();
        showView(next, true);
      });
    });
  }

  const dialog = document.getElementById('image-dialog');
  const dialogImage = document.getElementById('dialog-image');
  const dialogCaption = document.getElementById('dialog-caption');
  const dialogOriginal = document.getElementById('dialog-original');
  let returnFocus = null;

  if (dialog && typeof dialog.showModal === 'function') {
    document.querySelectorAll('[data-lightbox]').forEach((link) => {
      link.addEventListener('click', (event) => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        returnFocus = link;
        dialogImage.src = link.href;
        dialogImage.alt = link.querySelector('img')?.alt || link.dataset.caption || 'Research figure';
        dialogCaption.textContent = link.dataset.caption || '';
        dialogOriginal.href = link.href;
        dialog.showModal();
        document.body.classList.add('dialog-open');
      });
    });
    dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      const bounds = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
    });
    dialog.addEventListener('close', () => {
      document.body.classList.remove('dialog-open');
      returnFocus?.focus({ preventScroll: true });
    });
  }

  const copyButton = document.querySelector('[data-copy-citation]');
  if (copyButton) {
    copyButton.hidden = false;
    copyButton.addEventListener('click', async () => {
      const citation = document.getElementById('bibtex');
      const status = document.getElementById('copy-status');
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(citation.textContent);
        status.textContent = 'Citation copied.';
        copyButton.textContent = 'Copied';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(citation);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = 'Citation selected. Press Ctrl+C or ⌘C to copy.';
      }
    });
  }

  if ('IntersectionObserver' in window) {
    const links = [...document.querySelectorAll('nav a[href^="#"]')];
    const sections = links.map((link) => document.querySelector(link.getAttribute('href')));
    const observer = new IntersectionObserver((entries) => {
      const active = entries.find((entry) => entry.isIntersecting);
      if (!active) return;
      links.forEach((link) => {
        if (link.getAttribute('href') === `#${active.target.id}`) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    }, { rootMargin: '-15% 0px -55% 0px', threshold: 0 });
    sections.forEach((section) => { if (section) observer.observe(section); });
  }

  // Nonessential entrances: content is always visible, even off-screen or without JS.
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  if ('IntersectionObserver' in window && typeof Element.prototype.animate === 'function') {
    const activeAnimations = new Set();
    const entrances = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entrances.unobserve(entry.target);
        if (motionPreference.matches) return;
        const animation = entry.target.animate([
          { opacity: .65, transform: 'translateY(18px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ], { duration: 600, easing: 'cubic-bezier(.2, .7, .2, 1)' });
        activeAnimations.add(animation);
        animation.finished.catch(() => {}).finally(() => activeAnimations.delete(animation));
      });
    }, { threshold: .08 });
    document.querySelectorAll('[data-reveal]').forEach((element) => entrances.observe(element));
    motionPreference.addEventListener('change', () => {
      if (motionPreference.matches) activeAnimations.forEach((animation) => animation.cancel());
    });
  }
})();
