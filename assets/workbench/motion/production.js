'use strict'

const routeNames = {
  catalog: '现成动效',
  library: '素材册搭配',
  imagegen: '透明物件图',
  html: '步骤演示',
  gif: '动态贴纸',
}
const mediaUrl = (sample, name = 'poster.webp') => '/motion-media/' + sample.id + '/' + name
const watched = new Map()
let referenceFrame = null,
  referenceUrl = null
let editing = null
let pickerApply = null
function styleLabel(value = {}) {
  return Object.keys(value)
    .map((k) => VISUAL[k]?.find((entry) => entry.id === value[k])?.name)
    .filter(Boolean)
    .join(' · ')
}
function showStyle() {
  $('style-summary').textContent = styleLabel(state.visual)
}
function openPicker(value, quote, title, apply, tab) {
  const frame = $('visual-picker')
  $('visual-title').textContent = title
  pickerApply = apply
  $('favorite-load').hidden = !localStorage.getItem('talking-head-style-favorite')
  $('favorite-status').textContent = ''
  const select = () => frame.contentWindow.setVisualSelection(value, quote, tab)
  if (frame.contentWindow?.setVisualSelection) select()
  else {
    frame.onload = select
    frame.src = 'visual/index.html?picker=1'
  }
  $('visual-dialog').showModal()
}
$('favorite-save').onclick = () => {
  const frame = $('visual-picker').contentWindow
  if (!frame.readVisualSelection) return
  localStorage.setItem('talking-head-style-favorite', JSON.stringify(frame.readVisualSelection()))
  $('favorite-load').hidden = false
  $('favorite-status').textContent = '已记住'
}
$('favorite-load').onclick = () => {
  const frame = $('visual-picker').contentWindow
  if (frame.setVisualSelection)
    frame.setVisualSelection(
      JSON.parse(localStorage.getItem('talking-head-style-favorite')),
      editing?.item.quote || '',
    )
}
$('visual-close').onclick = () => $('visual-dialog').close()
$('visual-apply').onclick = () => {
  if (!$('visual-picker').contentWindow.readVisualSelection) return
  const value = $('visual-picker').contentWindow.readVisualSelection()
  $('visual-dialog').close()
  Promise.resolve(pickerApply(value)).catch(issue)
}
$('visual-open').onclick = () =>
  openPicker(state.visual, '', '挑整篇风格', async (value) => {
    state.visual = value
    showStyle()
    save()
    if (!state.script.trim()) return
    const old = state.review
    resetReview()
    if (old) {
      state.review.skipped = old.skipped.slice()
      state.review.rows = old.rows.slice()
    }
    await startReview()
  })
function chooseEffect(review, row, item) {
  editing = { review, row, item, visual: clone(item.visual || state.visual || {}) }
  $('effect-error').textContent = ''
  $('effect-quote').textContent = '「' + item.quote + '」'
  $('production-note').value = ''
  $('effect-style-summary').textContent = styleLabel(editing.visual)
  showSentenceOptions(review, row, item)
  $('all-routes').open = false
  $('effect-dialog').showModal()
}
$('effect-close').onclick = () => $('effect-dialog').close()
$('effect-style').onclick = () =>
  openPicker(editing.visual, editing.item.quote, '只改这句的风格', (value) => {
    editing.visual = value
    $('effect-style-summary').textContent = styleLabel(value)
  })
