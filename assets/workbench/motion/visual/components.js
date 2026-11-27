'use strict'

const COMPONENT_CSS = 'body{font:16px/1.55 system-ui,sans-serif;background:var(--demo-bg);color:var(--demo-text);margin:0;padding:24px}.component-surface{max-width:720px;padding:20px;margin:auto;border:1px solid currentColor;border-radius:16px}.component-surface label{display:block}.component-surface button,.component-surface input,.component-surface select{font:inherit;margin:4px;padding:.45em .7em;border:1px solid currentColor;border-radius:8px;background:var(--demo-bg);color:var(--demo-text)}.component-surface button{cursor:pointer}.component-surface button:focus-visible,.component-surface input:focus-visible,.component-surface select:focus-visible{outline:3px solid var(--demo-accent);outline-offset:2px}.component-surface input{max-width:100%;box-sizing:border-box}.component-surface .is-current{font-weight:800;text-decoration:underline;text-decoration-color:var(--demo-accent)}.component-surface progress{accent-color:var(--demo-accent);width:min(330px,90%)}.component-surface .compare-stage{display:grid;place-items:center;aspect-ratio:2/1;max-height:210px;background:var(--demo-object);border-radius:12px;overflow:hidden;position:relative}.component-surface .compare-stage span{position:absolute;inset:0;display:grid;place-items:center;background:var(--demo-bg);clip-path:inset(0 calc(100% - var(--position,50%)) 0 0)}.component-surface dialog{background:var(--demo-bg);color:var(--demo-text);border:1px solid currentColor;border-radius:12px;padding:18px}.component-surface nav{display:flex;flex-wrap:wrap;gap:6px}'

function wireComponent(root, kind) {
 const make=(tag,text)=>{
  const element=document.createElement(tag)
  if(text!=null)element.textContent=text
  return element
 }
 const button=(label, action)=>{
  const b=make('button',label);b.type='button';b.onclick=action;return b
 }
 const sharedStatus=make('p')
 sharedStatus.setAttribute('role','status')
 const end=text=>{sharedStatus.textContent=text}
 if(kind==='nav'){
  const menu=make('nav');menu.hidden=true;menu.style.display='none'
  const b=button('展开菜单',()=>{
   menu.hidden=!menu.hidden;menu.style.display=menu.hidden?'none':'flex'
   b.textContent=menu.hidden?'展开菜单':'收起菜单';b.setAttribute('aria-expanded',String(!menu.hidden))
  })
  b.setAttribute('aria-expanded','false')
  for(const name of ['首页','作品','联系'])menu.append(button(name,()=>{
   end('已进入'+name);menu.hidden=true;menu.style.display='none';b.textContent='展开菜单';b.setAttribute('aria-expanded','false');b.focus()
  }))
  root.append(b,menu)
 }else if(kind==='search'){
  const input=make('input');input.type='search';input.placeholder='搜相机、帐篷或伞';input.setAttribute('aria-label','搜索条目')
  const list=make('ul')
  const render=()=>{
   const q=input.value.trim()
   const matches=['袖珍相机','折叠伞','轻便帐篷'].filter(value=>value.includes(q))
   list.replaceChildren(...matches.map(text=>make('li',text)))
   end(matches.length?'找到 '+matches.length+' 个条目':'没有匹配条目')
  }
  input.oninput=render;render()
  root.append(input,button('清除筛选',()=>{input.value='';render();input.focus()}),list)
 }else if(kind==='upload'){
  const progress=make('progress');progress.max=100;progress.value=0;progress.setAttribute('aria-label','示例上传进度')
  let upload
  const fail=button('模拟失败',()=>{
   clearInterval(upload);end('连接中断，请重试。');start.disabled=false;start.textContent='重试'
  })
  const start=button('开始示例上传',()=>{
   start.disabled=true;progress.value=0;end('正在上传。')
   upload=setInterval(()=>{
    if(!root.isConnected){clearInterval(upload);return}
    progress.value=Math.min(100,progress.value+20)
    if(progress.value===100){
     clearInterval(upload);end('已上传 · 100%');start.disabled=false;start.textContent='再演示一次'
    }
   },140)
  })
  root.append(progress,make('br'),start,fail)
 }else if(kind==='compare'){
  const slider=make('input');slider.type='range';slider.value=50;slider.setAttribute('aria-label','前后对照位置')
  const image=make('div','处理后');image.className='compare-stage';image.append(make('span','处理前'))
  const update=()=>{image.style.setProperty('--position',slider.value+'%');end('对照位置 '+slider.value+'%')}
  slider.oninput=update
  root.append(image,slider,button('位置还原',()=>{slider.value=50;update()}));update()
 }else if(kind==='steps'){
  const list=make('ol');const steps=['选择文件','核对内容','完成导出'].map(n=>make('li',n));list.append(...steps)
  let pos=0
  const back=button('上一步',()=>{pos--;update()})
  const forward=button('下一步',()=>{pos++;update()})
  const update=()=>{
   steps.forEach((step,i)=>{step.className=i===pos?'is-current':'';if(i===pos)step.setAttribute('aria-current','step');else step.removeAttribute('aria-current')})
   back.disabled=pos===0;forward.disabled=pos===steps.length-1;end(steps[pos].textContent)
  }
  root.append(list,back,forward);update()
 }else if(kind==='feedback'){
  const dialog=make('dialog')
  const heading=make('h4','保存当前修改？');heading.id='component-dialog-title';dialog.setAttribute('aria-labelledby',heading.id)
  const opener=button('保存设置',()=>dialog.showModal())
  dialog.append(heading,make('p','可以继续编辑，或确认并应用。'),button('取消',()=>{dialog.close();end('已取消')}),button('确认完成',()=>{dialog.close();end('已保存设置')}))
  root.append(opener,dialog)
 }
 root.append(sharedStatus)
}

function mountComponentShelf(host, catalog, options) {
 const title=node('h3','试一下界面怎么工作')
 const lists=node('div',null,'practice-cards')
 const stage=node('iframe',null,'component-preview');stage.title='可操作的界面组件'
 const description=node('p',null,'muted')
 const save=node('button','保存可操作组件 HTML');save.type='button'
 let selected=catalog.components[0]
 const colors=()=>options.palette().colors
 const html=()=>{
  const palette=Object.entries(colors()).map(([key,value])=>'--demo-'+key+':'+value).join(';')
  const label=node('span',selected.name).innerHTML
  return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'+
   '<title>'+label+'</title><style>'+COMPONENT_CSS+'</style><body style="'+palette+'"><section class="component-surface"><h2>'+label+
   '</h2></section><script>('+wireComponent.toString()+')(document.querySelector("section"),'+JSON.stringify(selected.id)+')</script></body></html>'
 }
 function select(item){
  selected=item
  description.textContent=item.name+' · '+item.assetId+'。'+item.uses+'。'
  for(const card of lists.children)card.setAttribute('aria-pressed',String(card.dataset.uiId===item.assetId))
  stage.srcdoc=html()
 }
 for(const item of catalog.components){
  const button=node('button',item.name+' · '+item.assetId)
  button.dataset.uiId=item.assetId;button.type='button';button.onclick=()=>select(item);lists.append(button)
 }
 save.onclick=()=>options.download(selected.assetId+'-界面组件.html',html(),'text/html')
 host.append(title,lists,description,stage,save)
 select(selected)
 return {find(code){
  const item=catalog.components.find(item=>item.assetId===code)
  if(item)select(item)
 },refresh(){select(selected)}}
}
