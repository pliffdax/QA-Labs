#!/usr/bin/env python3
"""Isolated QA network exercises. Run with sudo; creates only qa3520-* namespaces."""
import argparse, contextlib, datetime, json, os, re, shlex, signal, subprocess as sp, time, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
N={'c':'qa3520-c','r':'qa3520-r','s':'qa3520-s'}
CFG=Path('/etc/dhcp/qa3520.conf'); CL=Path('/etc/dhcp/qa3520-client.conf')
LEASE=Path('/var/lib/dhcp/dhcpd.leases.qa3520'); CLIENT=Path('/var/lib/dhcp/dhclient-qa3520.leases')
STATE=ROOT/'network-state.json'
LOG=None

def run(*args,ns=None,ok=True,timeout=40):
 cmd=(['ip','netns','exec',N[ns]] if ns else [])+[str(x) for x in args]
 print('$ '+shlex.join(cmd),flush=True)
 p=sp.run(cmd,text=True,stdout=sp.PIPE,stderr=sp.STDOUT,timeout=timeout)
 print(p.stdout,end='',flush=True)
 if ok and p.returncode:raise RuntimeError(f'Exit {p.returncode}: {shlex.join(cmd)}')
 return p

@contextlib.contextmanager
def process(args,ns,output):
 with open(output,'w') as f:
  p=sp.Popen(['ip','netns','exec',N[ns],*map(str,args)],stdout=f,stderr=sp.STDOUT)
  try:
   time.sleep(.5)
   if p.poll() is not None:raise RuntimeError(f'Process exited: {output}: {Path(output).read_text()}')
   yield p
  finally:
   if p.poll() is None:
    p.send_signal(signal.SIGINT)
    try:p.wait(4)
    except sp.TimeoutExpired:p.kill();p.wait()

@contextlib.contextmanager
def capture(ns,iface,name,snap=0):
 with process(['tcpdump','--immediate-mode','-n','-U','-i',iface,'-s',str(snap),'-c','2000','-w',str(LOG/name)],ns,LOG/(name+'.log')):yield

def owned():
 if not STATE.exists():raise RuntimeError('Run setup first')
 state=json.loads(STATE.read_text())
 for ns,ino in state.items():
  if Path('/run/netns',ns).stat().st_ino!=ino:raise RuntimeError('Namespace identity changed')

def setup():
 if STATE.exists():
  if all(not Path('/run/netns',n).exists() for n in N.values()):STATE.unlink()
  else:owned();print('Existing owned topology retained');return
 existing=run('ip','netns','list').stdout
 if any(n in existing for n in N.values()):raise RuntimeError('Name collision; no namespace changed')
 created=[]
 try:
  for n in N.values():run('ip','netns','add',n);created.append(n)
  for ns in N:run('ip','link','set','lo','up',ns=ns)
  run('ip','link','add','c0','type','veth','peer','name','r0',ns='c')
  run('ip','link','set','r0','netns',N['r'],ns='c')
  run('ip','link','add','r1','type','veth','peer','name','s0',ns='r')
  run('ip','link','set','s0','netns',N['s'],ns='r')
  for ns,iface,addr in [('c','c0','10.35.20.10/24'),('r','r0','10.35.20.1/24'),('r','r1','172.22.20.1/24'),('s','s0','172.22.20.2/24')]:
   run('ip','addr','add',addr,'dev',iface,ns=ns);run('ip','link','set',iface,'up',ns=ns)
  run('ip','route','add','default','via','10.35.20.1',ns='c')
  STATE.write_text(json.dumps({n:Path('/run/netns',n).stat().st_ino for n in created},indent=2))
 except BaseException:
  for n in created:run('ip','netns','del',n,ok=False)
  raise

def cleanup():
 owned()
 for n in N.values():
  if run('ip','netns','pids',n).stdout.strip():raise RuntimeError('Close namespace processes before cleanup')
 for n in N.values():run('ip','netns','del',n)
 STATE.unlink()

def static():
 run('ip','addr','flush','dev','c0',ns='c')
 run('ip','addr','add','10.35.20.10/24','dev','c0',ns='c')
 run('ip','route','replace','default','via','10.35.20.1',ns='c')

