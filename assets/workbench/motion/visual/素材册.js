'use strict'
const catalog=JSON.parse(document.getElementById('catalog').textContent)
const embedded={}
const $=id=>document.getElementById(id)
const names={styles:'网页风格',palettes:'配色',objects:'3D 物件',stickers:'贴纸'}
const roles={surface:'局部底板',text:'正文与轮廓',object:'主体与结构',accent:'当前重点'}
const defaults={styles:'field',palettes:'atelier',objects:'pot',stickers:''}
const params = new URLSearchParams(location.search)
const libraryRelease = document.querySelector('meta[name="library-release"]')?.content
const versioned = path => libraryRelease ? path + (path.includes('?')?'&':'?') + 'library=' + encodeURIComponent(libraryRelease) : path
const inline = params.get('inline') === '1'
const storageKey = inline ? 'visual-recipes/gallery/' + (params.get('desk') || 'local') : 'visual-recipes/1'
document.documentElement.classList.toggle('inline', inline)
const galleryDefaults={styles:'signalcard',palettes:'tidal',objects:'mic',stickers:'voicewave'}
let selected={...(inline?galleryDefaults:defaults)},tab=inline?'objects':'styles', previewMode=inline?'overlay':'layout'
try{const prior=JSON.parse(localStorage.getItem(storageKey));for(const k in selected)if(prior&&(catalog[k].some(t=>t.id===prior[k])||(!prior[k]&&['objects','stickers'].includes(k))))selected[k]=prior[k]||''}catch{}
function tinted(e,color=selected.palettes){if(!e?.variants)return e
 const {variants,...meta}=e
 const files=Object.fromEntries(Object.entries(variants[color]).map(([key,path])=>[key,versioned(path)]))
 return {...meta,files,paletteId:color,variantId:e.assetId+"@"+catalog.palettes.find(p=>p.id===color).assetId}}
const item=k=>tinted(catalog[k].find(e=>e.id===selected[k]))
function uiButton(label,action){const b=node('button',label);b.type='button';b.onclick=action;return b}
function link(url,label,download=false){const a=node('a',label);a.href=url;if(download)a.download='';else{a.target='_blank';a.rel='noopener'}return a}

const currentWebStyles = catalog.styles.filter(style => style.website)
let showWebsites = currentWebStyles.length > 0
let phonePreview = false
let customWebPalette = null
let useSelectedObject = false

function openStyles(chooseWebsite) {
 if (!currentWebStyles.length) return
 if (chooseWebsite && showWebsites && !item('styles').website) {
  selected.styles = currentWebStyles[0].id
  selected.palettes = currentWebStyles[0].website.palette
 }
 $('recent-only').checked = false
}
function pickStyle(entry) {
 const previous = item('styles').website
 if (entry.website && (!previous || previous.palette === selected.palettes))
  selected.palettes = entry.website.palette
 $('preview').scrollTop = 0
 select('styles',entry.id)
}
function renderStyleControls() {
 const groups=$('web-kinds')
 groups.hidden = tab!=='styles' || !currentWebStyles.length
 document.querySelectorAll('[data-style-kind]').forEach(button => {
  button.setAttribute('aria-pressed',String((button.dataset.styleKind==='web')===showWebsites))
 })
 $('color-lab').hidden = tab!=='palettes'
}
function makeLayout(r, sources=null) {
 const palette = r.customWebPalette || r.palette
 if (!r.webStyle.website) return scene(r.webStyle,palette,r.object,r.sticker,sources)
 const result = websiteScene(r.webStyle,palette,r.websiteObject,r.sticker,sources)
 result.style.setProperty('--web-action-text',foregroundOn(palette.colors.accent))
 return result
}
function setLayoutPreview(r, overlay) {
 const area=$('preview'), website=!!r.webStyle.website && !overlay
 $('web-devices').hidden = !website
 $('desktop-layout').setAttribute('aria-pressed',String(!phonePreview))
 $('phone-layout').setAttribute('aria-pressed',String(phonePreview))
 $('use-website-object').checked = useSelectedObject
 area.classList.toggle('is-website',website)
 area.classList.toggle('is-phone',phonePreview)
 if (!overlay) area.replaceChildren(makeLayout(r))
}
function renderColorChips(colors) {
 const group=node('div',null,'color-chips')
 for(const [role,hex] of Object.entries(colors)) {
  const chip=node('div',null,'color-chip')
  chip.style.background=hex
  chip.style.color=foregroundOn(hex)
  chip.append(node('span',roles[role]),node('code',hex))
  group.append(chip)
 }
 return group
}

