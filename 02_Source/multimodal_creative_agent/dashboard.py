"""轻量本地控制台页面，不依赖前端构建工具。"""

DASHBOARD_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="theme-color" content="#070807" />
  <title>Multimodal Creative Agent · 电影创作工作站</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
      --ink: #070807;
      --ink-soft: #0d100f;
      --panel: rgba(18, 21, 19, .82);
      --panel-solid: #121512;
      --panel-raised: #191d1a;
      --line: rgba(232, 220, 184, .14);
      --line-strong: rgba(232, 220, 184, .28);
      --text: #f5f0e4;
      --muted: #9f9d95;
      --dim: #6f716c;
      --gold: #e0b968;
      --gold-pale: #f0d9a5;
      --green: #68c695;
      --red: #ef8379;
      --blue: #7eb7ce;
      --radius-outer: 24px;
      --radius-inner: 16px;
      --shadow: 0 28px 80px rgba(0, 0, 0, .38), inset 0 1px rgba(255, 255, 255, .03);
    }
    * { box-sizing: border-box; }
    html { color-scheme: dark; background: var(--ink); scroll-behavior: smooth; }
    body {
      margin: 0;
      min-width: 320px;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 82% 4%, rgba(224, 185, 104, .13), transparent 25rem),
        radial-gradient(circle at 4% 52%, rgba(74, 114, 97, .11), transparent 30rem),
        linear-gradient(180deg, #0b0d0c 0%, #070807 100%);
      overflow-x: hidden;
      -webkit-font-smoothing: antialiased;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .28;
      background-image:
        linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px);
      background-size: 64px 64px;
      mask-image: linear-gradient(to bottom, black, transparent 85%);
    }
    button, textarea, input, select { font: inherit; }
    button { touch-action: manipulation; -webkit-tap-highlight-color: rgba(224,185,104,.12); }
    .skip-link { position: fixed; z-index: 20; top: 10px; left: 10px; padding: 10px 14px; color: #15120b; border-radius: 10px; background: var(--gold-pale); transform: translateY(-160%); transition: transform 150ms cubic-bezier(.2,0,0,1); }
    .skip-link:focus { transform: translateY(0); }
    .shell { position: relative; z-index: 1; width: min(1520px, 100%); margin: 0 auto; padding: 22px 28px 54px; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      min-height: 56px;
      padding: 0 2px 18px;
      border-bottom: 1px solid var(--line);
    }
    .brand { display: flex; align-items: center; gap: 13px; min-width: 0; }
    .brand-mark {
      display: grid;
      place-items: center;
      flex: 0 0 auto;
      width: 38px;
      height: 38px;
      color: #15120b;
      border-radius: 12px;
      background: linear-gradient(145deg, var(--gold-pale), #bd8e3d);
      box-shadow: 0 8px 28px rgba(224,185,104,.19), inset 0 1px rgba(255,255,255,.55);
    }
    .brand-copy { min-width: 0; }
    .brand-name { overflow: hidden; font-size: 13px; font-weight: 720; letter-spacing: .13em; white-space: nowrap; text-overflow: ellipsis; }
    .brand-subtitle { margin-top: 3px; color: var(--muted); font-size: 11px; letter-spacing: .05em; }
    .health {
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 8px 13px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(7, 8, 7, .46);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .health::before { content: ""; width: 7px; height: 7px; margin-right: 8px; border-radius: 50%; background: var(--gold); box-shadow: 0 0 0 4px rgba(224,185,104,.1); }
    .health.online::before { background: var(--green); box-shadow: 0 0 0 4px rgba(104,198,149,.1); }
    .health.offline::before { background: var(--red); box-shadow: 0 0 0 4px rgba(239,131,121,.1); }
    .hero {
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(260px, .75fr);
      gap: 36px;
      min-height: 318px;
      margin: 24px 0;
      padding: clamp(28px, 4vw, 56px);
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 30px;
      background:
        linear-gradient(100deg, rgba(14,17,15,.98) 5%, rgba(14,17,15,.84) 48%, rgba(14,17,15,.26) 100%),
        radial-gradient(circle at 82% 45%, rgba(224,185,104,.22), transparent 26%),
        #111411;
      box-shadow: var(--shadow);
      isolation: isolate;
      --spot-x: 82%;
      --spot-y: 38%;
    }
    .hero-glow { position: absolute; z-index: -1; inset: 0; pointer-events: none; background: radial-gradient(circle at var(--spot-x) var(--spot-y), rgba(240,217,165,.16), transparent 23%); opacity: .85; transition-property: background; transition-duration: 220ms; }
    .hero::before {
      content: "";
      position: absolute;
      z-index: -1;
      top: -42%;
      right: -5%;
      width: 48%;
      aspect-ratio: 1;
      border: 1px solid rgba(224,185,104,.23);
      border-radius: 50%;
      box-shadow: 0 0 0 42px rgba(224,185,104,.025), 0 0 0 92px rgba(224,185,104,.018);
    }
    .hero::after {
      content: "";
      position: absolute;
      z-index: -1;
      right: 5%;
      bottom: 12%;
      width: 30%;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--gold), transparent);
      box-shadow: 0 -42px rgba(224,185,104,.15), 0 42px rgba(224,185,104,.09);
      transform: rotate(-13deg);
    }
    .hero-copy { align-self: center; max-width: 790px; }
    .kicker { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; color: var(--gold); font-size: 11px; font-weight: 700; letter-spacing: .22em; text-transform: uppercase; }
    .kicker::before { content: ""; width: 32px; height: 1px; background: currentColor; }
    h1 { max-width: 800px; margin: 0; font-family: Georgia, "Noto Serif SC", serif; font-size: clamp(34px, 5vw, 72px); font-weight: 500; line-height: 1.05; letter-spacing: -.045em; text-wrap: balance; }
    h1 em { color: var(--gold-pale); font-weight: inherit; font-style: normal; }
    .hero-description { max-width: 610px; margin: 22px 0 0; color: #b6b3ab; font-size: clamp(14px, 1.4vw, 17px); line-height: 1.85; text-wrap: pretty; }
    .hero-meta { align-self: stretch; display: grid; grid-template-rows: 1fr auto; min-width: 0; }
    .frame-visual { position: relative; align-self: center; aspect-ratio: 16/10; overflow: hidden; border: 1px solid var(--line-strong); border-radius: 8px; background: linear-gradient(135deg, rgba(224,185,104,.08), transparent 35%), repeating-linear-gradient(90deg, transparent 0 24px, rgba(255,255,255,.025) 25px 26px), #090b09; box-shadow: 0 24px 54px rgba(0,0,0,.45); transform: perspective(900px) rotateY(-7deg) rotateX(2deg); }
    .frame-visual::before, .frame-visual::after { content: ""; position: absolute; left: 12px; right: 12px; height: 8px; background: repeating-linear-gradient(90deg, var(--gold) 0 8px, transparent 8px 18px); opacity: .42; }
    .frame-visual::before { top: 11px; }
    .frame-visual::after { bottom: 11px; }
    .frame-center { position: absolute; inset: 31px 18px; display: grid; place-items: center; border: 1px solid rgba(224,185,104,.14); }
    .frame-center span { color: var(--gold-pale); font-family: Georgia, serif; font-size: clamp(28px, 4vw, 54px); opacity: .86; }
    .frame-center::after { content: ""; position: absolute; left: 9%; right: 9%; top: 50%; height: 1px; background: linear-gradient(90deg, transparent, rgba(240,217,165,.7), transparent); transform: translateY(-50%); animation: scan-line 4.2s ease-in-out infinite; }
    .frame-labels { display: flex; justify-content: space-between; margin-top: 18px; color: var(--dim); font-family: Consolas, monospace; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; }
    .workspace { display: grid; grid-template-columns: minmax(330px, 430px) minmax(0, 1fr); gap: 22px; align-items: start; }
    .workspace-side { display: grid; gap: 18px; }
    .panel {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: var(--radius-outer);
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }
    .panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 21px 22px 17px; border-bottom: 1px solid var(--line); }
    .panel-index { display: block; margin-bottom: 6px; color: var(--gold); font-family: Consolas, monospace; font-size: 10px; letter-spacing: .16em; }
    h2 { margin: 0; font-size: 16px; line-height: 1.3; letter-spacing: .01em; }
    .panel-note { margin: 6px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
    .panel-body { padding: 22px; }
    .field + .field { margin-top: 18px; }
    label { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 0 0 9px; color: #cbc7bd; font-size: 12px; font-weight: 650; }
    label small { color: var(--dim); font-size: 10px; font-weight: 500; }
    textarea, input, select {
      width: 100%;
      color: var(--text);
      border: 1px solid rgba(232,220,184,.16);
      border-radius: var(--radius-inner);
      outline: none;
      background: rgba(4, 6, 5, .56);
      transition-property: border-color, background-color, box-shadow;
      transition-duration: 160ms;
    }
    textarea { min-height: 156px; padding: 15px 16px; line-height: 1.75; resize: vertical; }
    textarea.compact { min-height: 92px; }
    input, select { min-height: 46px; padding: 0 13px; }
    textarea::placeholder, input::placeholder { color: #62645f; }
    textarea:hover, input:hover, select:hover { border-color: rgba(232,220,184,.3); }
    textarea:focus, input:focus, select:focus { border-color: var(--gold); background: rgba(8,10,8,.76); box-shadow: 0 0 0 3px rgba(224,185,104,.11); }
    button {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 42px;
      padding: 9px 14px;
      color: var(--text);
      border: 1px solid var(--line-strong);
      border-radius: 13px;
      background: rgba(255,255,255,.045);
      cursor: pointer;
      transition-property: color, border-color, background-color, transform, box-shadow, opacity;
      transition-duration: 150ms;
      transition-timing-function: cubic-bezier(.2, 0, 0, 1);
    }
    button:hover { color: var(--gold-pale); border-color: rgba(224,185,104,.48); background: rgba(224,185,104,.075); }
    button:focus-visible { outline: 2px solid var(--gold); outline-offset: 3px; }
    button:active { transform: scale(.96); }
    button:disabled { cursor: wait; opacity: .55; }
    button svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 1.8; fill: none; }
    button.primary { min-height: 50px; flex: 1; color: #17130b; border-color: transparent; background: linear-gradient(135deg, var(--gold-pale), #c99743); box-shadow: 0 12px 28px rgba(201,151,67,.18), inset 0 1px rgba(255,255,255,.55); font-weight: 750; }
    button.primary:hover { color: #100d08; border-color: transparent; background: linear-gradient(135deg, #f7e2b4, #d3a14b); box-shadow: 0 15px 34px rgba(201,151,67,.24), inset 0 1px rgba(255,255,255,.65); }
    button.danger { color: #eaa19a; border-color: rgba(239,131,121,.24); }
    button.danger:hover { color: #ffc1bb; border-color: rgba(239,131,121,.5); background: rgba(239,131,121,.08); }
    .actions { display: flex; gap: 10px; margin-top: 20px; }
    .notice { display: flex; align-items: center; min-height: 22px; margin-top: 13px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .notice:not(:empty)::before { content: ""; flex: 0 0 auto; width: 6px; height: 6px; margin-right: 8px; border-radius: 50%; background: currentColor; }
    .notice.error { color: var(--red); }
    .notice.good { color: var(--green); }
    .maintenance .panel-head { align-items: center; }
    .maintenance .panel-body { padding-top: 18px; }
    .cleanup-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    pre { max-height: 180px; margin: 15px 0 0; padding: 13px; overflow: auto; color: #8e918a; border-radius: 12px; background: rgba(3,4,3,.44); font: 11px/1.6 Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
    .queue-panel { min-height: 610px; }
    .count { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th, td { padding: 15px 16px; border-bottom: 1px solid rgba(232,220,184,.09); text-align: left; vertical-align: middle; font-size: 12px; }
    th { height: 47px; color: #73766f; background: rgba(0,0,0,.12); font-size: 10px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
    th:nth-child(1) { width: 116px; } th:nth-child(3) { width: 166px; } th:nth-child(4) { width: 136px; } th:nth-child(5) { width: 174px; }
    tbody tr { content-visibility: auto; contain-intrinsic-size: 64px; transition-property: background-color; transition-duration: 140ms; }
    tbody tr:hover { background: rgba(224,185,104,.035); }
    tbody tr:last-child td { border-bottom: 0; }
    td.request { overflow: hidden; color: #dad6cc; white-space: nowrap; text-overflow: ellipsis; }
    .status-badge { display: inline-flex; align-items: center; gap: 7px; min-height: 28px; padding: 5px 9px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.025); white-space: nowrap; }
    .status-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    .status-badge.succeeded { color: var(--green); background: rgba(104,198,149,.06); }
    .status-badge.failed { color: var(--red); background: rgba(239,131,121,.06); }
    .status-badge.running, .status-badge.retrying { color: var(--gold); background: rgba(224,185,104,.06); }
    .status-badge.pending, .status-badge.queued { color: var(--blue); background: rgba(126,183,206,.06); }
    .time { color: #898b84; font-variant-numeric: tabular-nums; }
    .asset-count { color: #898b84; font-variant-numeric: tabular-nums; }
    .row-actions { display: flex; gap: 7px; }
    .row-actions button { min-height: 36px; padding: 7px 10px; border-radius: 11px; font-size: 11px; }
    .empty { height: 420px; padding: 34px 20px; color: var(--muted); text-align: center; }
    .empty-state { display: grid; place-items: center; height: 100%; }
    .empty-icon { display: grid; place-items: center; width: 68px; height: 68px; margin: 0 auto 18px; color: var(--gold); border: 1px solid var(--line); border-radius: 22px; background: rgba(224,185,104,.04); }
    .empty-icon svg { width: 28px; height: 28px; stroke: currentColor; fill: none; stroke-width: 1.2; }
    .empty-title { color: #d8d3c8; font-size: 14px; font-weight: 700; }
    .empty-copy { max-width: 280px; margin: 8px auto 0; color: var(--dim); font-size: 12px; line-height: 1.7; }
    dialog { width: min(680px, calc(100% - 28px)); padding: 0; overflow: hidden; overscroll-behavior: contain; color: var(--text); border: 1px solid var(--line-strong); border-radius: 24px; background: #121512; box-shadow: 0 36px 100px rgba(0,0,0,.72); }
    dialog::backdrop { background: rgba(2,3,2,.76); backdrop-filter: blur(7px); }
    .dialog-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 22px; border-bottom: 1px solid var(--line); }
    .dialog-head button { width: 42px; padding: 0; }
    .dialog-body { padding: 22px; }
    .asset-hint { margin: 0 0 16px; color: var(--muted); font-size: 12px; line-height: 1.7; }
    .asset-list { display: grid; gap: 10px; max-height: 48vh; overflow-y: auto; }
    .asset-item { padding: 13px 14px; border: 1px solid var(--line); border-radius: 14px; background: rgba(0,0,0,.2); }
    .asset-key { color: var(--gold-pale); font: 12px/1.5 Consolas, monospace; word-break: break-word; }
    .asset-file { margin-top: 5px; color: var(--dim); font: 11px/1.55 Consolas, monospace; word-break: break-all; }
    .mobile-cards { display: none; }
    @keyframes fade-rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
    .topbar, .hero-copy, .hero-meta, .workspace-side, .queue-panel { animation: fade-rise .58s cubic-bezier(.2,0,0,1) both; }
    .hero-copy { animation-delay: 70ms; } .hero-meta { animation-delay: 140ms; } .workspace-side { animation-delay: 210ms; } .queue-panel { animation-delay: 280ms; }
    @media (max-width: 1040px) { .hero { grid-template-columns: 1fr 310px; } .workspace { grid-template-columns: 350px minmax(0,1fr); } th:nth-child(3), td:nth-child(3) { display: none; } }
    @media (max-width: 820px) {
      .shell { padding: 16px 14px 36px; }
      .topbar { align-items: flex-start; }
      .health { max-width: 46%; overflow: hidden; text-overflow: ellipsis; }
      .hero { grid-template-columns: 1fr; min-height: auto; padding: 34px 26px; }
      .hero-meta { display: none; }
      .workspace { grid-template-columns: 1fr; }
      .queue-panel { min-height: 0; }
    }
    @media (max-width: 600px) {
      .shell { padding-inline: 10px; }
      .brand-name { font-size: 11px; letter-spacing: .08em; }
      .brand-subtitle { display: none; }
      .health { min-height: 34px; padding: 7px 10px; font-size: 10px; }
      .hero { margin: 14px 0; padding: 30px 22px 34px; border-radius: 24px; }
      h1 { font-size: clamp(36px, 12vw, 50px); }
      .hero-description { margin-top: 18px; font-size: 13px; line-height: 1.75; }
      .panel { border-radius: 20px; }
      .panel-head, .panel-body { padding-inline: 17px; }
      .actions { flex-direction: column; }
      .actions button { width: 100%; }
      .cleanup-grid { grid-template-columns: 1fr; }
      .table-wrap { display: none; }
      .mobile-cards { display: grid; gap: 10px; padding: 12px; }
    .task-card { padding: 15px; border: 1px solid var(--line); border-radius: 16px; background: rgba(0,0,0,.16); }
      .task-card { animation: fade-rise .42s cubic-bezier(.2,0,0,1) both; }
      .task-card:nth-child(2) { animation-delay: 60ms; } .task-card:nth-child(3) { animation-delay: 120ms; } .task-card:nth-child(4) { animation-delay: 180ms; }
      .task-card-top { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
      .task-card-request { margin: 13px 0; color: #d9d5cb; font-size: 13px; line-height: 1.65; }
      .task-card-meta { display: flex; flex-wrap: wrap; gap: 6px 13px; color: var(--dim); font-size: 10px; font-variant-numeric: tabular-nums; }
      .task-card .row-actions { margin-top: 14px; }
      .task-card .row-actions button { flex: 1; min-height: 40px; }
      .mobile-empty { min-height: 280px; }
    }
    @media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; } }
    @keyframes scan-line { 0%, 100% { opacity: .12; transform: translateY(-50%) scaleX(.72); } 50% { opacity: .8; transform: translateY(-50%) scaleX(1); } }
  </style>
</head>
<body>
  <a class="skip-link" href="#workspace">跳到创作工作区</a>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20"><path d="M5 5.5h14v13H5zM5 9h14M9 5.5l2.5 3.5M14 5.5 16.5 9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg></div>
        <div class="brand-copy"><div class="brand-name">MULTIMODAL CREATIVE AGENT</div><div class="brand-subtitle">AI 多模态创作与短剧生成平台</div></div>
      </div>
      <div id="health" class="health" role="status" aria-live="polite">正在检查服务状态...</div>
    </header>

    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-glow" aria-hidden="true"></div>
      <div class="hero-copy">
        <div class="kicker">AI Production Studio · 01</div>
        <h1 id="hero-title">把一个想法，<br>推进成一段<em>可交付的短剧。</em></h1>
        <p class="hero-description">从故事意图、镜头规划到多模态资产编排，让创作过程像一间真正的数字片场：方向清楚、状态可见、结果可追踪。</p>
      </div>
      <div class="hero-meta" aria-hidden="true">
        <div class="frame-visual"><div class="frame-center"><span>01</span></div></div>
        <div class="frame-labels"><span>SCENE / CONCEPT</span><span>TAKE / GENERATE</span><span>SYNC / DELIVER</span></div>
      </div>
    </section>

    <main id="workspace" class="workspace">
      <div class="workspace-side">
        <section class="panel create-panel">
          <div class="panel-head"><div><span class="panel-index">01 / CREATE</span><h2>开启新的创作任务</h2><p class="panel-note">描述故事核心，其余工作交给 Agent 协同推进。</p></div></div>
          <div class="panel-body">
            <div class="field"><label for="request"><span>创作需求</span><small>必填</small></label><textarea id="request" name="creative_request" autocomplete="off" placeholder="例如：创作一段发生在雨夜便利店的三镜头悬疑短剧，结尾留下反转……"></textarea></div>
            <div class="field"><label for="constraints"><span>制作约束</span><small>每行一条 · 可选</small></label><textarea id="constraints" name="creative_constraints" autocomplete="off" class="compact" placeholder="竖屏 9:16…&#10;保持主角服装和发型连续…&#10;整体为冷暖对比的电影质感…"></textarea></div>
            <div class="actions">
              <button class="primary" id="create"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z"/></svg><span>创建并运行</span></button>
              <button id="refresh"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/></svg><span>刷新</span></button>
            </div>
            <div id="notice" class="notice" role="status" aria-live="polite"></div>
          </div>
        </section>

        <section class="panel maintenance">
          <div class="panel-head"><div><span class="panel-index">02 / MAINTAIN</span><h2>片场维护</h2><p class="panel-note">先预览，再决定是否清理历史任务。</p></div><button class="danger" id="cleanup">检查任务</button></div>
          <div class="panel-body">
            <div class="cleanup-grid">
              <div class="field"><label for="days"><span>保留期限</span></label><input id="days" name="retention_days" type="number" value="30" min="1" max="3650" inputmode="numeric" autocomplete="off" /></div>
              <div class="field"><label for="confirm"><span>执行方式</span></label><select id="confirm" name="cleanup_mode" autocomplete="off"><option value="false">安全预览</option><option value="true">确认删除</option></select></div>
            </div>
            <pre id="cleanup-result">默认仅检查超过 30 天的任务，不会删除数据。</pre>
          </div>
        </section>
      </div>

      <section class="panel queue-panel">
        <div class="panel-head"><div><span class="panel-index">03 / PIPELINE</span><h2>制作队列</h2><p class="panel-note">查看每个项目的推进状态与可用资产。</p></div><span id="count" class="count">0 个任务</span></div>
        <div class="table-wrap"><table><thead><tr><th>状态</th><th>创作需求</th><th>更新时间</th><th>资产</th><th>操作</th></tr></thead><tbody id="tasks"><tr><td colspan="5" class="empty"><div class="empty-state"><div><div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M4 7h16v11H4zM8 4v3M16 4v3M4 11h16"/></svg></div><div class="empty-title">片场尚未开机</div><div class="empty-copy">从左侧提交第一个创作想法，任务进度会在这里实时出现。</div></div></div></td></tr></tbody></table></div>
        <div id="task-cards" class="mobile-cards"><div class="empty-state mobile-empty"><div><div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M4 7h16v11H4zM8 4v3M16 4v3M4 11h16"/></svg></div><div class="empty-title">片场尚未开机</div><div class="empty-copy">提交第一个创作想法后，制作进度会显示在这里。</div></div></div></div>
      </section>
    </main>
  </div>

  <dialog id="asset-dialog" aria-labelledby="asset-title">
    <div class="dialog-head"><div><span class="panel-index">ASSET LIBRARY</span><h2 id="asset-title">图片资产</h2></div><button id="close-assets" aria-label="关闭资产窗口"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div>
    <div class="dialog-body"><p class="asset-hint">图片生成是可选的补充步骤，不影响剧本、镜头规划和主任务交付。这里仅展示当前任务已生成的图片文件。</p><div id="asset-list" class="asset-list"></div></div>
  </dialog>
  <script>
    const $ = (id) => document.getElementById(id);
    const notice = (text, kind='') => { $('notice').textContent = text; $('notice').className = `notice ${kind}`; };
    const icons = {
      run: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z"/></svg>',
      image: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4 17 5-5 4 4 2-2 5 5"/></svg>',
      empty: '<div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M4 7h16v11H4zM8 4v3M16 4v3M4 11h16"/></svg></div>'
    };
    const statusNames = { succeeded:'已完成', failed:'失败', running:'运行中', pending:'等待中', queued:'排队中', retrying:'重试中' };
    const emptyState = (compact=false) => `<div class="empty-state ${compact ? 'mobile-empty' : ''}"><div>${icons.empty}<div class="empty-title">片场尚未开机</div><div class="empty-copy">${compact ? '提交第一个创作想法后，制作进度会显示在这里。' : '从左侧提交第一个创作想法，任务进度会在这里实时出现。'}</div></div></div>`;
    async function api(url, options={}) {
      const res = await fetch(url, { headers:{'Content-Type':'application/json'}, ...options });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `请求失败（${res.status}）`);
      return data;
    }
    function render(tasks) {
      $('count').textContent = `${tasks.length} 个任务`;
      $('tasks').innerHTML = tasks.length ? tasks.map(t => {
        const status = escapeHtml(t.status || 'pending');
        const request = escapeHtml(t.request);
        const updated = formatTime(t.updated_at);
        return `<tr><td><span class="status-badge ${status}">${statusNames[t.status] || status}</span></td><td class="request" title="${request}">${request}</td><td class="time">${updated}</td><td class="asset-count">图 ${Number(t.image_asset_count || 0)} · 视频 ${Number(t.artclaw_job_count || 0)}</td><td><div class="row-actions"><button data-run="${escapeHtml(t.task_id)}">${icons.run}运行</button><button data-assets="${escapeHtml(t.task_id)}">${icons.image}图片</button></div></td></tr>`;
      }).join('') : `<tr><td colspan="5" class="empty">${emptyState()}</td></tr>`;
      $('task-cards').innerHTML = tasks.length ? tasks.map(t => {
        const status = escapeHtml(t.status || 'pending');
        return `<article class="task-card"><div class="task-card-top"><span class="status-badge ${status}">${statusNames[t.status] || status}</span><span class="time">${formatTime(t.updated_at)}</span></div><div class="task-card-request">${escapeHtml(t.request)}</div><div class="task-card-meta"><span>图片 ${Number(t.image_asset_count || 0)}</span><span>视频 ${Number(t.artclaw_job_count || 0)}</span></div><div class="row-actions"><button data-run="${escapeHtml(t.task_id)}">${icons.run}运行</button><button data-assets="${escapeHtml(t.task_id)}">${icons.image}图片资产</button></div></article>`;
      }).join('') : emptyState(true);
    }
    function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}); }
    function escapeHtml(value) { return String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    const hero = document.querySelector('.hero');
    if (hero && window.matchMedia('(hover: hover)').matches) {
      hero.addEventListener('pointermove', (event) => {
        const bounds = hero.getBoundingClientRect();
        hero.style.setProperty('--spot-x', `${((event.clientX - bounds.left) / bounds.width) * 100}%`);
        hero.style.setProperty('--spot-y', `${((event.clientY - bounds.top) / bounds.height) * 100}%`);
      });
      hero.addEventListener('pointerleave', () => { hero.style.setProperty('--spot-x', '82%'); hero.style.setProperty('--spot-y', '38%'); });
    }
    async function refresh() { const data = await api('/tasks?limit=100'); render(data.tasks); }
    function setBusy(button, busy, text) { button.disabled = busy; if (text) button.querySelector('span').textContent = text; }
    $('create').onclick = async () => {
      const request = $('request').value.trim();
      if (!request) { $('request').focus(); return notice('请先填写创作需求', 'error'); }
      const constraints = $('constraints').value.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
      const button = $('create');
      try {
        setBusy(button, true, '正在推进制作…'); notice('任务已进入制作流程，请稍候…');
        const task = await api('/tasks', {method:'POST', body:JSON.stringify({request, constraints})});
        await api(`/tasks/${task.task_id}/run`, {method:'POST'});
        $('request').value=''; notice('任务已完成并保存到制作队列', 'good'); await refresh();
      } catch (e) { notice(e.message, 'error'); }
      finally { setBusy(button, false, '创建并运行'); }
    };
    $('refresh').onclick = () => refresh().catch(e => notice(e.message, 'error'));
    async function handleTaskAction(event) {
      const button = event.target.closest('button[data-run], button[data-assets]');
      if (!button) return;
      const run = button.dataset.run;
      const assets = button.dataset.assets;
      try {
        button.disabled = true;
        if (run) { notice('正在重新推进任务…'); await api(`/tasks/${run}/run`, {method:'POST'}); notice('任务状态已更新', 'good'); await refresh(); }
        if (assets) { const data = await api(`/tasks/${assets}/image-assets`); showAssets(data.assets || []); }
      } catch (e) { notice(e.message, 'error'); }
      finally { button.disabled = false; }
    }
    $('tasks').onclick = handleTaskAction;
    $('task-cards').onclick = handleTaskAction;
    function showAssets(assets) {
      $('asset-list').innerHTML = assets.length ? assets.map(item => `<div class="asset-item"><div class="asset-key">${escapeHtml(item.asset_key || '未命名资产')}</div><div class="asset-file">${escapeHtml(item.local_file || '未提供本地文件路径')}</div></div>`).join('') : '<div class="empty-copy">当前任务还没有图片资产。图片生成是可选步骤，可在正式配置图片服务后使用。</div>';
      $('asset-dialog').showModal();
    }
    $('close-assets').onclick = () => $('asset-dialog').close();
    $('asset-dialog').onclick = (event) => { if (event.target === $('asset-dialog')) $('asset-dialog').close(); };
    $('cleanup').onclick = async () => {
      const days = Number($('days').value);
      const confirmDelete = $('confirm').value === 'true';
      if (!Number.isInteger(days) || days < 1 || days > 3650) { $('days').focus(); $('cleanup-result').textContent = '保留期限必须是 1 到 3650 之间的整数。'; return; }
      if (confirmDelete && !window.confirm(`确定永久删除超过 ${days} 天的任务吗？此操作无法撤销。`)) { $('cleanup-result').textContent = '已取消删除，数据没有变化。'; return; }
      try {
        $('cleanup').disabled = true;
        const data = await api('/maintenance/cleanup', {method:'POST', body:JSON.stringify({older_than_days:days, dry_run:!confirmDelete, confirm_delete:confirmDelete})});
        $('cleanup-result').textContent = JSON.stringify(data, null, 2); await refresh();
      } catch (e) { $('cleanup-result').textContent = e.message; }
      finally { $('cleanup').disabled = false; }
    };
    api('/health').then(h => { $('health').classList.add('online'); $('health').textContent = `服务在线 · ${h.model_provider} · 图片服务${h.image_provider_configured ? '已就绪' : '可选未配置'}`; }).catch(() => { $('health').classList.add('offline'); $('health').textContent = '服务暂不可用'; });
    refresh().catch(e => notice(`任务列表加载失败：${e.message}`, 'error'));
  </script>
</body></html>'''
