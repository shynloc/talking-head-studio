'use strict'

const FORMAT = 'talking-head-motion/1'
function prefix(length) {
  const buf = new ArrayBuffer(4)
  new DataView(buf).setUint32(0, length)
  return buf
}
function pngBlob(canvas) {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(Error('无法读取预览帧。'))), 'image/png'),
  )
}
async function jsonResponse(res) {
  const payload = await res.json()
  if (!res.ok) throw Error(payload.error || '工作台请求失败。')
  return payload
}
async function session() {
  token = (await jsonResponse(await fetch('/api/bootstrap', { cache: 'no-store' }))).token
}
function reviewedCopy(item) {
  const copy = clone(item)
  delete copy.thumb
  delete copy.changed
  return copy
}
function packItems() {
  return state.packFromScript ? sentenceItems() : state.items
}
async function makePack() {
  if (busy || !packItems().length) return
  busy = true
  exporting = true
  $('export').disabled = true
  $('approved').inert = true
  $('more').disabled = true
  const navBar = document.querySelector('nav'),
    back = document.querySelector('header .back')
  navBar.inert = true
  back.inert = true
  try {
    const capability = await jsonResponse(await fetch('/api/motion/status', { cache: 'no-store' }))
    if (!capability.ready && packItems().some((item) => !item.sample))
      throw Error('导出 MOV 需要 FFmpeg。安装媒体工具后回到这里重试，已选素材会保留。')
    const entries = packItems().map(reviewedCopy),
      header = new TextEncoder().encode(
        JSON.stringify({
          format: entries.some((item) => item.sample) ? 'talking-head-motion/2' : FORMAT,
          items: entries,
        }),
      )
    if (entries.length > 64 || header.byteLength > 32 * 1024 * 1024)
      throw Error('这个包的素材较多，请分批导出。')
    const chunks = [prefix(header.length), header]
    let total = 4 + header.length
    const canvas = document.createElement('canvas')
    canvas.width = 960
    canvas.height = 360
    for (const [n, item] of entries.entries()) {
      if (item.sample) continue
      const imgs = await loadImages(item),
        count = countFrames(item)
      for (let f = 0; f < count; f++) {
        paint(canvas, item, f, imgs)
        const blob = await pngBlob(canvas)
        chunks.push(prefix(blob.size), blob)
        total += 4 + blob.size
        if (total > 512 * 1024 * 1024) throw Error('本包的画面数据超过 512 MB，请分批导出。')
        if (f % 5 === 0)
          $('progress').textContent =
            '正在绘制第 ' +
            (n + 1) +
            ' / ' +
            entries.length +
            ' 款 · ' +
            Math.round(((f + 1) / count) * 100) +
            '%'
      }
    }
    $('progress').textContent = '正在本机编码透明 MOV 并打包…'
    await session()
    const response = await jsonResponse(
      await fetch('/api/motion/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream', 'X-Studio-Token': token },
        body: new Blob(chunks),
      }),
    )
    state.downloadItems = entries.map((item) => item.id).join()
    state.download = response.url
    save()
    $('download').href = response.url
    $('download').hidden = false
    $('download').click()
    $('progress').textContent = response.count + ' 款已导出。解压后，把透明图片和动画拖到视频上方。'
  } catch (e) {
    $('progress').textContent = e.message + ' 已选搭配保留，可再次导出。'
  } finally {
    busy = false
    exporting = false
    $('approved').inert = false
    $('more').disabled = false
    $('export').disabled = !packItems().length
    navBar.inert = false
    back.inert = false
  }
}
$('export').onclick = makePack
window.addEventListener('beforeunload', (event) => {
  if (exporting) {
    event.preventDefault()
    event.returnValue = ''
  }
})
function parseItem(raw) {
  if (
    raw?.sample &&
    typeof raw.quote === 'string' &&
    raw.quote.trim() &&
    /^[a-f0-9]{64}$/.test(raw.sample.id)
  ) {
    return {
      ...createItem({ quote: raw.quote, offset: raw.offset || 0 }),
      title: String(raw.title),
      producer: raw.producer,
      productionTask: raw.productionTask,
      treatment: raw.treatment,
      ids: [],
      sample: raw.sample,
      visual: raw.visual || {},
      seconds: raw.seconds || 3,
      thumb: mediaUrl(raw.sample),
    }
  }
  if (
    !raw ||
    typeof raw.quote !== 'string' ||
    !raw.quote.trim() ||
    !Array.isArray(raw.ids) ||
    !raw.ids.length ||
    raw.ids.some((id) => typeof id !== 'string' || !Object.hasOwn(TERM, id)) ||
    new Set(raw.ids.map(primarySlot)).size !== raw.ids.length
  )
    throw Error('这份文件包含无法识别的动作或原句。')
  if (
    !Number.isInteger(raw.seconds) ||
    raw.seconds < 1 ||
    raw.seconds > 12 ||
    !Number.isInteger(raw.poster) ||
    raw.poster < 0 ||
    raw.poster >= raw.seconds * FPS
  )
    throw Error('素材时长或定格位置无效。')
  const item = createItem({ quote: raw.quote, offset: Number.isInteger(raw.offset) ? raw.offset : 0 })
  for (const field of ['title', 'a', 'b', 'theme', 'notes', 'promptBase'])
    if (typeof raw[field] === 'string') item[field] = raw[field]
  if (item.theme !== 'neutral' && !DATA.quotes.some((q) => q.key === item.theme)) item.theme = 'neutral'
  if (Array.isArray(raw.labels) && raw.labels.length === 3 && raw.labels.every((s) => typeof s === 'string'))
    item.labels = raw.labels.slice()
  if (Array.isArray(raw.values) && raw.values.length === 2 && raw.values.every(Number.isFinite))
    item.values = raw.values.slice()
  item.visual = raw.visual || {}
  item.ids = raw.ids.slice()
  item.seconds = raw.seconds
  item.poster = raw.poster
  for (const slot of ['imageA', 'imageB'])
    if (raw.files?.[slot]) {
      const src = raw.files[slot]
      if (typeof src !== 'string' || !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(src))
        throw Error('文件里包含无法读取的图片。')
      item.files[slot] = src
    }
  return item
}
$('restore').onclick = () => $('restore-file').click()
$('restore-file').onchange = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  $('restore').disabled = true
  $('restore').textContent = '正在打开素材包…'
  tell('正在读取已采用的素材并准备透明预览。')
  try {
    const zipped = file.name.toLowerCase().endsWith('.zip')
    if (file.size > (zipped ? 512 : 32) * 1024 * 1024) throw Error('素材包太大，请分批打开。')
    let manifest
    if (zipped) {
      await session()
      manifest = await jsonResponse(
        await fetch('/api/motion/restore', {
          method: 'POST',
          headers: { 'X-Studio-Token': token, 'Content-Type': 'application/zip' },
          body: file,
        }),
      )
    } else manifest = JSON.parse(await file.text())
    if (
      ![FORMAT, 'talking-head-motion/2'].includes(manifest.format) ||
      !Array.isArray(manifest.items) ||
      !manifest.items.length ||
      manifest.items.length > 64
    )
      throw Error('请选择本工作台导出的「素材搭配.json」。')
    const incoming = manifest.items.map(parseItem),
      canvas = document.createElement('canvas')
    canvas.width = 480
    canvas.height = 180
    for (const item of incoming) {
      if (item.sample) {
        if (!(await fetch(mediaUrl(item.sample))).ok) throw Error('这款素材来自另一台电脑，请打开完整 ZIP。')
        continue
      }
      paint(canvas, item, item.poster, await loadImages(item))
      item.thumb = canvas.toDataURL()
    }
    state.packFromScript = false
    state.items.push(...incoming)
    state.download = ''
    if (!state.script.trim()) {
      let offset = 0
      for (const item of incoming) {
        item.offset = offset
        offset += item.quote.length + 1
      }
      state.script = incoming.map((s) => s.quote).join('\n')
      resetReview()
    }
    nav('pack')
    tell('已加入 ' + incoming.length + ' 款。点「改这款」可以继续编辑。')
  } catch (e) {
    issue(e)
  } finally {
    $('restore-file').value = ''
    $('restore').textContent = '打开已有搭配'
    $('restore').disabled = false
  }
}
async function initMaterials() {
  try {
    db = await getDB()
    const saved = await readSaved()
    if (saved && Array.isArray(saved.items)) state = { ...blank(), ...saved }
  } catch {
    $('save-state').textContent = '浏览器存储不可用，本次仍可导出'
  }
  try {
    if (state.page === 'edit' && state.draft) await openItem(state.draft)
    else nav(state.page === 'pack' ? 'pack' : 'script')
  } catch (e) {
    nav('script')
    issue(e)
  } finally {
    initReview()
    $('manuscript').disabled = false
    document.querySelector('main').inert = false
  }
}
initMaterials()
