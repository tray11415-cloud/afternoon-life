"""Clearly labelled, offline rules for first-run play and recordings."""
from .model import Action

class DemoBackend:
 model='offline-rules';dialogue_model='offline-rules'
 def decide(self,context,profile='',trigger='',model=None):
  own=context['self']
  if own['busy_until']>context['tick']:return Action('wait',{})
  if trigger=='玩家邀約':
   invite=next((i for i in context['invitations'] if i['recipient']==own['id'] and i['status']=='pending'),None)
   if invite:return Action('respond',{'invitation_id':invite['id'],'accept':True})
  target=context.get('conversation_target',{}).get('id')
  if target is None:target='player' if any(p['id']=='player' for p in context['nearby']) else None
  language=context.get('response_language','zh-TW')
  lines={'zh-TW':'我想先把手邊的事做好。有空的話，一起去公園走走吧。','en':"I'd like to finish what I'm working on first. Shall we walk in the park afterwards?",'ja':'まず今の作業を終わらせたいな。そのあと、一緒に公園を歩かない？'}
  return Action('say',{'target':target,'text':lines.get(language,lines['zh-TW'])})
 def express(self,context,profile,draft):return draft
 def stats(self):
  return {'model':self.model,'dialogue_model':self.dialogue_model,'demo':True,'calls':0,'successes':0,'failures':0,'estimated_usd':0,'uncertain_usd':0,'limit_usd':0,'max_calls':0}
