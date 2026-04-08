'use strict';
(function () {

var IDX = [
  // GETTING STARTED
  { page:'Getting Started', url:'getting-started/', anchor:'what-is-multai',
    title:'What MultAI does',
    text:'MultAI submits a single prompt to 7 AI platforms simultaneously Claude.ai ChatGPT Gemini Grok DeepSeek Perplexity Microsoft Copilot and collates results into a markdown archive. Runs as Claude Code skill or Cowork skill.' },
  { page:'Getting Started', url:'getting-started/', anchor:'prerequisites',
    title:'Prerequisites — Python, Chrome, Claude Code',
    text:'Required Python 3.11 or later. Google Chrome installed. Claude Code with MultAI plugin installed. Optional ANTHROPIC_API_KEY or GOOGLE_API_KEY for agent fallback.' },
  { page:'Getting Started', url:'getting-started/', anchor:'install',
    title:'Installing MultAI',
    text:'Install via Claude Code: /plugin install alo-exp/multai. Or clone repo and run bash setup.sh. Setup installs Playwright openpyxl creates .venv launches Chrome with CDP on port 9222.' },
  { page:'Getting Started', url:'getting-started/', anchor:'chrome-setup',
    title:'Setting up Chrome with CDP',
    text:'MultAI requires Chrome with remote debugging enabled on port 9222. Run bash setup.sh to launch Chrome automatically. Manual: google-chrome --remote-debugging-host=127.0.0.1 --remote-debugging-port=9222. Chrome must stay open during runs.' },
  { page:'Getting Started', url:'getting-started/', anchor:'first-run',
    title:'Your first run — submit a prompt to all platforms',
    text:'Invoke /multai in Claude Code. MultAI asks for your prompt mode and platforms. Results saved to output/ directory as markdown files then collated into archive. Cowork tab uses Claude-in-Chrome sequential path.' },
  { page:'Getting Started', url:'getting-started/', anchor:'whats-next',
    title:"What's next — Concepts, Running MultAI, Reference",
    text:'After first run read Core Concepts to understand DEEP vs REGULAR mode and rate limiting. Read Running MultAI for platform selection output format and consolidation.' },

  // CONCEPTS
  { page:'Core Concepts', url:'concepts/', anchor:'platforms',
    title:'The 7 platforms — Claude, ChatGPT, Gemini, Grok, DeepSeek, Perplexity, Copilot',
    text:'MultAI automates 7 AI web UIs: claude claude.ai ChatGPT chatgpt OpenAI gemini Google Gemini grok xAI deepseek DeepSeek perplexity microsoft copilot. Each platform has a short identifier used with --platforms flag.' },
  { page:'Core Concepts', url:'concepts/', anchor:'cdp',
    title:'How CDP browser automation works',
    text:'Chrome DevTools Protocol CDP connects Playwright to your existing Chrome on localhost 127.0.0.1 port 9222. MultAI opens tabs for each platform logs in via your saved sessions injects prompts extracts responses. No API keys needed for platform access.' },
  { page:'Core Concepts', url:'concepts/', anchor:'modes',
    title:'DEEP vs REGULAR mode',
    text:'REGULAR mode standard chat response. DEEP mode activates Deep Research or extended thinking on platforms that support it: ChatGPT Deep Research Gemini Deep Research DeepSeek DeepThink. DEEP mode takes longer but produces more thorough analysis.' },
  { page:'Core Concepts', url:'concepts/', anchor:'rate-limiting',
    title:'Rate limiting — fairness across platforms',
    text:'MultAI tracks per-platform usage and enforces cooldown periods after hitting platform rate limits. Rate limit state persisted in ~/.chrome-playwright/rate-limit-state.json. Platforms that hit limits are skipped gracefully.' },
  { page:'Core Concepts', url:'concepts/', anchor:'agent-fallback',
    title:'Agent fallback — browser-use when Playwright fails',
    text:'If Playwright automation fails for a platform MultAI falls back to browser-use agent powered by Claude or Gemini API. Requires ANTHROPIC_API_KEY or GOOGLE_API_KEY in .env. Agent fallback is slower but more resilient.' },
  { page:'Core Concepts', url:'concepts/', anchor:'session-modes',
    title:'Session modes — parallel vs sequential',
    text:'Claude Code tab runs all 7 platforms in parallel using asyncio. Cowork tab runs platforms sequentially via Claude-in-Chrome MCP tools. Parallel mode is faster. Sequential mode requires no setup beyond the Chrome extension.' },
  { page:'Core Concepts', url:'concepts/', anchor:'output',
    title:'Output files — per-platform responses and collated archive',
    text:'Each platform response saved as output/YYYY-MM-DD-task-name-platform.md wrapped in untrusted_platform_response tags. All responses collated into archive/YYYY-MM-DD-task-name-archive.md by collate_responses.py.' },

  // RUNNING MULTAI
  { page:'Running MultAI', url:'running-multai/', anchor:'overview',
    title:'Running MultAI — end-to-end workflow',
    text:'Invoke /multai select platforms and mode submit prompt wait for all platforms to complete read collated archive optionally invoke /consolidator for synthesis. Full run takes 2-15 minutes depending on mode and platform speed.' },
  { page:'Running MultAI', url:'running-multai/', anchor:'invoke',
    title:'Invoking /multai from Claude Code',
    text:'Type /multai in Claude Code chat. Skill detects runtime Code or Cowork routes accordingly. For Code tab runs Python orchestrator. Provide prompt inline or via file with --prompt-file flag.' },
  { page:'Running MultAI', url:'running-multai/', anchor:'platforms-flag',
    title:'Selecting platforms with --platforms',
    text:'Use --platforms flag to run subset: --platforms claude chatgpt gemini. Available identifiers: claude chatgpt gemini grok deepseek perplexity copilot. Omit flag to run all 7. Comma or space separated.' },
  { page:'Running MultAI', url:'running-multai/', anchor:'output',
    title:'Reading the output — per-platform files and archive',
    text:'Output directory contains one .md file per platform. Archive directory contains collated file with all responses. Each response wrapped in untrusted_platform_response XML tags. Task name derived from --task-name flag or prompt.' },
  { page:'Running MultAI', url:'running-multai/', anchor:'cowork',
    title:'Cowork path — Claude-in-Chrome sequential mode',
    text:'In Cowork tab MultAI uses Claude-in-Chrome MCP tools instead of Playwright. Platforms run one at a time. Requires Claude-in-Chrome browser extension installed and connected. No Python or Playwright required.' },
  { page:'Running MultAI', url:'running-multai/', anchor:'consolidator',
    title:'Consolidating results with /consolidator',
    text:'After MultAI run invoke /consolidator to synthesize all platform responses into a single structured intelligence report. Consolidator reads the archive file identifies consensus points and divergences.' },

  // REFERENCE
  { page:'Reference', url:'reference/', anchor:'platform-ids',
    title:'Platform identifiers',
    text:'claude claude.ai ChatGPT chatgpt gemini Google Gemini grok xAI Grok deepseek DeepSeek perplexity copilot Microsoft Copilot. Use with --platforms flag. Case insensitive.' },
  { page:'Reference', url:'reference/', anchor:'cli-flags',
    title:'CLI flags — --prompt, --platforms, --mode, --task-name, --output-dir',
    text:'--prompt inline prompt text. --prompt-file path to prompt file. --platforms space separated platform ids. --mode REGULAR or DEEP default REGULAR. --task-name output filename slug. --output-dir output directory default output/. --fresh force new Chrome instance. --with-fallback enable agent fallback.' },
  { page:'Reference', url:'reference/', anchor:'env-config',
    title:'.env configuration — API keys for agent fallback',
    text:'.env file at project root. ANTHROPIC_API_KEY enables Anthropic Claude agent fallback. GOOGLE_API_KEY enables Google Gemini agent fallback. CDP_PORT default 9222. Keys optional only needed for agent fallback.' },
  { page:'Reference', url:'reference/', anchor:'output-files',
    title:'Output files and directory structure',
    text:'output/ directory per-platform markdown files YYYY-MM-DD-task-platform.md. archive/ directory collated YYYY-MM-DD-task-archive.md. status.json current run status. agent-fallback-log.json agent fallback events.' },
  { page:'Reference', url:'reference/', anchor:'rate-limit-state',
    title:'Rate limit state file',
    text:'~/.chrome-playwright/rate-limit-state.json persists per-platform rate limit tracking. Automatically updated by orchestrator. Delete to reset all rate limits. tab-state.json tracks open tab IDs.' },

  // TROUBLESHOOTING
  { page:'Troubleshooting', url:'troubleshooting/', anchor:'chrome',
    title:'Chrome / CDP connection issues',
    text:'Chrome not found on port 9222 ensure Chrome is running with --remote-debugging-port=9222 flag. Run bash setup.sh to launch automatically. Cannot connect check 127.0.0.1 not 0.0.0.0. Only one Chrome instance allowed.' },
  { page:'Troubleshooting', url:'troubleshooting/', anchor:'auth',
    title:'Platform authentication — login required',
    text:'Platform shows login page MultAI cannot log in automatically. Open Chrome navigate to platform log in manually then re-run. Sessions persist via Chrome profile copy in ~/.chrome-playwright/.' },
  { page:'Troubleshooting', url:'troubleshooting/', anchor:'rate-limit',
    title:'Rate limit hit — platform skipped or slow',
    text:'Platform skipped due to rate limit wait for cooldown period or delete rate-limit-state.json to reset. ChatGPT Deep Research has daily quota. Gemini Deep Research has monthly cap. Run --mode REGULAR to avoid DR limits.' },
  { page:'Troubleshooting', url:'troubleshooting/', anchor:'extraction',
    title:'Extraction failures — empty or wrong response',
    text:'Response empty check platform loaded correctly. Wrong content extracted check for rate limit message or login redirect. Prompt echo detected means platform echoed prompt back use different platform. Try --fresh flag to reset browser state.' },
  { page:'Troubleshooting', url:'troubleshooting/', anchor:'agent-fallback',
    title:'Agent fallback errors — API key issues, timeout',
    text:'Agent fallback requires ANTHROPIC_API_KEY or GOOGLE_API_KEY in .env. API key not found set key in .env file. Agent timeout increase --max-steps or use --mode REGULAR for simpler prompts. Install browser-use with bash setup.sh --with-fallback.' },
  { page:'Troubleshooting', url:'troubleshooting/', anchor:'output',
    title:'Output and archive issues — missing files, wrong content',
    text:'Output file missing check status.json for error. Archive not created run python3 skills/orchestrator/engine/collate_responses.py manually. Task name contains special characters use --task-name with alphanumeric slug.' },
];

function _score(entry, terms) {
  var hay = (entry.title + ' ' + entry.text + ' ' + entry.page).toLowerCase();
  var score = 0, matched = 0;
  for (var i = 0; i < terms.length; i++) {
    var t = terms[i];
    if (hay.indexOf(t) === -1) continue;
    matched++;
    score += 1;
    if (entry.title.toLowerCase().indexOf(t) !== -1) score += 2;
    if (entry.page.toLowerCase().indexOf(t) !== -1) score += 0.5;
  }
  if (matched === 0) return 0;
  if (terms.length > 1 && matched < Math.ceil(terms.length * 0.5)) return 0;
  return score;
}

function doSearch(query) {
  if (!query || query.trim().length < 2) return [];
  var terms = query.toLowerCase().trim().split(/\s+/).filter(function(t){ return t.length >= 2; });
  var results = [];
  for (var i = 0; i < IDX.length; i++) {
    var s = _score(IDX[i], terms);
    if (s > 0) results.push({ entry: IDX[i], score: s });
  }
  results.sort(function(a, b){ return b.score - a.score; });
  return results.slice(0, 8).map(function(r){ return r.entry; });
}

function _url(e) { return e.anchor ? e.url + '#' + e.anchor : e.url; }

function _excerpt(text, terms) {
  var lower = text.toLowerCase(), best = 0;
  for (var i = 0; i < terms.length; i++) {
    var idx = lower.indexOf(terms[i]);
    if (idx !== -1) { best = idx; break; }
  }
  var start = Math.max(0, best - 40);
  var snippet = text.slice(start, start + 110).trim();
  if (start > 0) snippet = '\u2026' + snippet;
  if (start + 110 < text.length) snippet += '\u2026';
  return snippet;
}

function _initNavSearch() {
  var inp = document.getElementById('nav-search-input');
  var box = document.getElementById('nav-search-results');
  if (!inp || !box) return;
  var hideTimer;
  function render(q) {
    var results = doSearch(q);
    if (!results.length) { box.classList.remove('open'); box.innerHTML = ''; return; }
    var terms = q.toLowerCase().trim().split(/\s+/);
    box.innerHTML = results.map(function(r) {
      return '<a href="' + _url(r) + '" class="nsr-item">' +
        '<span class="nsr-page">' + r.page + '</span>' +
        '<span class="nsr-title">' + r.title + '</span>' +
        '<span class="nsr-excerpt">' + _excerpt(r.text, terms) + '</span>' +
        '</a>';
    }).join('');
    box.classList.add('open');
  }
  inp.addEventListener('input', function(){ render(this.value); });
  inp.addEventListener('keydown', function(e) {
    var items = box.querySelectorAll('.nsr-item');
    var active = box.querySelector('.nsr-active');
    if (e.key === 'Escape') { box.classList.remove('open'); inp.blur(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!active) { if(items[0]) items[0].classList.add('nsr-active'); }
      else { active.classList.remove('nsr-active'); var nx=active.nextElementSibling; if(nx) nx.classList.add('nsr-active'); }
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (active) { active.classList.remove('nsr-active'); var pv=active.previousElementSibling; if(pv) pv.classList.add('nsr-active'); }
    }
    if (e.key === 'Enter') {
      var sel = box.querySelector('.nsr-active');
      if (sel) { e.preventDefault(); window.location.href = sel.href; }
    }
  });
  inp.addEventListener('blur', function(){ hideTimer = setTimeout(function(){ box.classList.remove('open'); }, 150); });
  inp.addEventListener('focus', function(){ clearTimeout(hideTimer); if(inp.value.length>=2) render(inp.value); });
}

function _initHelpSearch() {
  var inp = document.getElementById('search-input');
  var sec = document.getElementById('search-results-section');
  var lst = document.getElementById('search-results-list');
  var main = document.getElementById('main-help-content');
  if (!inp || !sec || !lst || !main) return;
  inp.addEventListener('input', function() {
    var q = this.value.trim();
    if (q.length < 2) { sec.style.display='none'; main.style.display=''; lst.innerHTML=''; return; }
    var results = doSearch(q);
    var terms = q.toLowerCase().split(/\s+/);
    main.style.display = 'none';
    sec.style.display = '';
    if (!results.length) {
      lst.innerHTML = '<p class="sr-none">No results for \u201c' + q + '\u201d</p>';
      return;
    }
    lst.innerHTML = results.map(function(r) {
      return '<a href="' + _url(r) + '" class="sr-item">' +
        '<span class="sr-page">' + r.page + '</span>' +
        '<h4 class="sr-title">' + r.title + '</h4>' +
        '<p class="sr-excerpt">' + _excerpt(r.text, terms) + '</p>' +
        '</a>';
    }).join('');
  });
}

document.addEventListener('DOMContentLoaded', function() {
  _initNavSearch();
  _initHelpSearch();
});

})();
