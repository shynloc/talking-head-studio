'use strict'

const FORMAT = 'talking-head-motion/1'
function prefix(length) {
  const buf = new ArrayBuffer(4)
  new DataView(buf).setUint32(0, length)
  return buf
}
function pngBlob(canvas) {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(Error('无法读取预览帧。'))), 'image/png'),
  )
}
async function jsonResponse(res) {
  const payload = await res.json()
  if (!res.ok) throw Error(payload.error || '工作台请求失败。')
  return payload
}

async function exportMotionPack(entries, frameRenderer, report) {
  const capability = await jsonResponse(await fetch('/api/motion/status', { cache: 'no-store' }))
  if (!capability.ready && entries.some((item) => !item.sample))
    throw Error('导出 MOV 需要 FFmpeg。安装媒体工具后回到这里重试，已选素材会保留。')
  const header = new TextEncoder().encode(
    JSON.stringify({
      format: entries.some((item) => item.sample) ? 'talking-head-motion/2' : FORMAT,
      items: entries,
    }),
  )
  if (entries.length > 64 || header.byteLength > 32 * 1024 * 1024)
    throw Error('这个包的素材较多，请分批导出。')
  const chunks = [prefix(header.length), header]
  let total = 4 + header.length
  const canvas = document.createElement('canvas')
  canvas.width = 960
  canvas.height = 360
  for (const [n, item] of entries.entries()) {
    if (item.sample) continue
    const render = await frameRenderer(item),
      count = item.seconds * 25
    for (let f = 0; f < count; f++) {
      render(canvas, f)
      const blob = await pngBlob(canvas)
      chunks.push(prefix(blob.size), blob)
      total += 4 + blob.size
      if (total > 512 * 1024 * 1024) throw Error('本包的画面数据超过 512 MB，请分批导出。')
      if (f % 5 === 0)
        report(
          '正在绘制第 ' +
            (n + 1) +
            ' / ' +
            entries.length +
            ' 款 · ' +
            Math.round(((f + 1) / count) * 100) +
            '%',
        )
    }
  }
  report('正在本机编码透明 MOV 并打包…')
  const { token } = await jsonResponse(await fetch('/api/bootstrap', { cache: 'no-store' }))
  return jsonResponse(
    await fetch('/api/motion/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream', 'X-Studio-Token': token },
      body: new Blob(chunks),
    }),
  )
}
