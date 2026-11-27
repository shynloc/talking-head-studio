const parts={pot:['茎叶','盆沿','土面'],camera:['镜头','机身','快门'],lamp:['底座','支架','灯罩'],box:['箱体','盖板','搭扣']}
function node(tag,value,cls){const el=document.createElement(tag);if(value!=null)el.textContent=value;if(cls)el.className=cls;return el}

function scene(style,palette,obj,sticker,sources=null){
 const root=node('article',null,'scene '+style.id+(obj?'':' textonly'))
 for(const [key,color] of Object.entries(palette.colors))root.style.setProperty('--'+key,color)
 const n=obj?.name||'观察一件物品',list=obj?.parts?.includes('、')&&obj?.tokens?.anchors ? obj.parts.split(/[、与和]/).slice(0,3) : parts[obj?.id]||['轮廓','结构','细节']
 const h3=()=>node('h3',n),label=t=>node('small',t,'label')
 function picture(){const fig=node('figure');if(obj){const im=new Image();im.src=sources?sources[obj.files.preview]:obj.files.preview;im.alt=obj.name;fig.append(im)}return fig}
 function words(){const div=node('div',null,'contents');for(const v of list)div.append(node('span',v));return div}
 if(style.id==='field'){const side=node('div');side.append(label('观察记录'),h3(),words());root.append(picture(),side)}
 if(style.id==='manual'){const left=node('div'),ol=node('ol');left.append(h3(),picture());['先看'+list[0],'再看'+list[1],'最后看'+list[2]].forEach(t=>ol.append(node('li',t)));root.append(left,ol)}
 if(style.id==='editorial'){const head=node('header');head.append(label('物件观察'),h3());const note=node('p','从'+list[0]+'到'+list[2]+'，换个角度观察它的轮廓。');root.append(head,picture(),note)}
 if(style.id==='measure'){const h=node('header');h.append(h3());const meter=node('div',null,'meter');for(const [key,v] of [['摆位 A','20'],['摆位 B','35']]){const cell=node('div');cell.append(label(key),node('strong',v),node('small','厘米'));meter.append(cell)}root.append(h,meter,label('摆放距离示例 · 两次测量使用同一单位'))}
 if(style.id==='exhibit'){const plate=node('div',null,'plate');plate.append(h3(),label(list.join(' · ')));root.append(picture(),plate)}
 if(style.id==='route'){const head=node('div');head.append(label('观察路线'),h3());const ol=node('ol',null,'path');for(const s of list)ol.append(node('li',s));root.append(head,ol,label('依次查看三个位置'))}
 if(style.id==='compare'){
  for(const [i,title] of ['之前','之后'].entries()){
   const pane=node('section');pane.append(label(title),picture(),node('strong',i?'重点已标出':'看整体'))
   if(!i)pane.style.opacity='.68';else{const marker=node('span','◎','cmp-mark');pane.append(marker)}root.append(pane)
  }
 }
 if(style.id==='closeup'){
  root.append(h3(),picture());const lens=node('div',null,'lens')
  if(obj){const im=new Image();im.src=sources?sources[obj.files.preview]:obj.files.preview
   const anchor=Object.values(obj.tokens.anchors||{})[0]||[.5,.5]
   im.style.transform='translate('+((.5-anchor[0])*78)+'%,'+((.5-anchor[1])*78)+'%)';im.alt='部位放大';lens.append(im)
  }else lens.append(node('strong','细节'))
  root.append(lens,label('整体'),label('局部放大'))
 }
 if(style.id==='progress'){
  root.append(h3());const flow=node('ol')
  for(const [i,step] of ['准备','操作','完成'].entries()){
   const li=node('li');li.append(node('b',String(i+1).padStart(2,'0')),node('span',step));flow.append(li)
  }root.append(flow)
 }
 if(style.id==='contactsheet'){
  const head=node('header');head.append(label('接触印样'),h3());root.append(head,picture(),picture())
 }
 if(style.id==='recipeleaf'){
  const note=node('div'),steps=node('ol');for(const word of list)steps.append(node('li',word))
  note.append(label('手记'),h3(),steps);root.append(note,picture())
 }
 if(style.id==='signalcard'){
  const title=node('div'),wave=node('div',null,'wave');title.append(label('本期节目'),h3())
  for(const h of [24,46,78,35,61,100,54,27,68,92,48,20,64,35]){
   const bar=node('i');bar.style.height=h+'%';wave.append(bar)
  }wave.setAttribute('aria-hidden','true');root.append(title,picture(),wave)
 }
 if(sticker){const im=new Image();im.className='badge';im.src=sources?sources[sticker.files.vector]:sticker.files.vector;im.alt=sticker.name;root.append(im)}
 return root
}