const routes = [
  ['catalog', '挑现成动效'],
  ['library', '挑 3D 物件或贴纸'],
  ['imagegen', '画一个具体物件'],
  ['html', '把过程演一遍'],
  ['gif', '做一张会动的贴纸'],
]
for (const [route, label] of routes) {
  const b = button(label, 'quiet', async () => {
    const { review, row, item } = editing
    if (route === 'library') {
      openPicker(
        editing.visual,
        item.quote,
        '挑要放进这句的素材',
        async (value) => {
          if (!value.objects && !value.stickers) throw Error('请先选一个 3D 物件或一张贴纸。')
          await newProduction(review, row, item, route, value)
        },
        'objects',
      )
    } else if (route === 'catalog') {
      $('effect-dialog').close()
      const draft =
        item.sample || (item.producer && item.producer !== 'catalog')
          ? { ...createItem(item), id: item.id }
          : clone(state.edits[item.id] || item)
      draft.visual = editing.visual
      state.editFromReview = item.id
      await openItem(draft)
      $('open-library').click()
    } else await newProduction(review, row, item, route, editing.visual)
  })
  const click = b.onclick
  b.onclick = async (event) => {
    b.disabled = true
    try {
      await click(event)
    } catch (e) {
      $('effect-error').textContent = e.message
    } finally {
      b.disabled = false
    }
  }
  b.dataset.route = route
  $(route === 'catalog' ? 'catalog-route' : 'route-options').append(b)
}
async function newProduction(review, row, item, route, visual, treatment) {
  const note =
    $('production-note').value.trim() || '依照原句制作' + routeNames[route] + '，留透明边缘，突出讲到的内容。'
  const request = {
    workspace: state.motionWorkspace,
    request_id: key(),
    agent: review.agent,
    text: review.text,
    sentences: lines(review.text).map((line) => line.quote),
    sentence: row.sentence,
    brief: note,
    title: treatment?.label || item.title,
    seconds: Math.min(12, Math.max(1, Math.round(item.seconds || 3))),
    visual,
    route,
    ...(treatment ? { treatment: treatment.id, brief: treatment.description } : {}),
  }
  const task = await agentRequest('/api/agents/production', request)
  if (state.review !== review || (treatment && (editing?.row !== row || !$('effect-dialog').open))) return
  row.renderError = null
  row.item = {
    ...createItem(item),
    id: item.id,
    title: request.title,
    treatment: treatment?.id,
    producer: route,
    ids: [],
    visual,
    seconds: request.seconds,
  }
  row.item.productionTask = task.id
  row.candidate = true
  row.job = task.id
  row.brief = note
  if (task.sample) row.item.sample = task.sample
  $('effect-dialog').close()
  save()
  renderReview()
}
function revisitSample(item) {
  let review = state.review
  const units = lines(state.script)
  const i = units.findIndex((u) => u.quote === item.quote && u.offset === item.offset)
  if (i < 0) {
    tell('请先贴入这款素材对应的原稿，再从原句卡换效果。')
    return
  }
  if (!review || review.text !== state.script) {
    resetReview()
    review = state.review
  }
  let row = review.rows.find((r) => r.item.id === item.id)
  if (!row) {
    row = { item: clone(item), sentence: i, reason: '你已采用的素材。' }
    review.rows.push(row)
  }
  review.skipped = review.skipped.filter((s) => s !== i)
  nav('script')
  chooseEffect(review, row, item)
}
function acceptSample(item) {
  const next = clone(item)
  next.thumb = mediaUrl(next.sample)
  const index = state.items.findIndex((x) => x.id === item.id)
  if (index < 0) state.items.push(next)
  else state.items[index] = next
  delete state.edits[next.id]
  state.download = ''
}
function observeProduction(review) {
  for (const row of review.rows) {
    const job = row.job
    if (
      !job ||
      row.renderError ||
      row.item.sample ||
      watched.has(job) ||
      review.skipped.includes(row.sentence)
    )
      continue
    watched.set(job, row)
    const poll = async () => {
      if (
        row.job !== job ||
        state.review !== review ||
        !review.rows.includes(row) ||
        review.skipped.includes(row.sentence)
      ) {
        watched.delete(job)
        if (state.review) observeProduction(state.review)
        return
      }
      try {
        const task = await agentRequest('/api/agents/task?id=' + encodeURIComponent(job))
        if (row.job === job && state.review === review && (task.sample || task.status === 'failed')) {
          if (task.sample) row.item.sample = task.sample
          else row.renderError = task.error || '未能生成，可以换一版。'
          watched.delete(job)
          save()
          const card = $('picks').querySelector('[data-sentence="' + row.sentence + '"]')
          if (card) {
            const fragment = document.createDocumentFragment()
            addPick(fragment, review, row)
            card.replaceWith(fragment)
          }
          return
        }
      } catch {
        /* The durable job can be read again after the workstation reconnects. */
      }
      setTimeout(poll, 2200)
    }
    setTimeout(poll, 100)
  }
}
function sampleStage(stage, item, row) {
  if (!item.sample && item.treatment) {
    const msg = document.createElement('p')
    msg.textContent = row.renderError || '正在做好这版小样，会自动出现在这里…'
    stage.append(msg)
    return
  }
  if (!item.sample) {
    const waiting = document.createElement('small')
    waiting.textContent = '等待' + routeNames[item.producer] + '回到这里'
    stage.append(
      waiting,
      button('复制制作待办', 'quiet', async () => {
        try {
          const { card, text } = await agentRequest('/api/agents/card', { id: row.job })
          const instruction = text || card
          try {
            await navigator.clipboard.writeText(instruction)
            tell('已复制，粘贴到原助手对话即可。')
          } catch {
            const box = document.createElement('textarea')
            box.value = instruction
            stage.append(box)
            box.select()
          }
        } catch (e) {
          issue(e)
        }
      }),
    )
    return
  }
  const sample = item.sample
  const img = new Image()
  img.alt = item.title + '透明小样'
  img.src = mediaUrl(sample)
  stage.append(img)
  const backdrop = button('换底色', 'backdrop-choice', () => {
    const mode = stage.classList.contains('check')
      ? 'dark'
      : stage.classList.contains('dark')
        ? 'light'
        : 'check'
    stage.style.backgroundImage = ''
    stage.classList.remove('has-reference')
    stage.classList.remove('check', 'dark', 'light')
    stage.classList.add(mode)
  })
  stage.append(backdrop)
  if (sample.kind === 'image') stage.append(button('试看原图', 'watch', () => stage.classList.toggle('zoom')))
  else
    playerControls(
      stage,
      sample.frames,
      sample.poster,
      (f) => {
        img.src = mediaUrl(sample, 'f' + String(f).padStart(3, '0') + '.webp')
      },
      '▶ 试看 ' + sample.seconds + ' 秒',
    )
}
function playerControls(stage, count, poster, drawFrame, label) {
  const slider = document.createElement('input')
  slider.type = 'range'
  slider.className = 'pick-scrub'
  slider.setAttribute('aria-label', '逐帧查看')
  slider.min = 0
  slider.max = count - 1
  slider.value = poster
  let animation = 0,
    current = poster,
    started = false
  const stop = () => {
    cancelAnimationFrame(animation)
    animation = 0
    play.textContent = label
  }
  const paintFrame = (f) => {
    current = f
    slider.value = f
    drawFrame(f)
  }
  const play = button(label, 'watch', () => {
    if (animation) {
      stop()
      return
    }
    if (!started || current === count - 1) current = 0
    started = true
    play.textContent = '暂停'
    const start = performance.now() - (current * 1000) / FPS
    const tick = (now) => {
      if (!stage.isConnected || state.page !== 'script') {
        stop()
        return
      }
      const f = Math.min(count - 1, Math.floor(((now - start) * FPS) / 1000))
      if (f !== current || f === 0) paintFrame(f)
      if (f === count - 1) stop()
      else animation = requestAnimationFrame(tick)
    }
    animation = requestAnimationFrame(tick)
  })
  slider.oninput = () => {
    stop()
    started = true
    paintFrame(Number(slider.value))
  }
  stage.append(play, slider)
}

