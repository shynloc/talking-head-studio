'use strict'

function mountPractice(host, data, options) {
 const make=(tag,text,attrs={})=>{
  const el=node(tag,text)
  for(const [key,value] of Object.entries(attrs))el.setAttribute(key,value)
  return el
 }
 const cardList=make('div',null,{class:'practice-cards'})
 const query=make('input',null,{type:'search','aria-label':'想给口播配什么画面',placeholder:'例如：文件传好了、前后对比、怎么拆'})
 const resultCount=make('p',null,{'aria-live':'polite',class:'muted'})
 const topic=make('h3'), reason=make('p')
 const settings=make('div',null,{class:'practice-settings'})
 const attachmentBox=make('div',null,{class:'practice-attachments'})
 const notice=make('p',null,{role:'status'})
 const frame=make('iframe',null,{title:'口播搭配透明动画',class:'practice-preview'})
 frame.hidden=true
 const actions=make('div',null,{class:'actions'})
 const demos=new Map(data.lessonEffects.map(d=>[d.assetId,d]))
 const files=new Map()
 let state=null, stageRevision=0, template
 function field(label,control){
  const wrapper=make('label',label)
  wrapper.append(control)
  return wrapper
 }
 function pick(label,items,chosen,change){
  const select=make('select')
  items.forEach(([key,caption])=>select.add(new Option(caption,key)))
  select.value=chosen
  select.onchange=()=>change(select.value)
  return field(label,select)
 }
 function entry(group,id){return data[group].find(item=>item.id===id)}
 function plain(value){return value.trim().replace(/[「」()（）\r\n]/g,'').slice(0,26)}
 function current(){
  const kit=state.kit, demo=demos.get(state.demo), palette=entry('palettes',state.palette)
  const object=entry('objects',state.object), sticker=entry('stickers',state.sticker)
  const args={scene:demo.scene,heading:demo.label,seconds:3,frames:75,play:true,labels:state.labels.map((label,i)=>plain(label)||demo.labels[i]),
   colors:palette.colors,anchor:Object.values(object.tokens.anchors||{})[0]}
  if(sticker)args.sticker=options.path(sticker.variants[palette.id].vector)
  if(demo.scene==='focus')args.picture=options.path(object.variants[palette.id].preview)
  if(demo.scene==='wave'){
   const original=kit.originalWave
   args.waveBefore=files.get('前段音频')?.value||original[0]
   args.waveAfter=files.get('后段音频')?.value||original[1]
  }
  if(demo.scene==='status'&&files.has('截图'))args.screenshot=files.get('截图').value
  return {kit,demo,palette,object,sticker,args}
 }
 function mark(){
  const {demo,palette,object,sticker,args}=current()
  const refs=[object.assetId,palette.assetId,sticker&&sticker.assetId+'@'+palette.assetId,demo.assetId].filter(Boolean)
  const notes=args.labels.map((value,i)=>'字'+'一二三'[i]+'「'+value+'」')
  const slots=demo.scene==='wave'?['前段音频','后段音频']:demo.scene==='status'?['截图']:[]
  for(const slot of slots){
   if(files.has(slot))notes.push(slot+' '+files.get(slot).key)
  }
  return '（画面：用'+refs.join('、')+'。'+notes.join('，')+'，时长 3 秒。）'
 }
 function loadTemplate(){
  template ||= fetch('lesson-demo.html').then(reply=>{
   if(!reply.ok)throw Error('暂时读不到动效，请刷新页面重试。')
   return reply.text()
  }).catch(error=>{template=null;throw error})
  return template
 }
 function html(template,args){return template.replace('__SCENE__',JSON.stringify(args).replaceAll('<','\\u003c'))}
 let previewTimer
 async function preview(){
  const revision=++stageRevision
  try{
   const {args}=current(), source=await loadTemplate()
   if(revision!==stageRevision)return
   frame.srcdoc=html(source,args)
   frame.hidden=false
  }catch(error){notice.textContent=error.message}
 }
 function schedule(){clearTimeout(previewTimer);previewTimer=setTimeout(preview,130)}
 function update(){
  topic.textContent=state.kit.name+' · '+state.kit.assetId
  reason.textContent=state.kit.reason
  settings.replaceChildren()
  const {kit,demo}=current()
  settings.append(pick('动作',kit.demos.map(code=>[code,demos.get(code).label]),state.demo,code=>{
   state.demo=code
   const effect=demos.get(code)
   state.labels=[...effect.labels]
   if(effect.scene==='seal')state.object='sealjar'
   update()
  }))
  if(demo.scene==='focus')settings.append(pick('主体',kit.objects.map(key=>[key,entry('objects',key).name]),state.object,key=>{state.object=key;preview()}))
  settings.append(pick('配图或贴纸',[...kit.stickers.map(key=>[key,entry('stickers',key).name]),['','不加贴纸']],state.sticker,key=>{state.sticker=key;preview()}))
  settings.append(pick('配色',data.palettes.map(item=>[item.id,item.name]),state.palette,key=>{state.palette=key;preview()}))
  state.labels.forEach((value,i)=>{
   const input=make('input',null,{type:'text',maxlength:'26'})
   input.value=value
   input.oninput=()=>{state.labels[i]=input.value;schedule()}
   settings.append(field(demo.scene==='number'?['起始数值','结束数值','单位'][i]:'文字 '+(i+1),input))
  })
  attachmentBox.replaceChildren()
  if(demo.scene==='wave'){
   const actual=files.has('前段音频') && files.has('后段音频')
   const tip=actual?'波形来自你选择的两段文件，以同一尺度显示。原声可在剪辑时对齐。':
    options.workbench?'当前使用示例波形。选两段录音可换成实际波形。':'当前使用示例波形。可在本机工作台选两段录音换成实际波形。'
   attachmentBox.append(make('p',tip,{class:'muted'}))
   if(options.workbench)for(const label of ['前段音频','后段音频'])attachmentBox.append(fileField(label,'audio'))
  }
  if(demo.scene==='status'){
   if(options.workbench)attachmentBox.append(fileField('截图','image'))
   else attachmentBox.append(make('p','可在本机工作台替换为自己的截图。',{class:'muted'}))
  }
  buttons.hidden=false
  notice.textContent=''
  renderList()
  preview()
 }
 function fileField(slot,kind){
  const input=make('input',null,{type:'file',accept:kind==='image'?'image/png,image/jpeg,image/webp':'audio/*,.wav,.mp3,.m4a'})
  input.onchange=async()=>{
   const file=input.files[0];if(!file)return
   const editing=state
   if(file.size>12*1024**2){notice.textContent='请选择不超过 12 MB 的文件。';return}
   input.disabled=true
   notice.textContent='正在读取本机文件…'
   try{
    const bootstrap=await fetch('/api/bootstrap')
    const {token}=await bootstrap.json()
    const reply=await fetch('/api/motion/lesson-input',{method:'POST',body:file,headers:{'X-Studio-Token':token,'X-Lesson-Media':kind}})
    const content=await reply.json()
    if(!reply.ok)throw Error(content.error)
    if(editing!==state)return
    files.set(slot,content)
    update()
    notice.textContent=kind==='image'?'已换成你的截图。':'已读取这段录音。'
   }catch(error){notice.textContent=error.message;input.disabled=false}
  }
  const wrapper=field(slot,input)
  if(files.has(slot)){
   const clear=make('button','移除 '+slot,{type:'button'})
   clear.onclick=()=>{files.delete(slot);update()}
   const row=make('div',null,{class:'practice-file'})
   row.append(wrapper,clear)
   return row
  }
  return wrapper
 }
 function choose(kit){
  files.clear()
  state={kit,demo:kit.demos[0],palette:kit.palette,object:kit.objects[0],sticker:kit.stickers[0],labels:[...kit.labels]}
  update()
 }
 function searchMatches(kit,raw){
  const q=raw.trim().toLowerCase()
  if(!q)return 1
  const exact=[kit.name,kit.example,kit.kind,kit.assetId].some(text=>text.toLowerCase().includes(q))
  const terms=kit.tags.split(' ')
  return exact?100:terms.reduce((sum,term)=>sum+(q.includes(term)||term.includes(q)?term.length:0),0)
 }
 function renderList(){
  const ranked=data.practice.map(kit=>[kit,searchMatches(kit,query.value)]).filter(([,score])=>score)
  ranked.sort((a,b)=>b[1]-a[1])
  resultCount.textContent=ranked.length?'': '暂时找不到搭配，试试「步骤」「对比」或「上传」。'
  cardList.replaceChildren(...ranked.map(([kit])=>{
   const button=make('button',null,{type:'button','aria-pressed':String(state?.kit===kit),'data-kit':kit.assetId})
   button.append(make('strong',kit.name),make('span',kit.example))
   button.onclick=()=>choose(kit)
   return button
  }))
 }
 async function copy(){
  const {demo}=current()
  if(demo.scene==='wave'&&files.has('前段音频')!==files.has('后段音频')){
   notice.textContent='请为对照同时选前段和后段录音。';return
  }
  const text=mark()
  try{await navigator.clipboard.writeText(text);notice.textContent='已复制，粘贴到对应口播原句后。'}
  catch{const field=make('textarea',text,{'aria-label':'待复制的稿内标注'});notice.replaceChildren(field);field.select()}
 }
 async function save(){
  try{
   const {args,kit}=current()
   for(const key of ['sticker','picture']){
    if(!args[key])continue
    const response=await fetch(args[key])
    if(!response.ok)throw Error('素材未加载，请再试一次。')
    args[key]=await new Promise((resolve,reject)=>{
     response.blob().then(blob=>{
      const reader=new FileReader()
      reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob)
     },reject)
    })
   }
   options.download(kit.assetId+'-透明演示.html',html(await loadTemplate(),args),'text/html')
  }catch(error){notice.textContent=error.message}
 }
 function button(label, handler){const b=make('button',label,{type:'button'});b.onclick=handler;return b}
 actions.append(button('重播',()=>frame.contentWindow.previewPlayback?.('restart')),
  button('暂停',()=>frame.contentWindow.previewPlayback?.('pause')),
  button('看结束帧',()=>frame.contentWindow.previewPlayback?.('finish')),
  button('复制到稿件',copy),button('保存可编辑演示 HTML',save))
 actions.lastElementChild.previousElementSibling.className='go'
 const surface=make('div',null,{class:'practice-view checkboard'})
 surface.append(frame)
 const buttons=make('div',null,{class:'practice-active'})
 buttons.hidden=true
 buttons.append(topic,reason,settings,attachmentBox,surface,actions,notice)
 host.append(field('想给口播配什么画面？',query),resultCount,cardList,buttons)
 query.oninput=renderList
 renderList()
 return {find(code){
  query.value=code;renderList()
  const kit=data.practice.find(kit=>kit.assetId===code)
  if(kit)choose(kit)
 },search:query}
}
