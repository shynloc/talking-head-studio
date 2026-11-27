'use strict'

const harmonyOptions = {
  complementary: {label: '互补色', offsets: [180, 30, 210]},
  analogous: {label: '邻近色', offsets: [30, -30, 60]},
  monochrome: {label: '单色深浅', offsets: [0, 0, 0]},
  split: {label: '分裂互补', offsets: [150, 210, 20]},
  triadic: {label: '三色搭配', offsets: [120, 240, 60]},
  tetradic: {label: '四色搭配', offsets: [90, 180, 270]},
}

function paletteLuminance(hex) {
  const values = hex.slice(1).match(/../g).map(c => {
    const channel = parseInt(c, 16)/255
    return channel <= .04045 ? channel/12.92 : ((channel+.055)/1.055)**2.4
  })
  return .2126*values[0]+.7152*values[1]+.0722*values[2]
}

function foregroundOn(hex) {
  return paletteLuminance(hex) > .179 ? '#000000' : '#FFFFFF'
}

function toHsl(color) {
  const [r,g,b] = color.slice(1).match(/../g).map(c => parseInt(c,16)/255)
  const hi = Math.max(r,g,b), lo = Math.min(r,g,b), delta = hi-lo, l = (hi+lo)/2
  if (!delta) return [0,0,l]
  const sector = hi === r ? (g-b)/delta : hi === g ? 2+(b-r)/delta : 4+(r-g)/delta
  return [(60*sector+360)%360, delta/(1-Math.abs(2*l-1)), l]
}

function fromHsl(h, s, l) {
  const hue = (h % 360 + 360) % 360
  const a = s*Math.min(l,1-l)
  const channel = n => {
    const k = (n+hue/30)%12
    return Math.round(255*(l-a*Math.max(-1,Math.min(k-3,9-k,1)))).toString(16).padStart(2,'0')
  }
  return ('#'+channel(0)+channel(8)+channel(4)).toUpperCase()
}

function harmonyPalette(first, second, mode) {
  const rule = harmonyOptions[mode]
  const [h,s,l] = toHsl(first)
  const strength = mode === 'monochrome' ? s : Math.max(.35, s*.82)
  const related = [0,1,2].map((i) => fromHsl(h+rule.offsets[i], strength, [.43,.64,.78][i]))
  const colors = {
    surface: fromHsl(h, s*.35, .96),
    text: fromHsl(h, s*.28, .12),
    object: first.toUpperCase(),
    accent: second?.toUpperCase() || related[0],
    supporting: second ? related[0] : related[1],
    tint: mode === 'monochrome' ? fromHsl(h,s,l>.55?.30:.83) : related[2],
  }
  return {
    name: '自定义 · ' + rule.label,
    colors,
    theme: [first.toUpperCase(), second?.toUpperCase()].filter(Boolean),
    rule: rule.label+'围绕主题色生成，输入的主题色保留原值。',
    distribution: '浅色背景用于大片留白，正文用深色，主题色和强调色用于物件、按钮或重点提示。',
  }
}

function mountPaletteLab(host, apply, restore, report) {
  host.innerHTML = '<div class="color-lab-top"><h3>用自己的颜色做色卡</h3></div>'
    + '<div class="color-fields"><label>主题色 1 <input type="color" id="theme-one" value="#E8833E"></label>'
    + '<label><input id="theme-two-on" type="checkbox"> 加第二个主题色</label>'
    + '<label id="theme-two-label" hidden>主题色 2 <input type="color" id="theme-two" value="#002FA7"></label>'
    + '<label>搭配方式 <select id="harmony"></select></label></div>'
    + '<p id="harmony-note"></p><div class="color-chips" id="color-chips"></div>'
    + '<div class="actions"><button type="button" id="apply-colors">试到网页上</button>'
    + '<button type="button" id="copy-colors">复制色卡</button>'
    + '<button type="button" id="restore-colors" hidden>恢复所选色系</button></div>'
  const find = id => host.querySelector('#' + id)
  const mode = find('harmony')
  const notes = {
    complementary: '用色环上相对的颜色拉开重点。',
    analogous: '用色环上相邻的颜色做自然过渡。',
    monochrome: '沿用同一色相，用深浅拉开层次。',
    split: '用互补色两边的颜色增加变化，保持主色突出。',
    triadic: '用色环上等距的三种颜色，选一个主角。',
    tetradic: '用两组互补色，给每组分配清楚的用途。',
  }
  const colorLabels = {surface:'背景',text:'正文',object:'主题色 1',accent:'强调色',
    supporting:'搭配色',tint:'辅助色'}
  for (const [value, {label}] of Object.entries(harmonyOptions)) mode.add(new Option(label,value))
  let current
  let active = false
  function update() {
    const two = find('theme-two-on').checked
    find('theme-two-label').hidden = !two
    current = harmonyPalette(find('theme-one').value, two ? find('theme-two').value : null, mode.value)
    find('harmony-note').textContent = notes[mode.value] + (two ? ' 第二个主题色原样保留为强调色。' : '')
    find('color-chips').replaceChildren(...Object.entries(current.colors).map(([role, hex]) => {
      const item = node('div', null, 'color-chip')
      item.style.background = hex
      item.style.color = foregroundOn(hex)
      item.append(node('span', role === 'accent' && two ? '主题色 2' : colorLabels[role]), node('code', hex))
      return item
    }))
    if (active) apply(current)
  }
  host.addEventListener('input', update)
  find('apply-colors').onclick = () => {
    setActive(true)
    apply(current)
    report('已套用到网页预览，保存 HTML 会保留这套色卡。')
  }
  find('copy-colors').onclick = async () => {
    const text = current.name + '\n' + current.rule + '\n'
      + Object.entries(current.colors).map(([k,v]) => (k === 'accent' && current.theme.length===2 ? '主题色 2' : colorLabels[k])+' '+v).join('\n') + '\n\n'
      + ':root {\n'+Object.entries(current.colors).map(([k,v])=>'  --'+k+': '+v+';').join('\n')+'\n}'
    try {
      await navigator.clipboard.writeText(text)
      report('已复制色卡和 CSS 色值。')
    } catch {
      const field = node('textarea', text)
      field.value = text
      field.setAttribute('aria-label','待复制的色卡')
      host.querySelector('textarea')?.remove()
      host.append(field)
      field.select()
      report('色卡已选中，可按系统复制快捷键。')
    }
  }
  find('restore-colors').onclick = () => {
    setActive(false)
    restore()
    report('已恢复所选色系。')
  }
  function setActive(value) {
    active = value
    find('restore-colors').hidden = !active
    find('apply-colors').setAttribute('aria-pressed',String(active))
  }
  update()
  return {setActive}
}
