"""Replaceable local AI contracts; one actor projection, validated actions only."""
import json,threading
from urllib.request import Request,build_opener,ProxyHandler
from urllib.parse import urlsplit
from .policies import _NoRedirect
from .model import Action,canonical
from .xai import AIError,DIALOGUE_TRIGGERS

def local_endpoint(value):
 if not isinstance(value,str):raise ValueError('工具網址需為文字')
 u=urlsplit(value)
 if u.scheme!='http' or u.hostname not in {'127.0.0.1','localhost','::1'} or u.username or u.password or u.query or u.fragment or not u.port:raise ValueError('替換服務只接受有埠號的本機 HTTP，不接受金鑰或遠端網址')
 return value.rstrip('/')

def request_tool(endpoint,body):
 raw=canonical(body).encode()
 if len(raw)>65536:raise ValueError('工具上下文超過限制')
 req=Request(local_endpoint(endpoint),raw,{'Content-Type':'application/json'},method='POST')
 try:
  with build_opener(ProxyHandler({}),_NoRedirect).open(req,timeout=20) as r:data=r.read(65537)
  if len(data)>65536:raise ValueError('工具輸出超過限制')
  return json.loads(data)
 except (OSError,ValueError,KeyError):raise AIError('invalid_output') from None

class RoutedBackend:
 def __init__(self,base,manager):self.base=base;self.manager=manager;self.lock=threading.RLock()
 def __getattr__(self,k):return getattr(self.base,k)
 def stats(self):
  data=self.base.stats();data['component_routes']={k:self.manager.get('service:'+k)['adapter'] for k in ('dialogue','action')};data['local_tool_calls']=sum(self.manager.usage.values())
  for lane,field in (('dialogue','dialogue_model'),('action','model')):
   c=self.manager.get('service:'+lane)
   if c['adapter']!='existing':data[field]=c['model'] or '本機 '+lane+' 工具'
  return data
 def decide(self,context,profile='',trigger='自由活動',model=None):
  lane='dialogue' if model==getattr(self.base,'dialogue_model',None) and model is not None or trigger in DIALOGUE_TRIGGERS else 'action'
  c=self.manager.get('service:'+lane)
  if c['adapter']=='existing':return self.base.decide(context,profile,trigger,**({'model':model} if model is not None else {}))
  try:
   with self.lock:self.manager.reserve('service:'+lane,c['max_calls'])
  except Exception:raise AIError('budget') from None
  result=request_tool(c['endpoint'],{'contract':'lifebox.decide.v1','actor':context['self']['id'],'context':context,'profile':profile,'trigger':trigger,'model':c['model']})
  try:return Action.parse(result['action'])
  except (KeyError,TypeError,ValueError):raise AIError('invalid_output') from None
 def express(self,context,profile,draft):
  if self.manager.get('service:dialogue')['adapter']=='existing':return self.base.express(context,profile,draft)
  result=self.decide(context,profile,'另一位成員向你說話')
  if result.kind!='say' or result.params.get('target')!=draft.params.get('target'):raise AIError('invalid_output')
  return result