function setReference(image) {
  const c = document.createElement('canvas')
  const w = image.videoWidth || image.naturalWidth,
    h = image.videoHeight || image.naturalHeight
  if (!w || !h) return
  c.width = Math.min(900, w)
  c.height = Math.round((h * c.width) / w)
  c.getContext('2d').drawImage(image, 0, 0, c.width, c.height)
  referenceFrame = c.toDataURL('image/jpeg', 0.83)
  $('reference-clear').hidden = false
  renderReview()
}
$('reference-file').onchange = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  const v = $('reference-video')
  v.pause()
  v.removeAttribute('src')
  v.load()
  if (referenceUrl) URL.revokeObjectURL(referenceUrl)
  referenceUrl = URL.createObjectURL(file)
  const movie = file.type.startsWith('video/')
  v.hidden = $('reference-use').hidden = !movie
  if (movie) v.src = referenceUrl
  else {
    try {
      setReference(await decode(referenceUrl))
    } catch (e) {
      issue(e)
    }
  }
}
$('reference-use').onclick = () => setReference($('reference-video'))
$('reference-clear').onclick = () => {
  referenceFrame = null
  $('reference-clear').hidden = true
  renderReview()
}

function differentVersion(saved, candidate) {
  if (candidate.producer && candidate.producer !== 'catalog')
    return !!candidate.sample && saved.sample?.id !== candidate.sample.id
  return (
    !!saved.sample ||
    ['ids', 'title', 'theme', 'seconds', 'labels', 'values', 'a', 'b', 'files', 'visual'].some(
      (k) => JSON.stringify(saved[k] || null) !== JSON.stringify(candidate[k] || null),
    )
  )
}
