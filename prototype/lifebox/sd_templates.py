"""Fixed native requests. Keep plugin parameters and node graphs intact."""
from __future__ import annotations
import copy, json, re

VARIABLES={'prompt','negative','seed','checkpoint','lora','lora_weight','clothes_lora','clothes_weight','reference','control','denoise','width','height'}
SECRET=re.compile(r'api.?key|access.?token|authorization|password|secret',re.I)
REMOTE=re.compile(r'https?://(?!127\.0\.0\.1(?::|/)|localhost(?::|/)|\[::1\](?::|/))',re.I)

def infotext_payload(text):
 # reForge's API paste hook passes UI-only "Use same sampler" sentinels
 # straight into processing. Explicit null keeps native inheritance working.
 result={'infotext':text}
 for label,field in [('Hires sampler','hr_sampler_name'),('Hires schedule type','hr_scheduler'),('Hires checkpoint','hr_checkpoint_name')]:
  if not re.search(r'(?:^|, )'+re.escape(label)+r':',text.splitlines()[-1]):result[field]=None
 # This installed FreeU writes these fields but has no infotext_fields hook.
 fields={k:v for k,v in re.findall(r'(?:^|,\s*)(freeu_(?:enabled|b1|b2|s1|s2)):\s*([^,\n]+)',text.splitlines()[-1])}
 if fields.get('freeu_enabled')=='True' and all('freeu_'+k in fields for k in ('b1','b2','s1','s2')):
  try:args=[True]+[float(fields['freeu_'+k]) for k in ('b1','b2','s1','s2')]
  except ValueError:raise ValueError('PNG FreeU 參數不是有效數字')
  if not all(0<=v<=4 for v in args[1:]):raise ValueError('PNG FreeU 參數超出本機範圍')
  result['alwayson_scripts']={'FreeU Integrated':{'args':args}}
 return result

def pointer(document,path,value=None,write=False):
 if not isinstance(path,str) or not path.startswith('/') or len(path)>300:raise ValueError('綁定位置需為 /節點/inputs/欄位 或 /參數 的 JSON Pointer')
 parts=[p.replace('~1','/').replace('~0','~') for p in path[1:].split('/')];target=document
 try:
  for p in parts[:-1]:target=target[int(p)] if isinstance(target,list) else target[p]
  part=int(parts[-1]) if isinstance(target,list) else parts[-1]
  old=target[part]
  if write:target[part]=value
  return old
 except (KeyError,IndexError,TypeError,ValueError):raise ValueError('綁定欄位不存在：'+path)

def inspect_values(value,blocked,negative=False):
 if isinstance(value,dict):
  for k,v in value.items():
   if SECRET.search(k) and v not in ('',None,False):raise ValueError('模板不可保存金鑰或密碼，請在原生 SD 設定')
   inspect_values(v,blocked,negative or 'negative' in k.lower())
 elif isinstance(value,list):
  for v in value:inspect_values(v,blocked,negative)
 elif isinstance(value,str):
  if REMOTE.search(value):raise ValueError('遊戲固定模板只接受本機工作流；雲端節點請在原生 SD 手動使用')
  if not negative and blocked.search(value):raise ValueError('H 仍封印，遊戲只能保存 SFW 生成模板')

def infer(graph):
 """Only infer unambiguous standard nodes; custom fields stay explicit."""
 result={};samplers=[(n,v) for n,v in graph.items() if isinstance(v,dict) and v.get('class_type')=='KSampler']
 if len(samplers)==1:
  n,v=samplers[0];result['seed']='/'+n+'/inputs/seed';result['denoise']='/'+n+'/inputs/denoise'
  for var,field in [('prompt','positive'),('negative','negative')]:
   link=v['inputs'].get(field)
   if isinstance(link,list) and str(link[0]) in graph and isinstance(graph[str(link[0])],dict) and graph[str(link[0])].get('class_type')=='CLIPTextEncode':result[var]='/'+str(link[0])+'/inputs/text'
 for kind,var,field in [('CheckpointLoaderSimple','checkpoint','ckpt_name'),('LoraLoader','lora','lora_name'),('LoadImage','reference','image')]:
  found=[n for n,v in graph.items() if isinstance(v,dict) and v.get('class_type')==kind]
  if len(found)==1:
   n=found[0];result[var]='/'+n+'/inputs/'+field
   if kind=='LoraLoader':result['lora_weight']=['/'+n+'/inputs/strength_model','/'+n+'/inputs/strength_clip']
 return result

