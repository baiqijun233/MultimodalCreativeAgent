"""轻量本地控制台页面，不依赖前端构建工具。"""

DASHBOARD_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>多模态创作工作台</title>
  <style>
    :root { color-scheme: dark; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; --bg:#111418; --panel:#1a1f26; --line:#303944; --text:#edf2f7; --muted:#9da8b5; --accent:#f2b84b; --good:#65c18c; --danger:#e17171; }
    * { box-sizing: border-box; } body { margin:0; background:var(--bg); color:var(--text); } .shell { max-width:1280px; margin:0 auto; padding:28px 24px 48px; }
    header { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; } h1 { margin:0; font-size:28px; letter-spacing:0; } .eyebrow { color:var(--accent); font-size:12px; text-transform:uppercase; letter-spacing:1px; } .health { color:var(--muted); font-size:13px; }
    main { display:grid; grid-template-columns:minmax(280px, 360px) 1fr; gap:22px; margin-top:22px; } section { background:var(--panel); border:1px solid var(--line); border-radius:6px; } .section-head { display:flex; justify-content:space-between; align-items:center; padding:15px 16px; border-bottom:1px solid var(--line); } h2 { font-size:15px; margin:0; } .body { padding:16px; }
    label { display:block; color:var(--muted); font-size:13px; margin:0 0 7px; } textarea, input, select { width:100%; background:#101319; color:var(--text); border:1px solid var(--line); border-radius:4px; padding:10px; font:inherit; } textarea { min-height:130px; resize:vertical; }
    button { border:1px solid var(--line); border-radius:4px; background:#242c35; color:var(--text); padding:9px 12px; cursor:pointer; font:inherit; } button:hover { border-color:var(--accent); } button.primary { background:var(--accent); color:#17120a; border-color:var(--accent); font-weight:600; } button.danger { color:#ffd4d4; border-color:#7f4444; } .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
    .table-wrap { overflow:auto; } table { width:100%; border-collapse:collapse; min-width:680px; } th, td { text-align:left; padding:12px 14px; border-bottom:1px solid var(--line); vertical-align:top; font-size:13px; } th { color:var(--muted); font-weight:500; } td.request { max-width:360px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; } .status { color:var(--muted); } .status.succeeded { color:var(--good); } .status.failed { color:var(--danger); } .empty { padding:34px 16px; color:var(--muted); text-align:center; }
    .notice { min-height:22px; margin-top:12px; color:var(--muted); font-size:13px; } .notice.error { color:var(--danger); } .notice.good { color:var(--good); } .cleanup { margin-top:22px; } .cleanup-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; } pre { white-space:pre-wrap; word-break:break-word; color:var(--muted); font-size:12px; max-height:220px; overflow:auto; }
    @media (max-width: 820px) { .shell { padding:20px 14px 32px; } header { align-items:flex-start; flex-direction:column; } main { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="shell">
    <header><div><div class="eyebrow">MULTIMODAL CREATIVE AGENT</div><h1>创作工作台</h1></div><div id="health" class="health">正在检查服务状态...</div></header>
    <main>
      <div>
        <section><div class="section-head"><h2>新建任务</h2></div><div class="body"><label for="request">创作需求</label><textarea id="request" placeholder="例如：生成一段三镜头的城市夜行短剧"></textarea><label for="constraints">约束（每行一条，可选）</label><textarea id="constraints" style="min-height:78px" placeholder="竖屏 9:16&#10;保持角色服装连续"></textarea><div class="actions"><button class="primary" id="create">创建并运行</button><button id="refresh">刷新任务</button></div><div id="notice" class="notice"></div></div></section>
        <section class="cleanup"><div class="section-head"><h2>任务清理</h2><button class="danger" id="cleanup">预览过期任务</button></div><div class="body"><div class="cleanup-grid"><div><label for="days">超过天数</label><input id="days" type="number" value="30" min="1" max="3650" /></div><div><label for="confirm">实际删除</label><select id="confirm"><option value="false">否，仅预览</option><option value="true">是，确认删除</option></select></div></div><pre id="cleanup-result">清理默认只做预览。</pre></div></section>
      </div>
      <section><div class="section-head"><h2>任务列表</h2><span id="count" class="health">0 个任务</span></div><div class="table-wrap"><table><thead><tr><th>状态</th><th>需求</th><th>更新时间</th><th>资产</th><th>操作</th></tr></thead><tbody id="tasks"><tr><td colspan="5" class="empty">暂无任务</td></tr></tbody></table></div></section>
    </main>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const notice = (text, kind='') => { $('notice').textContent = text; $('notice').className = `notice ${kind}`; };
    async function api(url, options={}) { const res = await fetch(url, { headers:{'Content-Type':'application/json'}, ...options }); const data = await res.json().catch(() => ({})); if (!res.ok) throw new Error(data.detail || `请求失败（${res.status}）`); return data; }
    function render(tasks) { $('count').textContent = `${tasks.length} 个任务`; $('tasks').innerHTML = tasks.length ? tasks.map(t => `<tr><td class="status ${t.status}">${t.status}</td><td class="request" title="${escapeHtml(t.request)}">${escapeHtml(t.request)}</td><td>${new Date(t.updated_at).toLocaleString()}</td><td>图 ${t.image_asset_count} · 视频 ${t.artclaw_job_count}</td><td><button data-run="${t.task_id}">运行</button> <button data-assets="${t.task_id}">图片</button></td></tr>`).join('') : '<tr><td colspan="5" class="empty">暂无任务</td></tr>'; }
    function escapeHtml(value) { return String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    async function refresh() { const data = await api('/tasks?limit=100'); render(data.tasks); }
    $('create').onclick = async () => { const request = $('request').value.trim(); if (!request) return notice('请先填写创作需求', 'error'); const constraints = $('constraints').value.split(/\r?\n/).map(v => v.trim()).filter(Boolean); try { notice('正在创建并运行...'); const task = await api('/tasks', {method:'POST', body:JSON.stringify({request, constraints})}); await api(`/tasks/${task.task_id}/run`, {method:'POST'}); $('request').value=''; notice('任务已完成并保存', 'good'); await refresh(); } catch (e) { notice(e.message, 'error'); } };
    $('refresh').onclick = () => refresh().catch(e => notice(e.message, 'error'));
    $('tasks').onclick = async (event) => { const run = event.target.dataset.run; const assets = event.target.dataset.assets; try { if (run) { notice('正在运行任务...'); await api(`/tasks/${run}/run`, {method:'POST'}); notice('任务已更新', 'good'); await refresh(); } if (assets) { const data = await api(`/tasks/${assets}/image-assets`); alert(data.assets.length ? data.assets.map(item => `${item.asset_key}: ${item.local_file}`).join('\n') : '暂无图片资产'); } } catch (e) { notice(e.message, 'error'); } };
    $('cleanup').onclick = async () => { const days = Number($('days').value); const confirmDelete = $('confirm').value === 'true'; try { const data = await api('/maintenance/cleanup', {method:'POST', body:JSON.stringify({older_than_days:days, dry_run:!confirmDelete, confirm_delete:confirmDelete})}); $('cleanup-result').textContent = JSON.stringify(data, null, 2); await refresh(); } catch (e) { $('cleanup-result').textContent = e.message; } };
    api('/health').then(h => $('health').textContent = `服务正常 · ${h.model_provider} · 图片服务${h.image_provider_configured ? '已配置' : '未配置（可选）'}`).catch(() => $('health').textContent = '服务不可用'); refresh().catch(() => {});
  </script>
</body></html>'''