def lab02():
 static()
 mac=json.loads(run('ip','-j','link','show','r0',ns='r').stdout)[0]['address']
 with capture('c','c0','dynamic.pcap'):
  run('ip','neigh','flush','dev','c0',ns='c');run('ping','-c','3','10.35.20.1',ns='c')
 run('ip','neigh','show',ns='c')
 with capture('c','c0','static.pcap'):
  run('ip','neigh','replace','10.35.20.1','lladdr',mac,'nud','permanent','dev','c0',ns='c')
  run('ping','-c','3','10.35.20.1',ns='c');run('ip','neigh','show',ns='c')
 run('ip','neigh','del','10.35.20.1','dev','c0',ns='c')

def config(with_range=True):
 CFG.write_text('authoritative;\ndefault-lease-time 600;\nmax-lease-time 7200;\nsubnet 10.35.20.0 netmask 255.255.255.0 {\n'+('range 10.35.20.100 10.35.20.110;\n' if with_range else '')+'option subnet-mask 255.255.255.0;\noption routers 10.35.20.1;\noption domain-name-servers 172.22.20.2;\n}\n')
 CL.write_text('timeout 6;\nretry 2;\nselect-timeout 0;\ninitial-interval 1;\n')
 LEASE.write_text('');CLIENT.write_text('')

def dhcp(tag='good',bad=False):
 pidfile=Path('/run/dhcp-server/dhcpd.pid')
 if pidfile.exists() and Path('/proc',pidfile.read_text().strip()).exists():raise RuntimeError('System DHCP PID is active; refusing collision')
 Path('/run/dhcp-server').mkdir(exist_ok=True)
 config(not bad)
 (LOG/(tag+'-dhcpd.conf')).write_text(CFG.read_text())
 run('ip','addr','flush','dev','c0',ns='c')
 run('dhcpd','-t','-cf',CFG,ns='r')
 with process(['dhcpd','-4','-f','-d','-cf',CFG,'-lf',LEASE,'-pf','/run/dhcp-server/dhcpd.pid','r0'],'r',LOG/(tag+'-server.log')):
  with capture('c','c0',tag+'-dhcp.pcap'):
   clientlog=LOG/(tag+'-client.log')
   args=['dhclient','-4','-1','-d','-v','-cf',CL,'-lf',CLIENT,'-pf','/run/dhclient-qa3520.pid','-sf','/bin/true','c0']
   print('$ '+shlex.join(['ip','netns','exec',N['c'],*map(str,args)]),flush=True)
   with process(args,'c',clientlog) as proc:
    for _ in range(100):
     observed=clientlog.read_text()
     if 'bound to ' in observed or proc.poll() is not None:break
     time.sleep(.1)
   p=sp.CompletedProcess(args,proc.returncode,clientlog.read_text())
   print(p.stdout,flush=True)
  (LOG/(tag+'-client.log')).write_text(p.stdout)
  leases=CLIENT.read_text();(LOG/(tag+'-client.leases')).write_text(leases)
  (LOG/(tag+'-server.leases')).write_text(LEASE.read_text())
 if bad:
  if 'DHCPACK' in p.stdout:raise RuntimeError('Unexpected ACK in no-range test')
  print('Observed negative case: no DHCPACK; client exit',p.returncode)
 else:
  ips=re.findall(r'fixed-address\s+(10\.35\.20\.\d+);',leases)
  if 'DHCPACK' not in p.stdout or not ips:raise RuntimeError('No valid DHCP lease')
  # /bin/true suppresses global resolver hooks; apply the acquired lease only in client namespace.
  run('ip','addr','add',ips[-1]+'/24','dev','c0',ns='c')
  run('ip','route','replace','default','via','10.35.20.1',ns='c')
  run('ip','-br','addr',ns='c');run('ip','route',ns='c')

def lab03():
 dhcp();dhcp('no-range',True);dhcp('restored')

def nat():
 run('sysctl','-w','net.ipv4.ip_forward=1',ns='r')
 rule=['iptables','-t','nat','-C','POSTROUTING','-s','10.35.20.0/24','-o','r1','-j','MASQUERADE']
 if run(*rule,ns='r',ok=False).returncode:
  rule[3]='-A';run(*rule,ns='r')