def validate(data,backend,blocked,node_info=None,api_fields=None):
 if not isinstance(data,dict) or set(data)-{'title','backend','payload','bindings','output'}:raise ValueError('原生模板格式不正確')
 title=data.get('title','');payload=copy.deepcopy(data.get('payload'));bindings=copy.deepcopy(data.get('bindings',{}));output=str(data.get('output',''))
 if not isinstance(title,str) or not 1<=len(title.strip())<=100 or data.get('backend')!=backend or not isinstance(payload,dict) or not payload:raise ValueError('請填模板名稱並選擇相同 SD 引擎')
 if len(json.dumps(payload,ensure_ascii=False).encode())>2*1024*1024:raise ValueError('模板需小於 2 MB（圖片另由遊戲注入）')
 if not isinstance(bindings,dict) or set(bindings)-VARIABLES:raise ValueError('未知的工作流綁定變數')
 for var,paths in bindings.items():
  if isinstance(paths,str):paths=[paths]
  if not isinstance(paths,list) or not 1<=len(paths)<=24:raise ValueError('每個變數需指定一至二十四個欄位')
  for p in paths:
   if backend=='comfyui' and not re.fullmatch(r'/[\w.-]+/inputs/[^/]+',p):raise ValueError('ComfyUI 綁定只能指向節點的純值 inputs 欄位，不能更改連線或節點類型')
   old=pointer(payload,p)
   if isinstance(old,(dict,list)):raise ValueError('綁定需指向文字或數字欄位，不能覆蓋節點連線')
  bindings[var]=paths
 if backend=='comfyui':
  if 'nodes' in payload or 'links' in payload:raise ValueError('這是畫布 JSON。請在 ComfyUI 選 Export (API)，或直接擷取已完成的生成紀錄')
  if not 1<=len(payload)<=512 or any(not re.fullmatch(r'[\w.-]{1,80}',n) or not isinstance(v,dict) or not isinstance(v.get('class_type'),str) or not isinstance(v.get('inputs'),dict) for n,v in payload.items()):raise ValueError('需匯入 ComfyUI API 節點圖')
  if not {'prompt','negative','seed','checkpoint','lora','lora_weight'}.issubset(bindings):raise ValueError('請綁定正向、負向、Seed、底模、角色 LoRA 與權重，才能切換遊戲角色')
  if not output or output not in payload:raise ValueError('請選擇輸出圖片的節點 ID')
  # Exclude mapped negative conditioning strings from the SFW positive check.
  check=copy.deepcopy(payload)
  for var in ('negative','checkpoint','lora','clothes_lora'):
   for p in bindings.get(var,[]):pointer(check,p,'',True)
  inspect_values(check,blocked)
  if node_info is not None:
   missing=sorted({v['class_type'] for v in payload.values()}-set(node_info))
   if missing:raise ValueError('本機服務未載入節點：'+', '.join(missing)[:200])
   if any(node_info[v['class_type']].get('api_node') or node_info[v['class_type']].get('is_api_node') or str(node_info[v['class_type']].get('python_module','')).startswith('comfy_api_nodes') for v in payload.values()):raise ValueError('遊戲不自動執行付費 API 節點；請在原生 ComfyUI 手動使用')
   if not node_info[payload[output]['class_type']].get('output_node'):raise ValueError('所選節點不是工作流輸出節點')
 else:
  if isinstance(payload.get('infotext'),str) and payload['infotext'].strip():
   restored=infotext_payload(payload['infotext'])
   if 'alwayson_scripts' in restored:restored['alwayson_scripts'].update(payload.get('alwayson_scripts') or {})
   payload={**restored,**payload,**({'alwayson_scripts':restored['alwayson_scripts']} if 'alwayson_scripts' in restored else {})}
  for f in ('init_images','mask'):
   if payload.get(f):raise ValueError('固定模板不保存內嵌參考圖片，請刪除此欄位；生成時會注入當下人物圖')
  if api_fields is not None and set(payload)-set(api_fields):raise ValueError('本機 API 不接受欄位：'+', '.join(sorted(set(payload)-set(api_fields))))
  if payload.get('batch_size',1)!=1 or payload.get('n_iter',1)!=1:raise ValueError('遊戲每次使用一張輸出；批次生成請在完整 SD 視窗操作')
  if any(re.search('outdir|auth|script_path|file_path',k,re.I) for k in payload.get('override_settings',{})):raise ValueError('模板不能覆蓋 SD 的路徑或認證設定')
  check=copy.deepcopy(payload)
  # Native infotext contains both positive and negative prompts.
  info=check.pop('infotext','')
  if info and blocked.search(info.split('Negative prompt:')[0]):raise ValueError('H 仍封印，請使用 SFW 生成參數')
  if info:
   for label,value in re.findall(r'([A-Za-z_ ]*prompt(?: \d+)?):\s*(.*?)(?=,\s*[A-Za-z][A-Za-z0-9 _./-]*:\s|$)',info.splitlines()[-1],re.I):
    if 'negative' not in label.lower() and blocked.search(value):raise ValueError('PNG 的擴充正向提示包含 H 內容，目前不能存入遊戲模板')
  inspect_values(check,blocked)
 return {'title':title.strip(),'backend':backend,'payload':payload,'bindings':bindings,'output':output}

def mapped_payload(template,values):
 payload=copy.deepcopy(template['payload'])
 for var,paths in template['bindings'].items():
  if var in values:
   for path in paths:pointer(payload,path,values[var],True)
 return payload