function recipe(){
 const s=item('styles'),p=item('palettes'),o=item('objects'),t=item('stickers')
 const picture = s.website && (useSelectedObject ? o : tinted(catalog.objects.find(entry=>entry.id===s.website.picture)))
 return {schema:'creator-visual-brief/1',sentence:$('quote').value.trim(),catalogRevision:catalog.revision,webStyle:s,palette:p,object:o||null,sticker:t||null,customWebPalette,websiteObject:picture||null,
 render:{fullPage:'按版式和色板渲染 HTML；标题与标签取自用户原句。',overlay:'口播叠加时抽出主体、标签和必要引线，四周 alpha=0。局部说明底板可选 50% 或 75% 不透明度，文字保留 100%。',placement:'优先用人物侧面留白，底部避开口播字幕。没有原片时在深浅底和棋盘预览，放置位置待合成时调整。',colors:'网页、模型与贴纸采用所选配色。叶、土、镜片等辨识性部位保留原色；重新生成时按相同角色着色。',source:'按原句选择实际需要的元素。具体品牌与型号需有用户提供或可用的实物参考。'}}
}
function instructions(r){
 const s=r.webStyle,p=r.palette,o=r.object,t=r.sticker
 const lines=[r.sentence?'为以下口播原句制作画面。「'+r.sentence+'」':'为我的口播原句制作画面。','网页风格「'+s.name+'」。'+[s.layout,s.type,s.detail].join(' '),
 '转成口播叠加时，'+s.overlay,'配色「'+p.name+'」。'+Object.entries(p.colors).map(([k,c])=>roles[k]+' '+c).join('，')+'。'+p.rule+' '+p.distribution]
 if(r.customWebPalette)lines.push('网页使用自定义色卡。'+r.customWebPalette.rule+' '+Object.entries(r.customWebPalette.colors).map(([k,v])=>k+' '+v).join('，')+'。素材文件使用所选色系。')
 if(o)lines.push('可用 3D 物件「'+o.name+'」。'+[o.parts,o.projection,o.appearance,o.framing].join(' ')+' 模型文件 '+o.files.model+'。')
 if(t)lines.push('可用贴纸「'+t.name+'」。'+t.shape+' '+t.edge+' 源文件 '+t.files.vector+'。')
 lines.unshift('素材编号 '+[s,p,o,t].filter(Boolean).map(entry=>entry.assetId+' '+entry.name).join(' / '))
 if(o||t)lines.push('精确配色版本 '+[o,t].filter(Boolean).map(e=>e.variantId).join(' / '))
 lines.push('版式参数 '+JSON.stringify(s.tokens)+'。')
 if(o)lines.push('模型视角与灯光 '+JSON.stringify(o.tokens)+'。')
 if(t)lines.push('贴纸规格 '+JSON.stringify(t.tokens)+'。')
 lines.push(...Object.values(r.render))
 return lines.join('\n\n')
}
function downloadText(name,body,type){
 const address=URL.createObjectURL(new Blob([body],{type})),a=link(address,name,true);a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(address),15000)
}
function select(k,id){selected[k]=id;try{localStorage.setItem(storageKey,JSON.stringify(selected))}catch{};$('status').textContent='';render(k)}
function details(){
 const d=item(tab),root=$('detail');root.replaceChildren();if(!d)return
 root.append(node('h3',d.name,'section-title'),node('code',d.variantId||d.assetId,'asset-id'))
 root.append(uiButton('复制编号',async()=>{
  const code=d.variantId||d.assetId
  try{await navigator.clipboard.writeText(code);$('status').textContent='已复制 '+code}
  catch{const range=document.createRange();range.selectNodeContents(root.querySelector('code'));const selection=getSelection();selection.removeAllRanges();selection.addRange(range);$('status').textContent='编号已选中，可按系统复制快捷键。'}
 }))
 if(tab==='styles' && d.website && catalog.refs[d.source]){
  const [title,url]=catalog.refs[d.source];root.append(node('p',d.website.tag),link(url,title))
 }
 if(tab==='palettes')root.append(renderColorChips(d.colors))
 const lines={styles:[d.layout,d.type,d.detail,d.overlay],palettes:[d.rule,d.distribution],objects:[d.parts,d.framing,d.appearance,d.projection],stickers:[d.shape,d.edge]}[tab]
 for(const line of lines.filter(Boolean))root.append(node('p',line,'muted'))
 if(d.files){const media=node('div',null,'paint checkboard');const im=new Image();im.src=d.files.preview;im.alt=d.name+'透明预览';media.append(im);root.append(media)}
}
function render(changed){
 const tabs=$('tabs');tabs.replaceChildren()
 for(const [k,name] of Object.entries(names)){const b=uiButton(name,()=>{tab=k;$('asset-search').value='';previewMode=k==='styles'?'layout':k==='palettes'?previewMode:'overlay';if(k==='styles')openStyles(true);render()});b.setAttribute('aria-pressed',String(k===tab));tabs.append(b)}
 renderStyleControls()
 const box=$('grid');box.replaceChildren()
 const query=$('asset-search').value.trim().toLowerCase()
 const [needle,paletteCode]=query.split('@')
 const variant=catalog.palettes.find(p=>p.assetId.toLowerCase()===paletteCode)
 const entries=catalog[tab].filter(entry=>
  (!$('recent-only').checked || catalog.recent[tab].includes(entry.id)) &&
  (tab!=='styles' || !!needle || !!entry.website===showWebsites) &&
  [entry.assetId,entry.name,entry.uses,entry.parts,entry.shape,entry.summary,entry.layout].some(text=>text?.toLowerCase().includes(needle)) &&
  (!query.includes('@') || (query===needle+'@'+paletteCode && !!variant && !!entry.variants))
 ).map(entry=>tinted(entry,variant?.id||selected.palettes))
 if(!entries.length)box.append(node('p','没有找到这款素材，换个名称或清除筛选。'))
 if(!query && !$('recent-only').checked && ['objects','stickers'].includes(tab))entries.push({id:'',name:tab==='objects'?'不放物件':'不加贴纸'})
 for(const d of entries){
  const b=uiButton('',()=>{if(variant)selected.palettes=variant.id;
   if(tab==='styles'){showWebsites=!!d.website;pickStyle(d)}
   else {if(tab==='palettes'){customWebPalette=null;colorLab.setActive(false)} select(tab,d.id)}});b.className='entry';b.setAttribute('aria-pressed',String(d.id===selected[tab]))
  if(d.website)b.append(websiteCard(d))
  else if(d.id&&tab==='styles'){const mini=node('div',null,'mini');mini.setAttribute('aria-hidden','true');mini.append(scene(d,item('palettes'),item('objects'),null));b.append(mini)}
  if(tab==='palettes'){const sw=node('div',null,'swatches');for(const c of Object.values(d.colors)){const sample=node('i');sample.style.background=c;sw.append(sample)}b.append(sw)}
  if(d.files){const thumb=node('div',null,'thumb');const im=new Image();im.loading='lazy';im.src=d.files.preview;im.alt='';thumb.append(im);b.append(thumb)}
  b.append(node('strong',d.name));if(d.assetId){b.dataset.assetId=d.assetId;b.append(node('code',d.assetId,'asset-id'))}if(d.uses)b.append(node('small',d.summary||d.uses));box.append(b)
 }
 const r=recipe()
 showPreview(r, changed==='objects' ? r.object : (r.sticker || r.object))
 updateBrief(r)
 const files=$('files');files.replaceChildren()
 const html=uiButton('保存当前 HTML 样式',async()=>{
  const r=recipe()
  try {
   for(const path of [(r.webStyle.website?r.websiteObject:r.object)?.files.preview,r.sticker?.files.vector].filter(Boolean)){
    if(embedded[path])continue
    const response=await fetch(path);if(!response.ok)throw Error('无法读取所选素材。')
    const blob=await response.blob()
    embedded[path]=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob)})
   }
  const sampled=makeLayout(r,embedded).outerHTML
  const css=r.webStyle.website
   ? 'body{margin:0}'+$('website-css').textContent
   : 'body{margin:4vw auto;max-width:720px;padding:12px}'+$('scene-css').textContent
  const layoutName=r.webStyle.name+'-'+(r.customWebPalette||r.palette).name
  downloadText(layoutName+'.html','<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+node('span',r.webStyle.name).innerHTML+'</title><style>'+css+'</style>'+sampled+'</html>','text/html')
  }catch(e){$('status').textContent=e.message||'保存失败，请重试。'}
 });files.append(html)
 if(r.object)files.append(link(r.object.files.model,'3D 模型 GLB',true),link(r.object.files.preview,'物件透明 PNG',true))
 if(r.sticker)files.append(link(r.sticker.files.vector,'贴纸 SVG',true),link(r.sticker.files.preview,'贴纸透明 PNG',true))
 details()
}
function annotationLine(r){
 if(!r.object && !r.sticker)return ''
 return '（画面：用'+[r.object,r.sticker,r.webStyle,r.palette].filter(Boolean).map(asset=>
  asset.name+' '+(asset.variantId||asset.assetId)).join('、')+'。）'
}
function updateBrief(r){
 $('choice').textContent=[r.webStyle.name,(r.customWebPalette||r.palette).name,r.object?.name,r.sticker?.name].filter(Boolean).join('  /  ')
 const prompt=instructions(r);$('prompt').value=prompt
 $('copy-annotation').disabled=!annotationLine(r)
 if(inline && window.parent!==window)window.parent.postMessage({type:'studio-visual-selection',prompt,annotation:annotationLine(r),ids:[r.webStyle,r.palette,r.object,r.sticker].filter(Boolean).map(e=>e.assetId)},location.origin)
}
let pendingOverlay
function showPreview(r, hint=r.sticker||r.object){
 const overlay=previewMode==='overlay'
 $('preview').hidden=overlay;$('overlay').hidden=!overlay
 $('layout-view').setAttribute('aria-pressed',String(!overlay));$('overlay-view').setAttribute('aria-pressed',String(overlay))
 setLayoutPreview(r,overlay)
 if(!overlay){
  pendingOverlay=null
  return
 }
 $('preview').replaceChildren()
 const image=$('overlay-image'),thumb=$('overlay-thumbnail'),message=$('overlay-message')
 if(!r.object && !r.sticker){
  pendingOverlay=null
  image.hidden=true;thumb.hidden=true
  message.textContent='挑一个物件或贴纸，就能看透明效果。'
  return
 }
 const query=new URLSearchParams({palettes:r.palette.assetId})
 if(r.object)query.set('objects',r.object.assetId)
 if(r.sticker)query.set('stickers',r.sticker.assetId)
 const src=versioned('/api/motion/library-preview?'+query)
 if(image.getAttribute('src')===src && image.naturalWidth){
  pendingOverlay=null
  image.hidden=false;thumb.hidden=true;message.textContent=''
  return
 }
 if(pendingOverlay?.url===src)return
 image.hidden=true
 thumb.hidden=!hint
 if(hint)thumb.src=hint.files.preview
 message.textContent='正在合成透明小样…'
 const next=new Image()
 const request={url:src}
 pendingOverlay=request
 next.fetchPriority='high'
 next.id=image.id
 next.alt=image.alt
 next.onload=()=>{
  if(pendingOverlay!==request)return
  $('overlay-image').replaceWith(next)
  pendingOverlay=null
  thumb.hidden=true;message.textContent=''
 }
 next.onerror=()=>{
  if(pendingOverlay!==request)return
  pendingOverlay=null
  message.textContent='透明小样加载失败，请点选素材重试。'
 }
 next.src=src
}
$('layout-view').onclick=()=>{previewMode='layout';showPreview(recipe())}
$('overlay-view').onclick=()=>{previewMode='overlay';showPreview(recipe())}
$('asset-search').oninput=()=>{
 const key=$('asset-search').value.trim().toUpperCase().split('@')[0]
 const family=Object.keys(names).find(k=>catalog[k].some(e=>e.assetId===key))
 if(family){tab=family;$('recent-only').checked=false;previewMode=family==='styles'?'layout':'overlay'}
 render()
}
window.addEventListener('message',event=>{
 if(!inline || event.origin!==location.origin || event.source!==window.parent ||
    event.data?.type!=='studio-find-visual' || typeof event.data.code!=='string')return
 $('asset-search').value=event.data.code;$('asset-search').oninput()
})

