'use strict'

const annotationPrefix = /[（(][ \t]*画面[ \t]*[：:]/
let annotationRevision = 0
let annotationPending = false
let annotationTimer

const manuscriptInput = () => state.annotationSource ?? state.script
const scriptUnits = () => state.annotationUnits ?? lines(state.script)
const annotationAt = (index) => state.annotations?.[index]

function showAnnotationStatus(text) {
  const status = $('annotations-status')
  status.textContent = text
  status.hidden = !text
}

function loadManuscript(raw, recommend) {
  const revision = ++annotationRevision
  clearTimeout(annotationTimer)
  annotationPending = annotationPrefix.test(raw)
  state.annotationSource = annotationPending ? raw : null
  if (!annotationPending) {
    const hadMarks = !!state.annotationUnits
    state.annotationUnits = null
    state.annotations = []
    state.annotationParsed = null
    state.annotationErrors = []
    showAnnotationStatus('')
    state.script = raw
    if (hadMarks) resetReview()
    manuscriptChanged()
    sentences()
    save()
    if (recommend) startReview().catch(issue)
    return
  }
  showAnnotationStatus('正在读稿内画面标注…')
  renderReview()
  sentences()
  save()
  annotationTimer = setTimeout(async () => {
    try {
      const parsed = await agentRequest('/api/motion/annotations', { text: raw })
      if (revision !== annotationRevision) return
      const previous = state.review
      annotationPending = false
      state.script = parsed.text
      state.annotationUnits = parsed.units
      state.annotationParsed = raw
      state.hadAnnotations = true
      state.annotationErrors = parsed.errors
      state.annotations = []
      for (const binding of parsed.bindings)
        for (const index of binding.sentences) state.annotations[index] = binding
      resetReview(previous)
      showAnnotationSummary()
      renderReview()
      sentences()
      save()
      if (recommend) startReview().catch(issue)
    } catch (error) {
      if (revision !== annotationRevision) return
      showAnnotationStatus('画面标注暂未读完。' + error.message)
      // Keep the unparsed version out of recommendation and export.
    }
  }, 180)
}

function showAnnotationSummary() {
  const marks = (state.annotations || []).filter((binding, i) => binding?.sentences[0] === i)
  const summary = marks.length ? '已读到 ' + marks.length + ' 处画面标注。未标位置可让助手推荐。' : ''
  showAnnotationStatus([summary, ...(state.annotationErrors || [])].filter(Boolean).join(' '))
}

function annotationRows(units, previous = []) {
  const rows = []
  for (const [index, unit] of units.entries()) {
    const binding = annotationAt(index)
    if (!binding || binding.sentences[0] !== index) continue
    const signature = JSON.stringify([binding.quote, binding.notes])
    const item = createItem({ quote: binding.quote, offset: unit.offset })
    item.binding = { signature, notes: binding.notes, cue: binding.cue || '', sentences: binding.sentences }
    const old = previous.find(row => row.item.binding?.signature === signature && row.item.offset === unit.offset)
    if (old) {
      rows.push(old)
      continue
    }
    const adopted = state.items.find(s => s.binding?.signature === signature && s.offset === unit.offset)
    if (adopted) item.id = adopted.id
    item.ids = binding.ids || []
    item.visual = binding.visual || {}
    item.seconds = binding.seconds || 4
    item.poster = Math.floor(countFrames(item) * 0.55)
    item.overlay = !!binding.overlay
    item.sample = binding.sample
    item.treatment = binding.treatment
    item.producer = binding.sample || binding.treatment ? 'library' : 'catalog'
    rows.push({
      sentence: index,
      item,
      annotationMode: binding.mode,
      reason: '按你的稿内标注制作。',
      annotationError: binding.error,
    })
  }
  return rows
}

function isActiveMaterial(item) {
  if (!state.annotationUnits) return !item.binding || !state.hadAnnotations || !!item.restoredBinding
  const index = state.annotationUnits.findIndex(unit => unit.offset === item.offset)
  if (index < 0) return !item.binding
  const binding = annotationAt(index)
  if (!binding) return !item.binding
  return binding.mode === 'specified' && binding.sentences[0] === index &&
    item.binding?.signature === JSON.stringify([binding.quote, binding.notes])
}

function showAnnotationCard(index) {
  const binding = annotationAt(index)
  const card = binding && $('picks').querySelector('[data-sentence="' + binding.sentences[0] + '"]')
  card?.scrollIntoView({ block: 'center' })
}

function addAnnotationCard(list, review, row) {
  const card = document.createElement('article')
  card.className = 'paper review-card annotation-card'
  card.dataset.sentence = row.sentence
  card.dataset.annotation = row.annotationMode
  const quote = document.createElement('h3')
  quote.textContent = '「' + row.item.quote + '」'
  const status = document.createElement('p')
  status.textContent = row.renderError || {
    none: '纯口播 · 按稿内标注',
    error: row.annotationError,
    specified: '指定演示 · 按稿内标注',
  }[row.annotationMode]
  card.append(quote, status)
  if (row.annotationMode === 'specified') {
    const prepare = button('准备这版小样', 'primary', async () => {
      prepare.disabled = true
      try {
        const task = await agentRequest('/api/agents/production', {
          workspace: state.motionWorkspace,
          request_id: key(),
          agent: review.agent,
          text: review.text,
          sentences: scriptUnits().map(unit => unit.quote),
          sentence: row.sentence,
          brief: row.item.binding.notes.join(' '),
          title: row.item.title,
          seconds: row.item.seconds,
          visual: row.item.visual,
          route: 'library',
          treatment: row.item.treatment,
        })
        if (state.review !== review) return
        row.renderError = null
        row.job = task.id
        row.item.sample = task.sample
        save()
        renderReview()
      } catch (error) {
        status.textContent = error.message
        prepare.disabled = false
      }
    })
    card.append(prepare)
  }
  card.append(button('回稿件修改标注', 'quiet', focusManuscriptAnnotation))
  list.append(card)
}

function focusManuscriptAnnotation() {
  const editor = $('manuscript')
  editor.focus()
  editor.scrollIntoView({ block: 'center' })
}
