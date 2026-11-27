'use strict'

const agentNames = { codex: 'Codex', workbuddy: 'WorkBuddy', service: '模型服务' }
let pollTimer = 0,
  pastePending = false,
  postInFlight = null
const chosen = (item) => state.items.some((x) => x.id === item.id && isActiveMaterial(x))
function localPicks(units, respectMarks = false) {
  const candidates = []
  for (const [sentence, line] of units.entries()) {
    if (respectMarks && annotationAt(sentence)) continue
    const plain = line.quote.replace(/[。？！.!?]+$/u, '').trim()
    if (plain.length < 5) continue
    const values = (plain.match(/\d+(?:\.\d+)?/g) || []).map(Number)
    let match, plan
    if (
      values.length === 2 &&
      /从.+(?:到|至)|(?:增加|减少|上升|下降|提高|降低)(?:到|至)/.test(plain) &&
      !/[-负]\s*\d/.test(plain) &&
      values.every((n) => n <= 99999999)
    ) {
      const unit = plain.match(/\d(?:\.\d+)?\s*(%|％|分钟|小时|秒|张|次|倍|元|天|克|米|份|毫升)/)?.[1] || ''
      plan = [
        95,
        'slopePair',
        '用两个端点连起原文里的数值，观众能看清变化方向和幅度。',
        { a: '变化前' + (unit ? ' / ' + unit : ''), b: '变化后' + (unit ? ' / ' + unit : ''), values },
      ]
    } else if (
      (match = plain.match(
        /(?:先|首先)(.+?)[，,、；;]?\s*(?:然后|再|接着)(.+?)[，,、；;]?\s*(?:最后|最终)(.+)/,
      ))
    ) {
      plan = [
        93,
        'checkList',
        '这句连续交代了三个动作。按口播顺序勾选，观众更容易跟着做。',
        {
          labels: match.slice(1).map((x) =>
            x
              .replace(/[，,、；;]$/, '')
              .trim()
              .slice(0, 24),
          ),
        },
      ]
    } else if (
      (match = plain.match(/从(.+?)(?:出发)?[，,]?(?:途经|经过|经由)(.+?)[，,]?(?:抵达|到达|到)(.+)/))
    ) {
      plan = [
        90,
        'mapTrip',
        '沿路线依次点亮三个地点，可以看清从哪里出发、经过哪里、最后到哪里。',
        { labels: match.slice(1).map((x) => x.trim().slice(0, 24)) },
      ]
    } else if ((match = plain.match(/(.{1,18}?)(?:分为|分成)(.{1,18}?)(?:和|与|、)(.{1,18})$/))) {
      plan = [
        86,
        'forkTree',
        '用一处分叉呈现原句里的两类，让观众一眼看清分类关系。',
        { labels: match.slice(1) },
      ]
    } else if ((match = plain.match(/从(.{1,20}?)(?:变成|换成|切换到)(.{1,20})$/))) {
      plan = [
        82,
        'crossEdit',
        '把前后两种状态放在一起，观众能直接看到改动发生在哪里。',
        { a: match[1], b: match[2] },
      ]
    } else if (
      (match = plain.match(/(?:点击|点按|点开)[「“"]?(.{1,14}?)[」”"，,。]?(?:即可|就能|之后|按钮|$)/))
    ) {
      plan = [72, 'tapButton', '指针按下原话提到的按钮，给观众一个明确的操作位置。', { title: match[1] }]
    } else if ((match = plain.match(/(?:请记住|关键是|重点是|特别注意|诀窍是)[，,：:]?(.+)/))) {
      plan = [
        64,
        'pencilLoop',
        '圈出这句的核心提醒，让观众看到该记住什么。',
        { title: match[1].slice(0, 32) },
      ]
    }
    if (!plan) continue
    const [score, effect, reason, fields] = plan
    candidates.push({
      sentence,
      score,
      effect,
      reason,
      title: plain.slice(0, 32),
      seconds: 4,
      ids: ['fade', effect, 'vanish'],
      ...fields,
    })
  }
  candidates.sort((a, b) => b.score - a.score || a.sentence - b.sentence)
  const distinct = [],
    repeats = []
  for (const c of candidates) (distinct.some((v) => v.effect === c.effect) ? repeats : distinct).push(c)
  return [...distinct, ...repeats].slice(0, 5)
}
function buildRows(plans, units, previous = []) {
  return plans.map((plan) => {
    const { quote, offset } = units[plan.sentence]
    const before = previous.find((x) => x.item.offset === offset && x.item.quote === quote)
    const saved = state.items.find((x) => x.offset === offset && x.quote === quote && isActiveMaterial(x))
    const item = createItem({ quote, offset })
    for (const field of ['ids', 'title', 'seconds', 'a', 'b', 'labels', 'values', 'theme'])
      if (plan[field] !== undefined) item[field] = clone(plan[field])
    item.poster = Math.round((countFrames(item) - 1) * 0.55)
    item.id = saved?.id || before?.item.id || item.id
    item.visual = clone(plan.visual || state.visual || {})
    item.producer = plan.route || 'catalog'
    if (item.producer !== 'catalog') item.ids = []
    if (plan.treatment) item.treatment=plan.treatment
    if (plan.job) item.productionTask = plan.job
    if (plan.sample) item.sample = plan.sample
    return {
      item,
      reason: plan.reason,
      sentence: plan.sentence,
      brief: plan.brief,
      alternatives: plan.alternatives || [],
      job: plan.job,
      candidate: !!saved && !!plan.job && saved.sample?.id !== plan.sample?.id,
      previous: before?.previous,
    }
  })
}
function resetReview(previous = state.review) {
  clearTimeout(pollTimer)
  $('assistant-result').value = ''
  $('copy-fallback').hidden = true
  const units = scriptUnits()
  state.review = units.length
    ? {
        text: state.script,
        agent: state.motionAgent || 'codex',
        requestId: key(),
        status: 'local',
        rows: [...annotationRows(units, previous?.rows), ...buildRows(localPicks(units, true), units)],
        skipped: [],
      }
    : null
}
function manuscriptChanged() {
  if (state.review?.text !== state.script) resetReview()
  renderReview()
}
function takePasteRequest() {
  const value = pastePending
  pastePending = false
  return value
}
function initReview() {
  state.motionWorkspace ||= storageKey === 'workspace' ? 'motion_' + key().replaceAll('-', '') : storageKey
  state.motionAgent ||= 'codex'
  showStyle()
  $('agent-mode').value = state.motionAgent
  if (storageKey !== 'workspace') $('agent-mode').options[0].text = 'Codex · 此链接的原对话'
  if (state.script && state.review?.text !== state.script) resetReview()
  if (state.annotationSource && state.annotationSource !== state.annotationParsed)
    loadManuscript(state.annotationSource, false)
  else showAnnotationSummary()
  renderReview()
  const review = state.review
  if (review?.taskId && !['ready', 'failed'].includes(review.status)) schedulePoll(review, 0)
  else if (review?.status === 'sending' && !review.taskId) startReview().catch(issue)
  save()
}
function sentenceItems() {
  if (annotationPending) return []
  const units = scriptUnits(),
    locations = new Map(units.map((line) => [line.offset, line.quote]))
  return state.items.filter((item) => isActiveMaterial(item) &&
    (item.binding ? locations.has(item.offset) : locations.get(item.offset) === item.quote))
}
function renderReview() {
  const r = state.review
  $('review').hidden = !r || annotationPending
  $('review-title').textContent = state.annotationUnits ? '稿件配画面' : '值得配画面的原句'
  $('recommend').disabled =
    annotationPending || !state.script.trim() || !scriptUnits().some((_, i) => !annotationAt(i)) ||
    (r && ['sending', 'waiting', 'claimed', 'analyzing'].includes(r.status))
  $('service-note').hidden = $('agent-mode').value !== 'service'
  if (!r) {
    $('recommend').textContent = '推荐配画面的原句'
    return
  }
  const who = agentNames[r.agent],
    status = r.status
  $('recommend').textContent =
    status === 'local'
      ? '推荐配画面的原句'
      : status === 'ready'
        ? '重新推荐'
        : status === 'failed'
          ? '重试推荐'
          : '正在等' + who + '推荐'
  let message = '本机初选。点击推荐，让助手通读整篇稿子。'
  if (status === 'ready')
    message = who + ' 已读完整稿，推荐 ' + r.rows.filter((x) => !x.retained && !x.annotationMode).length + ' 句。'
  else if (status === 'failed') message = '本机初选仍可使用。' + (r.error || '助手未能完成，可重试。')
  else if (status !== 'local') {
    if (r.delivery === 'manual' && r.taskId && status === 'waiting')
      message = '本机初选可先用。复制待办到你的 ' + who + ' 对话，助手回复后这里会自动更新。'
    else
      message =
        '本机初选可先用。' +
        who +
        (status === 'claimed' || status === 'analyzing' ? ' 正在通读全文。' : ' 待办已提交，正在等回复。')
    if (r.delivery === 'queued' && status === 'waiting')
      message = '待办已排入原 Codex 对话。如果它未自动启动，打开原对话即可继续。'
    if (r.delivery === 'unconfirmed' || r.delivery === 'fallback')
      message = '本机初选可先用。自动续接未确认，可复制同一条待办给原对话。'
  }
  $('picks-status').textContent = message
  $('handoff').hidden = !r.taskId || r.agent === 'service' || status === 'ready'
  $('copy-task').textContent = '复制待办给 ' + who
  $('bind-chat').hidden = r.agent !== 'codex'
  const n = sentenceItems().length
  $('export-choices').textContent = '导出已采用的 ' + n + ' 款 ↓'
  $('export-choices').disabled = !n
  $('total').textContent = state.items.filter(isActiveMaterial).length
  const list = $('picks')
  list.replaceChildren()
  const rows = state.annotationUnits ? [...r.rows].sort((a, b) => a.sentence - b.sentence) : r.rows
  for (const row of rows) if (!r.skipped.includes(row.sentence) || row.annotationMode) addPick(list, r, row)
  if (!list.childElementCount) {
    const empty = document.createElement('p')
    empty.className = 'empty'
    empty.textContent = r.skipped.length
      ? '这组小样已全部跳过。'
      : '目前没有必须配画面的句子，可以保留口播，也可以从全部原句里补选。'
    list.append(empty)
  }
  observeProduction(r)
  $('undo-skip').hidden = !r.rows.some((row) => r.skipped.includes(row.sentence))
}
function addPick(list, review, row) {
  if (row.annotationMode && (row.annotationMode !== 'specified' || (row.item.treatment && (!row.job || row.renderError) && !row.item.sample))) {
    addAnnotationCard(list, review, row)
    return
  }
  const saved = state.items.find((x) => x.id === row.item.id)
  const item = (row.candidate ? row.item : saved) || row.item
  const adopted = !!saved && !row.candidate
  const card = document.createElement('article')
  card.className = 'paper review-card'
  card.dataset.sentence = row.sentence
  if (row.annotationMode) card.dataset.annotation = row.annotationMode
  const visual = document.createElement('div')
  visual.className = 'pick-stage check'
  if (item.producer && item.producer !== 'catalog') sampleStage(visual, item, row)
  else {
    const canvas = document.createElement('canvas')
    canvas.width = 720
    canvas.height = 270
    canvas.setAttribute('aria-label', item.title + '透明小样')
    let imgs = {}
    const still = () => paint(canvas, item, item.poster, imgs)
    still()
    if (item.overlay || Object.keys(item.files || {}).length)
      loadImages(item)
        .then((result) => {
          imgs = result
          if (canvas.isConnected) still()
        })
        .catch(issue)
    playerControls(
      visual,
      countFrames(item),
      item.poster,
      (f) => paint(canvas, item, f, imgs),
      '▶ 试看 ' + item.seconds + ' 秒',
    )
    visual.prepend(canvas)
  }
  const copy = document.createElement('div')
  copy.className = 'pick-copy'
  const quote = document.createElement('h3')
  quote.textContent = '「' + item.quote + '」'
  let recipeNote = ''
  const why = document.createElement('p')
  why.textContent = row.reason
  if (chosen(item) && item.ids.join() !== row.item.ids.join()) recipeNote = '已保留你采用的效果 · '

  const recipe = document.createElement('small')
  recipe.textContent = recipeNote + item.ids.map((id) => TERM[id].name).join(' · ')
  const actions = document.createElement('div')
  actions.className = 'pick-actions'
  const ready = !item.producer || item.producer === 'catalog' || !!item.sample
  const accept = button(
    adopted ? '已采用 · 撤销' : saved ? '采用新版' : '采用',
    'accept ' + (adopted ? 'quiet' : 'primary'),
    async () => {
      try {
        accept.disabled = true
        const loaded = await loadImages(item)
        if (state.review !== review || !card.isConnected) return
        if (!adopted && saved) row.previous = clone(saved)
        if (adopted) {
          state.items = state.items.filter((x) => x.id !== item.id)
          state.download = ''
        } else if (item.sample) acceptSample(item)
        else {
          const next = clone(item)
          if (next.overlay && !next.files.imageA) {
            const source = document.createElement('canvas')
            source.width = loaded.imageA.width
            source.height = loaded.imageA.height
            source.getContext('2d').drawImage(loaded.imageA, 0, 0)
            next.files.imageA = source.toDataURL('image/png')
          }
          putReviewed(next, item.poster, loaded)
        }
        row.candidate = false
        save()
        renderReview()
      } catch (e) {
        accept.disabled = false
        issue(e)
      }
    },
  )
  accept.disabled = !ready
  if (item.producer && item.producer !== 'catalog')
    recipe.textContent = (PART_EFFECTS.find(e=>e.id===item.treatment)?.label || routeNames[item.producer]) + (item.sample ? ' · 已就绪' : row.renderError ? ' · 可换一版' : ' · 制作中')
  accept.setAttribute('aria-pressed', String(adopted))
  actions.append(accept)
  if (row.annotationMode) actions.append(button('回稿件修改标注', 'quiet', focusManuscriptAnnotation))
  else actions.append(
    button('换效果', 'quiet change-effect', () => chooseEffect(review, row, item)),
    button('跳过', 'link skip', () => {
      if (saved) {
        state.items = state.items.filter((x) => x.id !== item.id)
        state.download = ''
      }
      review.skipped.push(row.sentence)
      save()
      renderReview()
    }),
  )
  if (saved && row.candidate)
    actions.append(
      button('保留已用版', 'link', () => {
        row.candidate = false
        save()
        renderReview()
      }),
    )
  if (!row.annotationMode && saved && !row.candidate && differentVersion(saved, row.item))
    actions.append(
      button('看新版', 'link', () => {
        row.candidate = true
        save()
        renderReview()
      }),
    )
  if (row.previous && adopted)
    actions.append(
      button('恢复上一版', 'link', () => {
        const idx = state.items.findIndex((x) => x.id === item.id)
        const previous = row.previous
        row.previous = clone(item)
        state.items[idx] = clone(previous)
        row.item = clone(previous)
        row.job = null
        row.candidate = false
        if (previous.sample) delete state.edits[item.id]
        else state.edits[item.id] = clone(previous)
        state.download = ''
        save()
        renderReview()
      }),
    )
  if (referenceFrame) {
    visual.classList.add('has-reference')
    visual.style.backgroundImage = 'url(' + referenceFrame + ')'
  }
  copy.append(quote, why, recipe, actions)
  if (item.binding?.cue) {
    const cue = document.createElement('p')
    cue.textContent = '说到「' + item.binding.cue + '」时出现'
    copy.append(cue)
  }
  if (row.annotationMode) {
    const detail = document.createElement('details')
    const label = document.createElement('summary')
    const note = document.createElement('p')
    label.textContent = '查看稿内标注'
    note.textContent = item.binding.notes.join('　')
    detail.append(label, note)
    copy.append(detail)
  }
  const codes = item.ids.map(id => TERM[id]?.assetId).filter(Boolean)
  const color = VISUAL.palettes.find(entry => entry.id === (item.visual?.palettes || 'atelier'))
  for (const group of ['styles', 'palettes', 'objects', 'stickers']) {
    const entry = VISUAL[group].find(asset => asset.id === item.visual?.[group])
    if (entry) codes.push(entry.variants && color ? entry.assetId + '@' + color.assetId : entry.assetId)
  }
  const treatment = PART_EFFECTS.find(effect => effect.id === item.treatment)
  if (treatment) codes.push(treatment.assetId)
  if (codes.length) {
    const detail = document.createElement('details')
    const label = document.createElement('summary')
    const text = document.createElement('code')
    label.textContent = '查看素材编号'
    text.textContent = codes.join(' / ')
    detail.append(label, text)
    copy.append(detail)
  }
  card.append(visual, copy)
  list.append(card)
}
async function agentRequest(url, body) {
  if (!token) await session()
  const call = () =>
    fetch(url, {
      method: body ? 'POST' : 'GET',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Studio-Token': token },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
  let response = await call()
  if (response.status === 403) {
    await session()
    response = await call()
  }
  return jsonResponse(response)
}
function consumeTask(r, task) {
  if (state.review !== r || r.text !== state.script) return
  const changed = r.status !== task.status || r.delivery !== task.delivery || r.taskId !== task.id
  r.taskId = task.id
  r.status = task.status
  r.delivery = task.delivery
  r.error = task.error
  if (task.status === 'ready' && changed) {
    const old = r.rows,
      units = scriptUnits()
    r.rows = [...annotationRows(units, old),
      ...buildRows(task.recommendations.filter(x => !annotationAt(x.sentence)), units, old)]
    // Keep a creator's earlier choices even when the Agent chose different lines.
    for (const row of old)
      if (
        !r.rows.some((x) => x.sentence === row.sentence) &&
        !annotationAt(row.sentence) && (chosen(row.item) || state.editFromReview === row.item.id)
      )
        r.rows.push({ ...row, retained: true, reason: '你在助手回复前保留的搭配。' })
  }
  if (changed) {
    save()
    renderReview()
  }
  if (!['ready', 'failed'].includes(r.status)) schedulePoll(r)
}
function schedulePoll(r, delay = 2600) {
  clearTimeout(pollTimer)
  pollTimer = setTimeout(async () => {
    if (state.review !== r) return
    try {
      const task = await agentRequest('/api/agents/task?id=' + encodeURIComponent(r.taskId))
      if (state.review !== r) return
      if (task.agent === 'codex' && task.status === 'waiting' && task.delivery === 'manual') {
        const link = await agentRequest(
          '/api/agents/connection?project=' + encodeURIComponent(state.motionWorkspace),
        )
        if (link.codex_bound && link.codex_available && state.review === r) {
          consumeTask(r, await agentRequest('/api/agents/resume', { id: r.taskId }))
          return
        }
      }
      consumeTask(r, task)
    } catch (e) {
      if (state.review === r) {
        $('picks-status').textContent = '连接暂时中断，已选小样保留。正在重连。'
        schedulePoll(r, 6000)
      }
    }
  }, delay)
}
async function startReview() {
  if (annotationPending || !state.script.trim() || !scriptUnits().some((_, i) => !annotationAt(i))) return
  if (!state.review || state.review.text !== state.script) resetReview()
  const r = state.review
  if (postInFlight === r) return
  if (r.taskId && ['waiting', 'claimed', 'analyzing'].includes(r.status)) return
  if (['ready', 'failed'].includes(r.status)) {
    r.requestId = key()
    r.taskId = null
    r.delivery = ''
    const previous = r.rows
    const units = scriptUnits()
    r.rows = [...annotationRows(units, previous), ...buildRows(localPicks(units, true), units, previous)]
    for (const row of previous)
      if (!annotationAt(row.sentence) && chosen(row.item) && !r.rows.some((x) => x.sentence === row.sentence))
        r.rows.push({ ...row, retained: true })
  }
  r.agent = state.motionAgent || 'codex'
  r.status = 'sending'
  postInFlight = r
  renderReview()
  save()
  try {
    const task = await agentRequest('/api/agents/motion', {
      workspace: state.motionWorkspace,
      request_id: r.requestId,
      agent: r.agent,
      text: r.text,
      visual: state.visual || {},
      sentences: scriptUnits().map((x) => x.quote),
      ...(state.annotationParsed ? { marked_script: state.annotationParsed } : {}),
    })
    consumeTask(r, task)
  } catch (e) {
    if (state.review === r) {
      r.status = 'failed'
      r.error = e.message
      save()
      renderReview()
    }
  } finally {
    if (postInFlight === r) postInFlight = null
  }
}
async function copyInstructions(kind) {
  const r = state.review
  const payload =
    kind === 'task'
      ? await agentRequest('/api/agents/card', { id: r.taskId })
      : await agentRequest('/api/agents/connection?project=' + encodeURIComponent(state.motionWorkspace))
  if (state.review !== r) return
  const text = payload.text || payload.card
  try {
    await navigator.clipboard.writeText(text)
    tell('已复制，粘贴到要继续的助手对话即可。')
  } catch {
    const box = $('copy-fallback')
    box.hidden = false
    box.value = text
    box.focus()
    box.select()
    tell('已选中指令，可复制到助手对话。')
  }
}
$('manuscript').addEventListener('paste', () => {
  pastePending = true
  setTimeout(() => {
    pastePending = false
  }, 0)
})
$('recommend').onclick = () => startReview().catch(issue)
$('agent-mode').onchange = () => {
  state.motionAgent = $('agent-mode').value
  resetReview()
  renderReview()
  save()
}
$('undo-skip').onclick = () => {
  state.review.skipped = []
  save()
  renderReview()
}
$('export-choices').onclick = () => {
  state.packFromScript = true
  state.download = ''
  nav('pack')
  makePack()
}
$('copy-task').onclick = () => copyInstructions('task').catch(issue)
$('bind-chat').onclick = () => copyInstructions('bind').catch(issue)
$('apply-result').onclick = async () => {
  const r = state.review
  try {
    consumeTask(
      r,
      await agentRequest('/api/agents/complete-manually', {
        id: r.taskId,
        result: $('assistant-result').value,
      }),
    )
    $('assistant-result').value = ''
  } catch (e) {
    issue(e)
  }
}
