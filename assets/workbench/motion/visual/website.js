'use strict'

function websiteImage(object, picture, sources) {
  if (!object && !picture) return null
  const image = new Image()
  const path = object?.files.preview || picture
  image.src = sources ? sources[path] : path
  image.alt = object?.name || ''
  return image
}

function websiteCard(style) {
  const site = style.website
  const card = node('div', null, 'web-card')
  card.style.setProperty('--card-ink', site.colors.text)
  card.style.setProperty('--card-bg', site.colors.surface)
  card.style.setProperty('--card-accent', site.colors.accent)
  card.dataset.theme = site.theme
  card.append(node('small', site.brand), node('b', site.headline))
  return card
}

function websiteScene(style, palette, object, sticker, sources, picture) {
  const site = style.website
  const root = node('article', null, 'website')
  root.dataset.theme = site.theme
  for (const [role, color] of Object.entries(palette.colors)) root.style.setProperty('--web-' + role, color)

  function jump(target, label, cls) {
    const anchor = node('a', label, cls)
    anchor.href = '#' + target
    return anchor
  }
  const bar = node('header', null, 'web-header')
  const nav = node('nav')
  nav.setAttribute('aria-label', '示例网站导航')
  nav.append(jump('web-home', '首页'), jump('web-guide', site.guide), jump('web-questions', '常见问题'))
  bar.append(jump('web-home', site.brand, 'web-brand'), nav)
  root.append(bar)

  const main = node('div', null, 'web-main')
  const hero = node('section', null, 'web-hero')
  hero.id = 'web-home'
  const cover = node('div', null, 'web-cover')
  const words = node('div', null, 'web-words')
  words.append(node('p', site.kicker, 'web-kicker'), node('h3', site.headline, 'web-headline'),
    node('p', site.intro, 'web-intro'), jump('web-guide', site.action, 'web-action'))
  const image = websiteImage(object, picture, sources)
  const artwork = node('div', null, 'web-art')
  artwork.setAttribute('aria-hidden', 'true')
  artwork.append(node('div', null, 'web-shape'))
  if (image) artwork.append(image)
  if (sticker) {
    const icon = new Image()
    icon.src = sources ? sources[sticker.files.vector] : sticker.files.vector
    icon.alt = ''
    icon.className = 'web-sticker'
    artwork.append(icon)
  }
  cover.append(words, artwork)
  hero.append(cover)
  main.append(hero)

  const guide = node('section', null, 'website-section web-guide')
  guide.id = 'web-guide'
  guide.append(node('h4', site.guide))
  const grid = node('div', null, 'web-features')
  for (const [index, [title, body]] of site.features.entries()) {
    const feature = node('article', null, 'web-feature')
    if (site.theme !== 'product') feature.append(node('span', String(index + 1).padStart(2, '0'), 'web-index'))
    feature.append(node('h5', title), node('p', body))
    grid.append(feature)
  }
  guide.append(grid)
  main.append(guide)

  const questions = node('section', null, 'website-section web-questions')
  questions.id = 'web-questions'
  questions.append(node('h4', '常见问题'))
  for (const [question, answer] of site.questions) {
    const fold = node('details')
    fold.append(node('summary', question), node('p', answer))
    questions.append(fold)
  }
  main.append(questions)
  root.append(main)

  const footer = node('footer', null, 'web-footer')
  footer.append(node('strong', site.brand), jump('web-home', '返回顶部 ↑'))
  root.append(footer)
  return root
}
