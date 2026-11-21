'use strict';

const agentNames = {codex:'Codex',workbuddy:'WorkBuddy'};
const taskLabels = {waiting:'等 AI 领取',claimed:'AI 已领取',ready:'结果已回来'};
let agentView = null;

function agentDialog(title, html) {
  if ($('#dialog').open && agentView) {
    $('#dialog-title').textContent = title;
    $('#dialog-body').innerHTML = html;
  } else {
    openDialog(title,html);
  }
}

function agentProject() {
  return homeMode ? null : P;
}

async function openAgentInbox() {
  const project = agentProject();
  const view = {kind:'list',projectId:project?.id};
  const query = view.projectId ? '?project='+encodeURIComponent(view.projectId) : '';
  const tasks = await api('/api/agents/tasks'+query);
  agentDialog('AI 待办',`
    <div class="agent-list-head">
      <p>${project ? '这里是当前项目交给 AI 的任务。' : '打开待办，可以查看进度和处理结果。'}</p>
      ${project ? '<button class="key" data-agent="compose">交给 AI</button>' : ''}
    </div>
    <div class="agent-list">${tasks.map(task => `
      <button class="agent-row" data-agent="task" data-task="${task.id}">
        <strong>${esc(task.instruction)}</strong>
        <span>${esc(task.project_title)} · ${agentNames[task.agent]}</span>
        <span class="agent-status">${taskLabels[task.status]}</span>
      </button>`).join('') || '<p class="hint">还没有交给 AI 的任务。</p>'}</div>`);
  agentView = view;
}

function composeAgentTask() {
  const project = agentProject();
  if (!project) return;
  const examples = ['把这份稿件改得更像日常说话', '帮我看哪些地方说重复了', '帮我检查字幕用词'];
  agentDialog('交给 AI',`
    <form id="agent-compose">
      <div class="field"><label for="agent-choice">交给谁</label><select id="agent-choice">
        <option value="codex">Codex</option><option value="workbuddy">WorkBuddy</option></select></div>
      <div class="field"><label for="agent-instruction">想请 AI 做什么</label>
        <textarea id="agent-instruction" required maxlength="4000" rows="4" placeholder="例如：${examples[stage - 1]}"></textarea></div>
      <p class="hint">待办会带上这个项目的稿件和字幕，方便 AI 理解你的要求。</p>
      <div class="action-row"><button class="key" type="submit">存为待办</button>
        <button class="ghost" type="button" data-agent="list">返回待办</button></div>
    </form>`);
  agentView = {kind:'compose'};
  const requestId = crypto.randomUUID();
  $('#agent-compose').onsubmit = async event => {
    event.preventDefault();
    const submit = event.submitter;
    submit.disabled = true;
    try {
      const instruction = $('#agent-instruction').value;
      const agent = $('#agent-choice').value;
      await save();
      const task = await api('/api/agents/create',{project_id:project.id, agent, instruction, request_id:requestId});
      await openAgentTask(task.id);
    } catch (error) {
      toast(error.message,true);
    } finally {
      submit.disabled = false;
    }
  };
  $('#agent-instruction').focus();
}

async function openAgentTask(id) {
  const owner = agentView;
  const task = await api('/api/agents/task?id='+encodeURIComponent(id));
  if (owner !== agentView) return;
  const view = {kind:'task',id,owner};
  await renderAgentTask(view,task);
}

