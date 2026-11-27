'use strict'

function enhanceWebsite(root, style) {
 const spec=style.website
 const form=node('div',null,'web-find')
 form.dataset.experience=spec.experience
 const label=node('label',spec.experience==='services'?'搜索服务':'搜索条目')
 const search=node('input');search.type='search';search.dataset.find='';label.append(search)
 const category=node('select');category.dataset.category=''
 category.setAttribute('aria-label','按类别筛选')
 category.add(new Option('全部类别',''))
 for(const name of new Set(spec.entries.map(([,kind])=>kind)))category.add(new Option(name,name))
 const clear=node('button','清除筛选');clear.type='button';clear.dataset.clear=''
 form.append(label,category,clear)
 const status=node('p',null,'web-results');status.setAttribute('role','status')
 const list=node('div',null,'web-records')
 for(const [name,kind,detail] of spec.entries){
  const record=node('article',null,'web-record')
  record.dataset.record='';record.dataset.name=name;record.dataset.kind=kind;record.dataset.detail=detail
  const open=node('button',spec.experience==='services'?'查看办理步骤':'打开详情')
  open.type='button';open.dataset.open=''
  open.setAttribute('aria-label',open.textContent+' · '+name)
  record.append(node('small',kind),node('h5',name),node('p',detail),open);list.append(record)
 }
 const detail=node('section',null,'web-record-detail');detail.hidden=true
 detail.dataset.recordDetail='';detail.tabIndex=-1
 const back=node('button','返回列表');back.type='button';back.dataset.back=''
 const heading=node('h5');heading.dataset.detailTitle=''
 const text=node('p');text.dataset.detailBody=''
 detail.append(back,heading,text)
 root.querySelector('.web-features').replaceWith(form,status,list,detail)
 wireWebsiteExperience(root)
}

function wireWebsiteExperience(root) {
 const form=root.querySelector('.web-find')
 if(!form)return
 const search=form.querySelector('[data-find]'), category=form.querySelector('[data-category]')
 const list=root.querySelector('.web-records'), status=root.querySelector('.web-results')
 const detail=root.querySelector('[data-record-detail]')
 let previous
 function filter(){
  const q=search.value.trim()
  const cards=[...list.querySelectorAll('[data-record]')]
  let count=0
  for(const card of cards){
   card.hidden=!!(category.value&&card.dataset.kind!==category.value) || ![card.dataset.name,card.dataset.detail].some(v=>v.includes(q))
   if(!card.hidden)count++
  }
  status.textContent=count?'找到 '+count+' 项':'找不到匹配项，试试其他名称或清除筛选。'
 }
 function close(){
  detail.hidden=true;list.hidden=false;form.hidden=false;status.hidden=false;filter()
  if(previous)previous.focus()
 }
 search.addEventListener('input',filter);category.addEventListener('change',filter)
 form.querySelector('[data-clear]').addEventListener('click',()=>{search.value='';category.value='';filter();search.focus()})
 detail.querySelector('[data-back]').addEventListener('click',close)
 list.addEventListener('click',event=>{
  const btn=event.target.closest('[data-open]')
  if(!btn)return
  const record=btn.closest('[data-record]')
  previous=btn
  detail.querySelector('[data-detail-title]').textContent=record.dataset.name
  detail.querySelector('[data-detail-body]').textContent=record.dataset.detail
  detail.hidden=false;list.hidden=true;form.hidden=true;status.hidden=true;detail.focus()
 })
 root.addEventListener('click',event=>{
  if(event.target.closest('a[href="#web-guide"]')&&!detail.hidden)close()
 })
 list.hidden=false;form.hidden=false;status.hidden=false;detail.hidden=true
 filter()
}
