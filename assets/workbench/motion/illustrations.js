// Foreground compositions share the preview/export clock and a 480 × 180 logical canvas.
const primarySlot = (id) => (TERM[id]?.foreground ? 'demo' : TERM[id]?.group)
function ringStroke(g, x, y, r, start, end, color, width = 4) {
  if (end <= start) return
  g.beginPath()
  g.arc(x, y, r, start, end)
  g.lineWidth = width
  g.strokeStyle = color
  g.lineCap = 'round'
  g.stroke()
}
function partialLine(g, points, p, color = BLUE, width = 3) {
  const lengths = points.slice(1).map(([x, y], i) => Math.hypot(x - points[i][0], y - points[i][1]))
  let left = lengths.reduce((a, b) => a + b, 0) * cut(p)
  const path = [points[0]]
  for (let i = 0; i < lengths.length; i++) {
    const f = cut(left / (lengths[i] || 1)),
      [x, y] = points[i],
      [u, v] = points[i + 1]
    path.push([x + (u - x) * f, y + (v - y) * f])
    left -= lengths[i]
    if (left <= 0) break
  }
  line(g, path, color, width)
  return path[path.length - 1]
}
function chartGraphic(g, id, t, c) {
  const p = ease(epoch(t, 0.08, 0.83)),
    [a, b] = c.values,
    max = Math.max(1, a, b),
    fraction = a + b > 0 ? a / (a + b) : 0
  const values = () => {
    caption(g, c.a + ' ' + a, 138, 132, c.plate)
    caption(g, c.b + ' ' + b, 342, 132, c.plate)
  }
  if (id === 'shareRing' || id === 'goalDial') {
    const start = id === 'goalDial' ? Math.PI : -Math.PI / 2,
      span = id === 'goalDial' ? Math.PI : TAU,
      r = 45,
      cy = id === 'goalDial' ? 86 : 63
    ringStroke(g, 240, cy, r, start, start + span, '#cbc8bd', 11)
    if (id === 'goalDial') {
      if (b > 0) {
        const angle = start + Math.PI * cut(a / b) * p
        ringStroke(g, 240, cy, r, start, angle, BLUE, 11)
        line(
          g,
          [
            [240, cy],
            [240 + 34 * Math.cos(angle), cy + 34 * Math.sin(angle)],
          ],
          ORANGE,
          4,
        )
        orb(g, 240, cy, 5, INK)
      } else label(g, '—', 240, 72, 22)
    } else if (a + b > 0) {
      ringStroke(g, 240, cy, r, start, start + span * Math.min(fraction, p), BLUE, 10)
      if (p > fraction) ringStroke(g, 240, cy, r, start + span * fraction, start + span * p, ORANGE, 10)
    }
  } else if (id === 'stackRatio') {
    box(g, 98, 60, 284, 24, 8, '#d4d1c6')
    if (a + b) {
      box(g, 98, 60, 284 * fraction * p, 24, 5, BLUE)
      box(g, 98 + 284 * fraction * p, 60, 284 * (1 - fraction) * p, 24, 5, ORANGE)
    }
  } else if (id === 'dotPair') {
    line(
      g,
      [
        [90, 70],
        [390, 70],
      ],
      '#b5b7b5',
      2,
    )
    for (let n = 0; n <= 6; n++)
      line(
        g,
        [
          [90 + 50 * n, 65],
          [90 + 50 * n, 75],
        ],
        INK,
        1,
      )
    const x = 90 + (300 * a) / max,
      y = x + ((300 * (b - a)) / max) * p
    line(
      g,
      [
        [x, 70],
        [y, 70],
      ],
      MINT,
      7,
    )
    orb(g, x, 70, 10, BLUE)
    orb(g, y, 70, 6, ORANGE)
  } else {
    const start = [132, 101 - (67 * a) / max],
      end = [346, 101 - (67 * b) / max]
    line(
      g,
      [
        [116, 107],
        [364, 107],
      ],
      '#aaa89d',
      2,
    )
    const tip = partialLine(g, [start, end], p, BLUE, 5)
    orb(g, ...start, 7, BLUE)
    orb(g, ...tip, 7, ORANGE)
  }
  values()
}
function relationGraphic(g, id, t, c) {
  const p = epoch(t, 0.05, 0.84)
  if (id === 'nestedBoxes') {
    for (let i = 0; i < 3; i++)
      isolate(g, () => {
        g.globalAlpha *= cut(p * 3 - i)
        box(g, 90 + i * 47, 18 + i * 27, 300 - i * 94, 116 - i * 29, 8, null, [BLUE, ORANGE, INK][i])
        caption(g, c.labels[i], 240, 30 + i * 32, 'clear', 150)
      })
    return
  }
  if (id === 'handover') {
    const pts = [
      [95, 66],
      [240, 66],
      [385, 66],
    ]
    line(g, pts, '#bfbdaf', 3)
    pts.forEach(([x, y], i) => {
      orb(g, x, y, 13, BLUE)
      caption(g, c.labels[i], x, 106, c.plate, 125)
    })
    const [x, y] = partialLine(g, pts, p, ORANGE, 4)
    box(g, x - 10, y - 17, 20, 12, 4, ORANGE)
    return
  }
  const fork = id === 'forkTree',
    pts = fork
      ? [
          [108, 77],
          [364, 38],
          [364, 113],
        ]
      : [
          [110, 38],
          [110, 113],
          [364, 77],
        ]
  const routes = fork
    ? [
        [pts[0], pts[1]],
        [pts[0], pts[2]],
      ]
    : [
        [pts[0], pts[2]],
        [pts[1], pts[2]],
      ]
  routes.forEach(([[x, y], [u, v]], i) =>
    partialLine(
      g,
      [
        [x, y],
        [225, y],
        [250, v],
        [u, v],
      ],
      cut(p * 1.8 - i * 0.6),
      i ? ORANGE : BLUE,
      4,
    ),
  )
  pts.forEach(([x, y], i) => {
    box(g, x - 60, y - 15, 120, 30, 9, CREAM, INK)
    label(g, c.labels[i], x, y, 14, INK, 700, 112)
  })
}
function locationGraphic(g, id, t, c) {
  const p = ease(epoch(t, 0.04, 0.86))
  if (id === 'mapTrip') {
    const pts = [
      [77, 83],
      [161, 83],
      [196, 44],
      [267, 44],
      [304, 81],
      [398, 81],
    ]
    isolate(g, () => {
      g.setLineDash([5, 6])
      line(g, pts, '#979b9c', 2)
    })
    const tip = partialLine(g, pts, p, BLUE, 4)
    ;[pts[0], pts[2], pts[5]].forEach(([x, y], i) => {
      orb(g, x, y, 6, ORANGE)
      caption(g, c.labels[i], x, y + 28, c.plate, 130)
    })
    orb(g, ...tip, 8, BLUE)
    return
  }
  if (id === 'pinDrop') {
    line(
      g,
      [
        [163, 90],
        [317, 90],
      ],
      MINT,
      2,
    )
    line(
      g,
      [
        [240, 45],
        [240, 108],
      ],
      MINT,
      2,
    )
    const y = 65 - 35 * (1 - p)
    poly(
      g,
      [
        [231, y],
        [249, y],
        [240, y + 25],
      ],
      ORANGE,
    )
    orb(g, 240, y - 4, 14, ORANGE)
    orb(g, 240, y - 4, 6, CREAM)
    caption(g, c.title, 240, 128, c.plate)
    return
  }
  if (id === 'radarFind') {
    ;[16, 30, 44].forEach((r) => ringStroke(g, 240, 65, r, 0, TAU, MINT, 1.5))
    const angle = t * TAU - Math.PI / 2
    poly(
      g,
      [
        [240, 65],
        [240 + 44 * Math.cos(angle - 0.5), 65 + 44 * Math.sin(angle - 0.5)],
        [240 + 44 * Math.cos(angle), 65 + 44 * Math.sin(angle)],
      ],
      '#8bbca0',
    )
    line(
      g,
      [
        [240, 65],
        [240 + 44 * Math.cos(angle), 65 + 44 * Math.sin(angle)],
      ],
      BLUE,
      2,
    )
    orb(g, 264, 48, 3 + 4 * p, ORANGE)
    caption(g, c.title, 240, 128, c.plate)
    return
  }
  orb(g, 159, 65, 14, BLUE)
  orb(g, 161, 61, 4, ORANGE)
  partialLine(
    g,
    [
      [174, 67],
      [224, 67],
      [261, 51],
    ],
    p,
    INK,
    2,
  )
  ringStroke(g, 301, 62, 18 + 15 * p, 0, TAU, BLUE, 3)
  orb(g, 301, 62, 7 + 8 * p, ORANGE)
  line(
    g,
    [
      [323, 84],
      [343, 101],
    ],
    INK,
    5,
  )
  caption(g, c.a, 150, 123, c.plate)
  caption(g, c.b, 330, 123, c.plate)
}
function interfaceGraphic(g, id, t, c) {
  const p = epoch(t, 0.05, 0.85)
  if (id === 'checkList') {
    c.labels.forEach((s, i) => {
      const y = 33 + i * 37
      box(g, 142, y - 9, 19, 19, 4, CREAM, BLUE)
      partialLine(
        g,
        [
          [145, y],
          [150, y + 5],
          [158, y - 7],
        ],
        cut(p * 3 - i),
        BLUE,
        3,
      )
      caption(g, s, 254, y, c.plate, 164)
    })
    return
  }
  if (id === 'sliderMove') {
    line(
      g,
      [
        [119, 70],
        [361, 70],
      ],
      '#b9b8ad',
      7,
    )
    const x = 119 + 242 * ease(p)
    line(
      g,
      [
        [119, 70],
        [x, 70],
      ],
      BLUE,
      7,
    )
    orb(g, x, 70, 12, ORANGE)
    caption(g, c.a, 127, 110, c.plate)
    caption(g, c.b, 355, 110, c.plate)
    return
  }
  if (id === 'typeField') {
    box(g, 78, 45, 324, 55, 10, CREAM, INK)
    const chars = Array.from(c.title),
      n = Math.ceil(chars.length * p)
    label(g, chars.slice(0, n).join('') + (n < chars.length ? '▏' : ''), 240, 72, 20, INK, 700, 296)
    return
  }
  if (id === 'fileDrop') {
    isolate(g, () => {
      g.setLineDash([6, 4])
      box(g, 281, 36, 78, 62, 7, null, BLUE)
    })
    const k = ease(p),
      x = 143 + 176 * k,
      y = 73 - 28 * Math.sin(Math.PI * k)
    box(g, x - 15, y - 18, 30, 36, 4, CREAM, INK)
    line(
      g,
      [
        [x - 8, y],
        [x + 9, y],
      ],
      BLUE,
      2,
    )
    if (p > 0.78)
      partialLine(
        g,
        [
          [330, 77],
          [336, 84],
          [348, 68],
        ],
        epoch(p, 0.78, 1),
        ORANGE,
        3,
      )
    caption(g, c.a, 145, 128, c.plate)
    caption(g, c.b, 326, 128, c.plate)
    return
  }
  const press = Math.sin(epoch(t, 0.43, 0.71) * Math.PI)
  box(g, 161 + press * 3, 47 + press * 2, 158 - 6 * press, 43 - 4 * press, 12, CREAM, BLUE)
  label(g, c.title, 240, 68, 17, INK, 750, 142)
  const x = 330 - 67 * ease(p * 1.8),
    y = 122 - 46 * ease(p * 1.8)
  poly(
    g,
    [
      [x, y],
      [x + 4, y + 19],
      [x + 10, y + 13],
      [x + 20, y + 12],
    ],
    INK,
  )
  if (t > 0.43 && t < 0.9)
    isolate(g, () => {
      const a = epoch(t, 0.43, 0.9)
      g.globalAlpha *= 1 - a
      ringStroke(g, 263, 76, 8 + 30 * a, 0, TAU, ORANGE, 2)
    })
}
function editorialGraphic(g, id, t, c) {
  const p = epoch(t, 0.05, 0.85)
  if (id === 'sideBrace') {
    partialLine(
      g,
      [
        [163, 21],
        [147, 21],
        [147, 130],
        [163, 130],
      ],
      p,
      BLUE,
      4,
    )
    c.labels.forEach((s, i) => caption(g, s, 257, 37 + i * 37, c.plate, 168))
    return
  }
  if (id === 'pencilLoop') {
    caption(g, c.title, 240, 72, c.plate, 210)
    const pts = Array.from({ length: 54 }, (_, i) => {
      const a = (i / 53) * TAU - 0.35
      return [240 + 105 * Math.cos(a) + 2 * Math.sin(3 * a), 72 + 31 * Math.sin(a) - 4 * Math.cos(a)]
    })
    partialLine(g, pts, p, ORANGE, 3)
    return
  }
  if (id === 'noteCorner') {
    box(g, 158, 36, 165, 80, 4, '#ffedbd', INK)
    const n = 5 + p * 22
    poly(
      g,
      [
        [323 - n, 36],
        [323, 36 + n],
        [323 - n, 36 + n],
      ],
      ORANGE,
    )
    label(g, c.title, 235, 77, 18, INK, 750, 140)
    return
  }
  if (id === 'crossEdit') {
    caption(g, c.a, 146, 71, c.plate, 127)
    partialLine(
      g,
      [
        [78, 73],
        [212, 67],
      ],
      cut(p * 2),
      ORANGE,
      4,
    )
    isolate(g, () => {
      g.globalAlpha *= epoch(p, 0.4, 1)
      caption(g, c.b, 340, 70, c.plate, 132)
    })
    return
  }
  if (id === 'quotePair') {
    const gap = 55 + 113 * ease(p)
    label(g, '“', 240 - gap, 63, 48, BLUE)
    label(g, '”', 240 + gap, 89, 48, ORANGE)
    isolate(g, () => {
      g.globalAlpha *= p
      caption(g, c.title, 240, 78, c.plate, 242)
    })
    return
  }
  if (id === 'verticalType') {
    const chars = Array.from(c.title),
      columns = Math.max(1, Math.ceil(chars.length / 7)),
      rows = Math.min(7, chars.length)
    const sz = Math.min(23, 146 / Math.max(1, rows), 350 / (columns + 1))
    chars
      .slice(0, Math.ceil(p * chars.length))
      .forEach((ch, i) =>
        label(g, ch, 240 + ((columns - 1) / 2 - Math.floor(i / 7)) * sz * 1.4, 18 + (i % 7) * sz, sz),
      )
    return
  }
  if (id === 'twoLines') {
    partialLine(
      g,
      [
        [135, 73],
        [345, 73],
      ],
      p,
      ORANGE,
      3,
    )
    caption(g, c.a, 232, 48, c.plate, 240)
    isolate(g, () => {
      g.globalAlpha *= epoch(p, 0.25, 0.9)
      caption(g, c.b, 252, 100, c.plate, 240)
    })
    return
  }
  const k = ease(p)
  isolate(g, () => {
    g.beginPath()
    g.rect(114, 33, 252 * k, 92)
    g.clip()
    box(g, 114, 33, 252, 92, 8, CREAM)
    box(g, 114, 33, 8, 92, 3, ORANGE)
    label(g, c.a, 239, 59, 21, INK, 800, 223)
    label(g, c.b, 239, 95, 15, BLUE, 700, 223)
  })
}
function illustration(g, id, t, c) {
  const group = TERM[id].group
  if (group === 'chart') chartGraphic(g, id, t, c)
  else if (group === 'relation') relationGraphic(g, id, t, c)
  else if (group === 'place') locationGraphic(g, id, t, c)
  else if (group === 'interface') interfaceGraphic(g, id, t, c)
  else editorialGraphic(g, id, t, c)
}
