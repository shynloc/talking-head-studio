'use strict'

const $ = (id) => document.getElementById(id)
const FPS = 25
const recipes = [
  ['一句话留在屏幕上', ['letterRise', 'underline', 'textFade']],
  ['两个状态翻面换', ['pop', 'flip', 'clear']],
  ['把路线走一遍', ['fade', 'travel', 'quarter', 'vanish']],
  ['把步骤讲清楚', ['lift', 'steps', 'quarter', 'vanish']],
  ['突出一个数字', ['counter', 'textFocus', 'textDown']],
  ['把过程排成时间线', ['fade', 'timeline', 'half', 'drop']],
  ['标出细节位置', ['lift', 'pointer', 'breathe', 'vanish']],
  ['前后结果比一比', ['wipe', 'compare', 'clear', 'shrink']],
  ['让标题像盖章', ['stamp', 'marker', 'eraseText']],
  ['卡片逐格换图', ['tiles', 'spark', 'clear']],
  ['看清图层结构', ['fade', 'explode', 'clear']],
  ['把两次数值连起来', ['fade', 'slopePair', 'vanish']],
  ['把三项逐一勾选', ['lift', 'checkList', 'vanish']],
  ['用铅笔圈出重点', ['fade', 'pencilLoop']],
  ['给图标一点呼吸', ['zoomIn', 'breathe', 'glint', 'vanish']],
]
const aliases = {
  flip: '翻面 翻牌 翻转',
  typeon: '打字机',
  letterRise: '逐字',
  tiles: '马赛克',
  shutter: '扇形',
  confetti: '粒子 礼花',
  spark: '粒子 闪光',
  burst: '粒子',
  cross: '叠化 淡入淡出',
  scramble: '乱码 解码',
  outlineText: '描边',
}
const deskParam = new URLSearchParams(location.search).get('desk') || ''
const storageKey = /^motion_[0-9a-f]{32}$/.test(deskParam) ? deskParam : 'workspace'
if (storageKey !== 'workspace') $('browse-gallery').href = 'gallery.html?desk=' + storageKey
const blank = () => ({ script: '', page: 'script', draft: null, edits: {}, items: [], download: '' })
let state = blank(),
  db,
  serial = 0,
  motion = 0,
  termMotion = 0,
  frame = 0,
  group = '',
  token = '',
  busy = false,
  exporting = false,
  images = {}
