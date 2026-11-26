'use strict'
;(() => {
  const $ = (s) => document.querySelector(s),
    rows = DATA.quotes,
    groups = Object.fromEntries(DATA.groups.map((g) => [g.id, g.name]))
  const desk = new URLSearchParams(location.search).get('desk')
  const scoped = /^motion_[0-9a-f]{32}$/.test(desk || '')
  const storageKey = scoped ? 'gallery-' + desk : 'studio-v311-general-2'
  if (scoped) $('#nav-example').href = 'index.html?desk=' + desk
  function loadState(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || 'null')
    } catch {
      return null
    }
  }
  const saved = loadState(storageKey),
    legacy = saved || scoped ? null : loadState('studio-v311-lexicon-1'),
    initial = saved || legacy || {}
  let ids = (Array.isArray(initial.ids) ? initial.ids : []).filter((id) => TERM[id]),
    quote = initial.quote || '',
    group = '',
    mixT = 0.52,
    cardAnim = 0,
    mixAnim = 0,
    heroAnim = 0,
    noticeTimer,
    previous = {},
    backdrop = null,
    images = {}
  const promptBox = $('#prompt'),
    full = $('#full-input'),
    dialog = $('#full-editor'),
    cards = $('#cards'),
    stage = $('#stage')
  const fields = ['caption-input', 'label-a', 'label-b', 'subject-input', 'num-a', 'num-b', 'step-labels']
  let bound = new Set(saved?.bound || (saved ? fields : legacy?.object ? ['subject-input'] : []))
  const val = (id) => document.getElementById(id).value
  function button(text, cls, click) {
    const el = document.createElement('button')
    el.type = 'button'
    el.textContent = text
    el.className = cls
    el.onclick = click
    return el
  }
  function announce(text) {
    $('#notice').textContent = text
    clearTimeout(noticeTimer)
    noticeTimer = setTimeout(() => ($('#notice').textContent = ''), 3600)
  }
  function go(id) {
    $(id).scrollIntoView({ block: 'start' })
  }
  for (const row of rows) {
    for (const el of [$('#demo-key'), $('#mix-theme')])
      el.add(new Option(row.theme + ' · ' + row.name, row.key))
  }
  function setTheme(key) {
    const r = sceneFor(key)
    $('#mix-theme').value = r.key
    const values = [
      r.title,
      r.a,
      r.b,
      r.object,
      r.key === 'sport' ? 6000 : 3,
      r.key === 'sport' ? 8000 : 5,
      r.labels.join('、'),
    ]
    fields.forEach((id, i) => (document.getElementById(id).value = values[i]))
  }
  setTheme(saved?.theme || 'book')
  if (saved?.fields)
    fields.forEach((id) => {
      if (typeof saved.fields[id] === 'string') document.getElementById(id).value = saved.fields[id]
    })
  if (legacy?.object) $('#subject-input').value = legacy.object
  $('#demo-key').value = saved?.demo || 'book'
  $('#duration').value = initial.duration || 4
  $('#position').value = initial.position || 'top'
  $('#manuscript').value = initial.script || ''
  function storeDraft() {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({
          ids,
          quote,
          bound: [...bound],
          theme: val('mix-theme'),
          demo: val('demo-key'),
          fields: Object.fromEntries(fields.map((id) => [id, val(id)])),
          duration: val('duration'),
          position: val('position'),
          script: val('manuscript'),
          text: promptBox.value,
        }),
      )
    } catch {}
  }
  function options() {
    const labels = val('step-labels')
      .split(/[，、,]/)
      .map((s) => s.trim())
    return {
      title: val('caption-input') || '你的标题',
      a: val('label-a') || '变化前',
      b: val('label-b') || '变化后',
      labels: [0, 1, 2].map((i) => labels[i] || '步骤' + (i + 1)),
      values: ['num-a', 'num-b'].map((id) => cut(Number(val(id)) || 0, 0, 99999999)),
      ...images,
    }
  }
  function parts() {
    const o = options(),
      p = { task: '制作一件可叠在口播画面上的透明动效素材。' }
    if (quote) p.quote = '对应原句「' + quote + '」'
    p.object =
      '素材主体：' +
      (bound.has('subject-input') && val('subject-input')
        ? val('subject-input')
        : '[填写要展示的文字、物件或概念]')
    if (ids.some((id) => TERM[id].fields.includes('title')))
      p.title = '显示文字「' + (bound.has('caption-input') ? o.title : '[填写你的标题]') + '」'
    if (ids.some((id) => TERM[id].fields.includes('states')))
      p.states =
        '前后状态：' +
        (bound.has('label-a') ? o.a : '[原状态]') +
        ' → ' +
        (bound.has('label-b') ? o.b : '[新状态]')
    if (ids.some((id) => TERM[id].fields.includes('values')))
      p.values =
        '演示数值：' +
        (bound.has('num-a') ? o.values[0] : '[起始数]') +
        ' → ' +
        (bound.has('num-b') ? o.values[1] : '[结束数]')
    if (ids.some((id) => TERM[id].fields.includes('labels')))
      p.nodes =
        '演示节点：' + (bound.has('step-labels') ? o.labels.join(' → ') : '[第一步] → [第二步] → [第三步]')
    for (const g of DATA.groups) {
      const term = ids.map((id) => TERM[id]).find((term) => term.group === g.id)
      if (term) p[g.id] = g.name + '：' + term.prompt
    }
    p.layout =
      '摆放在' +
      $('#position').selectedOptions[0].textContent +
      '，避开人物、手势和字幕。建议时长 ' +
      (Number(val('duration')) || 4) +
      ' 秒。'
    p.export = '导出时保留画布外围透明通道。静帧给透明 PNG，动画给带 Alpha 的 MOV，另附可编辑源文件。'
    return p
  }
  function fit() {
    if ($('#editor-body').hidden) return
    const scroll = promptBox.scrollTop
    promptBox.style.height = 'auto'
    promptBox.style.height = promptBox.scrollHeight + 2 + 'px'
    promptBox.scrollTop = scroll
  }
  function syncPrompt() {
    const next = parts(),
      lines = promptBox.value ? promptBox.value.split('\n') : []
    for (const key of new Set([...Object.keys(previous), ...Object.keys(next)])) {
      if (next[key] === previous[key]) continue
      const i = previous[key]
        ? lines.findIndex((line) => line === previous[key] || line.startsWith(previous[key]))
        : -1
      if (i >= 0) {
        const extra = lines[i].slice(previous[key].length)
        if (next[key] || extra) lines[i] = (next[key] || '') + extra
        else lines.splice(i, 1)
      } else if (next[key]) lines.push(next[key])
    }
    promptBox.value = lines.join('\n')
    previous = next
    fit()
    storeDraft()
  }
  function drawMix(t) {
    mixT = t
    $('#scrub').value = Math.round(100 * t)
    draw($('#mix'), t, ids, val('mix-theme'), false, options())
  }
  function play(duration, frame, reset) {
    const start = performance.now()
    function tick(now) {
      const t = cut((now - start) / duration)
      frame(t)
      if (t < 1) reset(requestAnimationFrame(tick))
    }
    reset(requestAnimationFrame(tick))
  }
  function replay() {
    cancelAnimationFrame(mixAnim)
    play(1000 * cut(Number(val('duration')) || 4, 1, 12), drawMix, (n) => (mixAnim = n))
  }
  function selectState() {
    const chips = $('#chips')
    chips.replaceChildren()
    for (const id of ids) {
      const t = TERM[id],
        b = button(t.name + ' ×', 'chip', () => toggle(id))
      b.setAttribute('aria-label', '移除' + t.name)
      chips.append(b)
    }
    $('#selected-count').textContent = ids.length ? '· ' + ids.length + ' 项' : ''
    for (const el of cards.querySelectorAll('[data-id]')) {
      const on = ids.includes(el.dataset.id)
      el.classList.toggle('chosen', on)
      el.querySelector('.pick').setAttribute('aria-pressed', on)
      el.querySelector('.pick i').textContent = on ? '✓' : '+'
    }
    syncPrompt()
    cancelAnimationFrame(mixAnim)
    drawMix(ids.includes('flip') ? 0.82 : 0.52)
  }
  function toggle(id) {
    const old = ids.find((x) => primarySlot(x) === primarySlot(id))
    ids = ids.filter((x) => x !== old)
    if (old !== id) ids.push(id)
    selectState()
    announce(
      old === id
        ? '已移除「' + TERM[id].name + '」'
        : old
          ? '已将「' + TERM[old].name + '」换为「' + TERM[id].name + '」'
          : '已加入「' + TERM[id].name + '」',
    )
  }
  const recipes = [
    ['一句话留在屏幕上', 'book', ['letterRise', 'underline', 'textFade']],
    ['两个状态翻面换', 'product', ['pop', 'flip', 'clear']],
    ['把路线走一遍', 'travel', ['fade', 'travel', 'quarter', 'vanish']],
    ['把步骤讲清楚', 'coffee', ['lift', 'steps', 'quarter', 'vanish']],
    ['突出一个数字', 'sport', ['counter', 'textFocus', 'textDown']],
    ['把过程排成时间线', 'photo', ['fade', 'timeline', 'half', 'drop']],
    ['标出细节位置', 'plant', ['lift', 'pointer', 'breathe', 'vanish']],
    ['前后结果比一比', 'work', ['wipe', 'compare', 'clear', 'shrink']],
    ['让标题像盖章', 'book', ['stamp', 'marker', 'eraseText']],
    ['卡片逐格换图', 'photo', ['tiles', 'spark', 'clear']],
    ['看清图层结构', 'product', ['fade', 'explode', 'clear']],
    ['给图标一点呼吸', 'travel', ['zoomIn', 'breathe', 'glint', 'vanish']],
  ]
  $('#recipe-count').textContent = '· ' + recipes.length + ' 款可修改的模板'
  for (const [name, key, list] of recipes) {
    const b = button('', 'recipe', () => {
      if (!quote && !bound.size && !images.imageA && !images.imageB) setTheme(key)
      ids = [...list]
      selectState()
      go('#sample')
      replay()
      announce('已套用「' + name + '」')
    })
    const c = document.createElement('canvas')
    c.width = 360
    c.height = 135
    draw(c, list.includes('flip') ? 0.82 : 0.52, list, key)
    const label = document.createElement('strong')
    label.textContent = name
    b.append(c, label)
    $('#recipes').append(b)
  }
  const featured = [
    'letterRise',
    'flip',
    'travel',
    'ring',
    'blinds',
    'counter',
    'spark',
    'steps',
    'waveText',
    'float',
    'circleSwap',
    'bars',
  ]
  const catalogue = [...featured.map((id) => TERM[id]), ...DATA.terms.filter((t) => !featured.includes(t.id))]
  const synonyms = {
    flip: '翻面 翻牌 翻转',
    typeon: '打字机 逐字',
    letterRise: '逐字 文字上浮',
    tiles: '马赛克 方格',
    shutter: '时钟 扇形',
    confetti: '粒子 彩带 礼花',
    spark: '闪光 粒子',
    burst: '粒子',
    cross: '叠化 淡入淡出',
    push: '推拉',
    scramble: '解码 乱码',
    inkWrite: '书写 擦写',
    blinds: '百叶窗',
    stamp: '印章',
    outlineText: '描边 空心',
  }
  const posterTime = (t) => (t.id === 'flip' ? 0.81 : t.group === 'textout' ? 0.4 : 0.52)
  function renderCards() {
    cancelAnimationFrame(cardAnim)
    const q = val('search').trim().toLowerCase().replace('专场', '转场'),
      terms = catalogue.filter(
        (t) =>
          (!group || group === t.group) &&
          [
            t.name,
            t.tech,
            t.prompt,
            groups[t.group],
            synonyms[t.id] || '',
            t.group === 'swap' ? '切换 替换 局部转场' : '',
            t.group === 'fx' ? '特效' : '',
          ]
            .join(' ')
            .toLowerCase()
            .includes(q),
      )
    $('#count').textContent = terms.length + ' 个效果'
    cards.replaceChildren()
    if (!terms.length) {
      const p = document.createElement('p')
      p.className = 'nores'
      p.textContent = '没有找到。试试「逐字」「翻面」「路线」，或点「全部」查看其他类别。'
      cards.append(p)
    }
    for (const term of terms) {
      const key = rows[DATA.terms.indexOf(term) % rows.length].key,
        card = document.createElement('article')
      card.className = 'card'
      card.dataset.id = term.id
      const pick = button('', 'pick', () => toggle(term.id))
      pick.innerHTML =
        '<span class="thumb"><canvas width="480" height="180"></canvas></span><span class="info"><b></b><small></small></span><i aria-hidden="true"></i>'
      pick.querySelector('b').textContent = term.name
      pick.querySelector('small').textContent = term.tech
      pick.setAttribute('aria-label', '选用或移除：' + term.name)
      pick.title = term.prompt
      const c = pick.querySelector('canvas'),
        paint = (t) => draw(c, t, [term.id], key, true),
        start = () => {
          cancelAnimationFrame(cardAnim)
          play(
            2100,
            (t) => paint(t === 1 ? posterTime(term) : t),
            (n) => (cardAnim = n),
          )
        }
      const b = button('▶', 'playterm', start)
      b.setAttribute('aria-label', '播放：' + term.name)
      card.append(pick, b)
      card.onpointerenter = (e) => {
        if (e.pointerType === 'mouse' && !matchMedia('(prefers-reduced-motion: reduce)').matches) start()
      }
      cards.append(card)
      paint(posterTime(term))
    }
    for (const el of cards.querySelectorAll('[data-id]')) {
      const on = ids.includes(el.dataset.id)
      el.classList.toggle('chosen', on)
      el.querySelector('.pick').setAttribute('aria-pressed', on)
      el.querySelector('i').textContent = on ? '✓' : '+'
    }
  }
  for (const g of [{ id: '', name: '全部' }, ...DATA.groups]) {
    const b = button(g.name, '', () => {
      group = g.id
      for (const el of $('#filters').children) {
        const on = el.dataset.group === group
        el.classList.toggle('on', on)
        el.setAttribute('aria-pressed', on)
      }
      renderCards()
    })
    b.dataset.group = g.id
    b.classList.toggle('on', !g.id)
    b.setAttribute('aria-pressed', !g.id)
    $('#filters').append(b)
  }
  $('#search').oninput = renderCards
  function tab(open) {
    $('#example').hidden = !open
    $('#nav-lib').setAttribute('aria-pressed', !open)
    go(open ? '#example' : '#library')
  }
  $('#nav-lib').onclick = () => tab(false)
  $('#try').onclick = () => {
    tab(true)
    if (!val('manuscript').trim()) $('#manuscript').value = sceneFor(val('demo-key')).quote
    ideas()
  }
  $('#load-script').onclick = () => {
    if (
      val('manuscript').trim() &&
      !rows.some((r) => r.quote === val('manuscript')) &&
      !confirm('用示例稿替换当前编辑的稿件？')
    )
      return
    $('#manuscript').value = sceneFor(val('demo-key')).quote
    ideas()
  }
  function suggest(s) {
    const base = { quote: s, object: '', secs: 4 }
    if (/(\d+|[一二三四五六七八九]千).*(目标|增加|降低|减少|从|到|倍|%)/.test(s))
      return {
        ...base,
        name: '把数值摆出来',
        why: '这句话在说数量变化，可用条形比较。',
        ids: ['fade', 'bars', 'clear'],
      }
    if (/相比|区别|两种|对比|不同的是/.test(s))
      return {
        ...base,
        name: '看清两种情况',
        why: '句子有比较线索，可以把两种情况并排。',
        ids: ['compare', 'clear'],
      }
    if (/从.+(变|换|切|到)|原本|原来.+现在|昨天.+今天/.test(s))
      return { ...base, name: '看一眼前后变化', why: '同一个位置先后出现两种状态。', ids: ['cross', 'clear'] }
    if (/先|然后|接着|第一步|最后/.test(s))
      return {
        ...base,
        name: '跟着顺序看',
        why: '句子有先后关系，可把步骤分开显示。',
        ids: ['steps', 'quarter'],
      }
    if (/关键|重点|记住|一句话|结论/.test(s))
      return {
        ...base,
        name: '把重点写出来',
        why: '可以给这句话单独配一个文字重点。',
        ids: ['letterRise', 'underline', 'textFade'],
      }
    return null
  }
  function applyRow(r) {
    bound = new Set(r.key ? fields : ['caption-input'])
    if (r.key) {
      setTheme(r.key)
    } else {
      setTheme(val('mix-theme'))
      $('#subject-input').value = r.object || ''
      $('#caption-input').value = r.quote
      $('#label-a').value = '变化前'
      $('#label-b').value = '变化后'
      $('#step-labels').value = '步骤一、步骤二、步骤三'
      const nums = r.quote.match(/\d+(?:\.\d+)?/g) || []
      $('#num-a').value = nums[0] || 0
      $('#num-b').value = nums[1] || 0
      if (nums[0]) bound.add('num-a')
      if (nums[1]) bound.add('num-b')
    }
    clearImages()
    quote = r.quote
    ids = [...r.ids]
    $('#duration').value = r.secs
    selectState()
    go('#sample')
    replay()
    announce(r.key ? '已套用示例，可替换文字或图形。' : '已带入原句，请根据实际内容调整示意标签。')
  }
  function ideas() {
    const text = val('manuscript').trim(),
      found = [],
      known = rows.filter((r) => text.includes(r.quote))
    const out = $('#ideas')
    out.replaceChildren()
    const sentences = text
      .split(/(?<=[。！？!?])|\n/)
      .map((s) => s.trim())
      .filter(Boolean)
    for (const s of sentences) {
      const exact = known.filter((r) => s.includes(r.quote))
      if (exact.length) found.push(...exact)
      else {
        const idea = suggest(s)
        if (idea) found.push(idea)
      }
    }
    $('#ideas-status').textContent = found.length
      ? '选一句，看推荐的搭配和理由。'
      : text
        ? '这段话可以保留人物画面，也可以在下面指定想配素材的原句。'
        : '先粘贴一段稿件，或填入示例稿。'
    for (const r of found) {
      const b = button('', 'idea', () => applyRow(r))
      for (const [tag, txt] of [
        ['strong', r.name + ' ↗'],
        ['span', '「' + r.quote + '」'],
        ['small', r.why + '  ' + r.ids.map((id) => TERM[id].name).join(' · ')],
      ]) {
        const el = document.createElement(tag)
        el.textContent = txt
        b.append(el)
      }
      out.append(b)
    }
    storeDraft()
  }
  $('#analyze').onclick = ideas
  $('#manuscript').oninput = () => {
    $('#ideas').replaceChildren()
    $('#ideas-status').textContent = ''
    storeDraft()
  }
  $('#demo-key').onchange = storeDraft
  $('#use-manual').onclick = () => {
    const q = val('manual-quote').trim()
    if (!q || !val('manuscript').includes(q)) {
      announce('请从稿件里复制连续的一句原话。')
      return
    }
    applyRow(suggest(q) || { quote: q, ids: ['letterRise', 'clear'], secs: 4 })
  }
  function clearImages() {
    images = {}
    $('#image-a').value = ''
    $('#image-b').value = ''
  }
  function stageStyle() {
    stage.className = 'stage ' + val('bg')
    const p = val('position')
    stage.style.setProperty('--ax', p === 'left' ? '32%' : p === 'right' ? '68%' : '50%')
    stage.style.justifyItems = p === 'left' ? 'start' : p === 'right' ? 'end' : 'center'
  }
  for (const [id, slot] of [
    ['image-a', 'imageA'],
    ['image-b', 'imageB'],
    ['backdrop-file', 'backdrop'],
  ]) {
    document.getElementById(id).onchange = async (e) => {
      const file = e.target.files[0]
      if (!file) return
      const url = URL.createObjectURL(file),
        img = new Image()
      img.src = url
      try {
        await img.decode()
        if (e.target.files[0] !== file) {
          URL.revokeObjectURL(url)
          return
        }
        if (slot === 'backdrop') {
          if (backdrop) URL.revokeObjectURL(backdrop)
          backdrop = url
          stage.style.setProperty('--still', 'url("' + url + '")')
          stage.style.setProperty('--img-ratio', img.naturalWidth + '/' + img.naturalHeight)
          $('#bg').value = 'portrait'
          stageStyle()
        } else {
          images[slot] = img
          URL.revokeObjectURL(url)
          if (slot === 'imageB' && !ids.some((id) => TERM[id].group === 'swap' || id === 'compare')) {
            ids.push('cross')
            selectState()
          }
          drawMix(mixT)
        }
      } catch {
        URL.revokeObjectURL(url)
        announce('图片未能打开，请选择可预览的 PNG、JPEG 或 WebP。')
      }
    }
  }
  $('#clear-images').onclick = () => {
    clearImages()
    drawMix(mixT)
  }
  $('#mix-theme').onchange = () => {
    setTheme(val('mix-theme'))
    bound = new Set(fields)
    clearImages()
    syncPrompt()
    drawMix(mixT)
  }
  fields.forEach(
    (id) =>
      (document.getElementById(id).oninput = () => {
        bound.add(id)
        cancelAnimationFrame(mixAnim)
        if (
          id === 'caption-input' &&
          val(id).trim() &&
          !ids.some((x) => ['type', 'textcue', 'textout'].includes(TERM[x].group))
        ) {
          ids.push('letterRise')
          selectState()
          announce('已用逐字上浮预览你的文字，可在词库中换一种。')
          return
        }
        syncPrompt()
        drawMix(mixT < 0.18 || mixT > 0.78 ? 0.52 : mixT)
      }),
  )
  $('#bg').onchange = () => {
    if (val('bg') === 'portrait' && !backdrop) {
      $('#bg').value = 'check'
      $('#backdrop-file').click()
    }
    stageStyle()
  }
  $('#position').onchange = () => {
    stageStyle()
    syncPrompt()
  }
  $('#duration').onchange = () => {
    $('#duration').value = cut(Number(val('duration')) || 4, 1, 12)
    syncPrompt()
  }
  $('#scrub').oninput = () => {
    cancelAnimationFrame(mixAnim)
    drawMix(Number(val('scrub')) / 100)
  }
  $('#playmix').onclick = replay
  $('#jumpmix').onclick = () => {
    go('#sample')
    replay()
  }
  $('#snapshot').onclick = () => {
    const c = $('#mix'),
      rgba = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
    let visible = false
    for (let i = 3; i < rgba.length; i += 4)
      if (rgba[i] > 8) {
        visible = true
        break
      }
    if (!visible) {
      announce('这一帧完全透明，请拖到能看见素材的位置。')
      return
    }
    const a = document.createElement('a')
    a.download = '通用动效-当前帧.png'
    a.href = c.toDataURL()
    a.click()
  }
  function syncFull() {
    promptBox.value = full.value
    $('#full-count').textContent = Array.from(full.value).length + ' 字'
    fit()
    storeDraft()
  }
  $('#expand').onclick = () => {
    full.value = promptBox.value
    $('#full-count').textContent = Array.from(full.value).length + ' 字'
    dialog.showModal()
    full.focus()
    full.setSelectionRange(0, 0)
    full.scrollTop = 0
  }
  full.oninput = syncFull
  $('#done-edit').onclick = () => dialog.close()
  dialog.addEventListener('close', () => {
    fit()
    $('#expand').focus({ preventScroll: true })
  })
  promptBox.oninput = () => {
    fit()
    storeDraft()
  }
  async function copy(box) {
    let ok = false
    try {
      await navigator.clipboard.writeText(box.value)
      ok = true
    } catch {
      if (box === promptBox && $('#editor-body').hidden) $('#fold').click()
      box.focus()
      box.select()
      try {
        ok = document.execCommand('copy')
      } catch {}
    }
    const msg = ok ? '已复制全文' : '提示词已选中，可按 Ctrl+C 或 ⌘C 复制'
    if (dialog.open) $('#full-count').textContent = msg
    else announce(msg)
  }
  $('#copy').onclick = () => copy(promptBox)
  $('#full-copy').onclick = () => copy(full)
  $('#fold').onclick = () => {
    const body = $('#editor-body')
    body.hidden = !body.hidden
    $('#fold').setAttribute('aria-expanded', !body.hidden)
    $('#fold').textContent = body.hidden ? '⌃' : '⌄'
    if (!body.hidden) fit()
  }
  new ResizeObserver(([e]) =>
    document.documentElement.style.setProperty('--dock-height', $('#composer').offsetHeight + 'px'),
  ).observe($('#composer'))
  window.addEventListener('resize', fit)
  $('#refs').onclick = () => $('#sources').showModal()
  $('#close').onclick = () => $('#sources').close()
  for (const [org, title, url] of Object.values(DATA.refs)) {
    const a = document.createElement('a')
    a.href = url
    a.target = '_blank'
    a.rel = 'noopener'
    a.textContent = org + ' · ' + title + ' ↗'
    $('#sources-list').append(a)
  }
  const hero = (t) => draw($('#hero-canvas'), t, ['flip', 'half'], 'book')
  hero(0.05)
  $('#hero-play').onclick = () => {
    cancelAnimationFrame(heroAnim)
    play(2200, hero, (n) => (heroAnim = n))
  }
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) $('#hero-play').click()
  if (typeof initial.text === 'string') {
    previous = parts()
    promptBox.value = initial.text
  }
  renderCards()
  selectState()
  stageStyle()
})()