async function renderAgentTask(view, task) {
  const connection = task.agent === 'codex'
    ? await api('/api/agents/connection?project='+encodeURIComponent(task.project_id)) : {};
  if (agentView !== (view.following ? view : view.owner)) return;
  const key = JSON.stringify([task,connection.codex_bound,connection.codex_available]);
  if (view.key === key) return;
  view.key = key;
  const canResume = task.agent === 'codex' && connection.codex_bound && connection.codex_available &&
    !['sending','queued','unconfirmed','fallback'].includes(task.delivery);
  const deliveryText = {
    sending:'正在找原来的 Codex 对话…',
    queued:'已排入原对话。若没有自动开始，打开原对话即可继续。',
    fallback:'这次没能续接原对话。待办还在，把任务卡粘贴到原对话即可继续。',
    unconfirmed:'暂时无法确认是否投递成功。待办还在，可复制任务卡到原对话继续。',
    manual:task.agent === 'workbuddy'
      ? '打开原来的 WorkBuddy 对话，把任务卡粘贴进去。'
      : canResume ? '已连接该项目的原 Codex 对话。' : '可以把任务卡粘贴到原来的 Codex 对话。',
  }[task.delivery];
  const waiting = task.status === 'waiting';
  const ready = task.status === 'ready';
  agentDialog('AI 待办',`
    <div class="agent-detail">
      <div class="agent-task-status"><strong>${taskLabels[task.status]}</strong>
        <span>${agentNames[task.agent]} · ${esc(task.project_title)}</span></div>
      <p class="agent-instruction">${esc(task.instruction)}</p>
      ${waiting ? `<p class="hint">${deliveryText}</p>` : ''}
      ${task.status === 'claimed' ? '<p class="hint">处理结果回来后会显示在这里。</p>' : ''}
      ${ready ? `${task.project_changed ? '<p class="hint">项目已更新。这份建议基于提交时的内容，采用前请对照。</p>' : ''}
        <div class="agent-result">${esc(task.result)}</div>` : ''}
      <div class="action-row">
        ${waiting && canResume ? '<button class="key" data-agent="resume">继续原对话</button>' : ''}
        ${waiting ? `<button class="${canResume?'ghost':'key'}" data-agent="card">复制任务卡</button>` : ''}
        ${waiting && task.agent === 'codex' && !connection.codex_bound
          ? '<button class="ghost" data-agent="bind">连接 Codex 原对话</button>' : ''}
        ${task.status === 'claimed' ? '<button class="ghost" data-agent="retry">让 AI 重新领取</button>' : ''}
        ${!ready && task.delivery !== 'sending' ? '<button class="ghost" data-agent="manual-result">粘贴 AI 的结果</button>' : ''}
        ${ready ? '<button class="key" data-agent="copy-result">复制结果</button>' : ''}
        <button class="ghost" data-agent="list">返回待办</button>
      </div>
      <div id="agent-copy-area" hidden></div>
    </div>`);
  Object.assign(view,{task,connection,following:true});
  agentView = view;
}

async function agentCopy(text, message) {
  const area = $('#agent-copy-area');
  if (!area) return;
  area.hidden = false;
  area.innerHTML = `<p class="hint">${esc(message)}</p><textarea rows="5" readonly aria-label="可复制内容">${esc(text)}</textarea>`;
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制');
  } catch {
    area.querySelector('textarea').select();
    toast('已选中内容，请使用复制快捷键。');
  }
}

function pasteAgentResult(view) {
  const area = $('#agent-copy-area');
  area.hidden = false;
  area.innerHTML = `<form id="agent-paste"><label for="agent-pasted-result">把对话里的处理结果粘贴在这里</label>
    <textarea id="agent-pasted-result" rows="6" maxlength="120000" required></textarea>
    <button class="key" type="submit">保存结果</button></form>`;
  $('#agent-pasted-result').focus();
  $('#agent-paste').onsubmit = async event => {
    event.preventDefault();
    const submit = event.submitter;
    submit.disabled = true;
    try {
      const task = await api('/api/agents/complete-manually',{id:view.id,result:$('#agent-pasted-result').value});
      if (agentView === view) await renderAgentTask(view,task);
    } catch (error) {
      toast(error.message,true);
    } finally {
      submit.disabled = false;
    }
  };
}

document.addEventListener('click',async event=>{
  const button = event.target.closest('button[data-agent]');
  if (!button) return;
  const view = agentView;
  button.disabled = true;
  try {
    switch (button.dataset.agent) {
      case 'list': await openAgentInbox(); break;
      case 'compose': composeAgentTask(); break;
      case 'task': await openAgentTask(button.dataset.task); break;
      case 'card': {
        const card = await api('/api/agents/card',{id:view.id});
        await agentCopy(card.text,`粘贴到你原来的 ${agentNames[view.task.agent]} 对话，处理完再回来看。`);
        break;
      }
      case 'bind':
        await agentCopy(view.connection.card,'粘贴到要连接的原 Codex 对话。连接完成后，这里会出现「继续原对话」。');
        break;
      case 'resume':
        await renderAgentTask(view,await api('/api/agents/resume',{id:view.id}));
        break;
      case 'retry':
        if (confirm('让 AI 重新领取？先前领取的结果将无法写回。')) {
          await renderAgentTask(view,await api('/api/agents/retry',{id:view.id}));
        }
        break;
      case 'copy-result':
        await agentCopy(view.task.result,'可以把结果粘贴到稿件或字幕里，再按需修改。');
        break;
      case 'manual-result':
        pasteAgentResult(view);
        break;
    }
  } catch (error) {
    toast(error.message,true);
  } finally {
    button.disabled = false;
  }
});

$('#dialog').addEventListener('close',()=>{agentView=null;});
setInterval(async()=>{
  const view=agentView;
  if (view?.kind !== 'task' || !$('#dialog').open || view.polling || view.task?.status === 'ready' || $('#agent-paste')) return;
  view.polling=true;
  try {
    const task=await api('/api/agents/task?id='+encodeURIComponent(view.id));
    if (agentView === view) await renderAgentTask(view,task);
  } catch {
    // Keep the last known task state visible when the local service is reconnecting.
  } finally {
    view.polling=false;
  }
},2400);
