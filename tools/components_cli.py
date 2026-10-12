"""Local component tools for assistants; never reads a model API key."""
import argparse,json
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler,ProxyHandler
from urllib.parse import urlsplit
from pathlib import Path
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*a,**k):return None
parser=argparse.ArgumentParser(description='生活沙箱部件替換工具')
parser.add_argument('--url',default='http://127.0.0.1:8765');sub=parser.add_subparsers(dest='op',required=True)
sub.add_parser('list');sub.add_parser('schema')
for name in ('get','export'):
 p=sub.add_parser(name);p.add_argument('--target',required=True);p.add_argument('--out',type=Path)
p=sub.add_parser('plan');p.add_argument('--target',required=True);p.add_argument('--instruction',required=True)
p=sub.add_parser('prepare');p.add_argument('--file',type=Path,required=True)
p=sub.add_parser('apply');p.add_argument('--proposal',required=True)
p=sub.add_parser('rollback');p.add_argument('--history',required=True)
args=parser.parse_args();base=args.url.rstrip('/');u=urlsplit(base)
if u.scheme!='http' or u.hostname not in {'127.0.0.1','localhost'} or not u.port or u.username or u.password or u.query or u.fragment:parser.error('只接受本機 HTTP 位址')
opener=build_opener(ProxyHandler({}),NoRedirect)
def get(path,token=None):
 with opener.open(Request(base+path,headers={'X-Play-Token':token} if token else {}),timeout=30) as r:return json.load(r)
token=get('/api/state')['token']
if args.op in ('list','schema'):result=get('/api/components'+('/schema' if args.op=='schema' else ''),token)
else:
 params={'target':args.target} if args.op=='get' else {'targets':[args.target]} if args.op=='export' else {'instruction':args.instruction,'targets':[args.target]} if args.op=='plan' else json.loads(args.file.read_text(encoding='utf-8-sig')) if args.op=='prepare' else {'proposal':args.proposal} if args.op=='apply' else {'history':args.history}
 req=Request(base+'/api/components',json.dumps({'operation':args.op,'params':params},ensure_ascii=False).encode(),{'Content-Type':'application/json','X-Play-Token':token,'Origin':base},method='POST')
 try:
  with opener.open(req,timeout=35) as r:result=json.load(r)
 except Exception as exc:
  if hasattr(exc,'read'):
   error=json.loads(exc.read(65536));raise SystemExit(error.get('message','部件操作被拒絕'))
  raise SystemExit('本機部件工具未連線')
text=json.dumps(result,ensure_ascii=False,indent=2)
if getattr(args,'out',None):args.out.write_text(text,encoding='utf-8');print(str(args.out.resolve()))
else:print(text)
