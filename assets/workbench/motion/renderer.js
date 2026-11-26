let BLUE = '#2044c5',
  INK = '#262727',
  ORANGE = '#f1843d',
  CREAM = '#fff5df',
  MINT = '#83b09a',
  FONT = '"Microsoft YaHei","PingFang SC",system-ui,sans-serif'
const TERM = Object.fromEntries(DATA.terms.map((term) => [term.id, term]))
const motionEase = { animation: { startFrame: 0, endFrame: 1, from: { p: 0 }, to: { p: 1 } } }
const cut = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)),
  ease = (v) => valueAt(cut(v), motionEase).p
const epoch = (t, a, b) => cut((t - a) / (b - a)),
  TAU = Math.PI * 2
const sceneFor = (key) =>
  DATA.quotes.find((r) => r.key === key) || {
    key: 'neutral',
    name: '重点',
    title: '重点',
    a: '之前',
    b: '之后',
    labels: ['第一步', '第二步', '第三步'],
  }
function box(g, x, y, w, h, r, fill, stroke) {
  g.beginPath()
  g.roundRect(x, y, Math.max(0, w), Math.max(0, h), r)
  if (fill) {
    g.fillStyle = fill
    g.fill()
  }
  if (stroke) {
    g.strokeStyle = stroke
    g.lineWidth = 2
    g.stroke()
  }
}
function line(g, pts, color = INK, w = 3) {
  g.beginPath()
  g.lineCap = 'round'
  g.lineJoin = 'round'
  pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)))
  g.strokeStyle = color
  g.lineWidth = w
  g.stroke()
}
function orb(g, x, y, r, col) {
  g.fillStyle = col
  g.beginPath()
  g.arc(x, y, r, 0, TAU)
  g.fill()
}
function poly(g, pts, col) {
  g.beginPath()
  pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)))
  g.closePath()
  g.fillStyle = col
  g.fill()
}
function label(g, s, x, y, size = 18, color = INK, weight = 750, max = 400) {
  g.font = weight + ' ' + size + 'px ' + FONT
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = color
  if (color === INK) {
    g.strokeStyle = '#fff5df'
    g.lineJoin = 'round'
    g.lineWidth = Math.max(1.7, size * 0.095)
    g.strokeText(s, x, y, max)
  }
  g.fillText(s, x, y, max)
}
function caption(g, s, x, y, plate = 'clear', max = 175) {
  const w = Math.min(max, 20 + Array.from(s).length * 17)
  if (plate !== 'clear')
    box(g, x - w / 2, y - 13, w, 26, 6, 'rgba(255,239,205,' + (plate === 'half' ? '.5' : '.25') + ')')
  g.font = '700 16px ' + FONT
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.strokeStyle = '#fff8e4'
  g.lineWidth = 3
  g.strokeText(s, x, y, max - 6)
  label(g, s, x, y, 16, INK, 700, max - 6)
}
function isolate(g, fn) {
  g.save()
  try {
    fn()
  } finally {
    g.restore()
  }
}
function star(g, x, y, r, color) {
  poly(
    g,
    Array.from({ length: 8 }, (_, i) => {
      const a = (i * Math.PI) / 4
      const k = i % 2 ? r * 0.24 : r
      return [x + Math.cos(a) * k, y + Math.sin(a) * k]
    }),
    color,
  )
}
function art(g, key, alt, x, y, scale = 1, image) {
  isolate(g, () => {
    g.translate(x, y)
    g.scale(scale, scale)
    if (image?.naturalWidth) {
      const k = Math.min(95 / image.width, 69 / image.height)
      g.drawImage(image, (-image.width * k) / 2, (-image.height * k) / 2, image.width * k, image.height * k)
      return
    }
    const c = alt ? ORANGE : BLUE
    switch (key) {
      case 'coffee':
        if (alt) {
          box(g, 12, -16, 22, 24, 10, null, INK)
          box(g, -28, -19, 50, 37, 12, c, INK)
          line(
            g,
            [
              [-32, 23],
              [31, 23],
            ],
            INK,
            3,
          )
          line(
            g,
            [
              [-13, -24],
              [-15, -30],
              [-13, -35],
            ],
            INK,
            2,
          )
        } else {
          g.rotate(-0.5)
          g.fillStyle = '#936142'
          g.beginPath()
          g.ellipse(-2, 0, 20, 30, 0, 0, TAU)
          g.fill()
          g.beginPath()
          g.moveTo(-4, -24)
          g.bezierCurveTo(13, -9, -13, 9, 0, 25)
          g.strokeStyle = CREAM
          g.lineWidth = 3
          g.stroke()
        }
        break
      case 'travel':
        if (!alt) {
          poly(
            g,
            [
              [-27, 5],
              [27, -24],
              [7, 27],
              [-1, 8],
            ],
            c,
          )
          line(
            g,
            [
              [-1, 8],
              [20, -16],
            ],
            CREAM,
            2,
          )
        } else {
          orb(g, 0, -9, 20, c)
          poly(
            g,
            [
              [-17, 0],
              [17, 0],
              [0, 29],
            ],
            c,
          )
          orb(g, 0, -9, 7, CREAM)
        }
        break
      case 'book':
        if (!alt) {
          box(g, -24, -29, 48, 59, 5, c, INK)
          line(
            g,
            [
              [-16, -26],
              [-16, 27],
            ],
            CREAM,
            2,
          )
          line(
            g,
            [
              [-7, -12],
              [15, -12],
            ],
            CREAM,
            3,
          )
          line(
            g,
            [
              [-7, -3],
              [9, -3],
            ],
            CREAM,
            2,
          )
        } else {
          poly(
            g,
            [
              [-15, -28],
              [15, -28],
              [15, 30],
              [0, 19],
              [-15, 30],
            ],
            c,
          )
          star(g, 0, -9, 8, CREAM)
        }
        break
      case 'plant':
        line(
          g,
          [
            [0, 26],
            [0, -9],
          ],
          INK,
          3,
        )
        g.fillStyle = alt ? MINT : BLUE
        g.beginPath()
        g.ellipse(alt ? 12 : 5, -6, alt ? 23 : 9, 11, -0.67, 0, TAU)
        g.fill()
        g.fillStyle = alt ? BLUE : MINT
        g.beginPath()
        g.ellipse(-9, 4, alt ? 14 : 8, 7, 0.55, 0, TAU)
        g.fill()
        break
      case 'product':
        box(g, -18, -17, 36, 46, 9, c, INK)
        if (!alt) {
          box(g, -19, -25, 38, 10, 4, INK)
        } else {
          box(g, -10, -35, 38, 7, 3, INK)
          line(
            g,
            [
              [17, -32],
              [22, -20],
            ],
            INK,
            2,
          )
        }
        line(
          g,
          [
            [-11, 2],
            [11, 2],
          ],
          CREAM,
          3,
        )
        break
      case 'work':
        box(g, -26, -27, 52, 55, 6, alt ? MINT : CREAM, INK)
        box(g, -13, -31, 26, 9, 4, INK)
        if (alt)
          line(
            g,
            [
              [-12, -1],
              [-2, 10],
              [15, -10],
            ],
            BLUE,
            5,
          )
        else
          for (let i = 0; i < 3; i++)
            line(
              g,
              [
                [-14, -9 + i * 10],
                [13, -9 + i * 10],
              ],
              BLUE,
              3,
            )
        break
      case 'sport':
        if (alt) {
          orb(g, 0, 0, 26, c)
          orb(g, 0, 0, 16, CREAM)
          orb(g, 0, 0, 8, BLUE)
        } else {
          poly(
            g,
            [
              [-31, 11],
              [-15, -13],
              [-2, -7],
              [2, 1],
              [29, 8],
              [31, 20],
              [-30, 20],
            ],
            c,
          )
          line(
            g,
            [
              [-28, 16],
              [27, 16],
            ],
            CREAM,
            3,
          )
        }
        break
      case 'photo':
        if (!alt) {
          box(g, -30, -18, 60, 40, 7, c, INK)
          box(g, -15, -24, 18, 7, 2, INK)
          orb(g, 2, 2, 13, CREAM)
          orb(g, 2, 2, 8, INK)
        } else {
          box(g, -30, -22, 60, 48, 4, CREAM, INK)
          poly(
            g,
            [
              [-25, 17],
              [-3, -7],
              [9, 8],
              [17, -1],
              [25, 17],
            ],
            c,
          )
          orb(g, 17, -12, 5, ORANGE)
        }
        break
      default:
        if (alt) star(g, 0, 0, 32, ORANGE)
        else orb(g, 0, 0, 25, BLUE)
    }
  })
}
function swapShape(g, id, n, ctx) {
  const x = 170,
    y = 20,
    w = 140,
    h = 108
  function tile(b) {
    const opacity = ctx.plate === 'half' ? 0.5 : ctx.plate === 'quarter' ? 0.25 : 0
    if (opacity) box(g, x, y, w, h, 15, 'rgba(' + (b ? '255,233,178,' : '212,225,255,') + opacity + ')', null)
    art(g, ctx.key, b, 240, 60, 0.82, b ? ctx.imageB : ctx.imageA)
    label(g, b ? ctx.b : ctx.a, 240, 103, 17, INK, 700, 120)
  }
  function clip(path, fn) {
    isolate(g, () => {
      g.beginPath()
      path()
      g.clip()
      fn()
    })
  }
  if (id === 'flip') {
    isolate(g, () => {
      g.translate(240, 0)
      g.scale(Math.max(0.014, Math.abs(Math.cos(Math.PI * n))), 1)
      g.translate(-240, 0)
      tile(n >= 0.5)
    })
    return
  }
  if (id === 'match') {
    isolate(g, () => {
      const k = 1 - 0.24 * Math.sin(n * Math.PI)
      g.translate(240, 72)
      g.scale(k, k)
      g.translate(-240, -72)
      tile(n >= 0.5)
    })
    return
  }
  clip(
    () => g.roundRect(x - 1, y - 1, w + 2, h + 2, 16),
    () => {
      if (id === 'push') {
        isolate(g, () => {
          g.translate(-n * w, 0)
          tile(false)
          g.translate(w, 0)
          tile(true)
        })
        return
      }
      if (n >= 1) {
        tile(true)
        return
      }
      if (n <= 0) {
        tile(false)
        return
      }
      if (id === 'cross') {
        isolate(g, () => {
          g.globalAlpha *= 1 - n
          tile(false)
        })
        isolate(g, () => {
          g.globalCompositeOperation = 'lighter'
          g.globalAlpha *= n
          tile(true)
        })
        return
      }
      const reveal = () => {
        switch (id) {
          case 'circleSwap':
            g.arc(240, 74, 95 * n, 0, TAU)
            break
          case 'shutter':
            g.moveTo(240, 74)
            g.arc(240, 74, 107, -Math.PI / 2, -Math.PI / 2 + TAU * n)
            g.closePath()
            break
          case 'blinds':
            for (let i = 0; i < 7; i++) g.rect(x - 1, y - 1 + i * 16, w + 2, 16 * n)
            break
          case 'tiles':
            for (let j = 0; j < 3; j++)
              for (let i = 0; i < 4; i++) {
                const k = cut(n * 2.1 - (i + j) * 0.22)
                g.rect(x - 1 + i * 36, y - 1 + j * 37, 36 * k, 37)
              }
            break
          case 'foldSwap':
            g.rect(240 - ((w + 2) * n) / 2, y - 1, (w + 2) * n, h + 2)
            break
          case 'diagonal': {
            const lead = x - 60 + (w + 125) * n
            g.moveTo(x - 130, y - 5)
            g.lineTo(lead, y - 5)
            g.lineTo(lead - 60, y + h + 6)
            g.lineTo(x - 130, y + h + 6)
            g.closePath()
            break
          }
        }
      }
      isolate(g, () => {
        g.beginPath()
        g.rect(x - 2, y - 2, w + 4, h + 4)
        reveal()
        g.clip('evenodd')
        tile(false)
      })
      clip(reveal, () => tile(true))
    },
  )
}
function diagram(g, id, t, c, plate) {
  if (TERM[id]?.foreground) return illustration(g, id, t, c)
  const n = epoch(t, 0.06, 0.82),
    xs = [89, 240, 391]
  if (['steps', 'travel', 'trace', 'timeline'].includes(id)) {
    for (let i = 0; i < 2; i++) {
      line(
        g,
        [
          [xs[i], 70],
          [xs[i + 1], 70],
        ],
        '#c6c4ba',
        3,
      )
      if (id === 'trace' || id === 'timeline')
        line(
          g,
          [
            [xs[i], 70],
            [xs[i] + 151 * cut(n * 2 - i), 70],
          ],
          BLUE,
          4,
        )
    }
    xs.forEach((x, i) => {
      if (id === 'timeline' && i > n * 2 + 0.14) return
      const on = i === Math.min(2, Math.floor(n * 3))
      orb(g, x, 70, id === 'steps' && on ? 23 : 18, id === 'steps' && on ? ORANGE : BLUE)
      label(g, '' + (i + 1), x, 70, 16, CREAM)
      caption(g, c.labels[i], x, 113, plate, 132)
    })
    if (id === 'travel') {
      const f = n < 0.43 ? n / 0.43 : n < 0.57 ? 1 : 1 + (n - 0.57) / 0.43
      art(g, c.key, false, 89 + 151 * f, 37, 0.47, c.imageA)
    }
    return
  }
  if (id === 'compare') {
    line(
      g,
      [
        [240, 30],
        [240, 125],
      ],
      '#aaa79d',
      1,
    )
    art(g, c.key, false, 142, 62, 0.9, c.imageA)
    caption(g, c.a, 142, 116, plate)
    if (n > 0.23) {
      art(g, c.key, true, 338, 62, 0.9, c.imageB)
      caption(g, c.b, 338, 116, plate)
    }
    return
  }
  if (id === 'switch') {
    const v = ease(epoch(n, 0.36, 0.65))
    box(g, 194, 35, 92, 44, 22, v > 0.5 ? BLUE : '#999b98')
    orb(g, 215 + 50 * v, 57, 15, CREAM)
    caption(g, n > 0.47 ? c.b : c.a, 240, 109, plate)
    return
  }
  if (id === 'explode' || id === 'stack') {
    for (let i = 2; i >= 0; i--) {
      const gap = id === 'explode' ? 5 + 21 * ease(n) : 27 - 21 * ease(n)
      const y = 74 + (i - 1) * gap
      poly(
        g,
        [
          [240, y - 21],
          [302, y],
          [240, y + 21],
          [178, y],
        ],
        [BLUE, ORANGE, MINT][i],
      )
    }
    return
  }
  if (id === 'bars') {
    const vals = c.values,
      m = Math.max(1, ...vals)
    ;[0, 1].forEach((i) => {
      const v = vals[i],
        y = 49 + 46 * i,
        k = ease(epoch(n, i * 0.18, 0.8 + i * 0.18))
      label(g, i ? c.b : c.a, 91, y, 16, INK, 700, 108)
      box(g, 154, y - 9, 200, 17, 6, '#d9dacd')
      box(g, 154, y - 9, ((200 * v) / m) * k, 17, 6, i ? ORANGE : BLUE)
      label(g, String(Math.round(v * k)), 390, y, 17)
    })
    return
  }
  if (id === 'cycle') {
    const points = [
      [240, 25],
      [321, 105],
      [159, 105],
    ]
    line(g, [...points, points[0]], '#a4acba', 3)
    points.forEach(([x, y], i) => {
      orb(g, x, y, 13, BLUE)
      label(g, '' + (i + 1), x, y, 12, CREAM)
      caption(g, c.labels[i], x + (i === 1 ? 53 : i === 2 ? -53 : 55), y, plate, 82)
    })
    const p = (n * 3) % 3,
      i = Math.floor(p),
      a = points[i],
      b = points[(i + 1) % 3]
    orb(g, a[0] + (b[0] - a[0]) * (p - i), a[1] + (b[1] - a[1]) * (p - i), 8, ORANGE)
  }
}
function titleLayer(g, opts, t, ids, y, solo, plate) {
  const find = (cat) => ids.find((id) => TERM[id]?.group === cat)
  const intro = find('type'),
    cue = find('textcue'),
    exit = find('textout')
  const text = opts.title || '此刻出发'
  const to = opts.values[1],
    from = opts.values[0]
  const str = cue === 'counter' ? String(Math.round(from + (to - from) * ease(epoch(t, 0.12, 0.84)))) : text
  const chars =
    typeof Intl.Segmenter === 'function'
      ? Array.from(new Intl.Segmenter('zh', { granularity: 'grapheme' }).segment(str), (s) => s.segment)
      : Array.from(str)
  if (!chars.length) return
  let wordStart = 0,
    wordEnd = 0
  if (cue === 'word') {
    const segments =
      typeof Intl.Segmenter === 'function'
        ? Array.from(new Intl.Segmenter('zh', { granularity: 'word' }).segment(str)).filter(
            (s) => s.isWordLike,
          )
        : []
    if (segments.length) {
      const seg = segments[Math.min(segments.length - 1, Math.floor(epoch(t, 0.15, 0.78) * segments.length))]
      wordStart = seg.index
      wordEnd = wordStart + seg.segment.length
    } else {
      wordStart = Math.min(str.length - 1, Math.floor(t * str.length))
      wordEnd = wordStart + 1
    }
  }
  let charOffset = 0
  const size = Math.min(34, 400 / Math.max(1, chars.length)),
    gap = Math.max(2, size * 0.1)
  g.font = '800 ' + size + 'px ' + FONT
  const widths = chars.map((c) => g.measureText(c).width)
  const en = epoch(t, 0.02, solo ? 0.79 : 0.4),
    out = epoch(t, solo ? 0.23 : 0.7, 0.98),
    beat = epoch(t, 0.15, 0.78)
  const spacing =
    gap + (intro === 'tracking' ? (1 - ease(en)) * 14 : 0) + (exit === 'textScatter' ? out * 23 : 0)
  const width = widths.reduce((a, b) => a + b, 0) + (chars.length - 1) * spacing
  let cursor = 240 - width / 2
  isolate(g, () => {
    if (plate !== 'clear')
      box(
        g,
        240 - width / 2 - 10,
        y - size * 0.7,
        width + 20,
        size * 1.4,
        7,
        'rgba(255,239,205,' + (plate === 'half' ? '.5' : '.25') + ')',
      )
    if (intro === 'stamp') {
      const k = 1 + 0.4 * (1 - ease(en * 2))
      g.translate(240, y)
      g.rotate(-0.08)
      g.scale(k, k)
      g.translate(-240, -y)
      box(g, 226 - width / 2, y - size * 0.8, width + 28, size * 1.6, 6, CREAM, BLUE)
    }
    if (intro === 'textFocus') g.filter = 'blur(' + (1 - ease(en)) * 9 + 'px)'
    if (intro === 'maskUp' || exit === 'textDown') {
      g.beginPath()
      g.rect(15, y - size * 0.62, 450, size * 1.32)
      g.clip()
      g.translate(
        0,
        (intro === 'maskUp' ? (1 - ease(en)) * size * 1.4 : 0) +
          (exit === 'textDown' ? out * size * 1.45 : 0),
      )
    }
    if (intro === 'inkWrite') {
      g.beginPath()
      g.rect(cursor - 3, y - size, (width + 9) * en, size * 2)
      g.clip()
    }
    if (cue === 'marker')
      box(g, cursor, y - size * 0.29, Math.max(0, width * beat), size * 0.72, 2, 'rgba(245,133,57,.6)')
    for (let i = 0; i < chars.length; i++) {
      const wordOn = charOffset >= wordStart && charOffset < wordEnd
      charOffset += chars[i].length
      const x = cursor + widths[i] / 2
      cursor += widths[i] + spacing
      const k = epoch(en * 1.55 - (i / Math.max(1, chars.length - 1)) * 0.55, 0, 1)
      const q = cut(out * 1.7 - (i / Math.max(1, chars.length - 1)) * 0.7)
      const focus = cut(1 - Math.abs(beat * (chars.length + 0.6) - i - 0.4))
      if (
        (intro === 'typeon' && i >= Math.ceil(en * chars.length)) ||
        (exit === 'eraseText' && i >= Math.ceil((1 - out) * chars.length))
      )
        continue
      isolate(g, () => {
        g.translate(x, y)
        if (intro === 'letterRise') {
          g.translate(0, (1 - k) * 27)
          g.globalAlpha *= k
        }
        if (intro === 'rollType') g.scale(Math.max(0.015, k), 1)
        if (exit === 'textFade') g.globalAlpha *= 1 - q
        if (exit === 'textScatter') g.globalAlpha *= 1 - out
        if (cue === 'waveText') g.translate(0, -12 * focus * focus)
        if (cue === 'letterBeat') g.translate(0, -20 * Math.sin((focus * Math.PI) / 2))
        const ch = intro === 'scramble' && k < 0.8 ? '0123456789'[Math.floor(t * 25 + i * 5) % 10] : chars[i]
        const col = cue === 'word' && wordOn ? BLUE : cue === 'colorText' && focus > 0.38 ? ORANGE : INK
        if (cue === 'outlineText') {
          g.font = '800 ' + size + 'px ' + FONT
          g.textAlign = 'center'
          g.textBaseline = 'middle'
          g.strokeStyle = BLUE
          g.lineWidth = 1.25
          g.strokeText(ch, 0, 0)
          g.beginPath()
          g.rect(-widths[i] / 2 - 2, -size, (widths[i] + 4) * cut(beat * chars.length - i), size * 2)
          g.clip()
        }
        label(g, ch, 0, 0, size, col, 800)
      })
    }
    if (cue === 'underline')
      line(
        g,
        [
          [240 - width / 2, y + size * 0.6],
          [240 - width / 2 + width * beat, y + size * 0.6],
        ],
        ORANGE,
        4,
      )
    if (intro === 'typeon' && en < 0.97 && t < 0.8)
      line(
        g,
        [
          [
            240 - width / 2 + ((width + spacing) * Math.ceil(en * chars.length)) / chars.length,
            y - size * 0.46,
          ],
          [
            240 - width / 2 + ((width + spacing) * Math.ceil(en * chars.length)) / chars.length,
            y + size * 0.46,
          ],
        ],
        BLUE,
        2,
      )
  })
}

