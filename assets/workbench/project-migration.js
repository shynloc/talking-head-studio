'use strict';

function projectImportDialog() {
  openDialog('导入工程包', `<section id="project-import">
    <p>选择 Talking Head Studio 导出的 ZIP。工作台会创建一份独立工程。</p>
    <button type="button" class="key" id="project-import-file">选择工程 ZIP</button>
    <p id="project-import-status" role="status"></p>
    <p id="project-import-error" role="alert" hidden></p></section>`);
  $('#project-import-file').onclick = () => chooseFile('project', '.zip');
}

async function openImportedProject(id, agentTasks = 0) {
  const project = await api('/api/project?id='+id);
  const recording = project.media.find(item => item.id===project.source_id);
  const stage = !recording ? 1 : recording.video && recording.path &&
    project.rough && project.rough_current ? 3 : 2;
  await refreshProjects();
  await load(id,stage);
  toast(agentTasks ? `工程已导入。项目的「AI 待办」中有 ${agentTasks} 条随包记录。` : '工程已导入，可以继续编辑。');
}

async function importProjectFile(file) {
  const dialog = $('#project-import');
  const button = $('#project-import-file');
  if (!dialog || button.disabled) return;
  button.disabled = true;
  $('#project-import-status').textContent = '正在核对和恢复工程，可以在完成后继续编辑。';
  $('#project-import-error').hidden = true;
  try {
    await save();
    const response = await fetch('/api/projects/import', {method:'POST',
      headers:{'X-Studio-Token':token}, body:file});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || '工程导入失败。');
    if (dialog.isConnected && $('#dialog').open) {
      closeDialog();
      await openImportedProject(result.project_id,result.agent_tasks);
    } else if (homeMode && !$('#dialog').open) {
      await dashboard();
      toast('工程已导入，可以在我的项目里打开。');
    } else {
      await refreshProjects();
      toast('工程已导入，可以在项目列表里打开。');
    }
  } catch (error) {
    if (!dialog.isConnected || !$('#dialog').open) return toast(error.message,true);
    $('#project-import-status').textContent = '';
    $('#project-import-error').textContent = error.message;
    $('#project-import-error').hidden = false;
  } finally { button.disabled = false; }
}
