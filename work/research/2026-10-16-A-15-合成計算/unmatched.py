import sys, subprocess, re
S=sys.argv[1]
v1=open(S+"/v01.md",encoding="utf-8").read().split("\n")
v2=open(S+"/v02.md",encoding="utf-8").read().split("\n")
v2set=set(v2)
v2text="\n".join(v2)
diff=subprocess.run(["git","diff","-U0","86c71c9","1b26f72","--",sys.argv[2]],capture_output=True,text=True).stdout
dels=[]
for h in re.finditer(r"^@@ -(\d+)(?:,(\d+))? ",diff,re.M):
    start=int(h.group(1)); cnt=int(h.group(2)) if h.group(2) is not None else 1
    for i in range(start,start+cnt):
        dels.append(i)
out=[]
for i in dels:
    line=v1[i-1]
    if line.strip()=="" : continue
    if line in v2set or ("> "+line) in v2set or (">"+line) in v2set: continue
    core=line.strip()
    out.append((i,line))
print(len(dels),"deleted; nonblank unmatched:",len(out))
with open(S+"/unmatched.txt","w",encoding="utf-8") as f:
    for i,l in out: f.write(f"{i}\t{l}\n")