if (!inline && !$('asset-search').value) openStyles(true)
for (const button of document.querySelectorAll('[data-style-kind]')) {
 button.onclick=()=>{
  showWebsites=button.dataset.styleKind==='web'
  tab='styles';previewMode='layout';$('asset-search').value=''
  openStyles(true)
  if (!showWebsites && item('styles').website) selected.styles=defaults.styles
  render()
 }
}
$('desktop-layout').onclick=()=>{phonePreview=false;setLayoutPreview(recipe(),false)}
$('phone-layout').onclick=()=>{phonePreview=true;setLayoutPreview(recipe(),false)}
$('use-website-object').onchange=event=>{
 useSelectedObject=event.target.checked;setLayoutPreview(recipe(),false)
}
$('preview').onclick=event=>{
 const viewport=$('preview')
 const jump=event.target.closest('.website a[href^="#"]')
 if (!jump) return
 const target=viewport.querySelector(jump.getAttribute('href'))
 if (!target) return
 event.preventDefault()
 viewport.scrollTop+=target.getBoundingClientRect().top-viewport.getBoundingClientRect().top
  - (viewport.querySelector('.web-header').offsetHeight + 8)
}
const colorLab=mountPaletteLab($('color-lab'), palette=>{
 customWebPalette=palette
 previewMode='layout'
 const current=recipe()
 showPreview(current);updateBrief(current)
}, ()=>{
 customWebPalette=null
 const current=recipe()
 showPreview(current);updateBrief(current)
}, message=>{$('status').textContent=message})