@contextlib.contextmanager
def services():
 web=ROOT/'web';web.mkdir(exist_ok=True);(web/'index.html').write_text('<h1>QA 3520: HTTP through NAT</h1>\n')
 with process(['python3','-m','http.server','8000','--bind','172.22.20.2','--directory',web],'s',LOG/'http-server.log'):
  with process(['dnsmasq','--no-daemon','--port=53','--no-resolv','--no-hosts','--bind-interfaces','--interface=s0','--address=/qa.test/172.22.20.2','--log-queries'],'s',LOG/'dns.log'):yield

def lab04():
 dhcp();nat()
 with services(),capture('r','r0','inside.pcap'),capture('r','r1','outside.pcap'):
  run('ping','-c','2','10.35.20.1',ns='c')
  run('dig','@172.22.20.2','qa.test','+short',ns='c')
  run('curl','--noproxy','*','--max-time','5','--resolve','qa.test:8000:172.22.20.2','http://qa.test:8000/',ns='c')
  run('iptables','-t','nat','-nvL',ns='r')
  try:
   run('ip','route','del','default',ns='c')
   p=run('curl','--noproxy','*','--max-time','3','http://172.22.20.2:8000/',ns='c',ok=False)
   if not p.returncode:raise RuntimeError('Missing-route defect did not reproduce')
  finally:run('ip','route','replace','default','via','10.35.20.1',ns='c')
  run('curl','--noproxy','*','--max-time','5','http://172.22.20.2:8000/',ns='c')

def lab05():
 static()
 with process(['iperf','-s'],'r',LOG/'tcp-server.log'),capture('c','c0','tcp.pcap',256):
  run('bash',ROOT/'Lab05/measure.sh','10.35.20.1',LOG,ns='c',timeout=50)
 with process(['iperf','-s','-u'],'r',LOG/'udp-server.log'),capture('c','c0','udp.pcap',256):
  for size in ['65000','1000']:
   with process(['vmstat','1','12'],'c',LOG/f'vmstat-{size}.txt'):
    p=run('iperf','-c','10.35.20.1','-u','-b','20M','-l',size,'-t','10','-i','1',ns='c')
    (LOG/f'udp-{size}.txt').write_text(p.stdout)
 run('gnuplot','-e',f"datadir='{LOG}'",ROOT/'Lab05/plot.gp')

def lab06():
 nat()
 with services(),capture('r','r0','session.pcap'):
  dhcp()
  run('ip','neigh','flush','dev','c0',ns='c')
  run('dig','@172.22.20.2','qa.test',ns='c')
  run('curl','--noproxy','*','--max-time','5','--resolve','qa.test:8000:172.22.20.2','http://qa.test:8000/',ns='c')
  # DNS is the separately analysed extra session, including UDP port 53 and a name answer.
  run('dig','@172.22.20.2','extra.qa.test',ns='c')

def main():
 global LOG
 p=argparse.ArgumentParser();p.add_argument('action',choices=['setup','cleanup','lab02','lab03','lab04','lab05','lab06']);a=p.parse_args()
 if os.geteuid()!=0:p.error('Run sudo python3 labctl.py ...')
 if a.action=='setup':setup();return
 if a.action=='cleanup':cleanup();return
 owned()
 LOG=ROOT/('L'+a.action[1:])/'results'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S');LOG.mkdir(parents=True)
 class Tee:
  def __init__(self,*streams):self.streams=streams
  def write(self,text):
   for stream in self.streams:stream.write(text);stream.flush()
   return len(text)
  def flush(self):
   for stream in self.streams:stream.flush()
 try:
  with (LOG/'execution.log').open('w') as transcript:
   with contextlib.redirect_stdout(Tee(sys.stdout,transcript)):
    globals()[a.action]()
 finally:
  uid=int(os.environ.get('SUDO_UID','1000'));gid=int(os.environ.get('SUDO_GID','1000'))
  for f in [LOG.parent,LOG,*LOG.rglob('*')]:os.chown(f,uid,gid)
  web=ROOT/'web'
  if web.exists():
   for f in [web,*web.rglob('*')]:os.chown(f,uid,gid)
  print('Results:',LOG)
if __name__=='__main__':main()