const clone = (v) => structuredClone(v)
const key = () => crypto.randomUUID()
const groupNames = Object.fromEntries(DATA.groups.map((g) => [g.id, g.name]))
const countFrames = (item) => item.seconds * FPS
const button = (label, cls, fn) => {
  const b = document.createElement('button')
  b.textContent = label
  b.className = cls
  b.onclick = fn
  return b
}
function tell(message) {
  $('notice').textContent = message
}
function issue(e) {
  tell(e.message || String(e))
}
function getDB() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open('talking-head-material-studio', 1)
    r.onupgradeneeded = () => r.result.createObjectStore('drafts')
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}
function readSaved() {
  return new Promise((resolve, reject) => {
    const r = db.transaction('drafts').objectStore('drafts').get(storageKey)
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}
function save() {
  if (state.draft) state.edits[state.draft.id] = state.draft
  if (!db) return
  const rev = ++serial
  $('save-state').textContent = '正在保存…'
  return new Promise((resolve) => {
    try {
      const tx = db.transaction('drafts', 'readwrite')
      tx.objectStore('drafts').put(state, storageKey)
      tx.oncomplete = () => {
        if (rev === serial) $('save-state').textContent = '草稿已存本机'
        resolve(true)
      }
      tx.onabort = () => {
        $('save-state').textContent = '草稿保存失败，请检查浏览器存储'
        resolve(false)
      }
      tx.commit?.()
    } catch {
      $('save-state').textContent = '草稿保存失败，请检查浏览器存储'
      resolve(false)
    }
  })
}
function lines(text) {
  const list = []
  // Keep the literal source, decimal points, and closing quotes with their sentence.
  for (const match of text.matchAll(/[^。！？!?\n]+(?:[。！？!?]+[”’」』）)]*)?|[。！？!?]+/gu)) {
    const raw = match[0],
      s = raw.trim()
    if (!s) continue
    for (const part of s.matchAll(/.+?(?:\.(?=\s|$)|$)/gu)) {
      const val = part[0].trim()
      if (val)
        list.push({ quote: val, offset: match.index + raw.indexOf(s) + part.index + part[0].indexOf(val) })
    }
  }
  return list
}
function guess(text) {
  const nums = text.match(/\d+(?:\.\d+)?/g) || []
  if (nums.length >= 2 && /从|到|降|升|目标|增长|减少|增加|对比/.test(text))
    return [7, '适合把两个数摆在一起', ['fade', 'bars', 'clear']]
  if (/先.{1,}再|第一步|接着|最后/.test(text)) return [3, '适合按顺序亮出步骤', recipes[3][1]]
  if (/从.+(?:切换|换成|变成)|变成|从.+到/.test(text)) return [1, '适合在同处演示前后变化', recipes[1][1]]
  if (/区别|相比|对比/.test(text)) return [7, '适合把两种情况并排看', recipes[7][1]]
  return [0, '适合用文字点出重点', recipes[0][1]]
}
function createItem(line) {
  const text = line.quote,
    parts = text
      .replace(/[。！？!?]+$/, '')
      .split(/[，,、；;]/)
      .map((s) => s.trim())
      .filter(Boolean)
  const nums = text.match(/\d+(?:\.\d+)?/g) || [],
    ids = guess(text)[2]
  const states = text.match(/从(.{1,16}?)(?:变成|换成|切换到)(.{1,16}?)[。！？!?]?$/)
  return {
    id: key(),
    libraryRelease: window.STUDIO_LIBRARY.libraryRelease,
    quote: text,
    offset: line.offset,
    title: (parts.find((s) => s.length > 2) || text).slice(0, 32),
    ids: [...ids],
    theme: 'neutral',
    visual: clone(state.visual || {}),
    a: states?.[1] || '之前',
    b: states?.[2] || '之后',
    labels: [0, 1, 2].map((v) => parts[v]?.slice(0, 12) || ['第一步', '第二步', '第三步'][v]),
    values: [Number(nums[0] || 0), Number(nums[1] || 0)],
    seconds: 4,
    poster: 52,
    files: {},
    notes: '',
  }
}
function paint(canvas, item, f, imgs) {
  const t = cut(f / (countFrames(item) - 1))
  draw(canvas, t, item.ids, item.theme, false, {
    title: item.title,
    name: item.title,
    a: item.a,
    b: item.b,
    labels: item.labels,
    values: item.values,
    colors: item.renderColors || VISUAL.palettes.find(p => p.id === item.visual?.palettes)?.colors,
    overlay: item.overlay,
    ...imgs,
  })
}
function decode(src) {
  return new Promise((resolve, reject) => {
    const im = new Image()
    im.onload = () => resolve(im)
    im.onerror = () => reject(Error('图片无法读取，请重新选一张。'))
    im.src = src
  })
}
async function loadImages(item) {
  const pairs = await Promise.all(
    Object.entries(item.files || {}).map(async ([id, src]) => [id, await decode(src)]),
  )
  const loaded = Object.fromEntries(pairs)
  if (item.overlay && !loaded.imageA) {
    const query = new URLSearchParams(item.visual)
    loaded.imageA = await decode(libraryPath('/api/motion/library-preview?' + query, item.libraryRelease || '1.0.0'))
  }
  return loaded
}
function secondsText(f) {
  return (f / FPS).toFixed(2) + ' s'
}
function redraw(f = frame) {
  if (!state.draft) return
  frame = Math.round(cut(f, 0, countFrames(state.draft) - 1))
  $('scrub').value = frame
  $('time').textContent = secondsText(frame)
  paint($('preview'), state.draft, frame, images)
}
function stop() {
  cancelAnimationFrame(motion)
  motion = 0
  $('play').textContent = '▶ 播放'
}
function play() {
  if (!state.draft) return
  if (motion) {
    stop()
    return
  }
  const start = performance.now()
  $('play').textContent = 'Ⅱ 暂停'
  function tick(now) {
    const f = Math.floor(((now - start) * FPS) / 1000)
    redraw(f)
    if (f < countFrames(state.draft) - 1) motion = requestAnimationFrame(tick)
    else stop()
  }
  motion = requestAnimationFrame(tick)
}
function sentences() {
  const box = $('sentences')
  box.replaceChildren()
  if (annotationPending) return
  const list = scriptUnits()
  if (!list.length) {
    const el = document.createElement('p')
    el.className = 'empty'
    el.textContent = '贴入稿件后，原句会列在这里。'
    box.append(el)
    return
  }
  for (const [index, line] of list.entries()) {
    const binding = annotationAt(index)
    const b = button(line.quote, 'sentence', () => {
      if (binding) showAnnotationCard(index)
      else selectLine(line).catch(issue)
    })
    const owned = state.items.find((x) => x.offset === line.offset && x.quote === line.quote)
    const info = document.createElement('small')
    info.textContent = binding ? { none: '纯口播', error: '标注待确认', specified: '已有指定画面' }[binding.mode]
      : owned ? '已加入 · 可以继续修改' : guess(line.quote)[1]
    b.append(info)
    box.append(b)
  }
}
function nav(page) {
  if (busy || !['script', 'edit', 'pack'].includes(page) || (page === 'edit' && !state.draft)) return
  stop()
  state.page = page
  for (const id of ['script', 'edit', 'pack']) $(id).hidden = id !== page
  document.querySelectorAll('nav button').forEach((b) => {
    b.disabled = b.dataset.page === 'edit' && !state.draft
    b.setAttribute('aria-current', b.dataset.page === page ? 'step' : 'false')
  })
  if (page === 'script') {
    sentences()
    $('manuscript').value = manuscriptInput()
    renderReview()
  }
  if (page === 'pack') showPack()
  $('total').textContent = state.items.filter(isActiveMaterial).length
  tell('')
  save()
  window.scrollTo(0, 0)
}
let imageVersion = 0
const imageLoads = { imageA: 0, imageB: 0 }
const pendingImages = new Map()
async function openItem(item) {
  const version = ++imageVersion
  pendingImages.clear()
  const imgs = await loadImages(item)
  if (version !== imageVersion) return
  state.draft = clone(item)
  images = imgs
  updateFields()
  nav('edit')
  redraw(item.poster)
}
async function selectLine(line) {
  state.editFromReview = ''
  const existing =
    Object.values(state.edits).find((x) => x.quote === line.quote && x.offset === line.offset && isActiveMaterial(x)) ||
    state.items.find((x) => x.quote === line.quote && x.offset === line.offset && isActiveMaterial(x))
  const same = state.draft && state.draft.quote === line.quote && state.draft.offset === line.offset
  if (existing?.sample) return revisitSample(existing)
  await openItem(same ? state.draft : existing || createItem(line))
}
function fieldValue(id, val) {
  $(id).value = val
}
function updateFields() {
  const d = state.draft
  $('selected-quote').textContent = d.standalone ? '动效词库里的自由搭配' : '「' + d.quote + '」'
  for (const id of ['title', 'theme', 'a', 'b', 'seconds']) fieldValue(id, d[id])
  fieldValue('labels', d.labels.join('、'))
  fieldValue('from', d.values[0])
  fieldValue('to', d.values[1])
  $('recipe').value = ''
  $('image-a').value = ''
  $('image-b').value = ''
  $('scrub').max = countFrames(d) - 1
  $('approve').textContent = state.items.some((x) => x.id === d.id)
    ? '采用修改，更新素材包 →'
    : '用这版，加入素材包 →'
  chips()
}
function usesField(ids, field) {
  return ids.some((id) => TERM[id].fields.includes(field))
}
function chips() {
  const root = $('chips')
  root.replaceChildren()
  for (const id of state.draft.ids) {
    const b = button(TERM[id].name + ' ×', 'chip', () => toggle(id))
    b.setAttribute('aria-label', '移除' + TERM[id].name)
    root.append(b)
  }
  const ids = state.draft.ids
  $('title-label').textContent = usesField(ids, 'title') ? '画面文字' : '素材名称'
  $('states-inputs').hidden = !usesField(ids, 'states')
  $('steps-inputs').hidden = !usesField(ids, 'labels')
  $('number-inputs').hidden = !usesField(ids, 'values')
  $('approve').disabled = !ids.length || pendingImages.size > 0
}
function changed() {
  state.draft.changed = true
  stop()
  state.draft.poster = Math.min(state.draft.poster, countFrames(state.draft) - 1)
  redraw(
    frame === 0 || frame >= countFrames(state.draft) * 0.82
      ? Math.round(countFrames(state.draft) * 0.52)
      : frame,
  )
  save()
}
function toggle(id) {
  const d = state.draft,
    on = d.ids.includes(id)
  d.ids = d.ids.filter((v) => primarySlot(v) !== primarySlot(id))
  if (!on) d.ids.push(id)
  chips()
  changed()
  if ($('lexicon').open) {
    markTerms()
    showPrompt()
  }
}
function updatePrompt(d) {
  const hasText = usesField(d.ids, 'title')
  const result = [
    d.standalone ? '制作一件可叠在口播画面上的透明动效素材。' : '为口播原句「' + d.quote + '」做一件透明叠加素材。',
    (hasText ? '画面文字' : '素材名称') + '「' + d.title + '」。',
    ...d.ids.map((id) => TERM[id].assetId + ' · ' + groupNames[TERM[id].group] + ' · ' + TERM[id].prompt),
  ]
  if (usesField(d.ids, 'states')) result.push('两项文字分别为「' + d.a + '」和「' + d.b + '」。')
  if (usesField(d.ids, 'labels')) result.push('三个节点为 ' + d.labels.join('、') + '。')
  if (usesField(d.ids, 'values')) result.push('两个数值为 ' + d.values.join(' 和 ') + '。')
  result.push('时长 ' + d.seconds + ' 秒，画布外围全透明，叠在人物留白处。')
  const next = result.join('\n')
  if (!d.promptBase) {
    d.promptBase = next
    d.notes = next
  } else if (d.promptBase !== next) {
    const old = d.promptBase.split('\n'),
      lines = d.notes.split('\n')
    for (const line of old)
      if (!result.includes(line) && lines.includes(line)) lines.splice(lines.indexOf(line), 1)
    for (const line of result) if (!old.includes(line) && !lines.includes(line)) lines.push(line)
    d.notes = lines.join('\n')
    d.promptBase = next
  }
  if (d === state.draft) $('prompt').value = d.notes
}
function showPrompt() {
  updatePrompt(state.draft)
}
function putReviewed(d, poster, imgs) {
  // A deliberate transparent first/last frame is fine in the MOV. Pick a visible still for the pack.
  const c = document.createElement('canvas')
  c.width = 480
  c.height = 180
  const visible = (f) => {
    paint(c, d, f, imgs)
    const data = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
    let n = 0
    for (let i = 3; i < data.length; i += 4) if (data[i] > 16 && ++n > 120) return true
    return false
  }
  if (!visible(poster)) {
    poster = [0.58, 0.82, 0.28].map((t) => Math.round(t * (countFrames(d) - 1))).find(visible)
    if (poster === undefined) {
      throw Error('这一组没有可见画面。请添加文字、图形或更换效果。')
    }
  }
  d.poster = poster
  d.renderColors = d.renderColors || clone(VISUAL.palettes.find(p => p.id === d.visual?.palettes)?.colors || null)
  d.changed = false
  updatePrompt(d)
  paint(c, d, poster, imgs)
  d.thumb = c.toDataURL('image/png')
  const index = state.items.findIndex((x) => x.id === d.id)
  if (index < 0) state.items.push(clone(d))
  else state.items[index] = clone(d)
  state.download = ''
  state.edits[d.id] = clone(d)
}
async function approve() {
  const d = state.draft
  if (!d?.ids.length) return
  stop()
  const old=state.items.find(i=>i.id===d.id)
  putReviewed(d, frame, images)
  const reviewPage = state.editFromReview === d.id
  if (reviewPage) {
    const row = state.review?.rows.find(r => r.item.id === d.id)
    if (row) Object.assign(row, {item:clone(d), candidate:false, job:null, previous:old ? clone(old) : row.previous})
  }
  if (!reviewPage) state.packFromScript = false
  state.editFromReview = ''
  $('approve').disabled = true
  await save()
  nav(reviewPage ? 'script' : 'pack')
}
function showPack() {
  const root = $('approved')
  root.replaceChildren()
  const items = packItems()
  if (!items.length) {
    const el = document.createElement('p')
    el.className = 'paper empty'
    el.textContent = '选一句原稿，试看后点「用这版，加入素材包」。'
    root.append(el)
  }
  items.forEach((item, i) => {
    const row = document.createElement('article')
    row.className = 'paper pack-item'
    const thumb = document.createElement('div')
    thumb.className = 'thumb'
    const img = document.createElement('img')
    img.alt = ''
    img.src = item.thumb
    thumb.append(img)
    const copy = document.createElement('div')
    copy.className = 'copy'
    const name = document.createElement('strong')
    name.textContent = i + 1 + ' · ' + item.title
    const text = document.createElement('small')
    text.textContent = (item.standalone ? '自由搭配' : '「' + item.quote + '」') + ' · ' + item.seconds + ' 秒'
    copy.append(name, text)
    row.append(
      thumb,
      copy,
      button('改这款', 'quiet', () => {
        state.editFromReview = ''
        if (item.sample) revisitSample(item)
        else openItem(state.edits[item.id] || item).catch(issue)
      }),
      button('移除', 'link', () => {
        state.items = state.items.filter((x) => x.id !== item.id)
        state.download = ''
        nav('pack')
      }),
    )
    root.append(row)
  })
  $('export').disabled = busy || !items.length
  $('download').hidden =
    !state.download || (state.downloadItems && items.map((item) => item.id).join() !== state.downloadItems)
  if (state.download) $('download').href = state.download
  $('progress').textContent = state.draft?.changed
    ? '素材包只含已采用的版本。当前还有修改，可回「配画面」采用。'
    : ''
}
function markTerms() {
  for (const card of $('cards').children) {
    if (!card.dataset.id) continue
    const on = state.draft.ids.includes(card.dataset.id)
    card.classList.toggle('on', on)
    card.querySelector('.pick').setAttribute('aria-pressed', on)
    card.querySelector('.choice').textContent = on
      ? '已选 · ' + TERM[card.dataset.id].tech
      : TERM[card.dataset.id].tech
  }
}
function renderTerms() {
  cancelAnimationFrame(termMotion)
  const root = $('cards'),
    q = $('search').value.trim().toLowerCase().replace('专场', '转场')
  root.replaceChildren()
  const terms = DATA.terms.filter(
    (t) =>
      (!group || t.group === group) &&
      [t.name, t.assetId, t.tech, t.prompt, t.keywords, aliases[t.id], groupNames[t.group]].join(' ').toLowerCase().includes(q),
  )
  for (const t of terms) {
    const card = document.createElement('div')
    card.className = 'card'
    card.dataset.id = t.id
    const pick = button('', 'pick', () => toggle(t.id))
    pick.title = t.prompt
    const c = document.createElement('canvas')
    c.width = 360
    c.height = 135
    const title = document.createElement('strong')
    title.textContent = t.name
    const tech = document.createElement('small')
    tech.className = 'choice'
    const code = document.createElement('small')
    code.textContent = t.assetId
    pick.append(c, title, tech, code)
    const subject = DATA.quotes[DATA.terms.indexOf(t) % DATA.quotes.length].key
    const poster = t.id === 'flip' ? 0.82 : 0.48
    const paintTerm = (n) => draw(c, n, [t.id], subject, true)
    paintTerm(poster)
    const replay = button('▶', 'term-play', () => {
      cancelAnimationFrame(termMotion)
      const start = performance.now()
      function tick(now) {
        if (!$('lexicon').open || !c.isConnected) return
        const v = cut((now - start) / 1700)
        paintTerm(v === 1 ? poster : v)
        if (v < 1) termMotion = requestAnimationFrame(tick)
      }
      termMotion = requestAnimationFrame(tick)
    })
    replay.setAttribute('aria-label', '播放' + t.name)
    card.append(pick, replay)
    const reference = DATA.refs[t.ref]
    if (reference) {
      const link = document.createElement('a')
      link.href = reference[2]
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      link.className = 'term-source'
      link.textContent = reference[0] + ' · ' + reference[1] + ' ↗'
      card.append(link)
    }
    root.append(card)
  }
  if (!terms.length) root.textContent = '没找到这个动作，可以换个词或选择「全部」。'
  markTerms()
}
for (const g of [{ id: '', name: '全部' }, ...DATA.groups]) {
  const b = button(g.name, '', () => {
    group = g.id
    $('groups')
      .querySelectorAll('button')
      .forEach((el) => {
        el.classList.toggle('selected', el === b)
        el.setAttribute('aria-pressed', el === b)
      })
    renderTerms()
  })
  b.dataset.group = g.id
  b.classList.toggle('selected', !g.id)
  b.setAttribute('aria-pressed', !g.id)
  $('groups').append(b)
}
$('search').oninput = renderTerms
$('open-library').onclick = () => {
  stop()
  renderTerms()
  showPrompt()
  $('lexicon').showModal()
}
$('close-library').onclick = () => $('lexicon').close()
$('lexicon').onclose = () => {
  cancelAnimationFrame(termMotion)
  save()
  redraw()
}
$('prompt').oninput = () => {
  state.draft.notes = $('prompt').value
  save()
}
$('copy').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('prompt').value)
    $('copy').textContent = '已复制'
  } catch {
    $('prompt').focus()
    $('prompt').select()
    document.execCommand('copy')
  }
  setTimeout(() => ($('copy').textContent = '复制提示词'), 1100)
}
for (const [i, r] of recipes.entries()) $('recipe').add(new Option(r[0], String(i)))
$('theme').add(new Option('通用图形', 'neutral'))
for (const r of DATA.quotes) $('theme').add(new Option(r.theme + ' · ' + r.name, r.key))
for (let n = 1; n <= 12; n++) $('seconds').add(new Option(n + ' 秒', String(n)))
$('recipe').onchange = () => {
  if ($('recipe').value === '') return
  state.draft.ids = [...recipes[Number($('recipe').value)][1]]
  chips()
  changed()
}
$('scrub').oninput = () => {
  stop()
  redraw(Number($('scrub').value))
  state.draft.poster = frame
  save()
}
$('play').onclick = play
$('backdrop').onchange = () => {
  $('stage').className = 'stage ' + $('backdrop').value
}
for (const id of ['title', 'theme', 'a', 'b', 'seconds', 'labels', 'from', 'to']) {
  $(id).addEventListener(['theme', 'seconds'].includes(id) ? 'change' : 'input', () => {
    const d = state.draft,
      v = $(id).value
    if (id === 'seconds') {
      d.seconds = Number(v)
      $('scrub').max = countFrames(d) - 1
    } else if (id === 'labels') {
      const list = v.split(/[，,、]/)
      d.labels = [0, 1, 2].map((i) => (list[i] || '').trim())
    } else if (id === 'from' || id === 'to')
      d.values[id === 'from' ? 0 : 1] = cut(Number(v) || 0, 0, 99999999)
    else d[id] = v
    changed()
  })
}
async function useImage(file, slot) {
  if (!file) return
  const request = ++imageLoads[slot],
    d = state.draft,
    version = imageVersion,
    url = URL.createObjectURL(file)
  pendingImages.set(slot, request)
  $('approve').disabled = true
  try {
    const im = await decode(url),
      canvas = document.createElement('canvas'),
      ratio = Math.min(1, 700 / Math.max(im.width, im.height))
    canvas.width = Math.max(1, Math.round(im.width * ratio))
    canvas.height = Math.max(1, Math.round(im.height * ratio))
    canvas.getContext('2d').drawImage(im, 0, 0, canvas.width, canvas.height)
    const src = canvas.toDataURL('image/png'),
      ready = await decode(src)
    if (version !== imageVersion || request !== imageLoads[slot] || state.draft !== d) return
    d.files[slot] = src
    images[slot] = ready
    if (slot === 'imageB' && !d.ids.some((id) => TERM[id].group === 'swap' || id === 'compare')) {
      d.ids.push('cross')
      chips()
    }
    changed()
  } finally {
    URL.revokeObjectURL(url)
    if (pendingImages.get(slot) === request) pendingImages.delete(slot)
    if (version === imageVersion && request === imageLoads[slot] && state.draft === d) chips()
  }
}
$('image-a').onchange = (e) => useImage(e.target.files[0], 'imageA').catch(issue)
$('image-b').onchange = (e) => useImage(e.target.files[0], 'imageB').catch(issue)
$('reset-images').onclick = () => {
  ++imageVersion
  pendingImages.clear()
  state.draft.files = {}
  images = {}
  $('image-a').value = ''
  $('image-b').value = ''
  chips()
  changed()
}
$('manuscript').oninput = () => {
  const recommend = takePasteRequest()
  loadManuscript($('manuscript').value, recommend)
}
$('approve').onclick = () => approve().catch(issue)
$('more').onclick = () => nav('script')
document.querySelectorAll('nav button').forEach(
  (b) =>
    (b.onclick = () => {
      if (b.dataset.page === 'pack') state.packFromScript = false
      if (b.dataset.page === 'edit' && state.draft) openItem(state.draft).catch(issue)
      else nav(b.dataset.page)
    }),
)
