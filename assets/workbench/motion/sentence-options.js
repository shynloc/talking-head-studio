'use strict'

function suggestedEffects(row, item) {
  const active = PART_EFFECTS.find(effect => effect.id === item.treatment)
  if (row.annotationMode && active?.kind === 'lesson') {
    const kit = VISUAL.practice?.find(entry => entry.demos.includes(active.assetId))
    return (kit?.demos || [active.assetId])
      .map(code => PART_EFFECTS.find(effect => effect.assetId === code))
      .filter(effect => effect && (effect.scene !== 'seal' || item.visual.objects === effect.object))
  }
  const agentChoices = (row.alternatives || [])
    .map((id) => PART_EFFECTS.find((e) => e.id === id))
    .filter(Boolean)
  const matched = PART_EFFECTS.filter(
    (e) => e.subjects?.some((word) => item.quote.includes(word)) || item.visual?.objects === e.object,
  )
    .map((effect) => ({
      effect,
      score: (effect.cues || []).filter((word) => item.quote.includes(word)).length,
    }))
    .sort((a, b) => b.score - a.score)
    .map((x) => x.effect)
  return [...new Map([...agentChoices, ...matched].map((e) => [e.id, e])).values()].slice(0, 3)
}
function showSentenceOptions(review, row, item) {
  const host = $('sentence-options')
  host.replaceChildren()
  const effects = suggestedEffects(row, item)
  function choice(label, detail, kind, action, id) {
    const b = button('', 'sentence-choice', async () => {
      if (host.inert) return
      host.inert = true
      const status = $('effect-error')
      status.textContent = '正在准备…'
      try {
        await action()
        status.textContent = ''
      } catch (e) {
        status.textContent = e.message
      } finally {
        host.inert = false
      }
    })
    const title = document.createElement('strong'),
      desc = document.createElement('small'),
      tag = document.createElement('span')
    title.textContent = label
    desc.textContent = detail
    tag.textContent = kind
    b.dataset.choice = id
    b.append(title, desc, tag)
    host.append(b)
  }
  for (const effect of effects) {
    choice(
      effect.label,
      effect.description + ' · ' + effect.assetId,
      effect.kind === 'still' ? '静态' : '动画',
      async () => {
        const visual = { ...editing.visual }
        if (effect.kind !== 'lesson' || effect.scene === 'seal' || !visual.objects) visual.objects = effect.object
        if (!row.annotationMode && !state.visual?.stickers) delete visual.stickers
        await newProduction(review, row, item, 'library', visual, effect)
      },
      effect.id,
    )
  }
  if (effects.length) return
  const normalize = (s) => s.replace(/\s/g, '').toLowerCase()
  const object = VISUAL.objects.find(
    (o) => o.id === item.visual?.objects || normalize(item.quote).includes(normalize(o.name)),
  )
  if (object) {
    choice(
      '看看' + object.name,
      '保留完整轮廓，按当前配色摆在人物旁边。',
      '静态',
      () => {
        const visual = { ...editing.visual, objects: object.id }
        delete visual.stickers
        return newProduction(review, row, item, 'library', visual)
      },
      'show-' + object.id,
    )
    if (object.tokens.anchors)
      choice(
        '放大关键部位',
        '在原物件上放大操作处，保留全貌作参照。',
        '静态',
        () =>
          newProduction(review, row, item, 'library', {
            ...editing.visual,
            objects: object.id,
            stickers: 'loupe',
          }),
        'detail-' + object.id,
      )
    if (object.tokens.anchors) return
  }
  const excerpt =
    item.quote
      .replace(/[。，、！!？?]+$/u, '')
      .split(/[，。；]/u)
      .filter(Boolean)
      .pop()
      ?.slice(0, 22) || item.quote.slice(0, 22)
  const local = localPicks([{ quote: item.quote, offset: item.offset }])[0]
  const variants = [
    ...(local ? [{ label: '用图讲清这句', desc: local.reason, plan: local }] : []),
    {
      label: '圈出重点词',
      desc: '圈出「' + excerpt + '」。',
      plan: { title: excerpt, ids: ['fade', 'pencilLoop', 'vanish'] },
    },
    {
      label: '让这句逐字出现',
      desc: '只显示「' + excerpt + '」，给人物多留一点画面。',
      plan: { title: excerpt, ids: ['typeon', 'vanish'] },
    },
  ]
  variants.forEach(({ label, desc, plan }, i) =>
    choice(
      label,
      desc,
      '动效',
      () => {
        row.item = {
          ...createItem(item),
          ...plan,
          id: item.id,
          visual: { ...editing.visual },
          producer: 'catalog',
        }
        row.candidate = true
        row.job = null
        row.renderError = null
        save()
        $('effect-dialog').close()
        renderReview()
      },
      'text-' + i,
    ),
  )
}