function draw(canvas, t, ids = [], subject = '', solo = false, settings = {}) {
  const palette = settings.colors || {}
  BLUE=palette.accent || '#2044c5'; INK=palette.text || '#262727'; ORANGE=palette.object || '#f1843d'
  CREAM=palette.surface || '#fff5df'; MINT=settings.colors ? palette.object : '#83b09a'
  const g = canvas.getContext('2d', { willReadFrequently: true })
  g.setTransform(1, 0, 0, 1, 0, 0)
  g.clearRect(0, 0, canvas.width, canvas.height)
  const base = sceneFor(subject),
    c = { ...base, values: base.key === 'sport' ? [6000, 8000] : [3, 5], ...settings }
  const pick = (cat) => ids.find((id) => TERM[id]?.group === cat),
    enter = pick('in'),
    cue = pick('cue'),
    action = pick('loop'),
    fx = pick('fx'),
    swap = pick('swap'),
    demo = ids.find((id) => primarySlot(id) === 'demo'),
    exit = pick('out'),
    plate = pick('plate') || 'clear'
  const textMode = !!(pick('type') || pick('textcue') || pick('textout')),
    lead = ease(t / (solo ? 0.64 : 0.18)),
    end = epoch(t, solo ? 0.3 : 0.79, solo ? 0.95 : 0.99)
  const beat = epoch(t, 0.17, 0.72),
    turn = epoch(t, 0.23, 0.76)
  isolate(g, () => {
    g.scale(canvas.width / 480, canvas.height / 180)
    let dx = 0,
      dy = 0,
      k = 1,
      r = 0,
      alpha = 1
    if (enter === 'fade') alpha *= lead
    if (enter === 'lift') {
      dy += 30 * (1 - lead)
      alpha *= lead
    }
    if (enter === 'slide') dx -= 105 * (1 - lead)
    if (enter === 'pop') k *= 0.72 + 0.28 * lead + 0.16 * Math.sin(lead * Math.PI)
    if (enter === 'zoomIn') k *= 0.18 + 0.82 * lead
    if (enter === 'blurIn') {
      g.filter = 'blur(' + 8 * (1 - lead) + 'px)'
      alpha *= lead
    }
    if (enter === 'swingIn') {
      g.translate(172, 37)
      g.rotate((1 - lead) * -0.94)
      g.translate(-172, -37)
      alpha *= lead
    }
    if (exit === 'vanish') alpha *= 1 - end
    if (exit === 'drop') {
      dy += 36 * end
      alpha *= 1 - end
    }
    if (exit === 'shrink' || exit === 'spinOut') {
      k *= 1 - end
      if (exit === 'spinOut') r += end * 1.8
    }
    if (cue === 'pulse') k *= 1 + 0.14 * Math.sin(beat * Math.PI)
    if (cue === 'tilt') r += Math.sin(beat * TAU * 2) * (1 - beat) * 0.28
    if (action === 'float') dy -= 7 * Math.sin(t * TAU)
    if (action === 'breathe') k *= 1 + (0.09 * (1 - Math.cos(t * TAU))) / 2
    if (action === 'spin') r += TAU * t
    if (action === 'pendulum') {
      g.translate(240, 26)
      g.rotate(0.2 * Math.sin(t * TAU))
      g.translate(-240, -26)
    }
    if (fx === 'trail') dx += 38 * (ease(t) - 0.5)
    g.translate(240 + dx, 82 + dy)
    g.scale(k, k)
    g.rotate(r)
    g.translate(-240, -82)
    g.globalAlpha *= alpha
    if (enter === 'wipe' || exit === 'closewipe') {
      g.beginPath()
      g.rect(0, 0, 480 * Math.min(enter === 'wipe' ? lead : 1, exit === 'closewipe' ? 1 - end : 1), 180)
      g.clip()
    }
    if (enter === 'irisIn' || exit === 'irisOut') {
      g.beginPath()
      g.arc(240, 82, 255 * Math.min(enter === 'irisIn' ? lead : 1, exit === 'irisOut' ? 1 - end : 1), 0, TAU)
      g.clip()
    }
    if (solo && pick('plate')) {
      art(g, c.key, true, 240, 57, 0.95)
      isolate(g, () => {
        g.beginPath()
        g.rect(175, 101, 130, 36)
        g.clip()
        for (let i = -3; i < 9; i++) {
          const x = 154 + i * 24 + t * 50
          line(
            g,
            [
              [x, 143],
              [x + 26, 97],
            ],
            i % 2 ? MINT : ORANGE,
            8,
          )
        }
      })
      caption(g, c.name, 240, 120, plate)
      return
    }
    const onlyType = textMode && !demo && !swap && !c.imageA
    c.plate = plate
    function body() {
      if (demo && swap) {
        isolate(g, () => {
          g.translate(-16, 18)
          g.scale(0.73, 0.75)
          diagram(g, demo, t, c, plate)
        })
        isolate(g, () => {
          g.translate(204, 16)
          g.scale(0.73, 0.8)
          swapShape(g, swap, turn, c)
        })
      } else if (swap) swapShape(g, swap, turn, c)
      else if (demo) diagram(g, demo, t, c, plate)
      else if (!onlyType) {
        art(g, c.key, true, 240, 70, 1.24, c.imageA)
        if (!textMode) caption(g, c.a === base.a ? c.name : c.a, 240, 132, plate)
      }
      if (textMode) titleLayer(g, c, t, ids, onlyType ? 89 : 154, solo, plate)
    }
    if (fx === 'trail') {
      for (const [shift, a] of [
        [-27, 0.12],
        [-14, 0.24],
      ])
        isolate(g, () => {
          g.globalAlpha *= a * (0.4 + Math.sin(t * Math.PI) * 0.6)
          g.translate(shift, 0)
          body()
        })
    }
    body()
    if (action === 'orbit') orb(g, 240 + 66 * Math.cos(t * TAU), 73 + 34 * Math.sin(t * TAU), 7, ORANGE)
    if (cue === 'ring') {
      g.beginPath()
      g.ellipse(240, 72, 52, 43, -0.12, -Math.PI / 2, -Math.PI / 2 + TAU * ease(t * 1.75))
      g.strokeStyle = ORANGE
      g.lineWidth = 4
      g.stroke()
    }
    if (cue === 'pointer') {
      const v = ease(t * 2)
      line(
        g,
        [
          [332, 33],
          [307, 33],
          [307 - 32 * v, 33 + 26 * v],
        ],
        ORANGE,
        3,
      )
      if (v > 0.85)
        line(
          g,
          [
            [277, 49],
            [275, 59],
            [286, 58],
          ],
          ORANGE,
          3,
        )
    }
    if (cue === 'halo') {
      g.beginPath()
      g.arc(240, 70, 23 + 46 * beat, 0, TAU)
      g.strokeStyle = 'rgba(241,132,61,' + (1 - beat) + ')'
      g.lineWidth = 4
      g.stroke()
    }
    if (fx === 'glint')
      isolate(g, () => {
        g.globalCompositeOperation = 'source-atop'
        const x = 155 + 185 * epoch(t, 0.12, 0.85)
        poly(
          g,
          [
            [x - 9, 4],
            [x + 2, 4],
            [x + 42, 172],
            [x + 31, 172],
          ],
          'rgba(255,255,255,.85)',
        )
      })
    if (fx === 'spark') {
      ;[
        [195, 39],
        [285, 50],
        [208, 105],
      ].forEach(([x, y], i) =>
        star(g, x, y, Math.max(0, Math.sin(Math.PI * cut((t - i * 0.1) * 1.6))) * 11, ORANGE),
      )
    }
    if (fx === 'burst' || fx === 'confetti') {
      const f = epoch(t, 0.05, 0.97)
      isolate(g, () => {
        g.globalAlpha *= Math.sin(f * Math.PI)
        for (let i = 0; i < 10; i++) {
          const theta = (i * TAU) / 10,
            rad = 34 + f * (34 + (i % 3) * 8),
            x = 240 + rad * Math.cos(theta),
            y = 70 + rad * 0.7 * Math.sin(theta)
          if (fx === 'burst')
            line(
              g,
              [
                [x, y],
                [x + 11 * Math.cos(theta), y + 11 * Math.sin(theta)],
              ],
              i % 2 ? ORANGE : BLUE,
              3,
            )
          else
            isolate(g, () => {
              g.translate(x, y + 24 * f * f)
              g.rotate(i + f * 4)
              box(g, -3, -5, 6, 10, 2, [BLUE, ORANGE, MINT][i % 3])
            })
        }
      })
    }
  })
}
