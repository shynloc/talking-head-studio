'use strict'
const catalog=JSON.parse(document.getElementById('catalog').textContent)
const embedded=JSON.parse(document.getElementById('embedded').textContent)
const $=id=>document.getElementById(id)
const names={styles:'网页风格',palettes:'配色',objects:'3D 物件',stickers:'贴纸'}
const roles={surface:'局部底板',text:'正文与轮廓',object:'主体与结构',accent:'当前重点'}
const defaults={styles:'field',palettes:'atelier',objects:'pot',stickers:''}
let selected={...defaults},tab='styles'
try{const prior=JSON.parse(localStorage.getItem('visual-recipes/1'));for(const k in selected)if(prior&&(catalog[k].some(t=>t.id===prior[k])||(!prior[k]&&['objects','stickers'].includes(k))))selected[k]=prior[k]||''}catch{}
function tinted(e){if(!e?.variants)return e
 const {variants,...meta}=e;return {...meta,files:variants[selected.palettes],paletteId:selected.palettes}}
const item=k=>tinted(catalog[k].find(e=>e.id===selected[k]))
const parts={pot:['茎叶','盆沿','土面'],camera:['镜头','机身','快门'],lamp:['底座','支架','灯罩'],box:['箱体','盖板','搭扣']}
function node(tag,value,cls){const el=document.createElement(tag);if(value!=null)el.textContent=value;if(cls)el.className=cls;return el}
function uiButton(label,action){const b=node('button',label);b.type='button';b.onclick=action;return b}
function link(url,label,download=false){const a=node('a',label);a.href=url;if(download)a.download='';else{a.target='_blank';a.rel='noopener'}return a}
function scene(style,palette,obj,sticker,portable=false){
 const root=node('article',null,'scene '+style.id+(obj?'':' textonly'))
 for(const [key,color] of Object.entries(palette.colors))root.style.setProperty('--'+key,color)
 const n=obj?.name||'观察一件物品',list=parts[obj?.id]||['轮廓','结构','细节']
 const h3=()=>node('h3',n),label=t=>node('small',t,'label')
 function picture(){const fig=node('figure');if(obj){const im=new Image();im.src=portable?embedded[obj.files.preview]:obj.files.preview;im.alt=obj.name;fig.append(im)}return fig}
 function words(){const div=node('div',null,'contents');for(const v of list)div.append(node('span',v));return div}
 if(style.id==='field'){const side=node('div');side.append(label('观察记录'),h3(),words());root.append(picture(),side)}
 if(style.id==='manual'){const left=node('div'),ol=node('ol');left.append(h3(),picture());['先看'+list[0],'再看'+list[1],'最后看'+list[2]].forEach(t=>ol.append(node('li',t)));root.append(left,ol)}
 if(style.id==='editorial'){const head=node('header');head.append(label('物件观察'),h3());const note=node('p','从'+list[0]+'到'+list[2]+'，换个角度观察它的轮廓。');root.append(head,picture(),note)}
 if(style.id==='measure'){const h=node('header');h.append(h3());const meter=node('div',null,'meter');for(const [key,v] of [['摆位 A','20'],['摆位 B','35']]){const cell=node('div');cell.append(label(key),node('strong',v),node('small','厘米'));meter.append(cell)}root.append(h,meter,label('摆放距离示例 · 两次测量使用同一单位'))}
 if(style.id==='exhibit'){const plate=node('div',null,'plate');plate.append(h3(),label(list.join(' · ')));root.append(picture(),plate)}
 if(style.id==='route'){const head=node('div');head.append(label('观察路线'),h3());const ol=node('ol',null,'path');for(const s of list)ol.append(node('li',s));root.append(head,ol,label('依次查看三个位置'))}
 if(sticker){const im=new Image();im.className='badge';im.src=portable?embedded[sticker.files.vector]:sticker.files.vector;im.alt=sticker.name;root.append(im)}
 return root
}
function recipe(){
 const s=item('styles'),p=item('palettes'),o=item('objects'),t=item('stickers')
 return {schema:'creator-visual-brief/1',sentence:$('quote').value.trim(),catalogRevision:catalog.revision,webStyle:s,palette:p,object:o||null,sticker:t||null,
 render:{fullPage:'按版式和色板渲染 HTML；标题与标签取自用户原句。',overlay:'口播叠加时抽出主体、标签和必要引线，四周 alpha=0。局部说明底板可选 50% 或 75% 不透明度，文字保留 100%。',placement:'优先用人物侧面留白，底部避开口播字幕。没有原片时在深浅底和棋盘预览，放置位置待合成时调整。',colors:'网页、模型与贴纸采用所选配色。叶、土、镜片等辨识性部位保留原色；重新生成时按相同角色着色。',source:'按原句选择实际需要的元素。具体品牌与型号需有用户提供或可用的实物参考。'}}
}
function instructions(r){
 const s=r.webStyle,p=r.palette,o=r.object,t=r.sticker
 const lines=[r.sentence?'为以下口播原句制作画面。「'+r.sentence+'」':'为我的口播原句制作画面。','网页风格「'+s.name+'」。'+[s.layout,s.type,s.detail].join(' '),
 '转成口播叠加时，'+s.overlay,'配色「'+p.name+'」。'+Object.entries(p.colors).map(([k,c])=>roles[k]+' '+c).join('，')+'。'+p.rule+' '+p.distribution]
 if(o)lines.push('可用 3D 物件「'+o.name+'」。'+[o.parts,o.projection,o.appearance,o.framing].join(' ')+' 模型文件 '+o.files.model+'。')
 if(t)lines.push('可用贴纸「'+t.name+'」。'+t.shape+' '+t.edge+' 源文件 '+t.files.vector+'。')
 lines.push('版式参数 '+JSON.stringify(s.tokens)+'。')
 if(o)lines.push('模型视角与灯光 '+JSON.stringify(o.tokens)+'。')
 if(t)lines.push('贴纸规格 '+JSON.stringify(t.tokens)+'。')
 lines.push(...Object.values(r.render))
 return lines.join('\n\n')
}
function downloadText(name,body,type){
 const address=URL.createObjectURL(new Blob([body],{type})),a=link(address,name,true);a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(address),15000)
}
function select(k,id){selected[k]=id;try{localStorage.setItem('visual-recipes/1',JSON.stringify(selected))}catch{};$('status').textContent='';render()}
function details(){
 const d=item(tab),root=$('detail');root.replaceChildren();if(!d)return
 root.append(node('h3',d.name,'section-title'))
 const lines={styles:[d.layout,d.type,d.detail,d.overlay],palettes:[d.rule,d.distribution,d.colors&&Object.entries(d.colors).map(([k,c])=>roles[k]+' '+c).join(' · ')],objects:[d.parts,d.framing,d.appearance,d.projection],stickers:[d.shape,d.edge]}[tab]
 for(const line of lines.filter(Boolean))root.append(node('p',line,'muted'))
 if(d.files){const media=node('div',null,'paint checkboard');const im=new Image();im.src=d.files.preview;im.alt=d.name+'透明预览';media.append(im);root.append(media)}
}
function render(){
 const tabs=$('tabs');tabs.replaceChildren()
 for(const [k,name] of Object.entries(names)){const b=uiButton(name,()=>{tab=k;render()});b.setAttribute('aria-pressed',String(k===tab));tabs.append(b)}
 const box=$('grid');box.replaceChildren()
 const entries=catalog[tab].map(tinted)
 if(['objects','stickers'].includes(tab))entries.push({id:'',name:tab==='objects'?'不放物件':'不加贴纸'})
 for(const d of entries){
  const b=uiButton('',()=>select(tab,d.id));b.className='entry';b.setAttribute('aria-pressed',String(d.id===selected[tab]))
  if(d.id&&tab==='styles'){const mini=node('div',null,'mini');mini.setAttribute('aria-hidden','true');mini.append(scene(d,item('palettes'),item('objects'),null));b.append(mini)}
  if(tab==='palettes'){const sw=node('div',null,'swatches');for(const c of Object.values(d.colors)){const sample=node('i');sample.style.background=c;sw.append(sample)}b.append(sw)}
  if(d.files){const thumb=node('div',null,'thumb');const im=new Image();im.src=d.files.preview;im.alt='';thumb.append(im);b.append(thumb)}
  b.append(node('strong',d.name));if(d.uses)b.append(node('small',d.summary||d.uses));box.append(b)
 }
 const r=recipe();$('choice').textContent=[r.webStyle.name,r.palette.name,r.object?.name,r.sticker?.name].filter(Boolean).join('  /  ')
 $('preview').replaceChildren(scene(r.webStyle,r.palette,r.object,r.sticker))
 $('prompt').value=instructions(r)
 const files=$('files');files.replaceChildren()
 const html=uiButton('保存当前 HTML 样式',()=>{
  const sampled=scene(r.webStyle,r.palette,r.object,r.sticker,true).outerHTML
  downloadText(r.webStyle.name+'-'+r.palette.name+'.html','<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+r.webStyle.name+'</title><style>body{margin:4vw auto;max-width:720px;padding:12px}'+$('scene-css').textContent+'</style>'+sampled+'</html>','text/html')
 });files.append(html)
 if(r.object)files.append(link(r.object.files.model,'3D 模型 GLB',true),link(r.object.files.preview,'物件透明 PNG',true))
 if(r.sticker)files.append(link(r.sticker.files.vector,'贴纸 SVG',true),link(r.sticker.files.preview,'贴纸透明 PNG',true))
 details()
}
$('quote').oninput=()=>{$('prompt').value=instructions(recipe());$('status').textContent=''}
$('copy').onclick=async()=>{const text=$('prompt');try{await navigator.clipboard.writeText(text.value);$('status').textContent='已复制生成说明，可粘贴给助手。'}catch{$('promptbox').open=true;text.focus();text.select();$('status').textContent=document.execCommand('copy')?'已复制生成说明。':'已选中说明，按系统复制快捷键即可。'}}
$('json').onclick=()=>downloadText('我的素材风格.json',JSON.stringify(recipe(),null,2),'application/json')
$('reset').onclick=()=>{selected={...defaults};select('styles',defaults.styles)}
for(const [title,url] of Object.values(catalog.refs))$('evidence').append(link(url,title))
render()

window.readVisualSelection=()=>Object.fromEntries(Object.entries(selected).filter(([,v])=>v))
window.setVisualSelection=(value,quote,group)=>{
 selected={...defaults,objects:'',stickers:''}
 for (const [k,v] of Object.entries(value||{})) if(catalog[k]?.some(x=>x.id===v)) selected[k]=v
 tab=group||'styles';$('quote').value=quote||'';render()
}
