"""Per-character WebUI options; immutable templates and explicit inheritance."""
import copy,math,re

KINDS={'portrait','pixel','cg'}
DEFAULTS={
 'refiner':{'mode':'inherit','targets':['portrait','cg'],'checkpoint':'','switch':.8},
 'hires':{'mode':'inherit','targets':['portrait','cg'],'scale':1.5,'upscaler':'Lanczos','steps':20,'denoise':.35,'sampler':'','cfg':6.0},
 'adetailer':{'mode':'inherit','targets':['portrait','cg'],'passes':[]}}
AD_DEFAULT={'model':'','follow':True,'prompt':'','negative':'','confidence':.3,'denoise':.4,'mask_blur':4,'dilate':4,'padding':32,'only_masked':True,'steps':28,'cfg':7.0,'sampler':'','parameters':{}}

def number(value,lo,hi,integer=False):
 if type(value) not in ((int,) if integer else (int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('進階生圖數值超出範圍')
def text(value,blocked=None,limit=1600):
 if not isinstance(value,str) or len(value)>limit or '<' in value or '>' in value or (blocked and blocked.search(value)):raise ValueError('無效的進階生圖文字')
def styles(profile):
 return ([{'lora':profile['style_lora'],'weight':profile.get('style_weight',.8),'trigger':profile.get('style_trigger',''),'enabled':True}] if profile.get('style_lora') else [])+profile.get('style_loras',[])
def validate_styles(entries,blocked):
 if not isinstance(entries,list) or len(entries)>7:raise ValueError('最多八個畫風 LoRA（含第一個）')
 for p in entries:
  if not isinstance(p,dict) or set(p)!={'lora','weight','trigger','enabled'}:raise ValueError('無效的多畫風 LoRA 配方')
  text(p['lora'],limit=100);text(p['trigger'],blocked);number(p['weight'],0,1.5)
  if type(p['enabled']) is not bool:raise ValueError('無效的畫風開關')
 return copy.deepcopy(entries)

# Optional advanced JSON supplements the visible controls. No paths, credentials,
# remote tools, or replacement of the fields controlled by the form are allowed.
AD_EXTRA={
 'ad_model_classes':str,'ad_mask_filter_method':str,'ad_mask_k':int,
 'ad_mask_min_ratio':float,'ad_mask_max_ratio':float,'ad_x_offset':int,'ad_y_offset':int,
 'ad_mask_merge_invert':str,'ad_use_inpaint_width_height':bool,'ad_inpaint_width':int,
 'ad_inpaint_height':int,'ad_use_checkpoint':bool,'ad_checkpoint':str,'ad_use_vae':bool,
 'ad_vae':str,'ad_scheduler':str,'ad_use_noise_multiplier':bool,'ad_noise_multiplier':float,
 'ad_use_clip_skip':bool,'ad_clip_skip':int,'ad_restore_face':bool,
 'ad_controlnet_model':str,'ad_controlnet_module':str,'ad_controlnet_weight':float,
 'ad_controlnet_guidance_start':float,'ad_controlnet_guidance_end':float,'is_api':bool}
def validate_options(value,blocked):
 if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('未知的進階生圖功能')
 result={}
 for name,raw in value.items():
  if not isinstance(raw,dict) or set(raw)-set(DEFAULTS[name]):raise ValueError('無效的 '+name+' 設定')
  p={**copy.deepcopy(DEFAULTS[name]),**copy.deepcopy(raw)}
  if p['mode'] not in ('inherit','on','off') or not isinstance(p['targets'],list) or not 1<=len(p['targets'])<=3 or any(not isinstance(k,str) or k not in KINDS for k in p['targets']) or len(set(p['targets']))!=len(p['targets']):raise ValueError('請選生圖模式與用途')
  if name=='refiner':text(p['checkpoint'],limit=100);number(p['switch'],.01,.99)
  elif name=='hires':
   number(p['scale'],1,2);number(p['steps'],1,80,True);number(p['denoise'],0,1);number(p['cfg'],1,20);text(p['upscaler'],limit=120);text(p['sampler'],limit=120)
  else:
   if not isinstance(p['passes'],list) or len(p['passes'])>4:raise ValueError('ADetailer 最多四個修補順序')
   for a in p['passes']:
    if not isinstance(a,dict) or set(a)-set(AD_DEFAULT):raise ValueError('無效 ADetailer 修補設定')
    for k,v in AD_DEFAULT.items():a.setdefault(k,copy.deepcopy(v))
    text(a['model'],limit=120);text(a['prompt'],blocked);text(a['negative']);text(a['sampler'],limit=120)
    if type(a['follow']) is not bool or type(a['only_masked']) is not bool:raise ValueError('無效 ADetailer 開關')
    for k in ('confidence','denoise'):number(a[k],0,1)
    for k,lo,hi in [('mask_blur',0,64),('dilate',-128,128),('padding',0,256),('steps',1,80)]:number(a[k],lo,hi,True)
    number(a['cfg'],1,20)
    extras=a['parameters']
    if not isinstance(extras,dict) or set(extras)-set(AD_EXTRA):raise ValueError('ADetailer 其他參數含未知或由表單管理的欄位')
    for k,v in extras.items():
     typ=AD_EXTRA[k]
     if typ==str:text(v,blocked,300)
     elif typ==bool:
      if type(v) is not bool:raise ValueError('ADetailer 其他參數型別無效')
     else:
      lo,hi=(-256,256) if k in ('ad_x_offset','ad_y_offset') else (64,2048) if k in ('ad_inpaint_width','ad_inpaint_height') else (1,12) if k=='ad_clip_skip' else (0,128) if k=='ad_mask_k' else (.5,1.5) if k=='ad_noise_multiplier' else (0,1)
      number(v,lo,hi,typ==int)
    if extras.get('ad_mask_filter_method','Area') not in ('Area','Confidence') or extras.get('ad_mask_merge_invert','None') not in ('None','Merge','Merge and Invert'):raise ValueError('ADetailer 遮罩選项無效')
   if p['mode']=='on' and (not p['passes'] or any(not a['model'] for a in p['passes'])):raise ValueError('請選 ADetailer 偵測器')
  # Do not change existing saved bindings or render hashes on upgrade.
  if p!=DEFAULTS[name]:result[name]=p
 return result

def active(recipe,template,name):
 p=recipe.get('profile',{}).get('render_options',{}).get(name,{})
 if not p:return {}
 kind=template.get('_kind') or ('cg' if recipe.get('kind')=='cg' else 'pixel' if recipe.get('kind')=='pixel' else 'portrait')
 return p if kind in p.get('targets',[]) else {}

def preflight(studio,profile,kinds):
 service=studio.services.get(studio.config['url'],{})
 for name,p in profile.get('render_options',{}).items():
  if p['mode']=='inherit' or not set(p['targets'])&kinds:continue
  if studio.config['backend']!='a1111':raise ValueError('Refiner／ADetailer／Hires.fix 角色面板使用 WebUI／Forge；ComfyUI 請沿用原生工作流，將面板設為沿用模板。')
  if p['mode']!='on':continue
  if name=='refiner':
   if not p['checkpoint']:raise ValueError('請選 Refiner 底模')
   studio._resource(p['checkpoint'],'checkpoint')
   if not {'refiner_checkpoint','refiner_switch_at'}.issubset(service.get('advanced_fields',[])):raise ValueError('本機 API 尚未確認 Refiner 欄位，請更新功能清單')
  if name=='hires':
   if p['upscaler'] not in service.get('upscalers',[]):raise ValueError('放大器未在本機可用，請更新功能清單')
   if p['sampler'] and p['sampler'] not in service.get('samplers',[]):raise ValueError('高解析採樣器未載入')
   for kind in set(p['targets'])&kinds:
    t=studio.config['templates'][kind]
    if max(t['width'],t['height'])*p['scale']>2048:raise ValueError('高解析輸出上限 2048px，請降低倍率或原尺寸')
  if name=='adetailer':
   if not service.get('adetailer_models'):raise ValueError('本機服務尚未確認 ADetailer，請更新功能清單')
   if len(p['passes'])>service.get('adetailer_slots',4):raise ValueError('修補順序超過本機 ADetailer API 可用數量')
   for a in p['passes']:
    if a['model'] not in service['adetailer_models']:raise ValueError('ADetailer 偵測器未載入：'+a['model'])
    if a['sampler'] and a['sampler'] not in service.get('samplers',[]):raise ValueError('ADetailer 採樣器未載入')

def webui_payload(payload,recipe,t,prompt,negative,model_name):
 result=copy.deepcopy(payload);opts=recipe['profile'].get('render_options',{})
 ref=active(recipe,t,'refiner')
 if ref.get('mode')=='off':result.update(refiner_checkpoint=None,refiner_switch_at=None)
 elif ref.get('mode')=='on':result.update(refiner_checkpoint=model_name(recipe['advanced_refiner']),refiner_switch_at=ref['switch'])
 hr=active(recipe,t,'hires')
 if hr.get('mode')=='off':result['enable_hr']=False
 elif hr.get('mode')=='on':result.update(enable_hr=True,hr_scale=hr['scale'],hr_upscaler=hr['upscaler'],hr_second_pass_steps=hr['steps'],hr_resize_x=0,hr_resize_y=0,denoising_strength=hr['denoise'],hr_sampler_name=hr['sampler'] or result.get('sampler_name'),hr_cfg=hr['cfg'],hr_prompt=prompt,hr_negative_prompt=negative,hr_checkpoint_name=model_name(recipe['checkpoint']))
 ad=active(recipe,t,'adetailer')
 if ad.get('mode') in ('on','off'):
  scripts=result.setdefault('alwayson_scripts',{});key=next((k for k in scripts if k.lower()=='adetailer'),recipe.get('adetailer_script','ADetailer'))
  if ad['mode']=='off':
   if key in scripts or recipe.get('adetailer_available'):scripts[key]={'args':[False,False]}
  else:
   profile=recipe['profile'];identity=('adult man' if recipe.get('gender')=='male' else 'adult woman')+', '+profile['identity']+', '+profile['trigger']+', '+t.get('_expression','natural expression')
   identity+=' '+ ' '.join(re.findall(r'<lora:[^<>]+>',prompt))
   args=[]
   for a in ad['passes']:
    args.append({**a['parameters'],'ad_model':a['model'],'ad_tab_enable':True,'ad_prompt':(identity+', '+a['prompt']).strip(' ,') if a['follow'] else a['prompt'],'ad_negative_prompt':a['negative'],'ad_confidence':a['confidence'],'ad_denoising_strength':a['denoise'],'ad_mask_blur':a['mask_blur'],'ad_dilate_erode':a['dilate'],'ad_inpaint_only_masked':a['only_masked'],'ad_inpaint_only_masked_padding':a['padding'],'ad_use_steps':True,'ad_steps':a['steps'],'ad_use_cfg_scale':True,'ad_cfg_scale':a['cfg'],'ad_use_sampler':bool(a['sampler']),'ad_sampler':a['sampler'] or result.get('sampler_name','Euler'),'ad_scheduler':a['parameters'].get('ad_scheduler','Use same scheduler')})
   args.extend({'ad_model':'None','ad_tab_enable':False} for _ in range(max(0,recipe.get('adetailer_slots',len(args))-len(args))))
   scripts[key]={'args':[True,False,*args]}
 return result

def disable_adetailer(payload):
 result=copy.deepcopy(payload)
 for name,script in result.get('alwayson_scripts',{}).items():
  if name.lower()=='adetailer':script['args']=[False,False]
 return result