$('recent-only').checked=inline && tab!=='styles'
$('recent-only').onchange=render
$('copy-annotation').onclick=async()=>{
 const line=annotationLine(recipe())
 try{await navigator.clipboard.writeText(line);$('status').textContent='已复制画面标注，粘贴到要配画面的段落后。'}
 catch{$('promptbox').open=true;$('prompt').value=line;$('prompt').select();$('status').textContent='画面标注已选中，可按系统复制快捷键。'}
}
$('quote').oninput=()=>{updateBrief(recipe());$('status').textContent=''}
$('copy').onclick=async()=>{const text=$('prompt');try{await navigator.clipboard.writeText(text.value);$('status').textContent='已复制生成说明，可粘贴给助手。'}catch{$('promptbox').open=true;text.focus();text.select();$('status').textContent=document.execCommand('copy')?'已复制生成说明。':'已选中说明，按系统复制快捷键即可。'}}
$('json').onclick=()=>downloadText('我的素材风格.json',JSON.stringify(recipe(),null,2),'application/json')
$('reset').onclick=()=>{
 selected={...(inline?galleryDefaults:defaults)};customWebPalette=null;colorLab.setActive(false);$('asset-search').value='';openStyles(tab==='styles');select('styles',selected.styles)
}
for(const [title,url] of Object.values(catalog.refs))$('evidence').append(link(url,title))
render()

window.readVisualSelection=()=>Object.fromEntries(Object.entries(selected).filter(([,v])=>v))
window.setVisualSelection=(value,quote,group)=>{
 selected={...defaults,objects:'',stickers:''};customWebPalette=null;colorLab.setActive(false)
 for(const k of Object.keys(names)){
  const match=catalog[k].find(x=>x.id===value?.[k] || x.assetId===String(value?.[k]).toUpperCase())
  if(match)selected[k]=match.id
 }
 $('asset-search').value='';$('recent-only').checked=false;previewMode=group==='objects'||group==='stickers'?'overlay':'layout'
 showWebsites=!!item('styles').website
 tab=group||'styles';$('quote').value=quote||'';render()
}
