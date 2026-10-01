// The look's numeric checks (X16; ported to the React page in the third pass, part 8). Loaded only by index.html?check;
// it drives the page as a person would (tabs, sliders, inputs), reads it as rendered, prints a table above the page
// and leaves the results in window.LOOK. Run it at 1440 × 900 (the height and first-screen checks), 1280 (the queues
// fit) and 375 px (no sideways scroll), in light and in dark (?check&theme=light, ?check&theme=dark: a bare ?check
// follows the system's scheme, and the browser pane can follow a dark app).
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  await document.fonts.ready; await sleep(600);
  const D = window.DASH, P = D.proto, G = D.group;
  const out = [], add = (check, pass, detail) => out.push({ check, pass: pass === null ? "info" : pass ? "pass" : "FAIL", detail });
  const root = document.documentElement, W = innerWidth, H = innerHeight;
  if (/[?&]theme=dark/.test(location.search)) { root.setAttribute("data-theme", "dark"); await sleep(300); }
  // the four team tabs, then the Programme office's own entry (apart from the tool, not a tab): every view is walked
  const tabs = () => [...document.querySelectorAll("[role=tab]")];
  const views = () => [...tabs(), document.querySelector(".office-btn")];
  const panel = () => document.querySelector("[role=tabpanel][data-state=active]");
  const show = async i => { const el = views()[i];
    el.getAttribute("role") === "tab" ? el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 })) : el.click();
    scrollTo(0, 0); await sleep(350);
    document.getAnimations().forEach(a => a.finish()); };   // a hidden page draws no frames: end what a shown one has ended
  const name = i => views()[i].textContent.trim();
  const openDetails = () => { const d = [...document.querySelectorAll("details:not([open])")]; d.forEach(x => x.open = true); return () => d.forEach(x => x.open = false); };
  const setVal = (el, v, ev = "input") => { const p = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(p, "value").set.call(el, String(v)); el.dispatchEvent(new Event(ev, { bubbles: true })); };
  const cars = P.cars, showcase = "55089" in cars ? 55089 : Number(Object.keys(cars)[0]);
  const openCar = async id => { window.LEDGER.open(id); await sleep(500); return document.querySelector(".drawer"); };
  const closeCar = async () => { document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await sleep(350); };
  const n = views().length;

  // 1. contrast of every text and UI token pair, light and dark (WCAG 2.2: 4.5:1 text, 3:1 non-text)
  const hex = s => { s = s.trim(); if (s[0] === "#") { let h = s.slice(1); if (h.length <= 4) h = [...h].map(c => c + c).join("");
      const q = [0, 2, 4, 6].map(i => i < h.length ? parseInt(h.slice(i, i + 2), 16) : 255); return { r: q[0], g: q[1], b: q[2], a: q[3] / 255 }; }
    const m = s.match(/[\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m[3] == null ? 1 : m[3] }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = c => { const f = v => (v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const TEXT = ["--ink", "--ink2", "--muted", "--title", "--link"];
  const UI = ["--axis", "--focus", "--crit", "--warn", "--good", "--series", "--deemph", "--ord1", "--ord2", "--bar", "--vtick"];
  const theme0 = root.getAttribute("data-theme");
  for (const theme of ["light", "dark"]) {
    root.setAttribute("data-theme", theme); await sleep(50);
    const cs = getComputedStyle(root), v = k => hex(cs.getPropertyValue(k));
    // text sits on the canvas, the cards and the popovers; marks sit on the cards and popovers only
    for (const [kind, tokens, min, bgs] of [["Text", TEXT, 4.5, ["--page", "--surface", "--overlay"]], ["UI", UI, 3, ["--surface", "--overlay"]]]) {
      let worst = [99], fails = [];
      for (const bn of bgs) for (const t of tokens) {
        const bg = v(bn), r = ratio(over(v(t), bg), bg);
        if (r < worst[0]) worst = [r, t, bn];
        if (r < min) fails.push(`${t} on ${bn} ${r.toFixed(2)}`);
      }
      add(`${kind} contrast ≥ ${min}:1, ${theme}`, !fails.length, `${tokens.length} tokens × ${bgs.length} backgrounds; lowest ${worst[0].toFixed(2)} (${worst[1]} on ${worst[2]})${fails.length ? "; fails: " + fails.join(", ") : ""}`);
    }
    const band = [["--on-band", 4.5], ["--on-band2", 4.5]].map(([t, min]) => [t, ratio(v(t), v("--band")), min]);
    add(`The navy band's text ≥ 4.5:1, ${theme}`, band.every(([, r, m]) => r >= m), band.map(([t, r]) => `${t} ${r.toFixed(2)}`).join(", "));
    const bt = ratio(v("--vtick"), over(v("--vband"), v("--surface")));
    add(`The value tick on its band ≥ 3:1, ${theme}`, bt >= 3, bt.toFixed(2));
  }
  theme0 ? root.setAttribute("data-theme", theme0) : root.removeAttribute("data-theme");
  await sleep(200);

  // 2. six type sizes, counted from computed styles over every rendered text node (chart text too), the drawer too
  const ALLOWED = [12, 14, 16, 20, 28, 42], sizes = new Map();
  const scan = scope => scope && scope.querySelectorAll("*").forEach(el => {
    if (!el.getClientRects().length) return;
    const text = [...el.childNodes].some(x => x.nodeType === 3 && x.textContent.trim()) || el.matches("input, button, select");
    if (!text) return;
    const s = Math.round(parseFloat(getComputedStyle(el).fontSize) * 10) / 10; sizes.set(s, (sizes.get(s) || 0) + 1);
  });
  const chars = new Set(), take = s => { for (const ch of s) chars.add(ch); };
  const svgText = scope => [...scope.querySelectorAll("svg text")].map(x => x.textContent).join("");
  for (let i = 0; i < n; i++) {
    await show(i); const close = openDetails();
    scan(document.querySelector("header.top")); scan(document.querySelector(".tabs-bar")); scan(panel());
    take(document.querySelector("header.top").innerText + panel().innerText + svgText(panel())); close();
  }
  let dr = await openCar(showcase);
  { const close = openDetails(); scan(dr); take(dr.innerText + svgText(dr)); close(); }
  await closeCar();
  const got = [...sizes.keys()].sort((a, b) => a - b);
  add("Type: six sizes", got.every(s => ALLOWED.includes(s)) && got.length <= 6, "in use: " + got.map(s => `${s} px (${sizes.get(s)})`).join(", "));
  const fam = getComputedStyle(document.body).fontFamily, faces = [...document.fonts].filter(f => f.family.replace(/"/g, "") === "IBM Plex Sans" && f.status === "loaded");
  add("Font: IBM Plex Sans 400 and 600 loaded", fam.includes("IBM Plex Sans") && faces.length === 2, `${faces.map(f => f.weight).join(" and ")} loaded`);

  // 3. glyphs: every character on the page is drawn by Plex (a glyph Plex lacks falls back, so two fallbacks differ)
  const cv = document.createElement("canvas").getContext("2d");
  const wd = (ch, f, wt) => { cv.font = `${wt} 40px ${f}`; return cv.measureText(ch).width; };
  const miss = [...chars].filter(ch => ch.trim() && [400, 600].some(wt => Math.abs(wd(ch, '"IBM Plex Sans", monospace', wt) - wd(ch, '"IBM Plex Sans", serif', wt)) > 0.01));
  const special = [...chars].filter(ch => ch.charCodeAt(0) > 126).sort().join(" ");
  add("Glyphs: every character in Plex, € included", !miss.length && chars.has("€"), `${chars.size} distinct characters; beyond ASCII: ${special}${miss.length ? "; missing: " + miss.join(" ") : ""}`);

  // 4. targets: at least 24 px each way (WCAG 2.5.8); 40 px tall in the dense queues (rows of a value and its band)
  const SEL = "button, a[href], input, select, summary, [role=button], [tabindex]:not([tabindex='-1'])";
  let cnt = 0, small = [], dense = 0, denseLow = [], smallest = [1e9];
  for (let i = 0; i < n; i++) {
    await show(i); const close = openDetails();
    for (const el of [...document.querySelectorAll(".tabs-bar [role=tab], .tabs-bar .office-btn, header.top :is(" + SEL + ")"), ...panel().querySelectorAll(SEL)]) {
      const r = el.getBoundingClientRect(); if (!r.width && !r.height) continue;
      if (el.matches("[role=tabpanel]")) continue;
      cnt++; const m = Math.min(r.width, r.height);
      if (m < smallest[0]) smallest = [m, `${el.tagName.toLowerCase()}.${String(el.className.baseVal ?? el.className).split(" ")[0]} ${Math.round(r.width)}×${Math.round(r.height)}`];
      if (r.width < 24 || r.height < 24) small.push(`${name(i)}: ${el.tagName.toLowerCase()}.${String(el.className.baseVal ?? el.className).split(" ")[0]} ${Math.round(r.width)}×${Math.round(r.height)}`);
      if (el.closest(".queue.tall tbody")) { dense++; if (r.height < 40) denseLow.push(`${el.tagName.toLowerCase()} ${Math.round(r.height)}`); }
    }
    close();
  }
  add("Targets ≥ 24 px (WCAG 2.5.8)", !small.length, `${cnt} targets in ${n} views; smallest ${smallest[0].toFixed(1)} px (${smallest[1]})${small.length ? "; under 24: " + small.slice(0, 6).join(", ") : ""}`);
  add("Targets 40 px tall in the dense queues", !denseLow.length && dense > 0, `${dense} car buttons and inputs in rows of a value and its band${denseLow.length ? "; lower: " + denseLow.slice(0, 6).join(", ") : ""}`);

  // 5. keyboard: nothing jumps the order, everything clickable is reachable, the tabs pattern, a 2 px ring
  const pos = [...document.querySelectorAll("[tabindex]")].filter(e => e.tabIndex > 0);
  let clickable = 0, unreachable = [];
  for (let i = 0; i < n; i++) { await show(i);
    for (const e of panel().querySelectorAll("button, [role=button], input, select, summary")) { clickable++; if (e.tabIndex < 0 && !e.disabled) unreachable.push(e.tagName); } }
  await show(0); const zero = tabs().filter(t => t.tabIndex === 0);
  add("Keyboard: no positive tabindex; every control reachable", !pos.length && !unreachable.length, `${clickable} controls checked${unreachable.length ? "; unreachable: " + unreachable.length : ""}`);
  add("Keyboard: the tabs take one stop", zero.length === 1 && zero[0].getAttribute("aria-selected") === "true", `${tabs().length} tabs, ${zero.length} in the tab order`);
  const ring = [...document.styleSheets].flatMap(s => { try { return [...s.cssRules]; } catch (e) { return []; } }).find(r => r.selectorText === ":focus-visible");
  add("Focus ring 2 px", !!ring && /outline:\s*2px solid/.test(ring.cssText), ring ? ring.cssText : "no rule");

  // 6. layout: no sideways scroll; queues fit at 1280 px and above; each view's height and first screen (1440 × 900)
  const over1 = [], qover = [], tall = [], first = [];
  for (let i = 0; i < n; i++) {
    await show(i);
    const o = root.scrollWidth - root.clientWidth; if (o > 0) over1.push(`${name(i)} +${o}`);
    panel().querySelectorAll(".qwrap").forEach(q => { const d = q.scrollWidth - q.clientWidth; if (d > 0) qover.push(`${name(i)} +${d}`); });
    tall.push([name(i), +(root.scrollHeight / H).toFixed(2)]);
    const c = panel().querySelector(".card"), tiles = panel().querySelector(".tiles");
    first.push([name(i), Math.round(c.getBoundingClientRect().bottom), Math.round(tiles.getBoundingClientRect().bottom)]);
  }
  add(`No sideways scroll at ${W} px`, !over1.length, over1.length ? over1.join(", ") : `${n} views`);
  if (W >= 1280) add("Queues fit without scrolling sideways at 1280 px and above", !qover.length, qover.length ? qover.join(", ") : "every queue");
  if (W >= 1400 && H >= 880) {
    add("No view taller than about 1.6 screens (1.62)", tall.every(([, s]) => s <= 1.62), tall.map(([v, s]) => `${v} ${s}`).join(", "));
    add("The first card and the tiles on the first screen", first.every(([, c, t]) => c <= H && t <= H), first.map(([v, c]) => `${v} ${c} px`).join(", "));
  }

  // 7. prose and charts: at most 120 words outside charts, tables, controls and badges; at least two charts, each with a
  //    twin (the tool pass: a tool shows a chart only where its team decides with it; the third pass asked four)
  const words = [], twins = [];
  for (let i = 0; i < n; i++) {
    await show(i);
    const w = document.createTreeWalker(panel(), NodeFilter.SHOW_TEXT); let k = 0;
    while (w.nextNode()) { const el = w.currentNode.parentElement;
      if (el.closest("svg, .echart, .chart, table, .twin, .queue, select, .sr, [aria-hidden=true], .card-tools, .chart-ctl, .badge")) continue;
      k += w.currentNode.textContent.trim().split(/\s+/).filter(Boolean).length; }
    words.push([name(i), k]); twins.push([name(i), panel().querySelectorAll('[aria-label^="Show as a table"]').length]);
  }
  add("Prose: at most 120 words a view on load", words.every(([, k]) => k <= 120), words.map(([v, k]) => `${v} ${k}`).join(", "));
  add("At least two charts a view, each with a table twin", twins.every(([, k]) => k >= 2), twins.map(([v, k]) => `${v} ${k}`).join(", "));
  // the text diet (the user, 30 September): a card holds at most 60 words, its tables and any chart built of text counted
  // (the prose check above skips both); a queue's rows are the team's work, and a drawn chart's labels are the chart.
  // The KPI board's rows are records too (a KPI each: a name, a target, a reading): each is held to 20 words instead
  {
    const CAP = 60, ROW = 20, skip = "svg, .echart, .queue, select, .sr, [aria-hidden=true], .card-tools, .chart-ctl, .badge";
    const words = (root, not) => { const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let k = 0;
      while (w.nextNode()) { const el = w.currentNode.parentElement;
        if (el.closest(skip) || (not && el.closest(not))) continue;
        k += w.currentNode.textContent.trim().split(/\s+/).filter(Boolean).length; }
      return k; };
    const over = [], most = []; let rows = 0, longest = 0;
    for (let i = 0; i < n; i++) {
      await show(i);
      let top = 0;
      panel().querySelectorAll(".card").forEach(c => {
        const k = words(c, ".kpi, .single"), t = ((c.querySelector(".card-head h3") || {}).textContent || "?").trim();
        if (k > CAP) over.push(`${t} ${k}`);
        top = Math.max(top, k);
        c.querySelectorAll(".kpi, .single").forEach(r => { const m = words(r); rows++; longest = Math.max(longest, m);
          if (m > ROW) over.push(`${t}: a row of ${m}`); });
      });
      most.push(`${name(i).split(" ")[0]} ${top}`);
    }
    add(`Text: at most ${CAP} words a card, its tables and text-built charts counted, queues not; a KPI row at most ${ROW}`,
      !over.length && rows >= 15, `${over.length ? "over: " + over.join(", ") + "; " : ""}the most a card: ${most.join(", ")}; ` +
      `${rows} KPI rows, the longest ${longest}`);
  }
  // card titles are labels (the AI look, part 1; SAP Fiori's "Revenue by Quarter"): six words at most and no figure,
  // the card's figure on the line below
  {
    const bad = []; let cards = 0;
    for (let i = 0; i < n; i++) {
      await show(i);
      panel().querySelectorAll(".card").forEach(c => {
        const h = c.querySelector(".card-head h3"); if (!h) return;
        const t = [...h.childNodes].filter(x => !(x.nodeType === 1 && x.classList.contains("card-badges"))).map(x => x.textContent).join("").trim();
        const sub = ((c.querySelector(".card-sub") || {}).textContent || "").trim(); cards++;
        if (t.split(/\s+/).length > 6 || /\d/.test(t) || !sub) bad.push(`${name(i)}: "${t}"${sub ? "" : " (no line below)"}`);
      });
    }
    add("Card titles are labels: six words at most, no figures, the figure on the line below", !bad.length && cards >= 21,
      bad.length ? bad.join("; ") : `${cards} cards`);
  }
  // the internal prices as a table (the AI look, part 2): three prices by who pays, who is paid, when, rate and euros a
  // year, the euros right-aligned (GOV.UK's tables); no drawn arrows left on the page
  {
    await show(0);
    const card = [...panel().querySelectorAll(".card")].find(c => (c.querySelector("h3") || {}).textContent === "Internal prices");
    const tb = card && card.querySelector(".prices table"), rows = tb ? tb.querySelectorAll("tbody tr") : [];
    const cols = tb ? tb.querySelectorAll("thead th").length : 0;
    const right = [...rows].every(r => getComputedStyle(r.lastElementChild).textAlign === "right");
    const arrows = document.querySelectorAll(".pipe, .flows, .node").length;
    add("Internal prices: a table of the three prices, euros right-aligned, no drawn arrows",
      rows.length === 3 && cols === 6 && right && arrows === 0,
      `${rows.length} rows, ${cols} columns; euros ${right ? "right-aligned" : "not right-aligned"}; ${arrows} diagram parts left`);
  }
  // provenance said once (the AI look, part 3): each view's band names its layer; no card repeats it, and a card whose
  // data differs from its view's (a group figure in a prototype view, a prototype figure among group figures) says so
  {
    const repeat = [], per = []; let shown = 0;
    for (let i = 0; i < n; i++) {
      await show(i);
      const band = panel().querySelectorAll(".tiles-badge .badge"), layer = band.length === 1 ? [...band[0].classList].find(c => c !== "badge") : null;
      const cards = [...panel().querySelectorAll(".card-badges .badge")];
      shown += cards.length; per.push(`${name(i).split(" ")[0]} ${layer || "?"}: ${cards.length}`);
      if (!layer || cards.some(b => b.classList.contains(layer))) repeat.push(name(i));
    }
    add("Provenance said once: the band names each view's layer; a card badge only where a card's data differs",
      !repeat.length && shown <= 8, `${per.join(", ")} card badges${repeat.length ? "; repeated in " + repeat.join(", ") : ""}`);
  }
  // a compact band on the team views (the AI look, part 6; SAP Fiori's dynamic page: a worklist's key figures sit in its
  // title area): no navy and no card over it; each figure a label (six words at most, no figure, a capital first) before
  // its value. The CFO's and the Programme office's views keep the navy strip with the cards over it
  {
    const probe = document.createElement("div"); probe.style.background = "var(--band)"; document.body.appendChild(probe);
    const navy = getComputedStyle(probe).backgroundColor; probe.remove();
    const TEAM = ["New-car incentives", "Captive finance", "Used-car resale"], bad = [], hs = [];
    for (let i = 0; i < n; i++) {
      await show(i);
      const v = name(i), band = panel().querySelector(".band"), b = band.getBoundingClientRect();
      const top = panel().querySelector(".grid > *").getBoundingClientRect().top;
      const isNavy = getComputedStyle(band).backgroundColor === navy, team = TEAM.some(t => v.startsWith(t));
      hs.push(`${v.split(" ")[0]} ${Math.round(b.height)} px`);
      if (!team) { if (!isNavy || top >= b.bottom) bad.push(`${v}: the navy strip lost`); continue; }
      if (isNavy || !band.classList.contains("compact") || top < b.bottom) bad.push(`${v}: not compact`);
      panel().querySelectorAll(".band .tile").forEach(t => {
        const l = t.firstElementChild, s = (l.textContent || "").trim();
        if (!l.classList.contains("tl") || s.split(/\s+/).length > 6 || /\d/.test(s) || !/^[A-Z]/.test(s)) bad.push(`${v}: "${s}"`);
      });
    }
    add("A compact band on the team views, each figure's label first; the CFO's and the office's keep the navy strip",
      !bad.length, `${bad.length ? bad.join("; ") + "; " : ""}band heights: ${hs.join(", ")}`);
  }
  // the writing (the AI look, part 4): no facts joined by "·" and none of the slogans the pass removed, in any view
  {
    const SLOGANS = /by design|on purpose|never cut it|what to budget|latitude, not euros/i, found = [];
    let dots = 0;
    for (let i = 0; i < n; i++) {
      await show(i);
      const txt = document.body.innerText; dots += (txt.match(/·/g) || []).length;
      const m = txt.match(SLOGANS); if (m) found.push(`${name(i)}: "${m[0]}"`);
    }
    add("Writing: no facts joined by a middle dot, no slogans", dots === 0 && !found.length,
      `${dots} middle dots${found.length ? "; " + found.join(", ") : ", no slogans"} across the ${n} views`);
  }

  // 8. queue rows and padding: 48 px with a value and its band, 32 px otherwise; 12 px sides
  let rowsBad = [], padBad = [], r48 = 0, r32 = 0;
  for (let i = 0; i < n; i++) {
    await show(i);
    panel().querySelectorAll(".queue").forEach(q => {
      const want = q.classList.contains("tall") ? 48 : 32;
      q.querySelectorAll("tbody tr").forEach(r => { const h = Math.round(r.getBoundingClientRect().height); if (!h) return;
        want === 48 ? r48++ : r32++; if (h !== want) rowsBad.push(`${name(i)} ${h}`); });
      const td = q.querySelector("tbody td"); if (td && parseFloat(getComputedStyle(td).paddingLeft) !== 12) padBad.push(name(i));
    });
  }
  add("Queue rows: 48 px with a band, 32 px otherwise", !rowsBad.length, `${r48} rows of 48 and ${r32} of 32${rowsBad.length ? "; off: " + rowsBad.slice(0, 6).join(", ") : ""}`);
  add("Queue cells: 12 px sides", !padBad.length, padBad.length ? padBad.join(", ") : "every queue");

  // 9. motion: 110 ms on hover, colour and popovers (70 ms out); 240 ms when data or the view changes, the tab's line and
  //    the drawer (in and out); 400 ms for the theme's cross-fade; Carbon's curves; no transitions on rows or tables
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tabT = getComputedStyle(tabs()[0]);
  dr = await openCar(showcase); const drA = getComputedStyle(dr).animationDuration; await closeCar();
  const rule = sel => [...document.styleSheets].flatMap(x => [...x.cssRules]).find(r => r.selectorText === sel || (r.selectorText || "").includes(sel));
  const rd = sel => { const r = rule(sel); return r ? (r.style.animation || r.style.transition || `${r.style.animationDuration} ${r.style.animationTimingFunction}`) : "missing"; };
  const R = { ink: rd(".tab-ink"), popIn: rd('.pop[data-state="open"]'), popOut: rd('.pop[data-state="closed"]'),
    drOut: rd('.drawer[data-state="closed"]'), theme: rd("::view-transition-new(root)") };
  const tok = k => getComputedStyle(root).getPropertyValue(k).trim();   // as the build writes them (".24s", ".38")
  const ms = v => Math.round(v.endsWith("ms") ? parseFloat(v) : parseFloat(v) * 1000);
  const okRules = ["transform", "width", "background-color", "opacity"].every(k => R.ink.includes(`${k} var(--slow) var(--ease)`))
    && rule('.pop[data-state="open"]').style.animation.includes("var(--fast) var(--enter)") && rule('.pop[data-state="closed"]').style.animation.includes("var(--out) var(--exit)")
    && rule('.drawer[data-state="closed"]').style.animation.includes("var(--slow) var(--exit)") && /^(400ms|0\.4s) var\(--ease\)$/.test(R.theme)
    && ms(tok("--fast")) === 110 && ms(tok("--slow")) === 240 && ms(tok("--out")) === 70 && ms(tok("--rise")) === 300
    && /\(0?\.05, 0?\.7, 0?\.1, 1\)/.test(tok("--decel"))
    && /\(0, 0, 0?\.38, 0?\.9\)/.test(tok("--enter")) && /\(0?\.2, 0, 1, 0?\.9\)/.test(tok("--exit"));
  const okMotion = reduce ? tabT.transitionDuration.split(", ").every(d => d === "0s") && (drA === "0s" || getComputedStyle(dr).animationName === "none")
    : tabT.transitionDuration.split(", ").every(d => d === "0.11s") && drA === "0.24s" && /0\.2, 0, 0\.38, 0\.9/.test(tabT.transitionTimingFunction) && okRules;
  const moving = [...document.querySelectorAll("tbody tr, td, .view, table")].slice(0, 600).filter(e => getComputedStyle(e).transitionDuration.split(", ").some(d => d !== "0s")).length;
  add("Motion: Carbon's productive durations and curves", okMotion && moving === 0, `${reduce ? "reduced motion: none" : `tabs ${tabT.transitionDuration}; drawer ${drA} in, then "${R.drOut}"; arrivals ${tok("--rise")} on ${tok("--decel")}; tab line "${R.ink.split(",")[0]}, …"; popovers "${R.popIn}", "${R.popOut}"; theme "${R.theme}"`}; rows, tables and views without transitions: ${moving === 0}`);

  // 10. only its own files load (the fonts are inlined)
  const res = performance.getEntriesByType("resource").map(r => r.name).filter(u => !u.startsWith("data:"));
  const foreign = res.filter(u => { try { return new URL(u).origin !== location.origin; } catch (e) { return true; } });
  add("Loads only its own files", !foreign.length, res.map(u => u.split("/").pop().split("?")[0]).join(", "));

  // 11. the functional checks
  await show(0);
  const lvl = document.getElementById("lvl");
  // numbers roll (after the tool pass, part 7): the book's tile rolls its digits to the moved value, then rests
  const flow = () => panel().querySelector(".tile .tv .roll > *");
  const running = () => { const f = flow(); return f && f.shadowRoot ? f.shadowRoot.getAnimations().filter(a => a.playState === "running").length : 0; };
  setVal(lvl, -10); await sleep(80);
  const rolling = running(); await sleep(1100); const resting = running();
  const tv = panel().querySelector(".tile .tv"), tile = tv.querySelector("[data-value]") ? tv.querySelector("[data-value]").dataset.value : tv.textContent;
  const want = "€" + (P.book_now.book * 0.9 / 1e6).toLocaleString("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "m";
  add("Level slider: −10% gives 90% of the book", tile === want, `${tile} (want ${want})`);
  const rolls = [...document.querySelectorAll(".tile .tv")].filter(x => x.querySelector(".roll")).length;
  add("Numbers roll: the book's tile rolls its digits to the moved value, then rests; every single-number tile rolls",
    !!flow() && (reduce ? rolling === 0 : rolling > 0) && resting === 0 && rolls > 0 && [...document.querySelectorAll(".tile .tv")].every(x => x.querySelector(".roll") || !/^[^\d]*[\d,]+(\.\d+)?[^\d]*$/.test(x.textContent)),
    `${rolling} digit animations running 80 ms after the slider moved, ${resting} after 1.2 s${reduce ? " (reduced motion)" : ""}; ${rolls} tiles in this view roll${document.hidden ? "; the page is hidden: no frames" : ""}`);
  await show(2);
  const past = P.book.slice(-37, -1).map(r => r.level), avg = past.reduce((a, b) => a + b, 0) / 36;
  const gap = 100 * (P.book_now.level * 0.9 / avg - 1), shown = panel().querySelector(".nl-label").textContent;
  const g2 = (gap < 0 ? "−" : "+") + Math.abs(gap).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
  add("Level slider: the charge's number line moves with it", shown.includes(g2), `${shown} (want ${g2})`);
  setVal(lvl, 0); await sleep(200);
  const car = cars[String(showcase)], hold = car.events.find(e => e[2] === "claim hold");
  if (hold) {
    dr = await openCar(showcase); dr.querySelector("details").open = true;
    const r = dr.querySelector("#asofr"); let before = -1;
    for (let i = 0; i <= +r.max; i++) { setVal(r, i); await sleep(0); if (dr.querySelector(".dr-asof output").textContent < hold[1]) before = i; }
    await sleep(100);
    const rowOf = () => [...dr.querySelectorAll(".dr-events tbody tr")].find(tr => tr.children[2].textContent.startsWith("claim hold"));
    setVal(r, before); await sleep(150); const greyed = rowOf() && rowOf().classList.contains("unknown");
    setVal(r, before + 1); await sleep(150); const known = rowOf() && !rowOf().classList.contains("unknown");
    add(`Drawer as-of: car ${showcase}'s hold is grey the day before it was learnt`, greyed && known, `learnt ${hold[1]}; grey before: ${greyed}; known on the day: ${known}`);
    await closeCar();
  }
  await show(3);
  [...panel().querySelectorAll(".seg button")].find(b => b.textContent === "Pricing desk").click(); await sleep(200);
  const all = [...panel().querySelectorAll(".q-tools .text-btn")].find(b => /Show all/.test(b.textContent)); if (all) { all.click(); await sleep(200); }
  const desk = P.pricing_desk, inRow = desk.find(x => !x.thin), thinRow = desk.find(x => x.thin);
  const tryDesk = async (row, value) => { const i = panel().querySelector(`[aria-label="First proposal for car ${row.car}"]`);
    setVal(i, Math.round(value)); await sleep(100); const k = i.closest("tr").lastElementChild.querySelector(".st"); const cls = k ? k.className : "";
    setVal(i, ""); await sleep(50); return cls; };
  const a1 = await tryDesk(inRow, inRow.mark), a2 = await tryDesk(inRow, inRow.mark * (1 + 2 * inRow.cap_pct / 100)), a3 = await tryDesk(thinRow, thinRow.mark);
  add("Pricing desk: inside, outside (a manager) and little history (sign-off)", a1.includes("ok") && a2.includes("crit") && a3.includes("warn"), `${a1} · ${a2} · ${a3}`);

  // 12. actions (the tool pass, part 4), simulated in the page: a decision shows on its row at the row's height, joins
  //     the car's record and feeds the CFO's reading; undo takes it back
  const rowH = el => Math.round(el.closest("tr").getBoundingClientRect().height);
  const deskIn = panel().querySelector(`[aria-label="First proposal for car ${inRow.car}"]`);
  setVal(deskIn, Math.round(inRow.mark)); await sleep(100);
  deskIn.closest("tr").querySelector("button.log").click(); await sleep(150);
  const lockedH = [panel().querySelector(`[aria-label="First proposal for car ${inRow.car}"]`).disabled,
    rowH(panel().querySelector(`[aria-label="Undo the logged price for car ${inRow.car}"]`))];
  await show(0);
  const reading = () => ([...panel().querySelectorAll(".single")].find(x => x.textContent.startsWith("Pricers")) || {}).textContent || "";
  const r1 = reading();
  dr = await openCar(inRow.car);
  const onRecord = [...dr.querySelectorAll(".dr-events tbody tr")].some(tr => tr.children[2].textContent.startsWith("price logged"));
  await closeCar();
  await show(3);
  [...panel().querySelectorAll(".seg button")].find(b => b.textContent === "Pricing desk").click(); await sleep(200);
  { const b = [...panel().querySelectorAll(".q-tools .text-btn")].find(b => /Show all/.test(b.textContent)); if (b) { b.click(); await sleep(200); } }
  panel().querySelector(`[aria-label="Undo the logged price for car ${inRow.car}"]`).click(); await sleep(150);
  await show(0); const r0 = reading();
  add("Actions: a logged price joins the car's record and the CFO's reading; undo takes it back",
    lockedH[0] && lockedH[1] === 48 && /1 of 1 logged, 100%/.test(r1) && onRecord && /logged proposals$/.test(r0.trim()),
    `row ${lockedH[1]} px, locked ${lockedH[0]}; reading "${r1.split("·").pop().trim()}"; on the record ${onRecord}; after undo "${r0.split("·").pop().trim()}"`);
  await show(1);
  const sel = panel().querySelector("select.act"), claimId = sel.getAttribute("aria-label").split(" ").pop();
  setVal(sel, "pay", "change"); await sleep(150);
  const undoC = panel().querySelector(`[aria-label="Undo the decision on claim ${claimId}"]`);
  const paid = !!undoC && undoC.closest("td").textContent.includes("Paid"), paidH = undoC ? rowH(undoC) : 0;
  undoC && undoC.click(); await sleep(150);
  const back = !!panel().querySelector(`select.act[aria-label="Decide claim ${claimId}"]`);
  add("Actions: a claim paid shows on its row at 32 px; undo restores the choice", paid && paidH === 32 && back,
    `claim ${claimId}: paid ${paid}, row ${paidH} px, undone ${back}`);

  // 13. the pilot and the reason types (the tool pass, part 5): the upgrade queue shows the treated arm and only the
  //     held-out count (the export carries no held-out car); the CFO's screen reads treated against control as not yet
  //     measured, with both arms; every row of the four queues carries one type from its queue's fixed list
  const pl = P.upgrade.pilot, gb = x => x.toLocaleString("en-GB");
  await show(2);
  const heldTxt = ((panel().querySelector(".held") || {}).textContent || "").trim();
  const qTitle = panel().querySelector(".card .card-title").textContent;   // the label and the line below it
  await show(0);
  const upl = ([...panel().querySelectorAll(".single")].find(x => x.textContent.startsWith("Retention uplift")) || {}).textContent || "";
  const typed = [], untyped = [];
  const readQ = (list, label) => panel().querySelectorAll(".queue tbody tr").forEach(tr => {
    const c = [...tr.querySelectorAll(".chip.type")].map(x => x.textContent);
    (c.length === 1 && P.reason_types[list].some(([t]) => t === c[0]) ? typed : untyped).push(`${label}: ${c.join("+") || "none"}`); });
  await show(1); readQ("claims", "claims");
  await show(2); readQ("timing", "upgrade");
  await show(3); readQ("timing", "incoming");
  [...panel().querySelectorAll(".seg button")].find(b => b.textContent === "Pricing desk").click(); await sleep(200);
  readQ("desk", "desk");
  const pilotOk = heldTxt === `${gb(pl.control)} held out by the pilot and not shown` && qTitle.includes(`${gb(pl.treated)} financed`)
    && /not yet measured/.test(upl) && upl.includes(gb(pl.treated)) && upl.includes(gb(pl.control));
  add("Pilot and reason types: the queue shows the treated arm and the held-out count; the CFO's reading waits; a type on every row",
    pilotOk && !untyped.length && typed.length >= 40,
    `"${heldTxt}"; queue of ${gb(pl.treated)}; CFO: ${/not yet measured/.test(upl) ? "not yet measured" : "missing"}, both arms ${upl.includes(gb(pl.control))}; ` +
    `types on ${typed.length} of ${typed.length + untyped.length} rows${untyped.length ? "; without: " + untyped.slice(0, 4).join(", ") : ""}`);

  // 14. find a car and each source's date (the tool pass, part 6): a number opens its record (Enter takes the first
  //     match) and focus comes back to the box; a model lists its cars; no match says what the search covers
  const sbox = document.querySelector(".search input"), idx = P.car_index;
  const typeIn = async v => { sbox.focus(); setVal(sbox, v); await sleep(150); return (document.querySelector(".search-pop .sub") || {}).textContent || ""; };
  const far = idx.filter(x => x.in.length === 1 && x.in[0] === "incoming").pop() || idx[idx.length - 1];
  await typeIn(String(far.car));
  sbox.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await sleep(500);
  dr = document.querySelector(".drawer");
  const opened = !!dr && dr.textContent.includes(String(far.car)) && dr.textContent.toLowerCase().includes(far.model);
  await closeCar(); const focusBack = document.activeElement === sbox;
  const mdl = idx[Math.floor(idx.length / 2)], wantN = idx.filter(x => `${x.make} ${x.model}`.includes(mdl.model)).length;
  const listed = await typeIn(mdl.model), none = await typeIn("zzzz");
  await typeIn(""); sbox.blur(); await sleep(100);
  add("Search: a car number opens its record, focus returns; a model lists its cars; no match says what is searched",
    opened && focusBack && listed.startsWith(`${gb(wantN)} of the ${gb(idx.length)} cars`) && /^No car matches/.test(none),
    `car ${far.car} (${far.in.join(", ")}): opened ${opened}, focus back ${focusBack}; "${mdl.model}": ${listed.split(";")[0]}; no match: ${/^No car matches/.test(none)}`);
  const srcBtn = [...document.querySelectorAll("header.top .text-btn")].find(b => b.textContent === "Each source's date");
  srcBtn.click(); await sleep(300);
  const srows = [...document.querySelectorAll(".pop.xwide tbody tr")].map(tr => [...tr.children].map(td => td.textContent));
  const same = srows.length === P.sources.length && P.sources.every((s, i) => srows[i][0].startsWith(s.name)
    && srows[i][4] === s.happened && srows[i][5] === s.learnt);
  document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await sleep(250);
  add("Each source's date: every source's latest event and last learnt, as exported", same && !document.querySelector(".pop.xwide"),
    `${srows.length} of ${P.sources.length} rows; learnt ${P.sources.map(s => s.learnt).sort()[0]} to ${P.sources.map(s => s.learnt).sort().pop()}`);

  // 15. tool icons (the tool pass, part 7): each event on a record shows its type's icon, a claim held or in review
  //     its status shape; the timeline draws an icon per event; every model cell names its car's body type; the icon
  //     set's licence ships inside the page
  const sc = cars[String(showcase)], statusEv = sc.events.filter(e => /^claim (hold|review)$/.test(e[2])).length;
  dr = await openCar(showcase); dr.querySelector("details").open = true; await sleep(150);
  const evRows = [...dr.querySelectorAll(".dr-events tbody tr")];
  const bare = evRows.filter(tr => !tr.children[2].querySelector("svg.ic-ev, .st")).map(tr => tr.children[2].textContent);
  const imgs = dr.querySelectorAll(".dr-chart image").length, head = dr.querySelector(".dr-title .body-ic");
  await closeCar();
  add("Icons: every event on the record shows its type's icon or its status shape, one timeline icon each",
    evRows.length === sc.events.length && !bare.length && imgs === sc.events.length - statusEv
      && !!head && head.getAttribute("aria-label") === sc.body,
    `car ${showcase}: ${evRows.length} events, ${imgs} icons and ${statusEv} status shapes on the timeline; header "${head && head.getAttribute("aria-label")}"${bare.length ? "; without an icon: " + bare.join(", ") : ""}`);
  // the record in plain words (the user, 30 September, for the deck's screenshots): no store id in its Source column, no
  // raw "key: value" of the register in its Detail column; and no swatch on the navy strip (it read as an empty checkbox)
  {
    dr = await openCar(showcase); dr.querySelector("details").open = true; await sleep(150);
    const rows = [...dr.querySelectorAll(".dr-events tbody tr")];
    const raw = rows.map(tr => `${tr.children[3].textContent} | ${tr.children[5].textContent}`)
      .filter(t => /_|\b(Nee|Ja|stationwagen)\b|make: |export: /.test(t));
    // each source named as the page's source list names it ("Each source's date"), so the two never disagree
    const known = new Set([...P.sources.map(s => s.name), "Claims controls", "this page"]);
    const odd = [...new Set(rows.map(tr => tr.children[3].textContent).filter(x => !known.has(x)))];
    await closeCar();
    let sw = 0; for (let i = 0; i < n; i++) { await show(i); sw += panel().querySelectorAll(".band:not(.compact) .band-sw").length; }
    add("The record in plain words, its sources named as the source list does; no swatch on the navy strip",
      rows.length > 0 && !raw.length && !odd.length && sw === 0,
      `car ${showcase}: ${rows.length} events${raw.length ? "; raw: " + raw.slice(0, 3).join("; ") : ", no store id or raw value"}` +
      `${odd.length ? "; names not in the source list: " + odd.join(", ") : ""}; ${sw} swatches on navy`);
  }
  const bodyOf = Object.fromEntries(idx.map(x => [x.car, x.body])), cells = [], wrong = [];
  const readBodies = label => panel().querySelectorAll(".queue tbody tr").forEach(tr => {
    const id = Number((tr.querySelector("button.car") || {}).textContent), b = tr.querySelector(".body-ic");
    cells.push(label); if (!b || b.getAttribute("aria-label") !== bodyOf[id]) wrong.push(`${label} ${id}`); });
  await show(2); readBodies("upgrade");
  await show(3); readBodies("incoming");
  [...panel().querySelectorAll(".seg button")].find(b => b.textContent === "Pricing desk").click(); await sleep(200);
  readBodies("desk");
  add("Body types: every model cell in the queues shows its car's silhouette, named as the export names it",
    cells.length >= 30 && !wrong.length, `${cells.length - wrong.length} of ${cells.length} rows${wrong.length ? "; off: " + wrong.slice(0, 4).join(", ") : ""}`);
  const js = [...document.scripts].map(s => s.textContent).join("");
  add("Licence: Carbon's and MDI's Apache 2.0, NumberFlow's and AutoAnimate's MIT notices ship inside the page",
    js.includes("@carbon/icons 11.89.0") && js.includes("Copyright 2015 IBM Corp.")
      && js.includes("Pictogrammers Free License") && (js.match(/END OF TERMS AND CONDITIONS/g) || []).length >= 2
      && js.includes("Copyright (c) 2024 Maxwell Barvian") && js.includes("Copyright 2022 FormKit Inc.")
      && !/lucide/i.test(js),
    "Carbon's (with the Apache License 2.0), MDI's (with it too), NumberFlow's and AutoAnimate's notices, verbatim, in the page's script; no Lucide left");
  // the header's theme toggle (after the tool pass, the user): top right; a click flips the page and its charts, says
  // so and is remembered; a second click goes back. The check leaves the theme and the remembered pick as it found them.
  {
    await show(0);
    const btn = document.querySelector(".theme-btn"), a0 = root.getAttribute("data-theme");
    let s0 = null; try { s0 = localStorage.getItem("vvl-theme"); } catch { /* blocked */ }
    const eff = () => root.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const bg = () => getComputedStyle(document.body).backgroundColor;
    const ink = () => { const tx = panel().querySelector(".echart svg text"); return tx ? getComputedStyle(tx).fill : "no chart text"; };
    const w = btn.closest(".wrap"), r = btn.getBoundingClientRect(), h1 = document.querySelector(".top h1").getBoundingClientRect();
    const corner = Math.abs(w.getBoundingClientRect().right - parseFloat(getComputedStyle(w).paddingRight) - r.right) <= 1
      && r.top <= h1.top + 8;
    const t0 = eff(), bg0 = bg(), ink0 = ink(), on0 = btn.getAttribute("aria-checked");
    btn.click(); await sleep(400);
    const t1 = eff(), bg1 = bg(), ink1 = ink(), on1 = btn.getAttribute("aria-checked");
    let s1 = null; try { s1 = localStorage.getItem("vvl-theme"); } catch { /* blocked */ }
    btn.click(); await sleep(400);
    const t2 = eff(), bg2 = bg(), ink2 = ink(), on2 = btn.getAttribute("aria-checked");
    a0 ? root.setAttribute("data-theme", a0) : root.removeAttribute("data-theme");
    try { s0 === null ? localStorage.removeItem("vvl-theme") : localStorage.setItem("vvl-theme", s0); } catch { /* blocked */ }
    await sleep(300);
    add("Theme toggle: top right; a click flips the page and its charts, says so and is remembered; a second goes back",
      corner && t1 !== t0 && bg1 !== bg0 && ink1 !== ink0 && on0 === String(t0 === "dark") && on1 === String(t1 === "dark")
        && s1 === t1 && t2 === t0 && bg2 === bg0 && ink2 === ink0 && on2 === on0,
      `${corner ? "top right" : "not in the corner"}; ${t0} → ${t1} → ${t2}; page ${bg0} → ${bg1}; chart text ${ink0} → ${ink1}; remembered "${s1}"`);
  }
  // glass (the user: a small dose of Apple's Liquid Glass): the sticky tab row is frosted in light and dark; its labels
  // hold 4.5:1 over every colour that can scroll beneath, the tint laid over each as a solid (blur only helps); the page
  // passes under the row while it sticks; solid when the system asks for less transparency or more contrast, or the
  // browser has no backdrop-filter (the rules read from the page; under either setting the row itself must be solid)
  {
    await show(0);
    const bar = document.querySelector(".tabs-bar"), a0 = root.getAttribute("data-theme");
    const solid = matchMedia("(prefers-reduced-transparency: reduce), (prefers-contrast: more)").matches;
    const UNDER = ["--band", "--on-band", "--on-band2", "--page", "--surface", "--overlay", "--ink", "--ink2", "--series",
      "--ord1", "--ord2", "--vband", "--vtick", "--bar", "--deemph", "--crit", "--warn", "--good"];
    const per = [];
    for (const theme of ["light", "dark"]) {
      root.setAttribute("data-theme", theme); await sleep(50);
      document.getAnimations().forEach(a => a.finish());   // the labels' colour transition, else read mid-way
      const cs = getComputedStyle(bar), tint = hex(cs.backgroundColor), v = k => hex(getComputedStyle(root).getPropertyValue(k));
      const labels = new Set([...bar.querySelectorAll(".tab, .office-btn, .office-btn .apart")].map(e => getComputedStyle(e).color));
      let worst = [99];
      for (const k of UNDER) for (const l of labels) { const r = ratio(hex(l), over(tint, v(k))); if (r < worst[0]) worst = [r, k]; }
      const ok = solid ? cs.backdropFilter === "none" && tint.a === 1
        : /blur\(20px\)/.test(cs.backdropFilter) && /saturate\((1\.8|180%)\)/.test(cs.backdropFilter) && tint.a > .5 && tint.a < 1;
      per.push([theme, ok && worst[0] >= 4.5, `${theme} ${solid ? "solid" : `tint ${tint.a.toFixed(2)}, ${cs.backdropFilter}`}, lowest ${worst[0].toFixed(2)} (${worst[1]})`]);
    }
    a0 ? root.setAttribute("data-theme", a0) : root.removeAttribute("data-theme"); await sleep(50);
    const all = [...document.styleSheets].flatMap(x => [...x.cssRules]);
    const inner = r => [...(r.cssRules || [])].find(x => (x.selectorText || "").includes(".tabs-bar"));
    const mr = all.find(r => r instanceof CSSMediaRule && /prefers-reduced-transparency: reduce/.test(r.conditionText)
      && /prefers-contrast: more/.test(r.conditionText) && inner(r));
    const sr = all.find(r => r instanceof CSSSupportsRule && /^not/.test(r.conditionText.trim()) && /backdrop-filter/.test(r.conditionText) && inner(r));
    const fallback = !!mr && !!sr && inner(mr).style.backdropFilter === "none" && /var\(--surface\)/.test(inner(mr).style.background)
      && /var\(--surface\)/.test(inner(sr).style.background);
    const band = panel().querySelector(".band"), top0 = band.getBoundingClientRect().top + scrollY;
    scrollTo(0, top0 + 20); await sleep(100);
    const br = bar.getBoundingClientRect(), stuck = Math.abs(br.top) < 1;
    const beneath = document.elementsFromPoint(br.left + br.width / 2, br.top + br.height / 2).some(e => band.contains(e));
    scrollTo(0, 0); await sleep(100);
    add("Glass: the tab row is frosted in light and dark, its labels ≥ 4.5:1 over all that scrolls beneath; solid under reduced transparency or more contrast",
      per.every(p => p[1]) && stuck && beneath && fallback,
      `${per.map(p => p[2]).join("; ")}; ${stuck && beneath ? "the band passes under the row while it sticks" : `stuck ${stuck}, band beneath ${beneath}`}; fallbacks ${fallback ? "for less transparency, more contrast and no backdrop-filter" : "missing"}`);
  }
  // the frosted backdrop (Liquid Glass, part 2): when a car's record opens, the page behind it blurs 8 px as it dims; the
  // record itself stays solid; no blur under reduced transparency or more contrast (the rule read from the page)
  {
    await show(0);
    const solid = matchMedia("(prefers-reduced-transparency: reduce), (prefers-contrast: more)").matches;
    const d = await openCar(showcase), scs = getComputedStyle(document.querySelector(".scrim")), ds = getComputedStyle(d);
    const blur = scs.backdropFilter, dim = hex(scs.backgroundColor).a, recA = hex(ds.backgroundColor).a, recF = ds.backdropFilter;
    await closeCar();
    const mr = [...document.styleSheets].flatMap(x => [...x.cssRules]).find(r => r instanceof CSSMediaRule
      && /prefers-reduced-transparency: reduce/.test(r.conditionText) && /prefers-contrast: more/.test(r.conditionText)
      && [...r.cssRules].some(x => x.selectorText === ".scrim" && x.style.backdropFilter === "none"));
    add("Frosted backdrop: behind the car's record the page blurs 8 px as it dims; the record stays solid; no blur under reduced transparency or more contrast",
      (solid ? blur === "none" : blur === "blur(8px)") && dim > 0 && dim < 1 && recA === 1 && recF === "none" && !!mr,
      `backdrop ${blur}, dimmed ${dim.toFixed(2)}; record ${recA === 1 ? "solid" : "translucent " + recA.toFixed(2)}, filter ${recF}; fallback ${mr ? "in place" : "missing"}`);
  }
  // controls (Liquid Glass, part 3): the two sliders' knobs grow into glass while dragged, their ring in the title blue
  // at 3:1 or more on the header and the record in both themes; each track fills to its value (--p, set by the page);
  // the knob stays solid under reduced transparency or more contrast (the rules read from the page)
  {
    await show(0);
    const lv = document.querySelector("#lvl"), pOf = el => parseFloat(getComputedStyle(el).getPropertyValue("--p"));
    const want = el => (el.value - el.min) / (el.max - el.min);
    setVal(lv, 12); await sleep(100); const f1 = [pOf(lv), want(lv)];
    setVal(lv, 0); await sleep(100); const f0 = [pOf(lv), want(lv)];
    document.getAnimations().forEach(a => a.finish());
    const d = await openCar(showcase), ar = d.querySelector("#asofr"), f2 = [pOf(ar), want(ar)]; await closeCar();
    const fills = [f1, f0, f2].every(([got, w]) => Math.abs(got - w) < 1e-6);
    const flat = rs => rs.flatMap(r => r.cssRules ? [r, ...flat([...r.cssRules])] : [r]);
    const all = flat([...document.styleSheets].flatMap(x => [...x.cssRules]));
    const pressed = all.find(r => r.parentRule === null && /:active::-webkit-slider-thumb/.test(r.selectorText || ""));
    const knob = all.find(r => r.parentRule === null && /range"\]::-webkit-slider-thumb$/.test(r.selectorText || ""));
    const shapeOk = !!knob && knob.style.width === "28px" && knob.style.height === "16px" && knob.style.borderRadius === "8px";
    const track = all.find(r => r.parentRule === null && /range"\]::-webkit-slider-runnable-track$/.test(r.selectorText || ""));
    const held = all.find(r => r.parentRule === null && /range"\]:active$/.test(r.selectorText || ""));
    const gapOk = !!track && (track.style.background.match(/var\(--knob-half\)/g) || []).length === 4
      && !!held && held.style.getPropertyValue("--knob-half").trim() === "21px";
    const glassOk = shapeOk && gapOk && !!pressed && /scale\(1\.5\)/.test(pressed.style.transform) && /var\(--knob-glass\)/.test(pressed.style.background)
      && /var\(--knob-rim\)/.test(pressed.style.boxShadow);
    const solidOk = all.some(r => r instanceof CSSMediaRule && /prefers-reduced-transparency: reduce/.test(r.conditionText)
      && /prefers-contrast: more/.test(r.conditionText)
      && [...r.cssRules].some(x => /:active::-webkit-slider-thumb/.test(x.selectorText || "") && /var\(--title\)/.test(x.style.background)));
    const a0 = root.getAttribute("data-theme"), rings = [];
    for (const theme of ["light", "dark"]) {
      root.setAttribute("data-theme", theme); await sleep(50);
      const v = k => hex(getComputedStyle(root).getPropertyValue(k));
      for (const bg of ["--surface", "--overlay"]) rings.push(ratio(v("--title"), v(bg)));
    }
    a0 ? root.setAttribute("data-theme", a0) : root.removeAttribute("data-theme"); await sleep(50);
    const low = Math.min(...rings);
    add("Controls: the sliders' rounded knobs turn to glass while dragged, ringed at 3:1 or more; each track fills to its value; solid under reduced transparency or more contrast",
      fills && glassOk && solidOk && low >= 3,
      `fills ${[f1, f0, f2].map(([g]) => g.toFixed(3)).join(", ")} (as the values); knob ${shapeOk ? "28 × 16 px, ends rounded" : "not as set"}, line ${gapOk ? "stops at its edges, 21 px either side when held" : "runs through it"}, pressed ${glassOk ? "150%, frosted, rim" : "rule missing"}; ring lowest ${low.toFixed(2)}; fallback ${solidOk ? "in place" : "missing"}`);
  }
  // motion (after the tool pass, the user): a view's tiles then cards arrive in reading order (300 ms each, 40 ms apart)
  // and end in place; the open tab's line slides under the tab opened, in its colour; the theme's switch goes through the
  // browser's view transition where it has one
  {
    await show(0);
    const ink = document.querySelector(".tab-ink"), t1 = tabs()[1];
    t1.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 })); await sleep(20);
    const els = [...panel().querySelectorAll(".tiles > :not(.tiles-badge), .grid > *")];
    const cs = els.map(e => getComputedStyle(e)), delays = cs.map(c => Math.round(parseFloat(c.animationDelay) * 1000));
    const started = reduce ? cs.every(c => c.animationName === "none")
      : cs.every(c => c.animationName === "rise-in" && c.animationDuration === "0.3s" && /0\.05, 0\.7, 0\.1, 1/.test(c.animationTimingFunction))
        && delays.every((d, k) => k === 0 || d - delays[k - 1] === 40 || (d === delays[k - 1] && d === 360));
    const vaText = `${els.length} tiles and cards, ${cs[0].animationName} ${cs[0].animationDuration}, delays ${delays.join(", ")} ms`;
    await sleep(800);
    const still = [...ink.getAnimations(), ...els.flatMap(e => e.getAnimations())];   // running only where no frames are drawn
    still.forEach(a => a.finish());
    const ir = ink.getBoundingClientRect(), tr = t1.getBoundingClientRect();
    const landed = Math.abs(ir.left - tr.left) <= 1 && Math.abs(ir.width - tr.width) <= 1
      && els.every(e => { const c = getComputedStyle(e); return c.opacity === "1" && c.transform === "none"; })
      && getComputedStyle(ink).backgroundColor === getComputedStyle(t1.querySelector(".sw")).backgroundColor;
    const btn = document.querySelector(".theme-btn"), a0 = root.getAttribute("data-theme"), has = !!document.startViewTransition;
    let s0 = null; try { s0 = localStorage.getItem("vvl-theme"); } catch { /* blocked */ }
    let calls = 0;
    if (has) { const svt = document.startViewTransition; document.startViewTransition = function (...x) { calls++; return svt.apply(document, x); }; }
    btn.click(); await sleep(450); btn.click(); await sleep(450);
    delete document.startViewTransition;
    a0 ? root.setAttribute("data-theme", a0) : root.removeAttribute("data-theme");
    try { s0 === null ? localStorage.removeItem("vvl-theme") : localStorage.setItem("vvl-theme", s0); } catch { /* blocked */ }
    const faded = !has || calls === (reduce ? 0 : 2);
    add("Motion: tiles then cards arrive in reading order and end in place; the tab's line slides under the tab opened, in its colour; the theme cross-fades",
      started && landed && faded,
      `${vaText}; line at ${Math.round(ir.left)} px under the tab at ${Math.round(tr.left)} px; theme: ${has ? `${calls} view transitions for 2 switches` : "no view transitions in this browser, so it switches at once"}${still.length ? `; the page is hidden, so ${still.length} motions were ended to read where they land` : ""}`);
    await show(0); await sleep(300);
  }
  // charts draw in (after the tool pass, part 5): in each team's view every chart changes after the view opens (600 ms,
  // its points up to 240 ms apart) and is still by 1.5 s; under reduced motion it is drawn at once
  {
    const per = [];
    let ok = true;
    for (let i = 0; i < tabs().length; i++) {
      if (i === 0) await show(1);   // leave Management so that opening it draws its charts again
      tabs()[i].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
      const svgs = () => [...panel().querySelectorAll(".echart svg")].map(x => x.innerHTML);
      await sleep(60); const a = svgs(); await sleep(500); const m = svgs(); await sleep(1000); const b = svgs(); await sleep(200); const c = svgs();
      const moved = a.filter((x, k) => x !== m[k]).length, settled = b.every((x, k) => x === c[k]);
      ok = ok && settled && (reduce ? moved === 0 : moved === a.length && a.length > 0);
      per.push(`${name(i).split(" ")[0]} ${moved} of ${a.length}`);
    }
    await show(0);
    add("Charts draw in: every chart of a view moves after the view opens, and is still by 1.5 s", ok,
      `${reduce ? "reduced motion: drawn at once; " : ""}moving in the first 0.5 s: ${per.join(", ")}${document.hidden ? "; the page is hidden: no frames" : ""}`);
  }
  // queue rows glide (after the tool pass, part 8): a sort moves each row to its new place (240 ms), then the rows rest
  // at 48 or 32 px; under reduced motion they jump
  {
    await show(1);
    const q = panel().querySelector(".queue"), trs = () => [...q.querySelectorAll("tbody tr")];
    const busy = () => trs().filter(tr => tr.getAnimations().some(x => x.playState === "running")).length;
    const th = [...q.querySelectorAll("th .sort")].find(b => b.closest("th").getAttribute("aria-sort") === "none");
    const order = () => trs().map(tr => tr.textContent).join("|"), before = order();
    q.scrollIntoView({ block: "start" }); await sleep(150);   // AutoAnimate moves only what is on screen, as a person sees it
    th.click(); await sleep(40);
    const moving = busy(); await sleep(600);
    const resting = busy(), hs = trs().map(tr => Math.round(tr.getBoundingClientRect().height));
    add("Queue rows glide: a sort moves each row to its new place, then they rest at 48 or 32 px",
      (reduce ? moving === 0 : moving > 0) && resting === 0 && order() !== before && hs.every(h => h === 48 || h === 32),
      `${moving} of ${trs().length} rows moving 40 ms after a sort by "${th.textContent.replace(/[↑↓↕]/g, "").trim()}", ${resting} after 0.6 s; rows ${[...new Set(hs)].join(" and ")} px${document.hidden ? "; the page is hidden: no frames" : ""}`);
    await show(0);
  }
  // a row opens into the car's record (after the tool pass, part 9): the row and the drawer share one view transition
  // name, so the browser grows the row into the drawer and shrinks it back on close; names and state cleared after
  {
    await show(3);
    const btn = panel().querySelector(".queue tbody .car"), tr = btn.closest("tr"), id = btn.textContent;
    tr.scrollIntoView({ block: "center" }); await sleep(150);
    const has = !!document.startViewTransition, names = [];
    if (has) { const svt = document.startViewTransition; document.startViewTransition = function (...x) { names.push(tr.style.viewTransitionName || "(none)"); return svt.apply(document, x); }; }
    btn.focus(); btn.click(); await sleep(600);
    const d = document.querySelector(".drawer"), opened = !!d && d.textContent.includes(id);
    const dName = d ? getComputedStyle(d).viewTransitionName : "", rowOpen = tr.style.viewTransitionName;
    await closeCar(); await sleep(300);
    delete document.startViewTransition;
    const clean = !document.querySelector(".drawer") && tr.style.viewTransitionName === "" && !document.documentElement.dataset.vt;
    const morphed = has && !reduce ? names.length === 2 && names[0] === "car-record" && dName === "car-record" && rowOpen === "" : names.length === 0;
    add("A row opens into the car's record and closes back into it; the names clear and focus returns",
      opened && morphed && clean && document.activeElement === btn,
      `car ${id}: ${has ? `${names.length} view transitions (the row named "${names[0]}" as it opened), the drawer named "${dName}"` : "no view transitions in this browser: it slides as before"}; closed clean ${clean}; focus back ${document.activeElement === btn}`);
    await show(0);
  }
  add("Export checks", D.checks.every(c => c[1]), `${D.checks.filter(c => c[1]).length} of ${D.checks.length}`);

  await show(0);
  window.LOOK = out;
  const fails = out.filter(o => o.pass === "FAIL").length;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const box = document.createElement("section"); box.id = "lookcheck"; box.className = "wrap"; box.style.padding = "16px 24px";
  box.innerHTML = `<h2 style="font-size:1rem;line-height:1.25rem;margin:0 0 8px">Look checks at ${W} × ${H}${root.getAttribute("data-theme") === "dark" ? ", dark" : ""}: ${out.length - fails} of ${out.length} pass</h2>` +
    `<div class="twin"><table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>` +
    out.map(o => `<tr><td>${esc(o.check)}</td><td>${o.pass}</td><td>${esc(o.detail)}</td></tr>`).join("") + "</tbody></table></div>";
  document.body.insertBefore(box, document.body.firstChild);
  console.log("LOOK " + JSON.stringify({ width: W, height: H, pass: out.length - fails, of: out.length, fails: out.filter(o => o.pass === "FAIL") }));
})();
