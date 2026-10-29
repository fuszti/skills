'use strict';
// Injected into every visual by serve.py. It runs inside the sandboxed iframe and tells the deck page what is
// broken: a mermaid diagram that failed to parse, or text that is too faint to read on its background.
(() => {
  const MIN_CONTRAST = 4.5;

  function rgba(css) {
    const m = css.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return [r, g, b, a];
  }

  function luminance([r, g, b]) {
    const c = [r, g, b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }

  // the first opaque background behind an element; translucent layers are blended over it
  function backdrop(el) {
    const layers = [];
    for (let n = el; n; n = n.parentElement) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    let base = rgba(getComputedStyle(document.documentElement).backgroundColor) || [255, 255, 255, 1];
    if (base[3] < 1) base = [255, 255, 255, 1];
    for (const c of layers.reverse()) base = base.map((v, i) => (i < 3 ? c[i] * c[3] + v * (1 - c[3]) : 1));
    return base;
  }

  function contrastProblems() {
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    for (let t = walker.nextNode(); t && out.length < 3; t = walker.nextNode()) {
      const el = t.parentElement;
      if (!el || seen.has(el) || !t.textContent.trim() || el.closest('svg')) continue;
      seen.add(el);
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
      const fg = rgba(cs.color);
      if (!fg) continue;
      const bg = backdrop(el);
      const fgb = fg.map((v, i) => (i < 3 ? v * fg[3] + bg[i] * (1 - fg[3]) : 1));
      const [l1, l2] = [luminance(fgb), luminance(bg)].sort((a, b) => b - a);
      const ratio = (l1 + 0.05) / (l2 + 0.05);
      if (ratio < MIN_CONTRAST) out.push(`text "${t.textContent.trim().slice(0, 40)}" has contrast ${ratio.toFixed(1)}:1 (needs ${MIN_CONTRAST})`);
    }
    return out;
  }

  function mermaidProblems() {
    const out = [];
    for (const el of document.querySelectorAll('.mermaid, [id^="mermaid"], svg[aria-roledescription="error"]')) {
      const text = el.textContent || '';
      if (/Syntax error in text|Parse error/i.test(text) || el.getAttribute('aria-roledescription') === 'error') {
        out.push('mermaid failed to parse: ' + (text.match(/Parse error[^\n]*/)?.[0] || 'syntax error').slice(0, 120));
      }
    }
    return [...new Set(out)];
  }

  function report() {
    const problems = [...mermaidProblems(), ...contrastProblems()];
    if (problems.length) parent.postMessage({ type: 'grill-deck-lint', problems }, '*');
  }

  // mermaid renders after load: look once it had time to finish
  addEventListener('load', () => setTimeout(report, 2500));
})();
