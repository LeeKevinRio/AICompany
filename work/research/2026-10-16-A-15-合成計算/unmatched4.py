import sys,re
S=sys.argv[1]
def norm(t):
    t=re.sub(r"\*\*","",t); t=re.sub(r"\s+","",t)
    return t
v2n=norm(open(S+"/v02.md",encoding="utf-8").read().replace("\n>"," "))
rows=[l.rstrip("\n").split("\t",1) for l in open(S+"/unmatched.txt",encoding="utf-8")]
def core(t):
    t=t.strip(); t=re.sub(r"^(>\s*)?(-|\d+\.|\|)\s*","",t); t=re.sub(r"\|\s*$","",t)
    return norm(t)
rest=[(int(i),l) for i,l in rows if not (core(l) and core(l) in v2n)]
print(len(rest))
open(S+"/unmatched_norm.tsv","w",encoding="utf-8").write("".join(f"{i}\t{l}\n" for i,l in rest))
print(" ".join(str(i) for i,_ in rest))
