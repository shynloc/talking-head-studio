'use strict'

function libraryPath(path, version = window.STUDIO_LIBRARY.libraryRelease) {
  return path + (path.includes('?') ? '&' : '?') + 'library=' + encodeURIComponent(version)
}

function connectLibrarySources(state) {
  const panel = document.getElementById('library-source')
  if (!panel) return
  const find = (selector) => panel.querySelector(selector)
  const notice = find('[role=status]')
  find('summary').textContent = '素材来源 · ' + (state.mode === 'online' ? '在线库' : '本地库')
  find('[data-library-version]').textContent = '当前版本 ' + state.libraryRelease +
    (state.mode === 'local' && !state.installed ? ' · 随工作台安装' : '')
  if (state.offlineUpdate)
    find('[data-library-action=update]').textContent = '更新本地库到 ' + state.offlineUpdate
  find('[data-vision-website]').href = state.website
  if (state.warning) notice.textContent = state.warning

  async function change(action, file) {
    const buttons = panel.querySelectorAll('button,input')
    buttons.forEach(button => { button.disabled = true })
    notice.textContent = file || action === 'update' ? '正在校验并安装整库，请稍候…' : '正在切换素材来源…'
    try {
      const opened = await fetch('/api/bootstrap', { cache: 'no-store' })
      const {token} = await opened.json()
      const response = await fetch(file ? '/api/motion/library-install' : '/api/motion/library-source', {
        method: 'POST',
        headers: {
          'X-Studio-Token': token,
          'Content-Type': file ? 'application/zip' : 'application/json',
        },
        body: file || JSON.stringify({action}),
      })
      const result = await response.json()
      if (!response.ok) throw Error(result.error || '素材库切换失败。')
      await window.beforeLibraryReload?.()
      location.reload()
    } catch (error) {
      notice.textContent = error.message
      buttons.forEach(button => { button.disabled = false })
    }
  }

  for (const button of panel.querySelectorAll('[data-library-action]'))
    button.onclick = () => change(button.dataset.libraryAction)
  const input = find('input[type=file]')
  find('[data-library-import]').onclick = () => input.click()
  input.onchange = () => {
    const file = input.files[0]
    input.value = ''
    if (file) change(null, file)
  }
}
