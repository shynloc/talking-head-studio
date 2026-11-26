// Load one catalogue for the renderer, the picker and the local Agent contract.
async function startMaterialDesk() {
  const response = await fetch('catalog.json')
  if (!response.ok) throw Error('动效词库加载失败，请刷新页面。')
  window.DATA = await response.json()
  window.VISUAL = await (await fetch('visual/catalog.json')).json()
  window.PART_EFFECTS = await (await fetch('visual/treatments.json')).json()
  for (const file of ['renderer.js', 'illustrations.js', 'studio.js', 'recommendations.js', 'production.js', 'sentence-options.js', 'pack.js']) {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.onload = resolve
      script.onerror = () => reject(Error('工作台组件加载失败，请刷新页面。'))
      script.src = file
      document.body.append(script)
    })
  }
}
startMaterialDesk().catch((e) => {
  document.querySelector('main').inert = false
  document.getElementById('notice').textContent = e.message
})
