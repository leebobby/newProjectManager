// 把页面上的 <svg> 导出成 SVG / PNG 文件。**两张 WBS 图共用这一份**
// （WbsDiagram 的调试框图、WbsTimeline 的 A 图），各写一份的表现是同一个「导出
// PNG」在两张图上一个带白底、一个透明底，而两边单独看都正常。
//
// 三条容易踩的：
// 1. **画笔必须写成元素属性**，不能靠 `<style scoped>`：scoped CSS 靠 data-v 属性
//    挂在页面 DOM 上，XMLSerializer 序列化出去的那份带不走它，表现是「页面上好好
//    的，导出来全变成黑的默认色」（见 CLAUDE.md「前端约定」）。这一条得由调用方
//    的模板保证，这儿只负责序列化。
// 2. **补一个白底**：导出的图多半要贴进 PPT 或邮件，透明底在深色版式上就是看不清
//    的一团。
// 3. PNG 按 2 倍画，贴进 PPT 放大不糊。

const NS = 'http://www.w3.org/2000/svg'

/** 序列化成独立的一份 SVG 文本（带 xmlns 与白底）。 */
export function serializeSvg(el, width, height) {
  if (!el) return null
  const clone = el.cloneNode(true)
  clone.setAttribute('xmlns', NS)
  clone.removeAttribute('class')
  const bg = document.createElementNS(NS, 'rect')
  bg.setAttribute('x', '0')
  bg.setAttribute('y', '0')
  bg.setAttribute('width', String(width))
  bg.setAttribute('height', String(height))
  bg.setAttribute('fill', '#ffffff')
  clone.insertBefore(bg, clone.firstChild)
  return new XMLSerializer().serializeToString(clone)
}

/** 文件名后缀：到秒，同一张图导两次不会互相覆盖。 */
export function stamp() {
  return new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
}

export function svgBlob(xml) {
  return new Blob([xml], { type: 'image/svg+xml;charset=utf-8' })
}

/** SVG 文本 → PNG Blob（走 canvas，2 倍图）。 */
export async function svgToPngBlob(xml, width, height, scale = 2) {
  const url = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(xml)))
  const img = new Image()
  await new Promise((resolve, reject) => {
    img.onload = resolve
    img.onerror = () => reject(new Error('图片渲染失败'))
    img.src = url
  })
  const canvas = document.createElement('canvas')
  canvas.width = width * scale
  canvas.height = height * scale
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('导出 PNG 失败')
  return blob
}
