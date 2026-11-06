import os,re,io,json,sqlite3
from pathlib import Path
from datetime import datetime
from flask import Flask,render_template,request,jsonify,send_file,abort
from werkzeug.utils import secure_filename

BASE=Path(__file__).parent; DB=BASE/"smart_notes.db"; UP=BASE/"uploads"; UP.mkdir(exist_ok=True)
app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=80*1024*1024
def conn(): 
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now().strftime("%d %b %Y, %H:%M")
with conn() as c:
 c.executescript("""CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,title TEXT,subject TEXT,method TEXT,content TEXT,source TEXT,fav INTEGER DEFAULT 0,created TEXT);
 CREATE TABLE IF NOT EXISTS recordings(id INTEGER PRIMARY KEY,title TEXT,subject TEXT,file TEXT,transcript TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS tests(id INTEGER PRIMARY KEY,note_id INTEGER,title TEXT,subject TEXT,score INTEGER,total INTEGER,pct REAL,details TEXT,created TEXT);""")

def sents(t): return [x.strip() for x in re.split(r'(?<=[.!?])\s+',re.sub(r'\s+',' ',t).strip()) if len(x.strip())>20]
def paras(t): return [re.sub(r'\s+',' ',x).strip() for x in t.splitlines() if x.strip()]
def defs(t):
 out=[]
 for p in [r'([A-Z][\w ()/-]{1,50}?)\s+(?:is defined as|is|are|refers to|means)\s+([^.!?\n]{8,180})',r'([A-Z][\w ()/-]{1,50})\s*:\s*([^.!?\n]{8,180})']:
  for a,b in re.findall(p,t):
   if len(a.split())<9 and (a,b) not in out: out.append((a.strip(),b.strip()))
 return out[:8]
def keywords(t):
 stop=set("the a an and or but if then of in on at to for from by with is are was were be this that it as into can could will may we you they".split())
 w=re.findall(r'[A-Za-z][A-Za-z0-9-]{3,}',t.lower()); f={}
 for x in w:
  if x not in stop:f[x]=f.get(x,0)+1
 return [x for x,n in sorted(f.items(),key=lambda z:-z[1])[:12]]
def generate(title,subject,source,method):
 p=paras(source); ss=sents(source) or p; heads=[x.strip(" #:-") for x in p if len(x.split())<=9 and not x.endswith(('.','?','!'))]
 sig=("important","therefore","because","however","consists","defined","example","such as","process","function","advantages","formula","result")
 key=sorted(ss,key=lambda x:sum(z in x.lower() for z in sig)+min(len(x),240)/240,reverse=True)[:8]
 ds=defs(source); kw=keywords(source); summary=" ".join(ss[:3])
 qs=[f"Explain {h}." for h in heads[:4]]+[f"Define {a}." for a,b in ds[:4]]+[f"Why is {k} important?" for k in kw[:4]]
 if not qs:qs=["What are the main ideas in this lecture?"]
 o=[f"# {title}",f"**Subject:** {subject}",f"**Method:** {method}",""]
 if method=="Cornell Method":o+=["## Cue questions"]+[f"- {q}" for q in qs]+["","## Lecture notes"]+[f"- {x}" for x in ss[:12]]+["","## Summary",summary]
 elif method=="Outline Method":
  o+=["## Main headings"]
  for h in heads[:7]:
   o += [f"### {h}"]+[f"- {x}" for x in ([x for x in ss if h.lower().split()[0] in x.lower()][:3] or ss[:2])]
  if not heads:o+=["### Core ideas"]+[f"- {x}" for x in ss[:10]]
  o+=["","## Important points"]+[f"- {x}" for x in key]
 elif method=="Mind Mapping":
  o += [f"## Central topic: {title}","```text",title]
  for i,h in enumerate(heads[:7] or kw[:7]):
   o += [f"├── {h}"]+[f"│   └── {x}" for x in ([x for x in ss if h.lower().split()[0] in x.lower()][:2] or ss[i:i+1])]
  o+=["```"]
 else:
  o+=["## Concept chart","| Topic | Explanation |","|---|---|"]
  for i,h in enumerate(heads[:7] or kw[:7]):
   rel=[x for x in ss if h.lower().split()[0] in x.lower()]
   o += [f"| {h} | {(rel or ss[i:i+1] or ['See lecture'])[0].replace('|','/')} |"]
  o+=["","## Important points"]+[f"- {x}" for x in key]
 o+=["","## Key definitions"]+([f"- **{a}:** {b}" for a,b in ds] or ["- No explicit definition pattern detected."])
 o+=["","## Important keywords",", ".join(kw),"","## Short summary",summary,"","## Revision questions"]+[f"{i+1}. {q}" for i,q in enumerate(qs)]
 return "\n".join(o)
def makequiz(text,count,typ):
 ss=sents(text); kw=keywords(text); ds=defs(text); q=[]
 for a,b in ds:q.append(dict(type="Short Answer",question=f"Define {a}.",answer=b,explanation=f"The notes define {a} as {b}",options=[]))
 for x in ss:
  words=re.findall(r'\b[A-Za-z][A-Za-z0-9-]{3,}\b',x); candidates=[w for w in words if w.lower() in kw]
  if candidates:
   ans=max(candidates,key=len); blank=re.sub(r'\b'+re.escape(ans)+r'\b',"________",x,count=1,flags=re.I)
   q.append(dict(type="Fill in the Blanks",question=blank,answer=ans,explanation=x,options=[]))
  q.append(dict(type="True or False",question=f"True or False: {x}",answer="True",explanation="This statement is directly supported by the saved notes.",options=["True","False"]))
  q.append(dict(type="Important Exam Question",question="Discuss the following lecture point: "+x,answer=x,explanation="Use this point from the saved notes as the basis of a complete exam answer.",options=[]))
 if typ in ("MCQ","Mixed"):
  for x in list(q):
   if x["type"]=="Fill in the Blanks" and len(kw)>2:
    opts=list(dict.fromkeys([x["answer"]]+[z for z in kw if z.lower()!=x["answer"].lower()][:3]))
    x["type"]="MCQ"; x["options"]=opts
 if typ not in ("Mixed","All"): q=[x for x in q if x["type"]==typ]
 # Questions are extracted/generated only from actual saved note text.
 seen=set(); q=[x for x in q if not (x["question"] in seen or seen.add(x["question"]))]
 return q[:max(1,min(int(count),30))]
def grade(ans,expected,kind):
 if kind in ("MCQ","Fill in the Blanks","True or False"):return ans.strip().lower()==expected.strip().lower()
 a=set(keywords(ans)); e=set(keywords(expected)); return bool(e) and len(a&e)/len(e)>=.35

@app.get("/")
def index():return render_template("index.html",transcription_ready=bool(os.getenv("OPENAI_API_KEY")))
@app.get("/api/dashboard")
def dashboard():
 with conn() as c:
  return jsonify(notes=[dict(x) for x in c.execute("SELECT id,title,subject,method,fav,created FROM notes ORDER BY id DESC LIMIT 5")],
  recordings=[dict(x) for x in c.execute("SELECT id,title,subject,created FROM recordings ORDER BY id DESC LIMIT 5")],
  tests=[dict(x) for x in c.execute("SELECT id,title,subject,score,total,pct,created FROM tests ORDER BY id DESC LIMIT 5")],
  total_notes=c.execute("SELECT count(*) FROM notes").fetchone()[0],total_recordings=c.execute("SELECT count(*) FROM recordings").fetchone()[0],
  total_tests=c.execute("SELECT count(*) FROM tests").fetchone()[0],average=round(c.execute("SELECT avg(pct) FROM tests").fetchone()[0] or 0,1),
  subjects=[dict(x) for x in c.execute("SELECT subject,count(*) count FROM notes GROUP BY subject")])
@app.route("/api/notes",methods=["GET","POST"])
def notes():
 if request.method=="POST":
  d=request.get_json(); title=d.get("title","").strip(); sub=d.get("subject","").strip(); src=d.get("text","").strip(); method=d.get("method","Outline Method")
  if not title or not sub or len(src)<60:return jsonify(error="Enter title, subject and at least 60 characters of lecture content."),400
  if method not in ["Cornell Method","Outline Method","Mind Mapping","Chart Method"]:return jsonify(error="Invalid method"),400
  content=generate(title,sub,src,method)
  with conn() as c: nid=c.execute("INSERT INTO notes(title,subject,method,content,source,created) VALUES(?,?,?,?,?,?)",(title,sub,method,content,src,now())).lastrowid
  return jsonify(id=nid,content=content)
 q=request.args.get("q","")
 with conn() as c: rows=[dict(x) for x in c.execute("SELECT * FROM notes WHERE title LIKE ? OR subject LIKE ? ORDER BY id DESC",(f"%{q}%",f"%{q}%"))]
 return jsonify(notes=rows)
@app.put("/api/notes/<int:i>")
def editnote(i):
 d=request.get_json()
 with conn() as c:c.execute("UPDATE notes SET title=?,subject=?,content=? WHERE id=?",(d["title"],d["subject"],d["content"],i))
 return jsonify(ok=True)
@app.delete("/api/notes/<int:i>")
def delnote(i):
 with conn() as c:c.execute("DELETE FROM notes WHERE id=?",(i,))
 return jsonify(ok=True)
@app.post("/api/notes/<int:i>/favorite")
def fav(i):
 with conn() as c:
  r=c.execute("SELECT fav FROM notes WHERE id=?",(i,)).fetchone()
  if not r:return jsonify(error="Not found"),404
  v=1-r["fav"];c.execute("UPDATE notes SET fav=? WHERE id=?",(v,i))
 return jsonify(favorite=v)
@app.post("/api/quiz")
def quiz():
 d=request.get_json()
 with conn() as c:r=c.execute("SELECT * FROM notes WHERE id=?",(d.get("note_id"),)).fetchone()
 if not r:return jsonify(error="Select a saved note."),400
 qs=makequiz(r["content"],d.get("count",10),d.get("type","Mixed"))
 if not qs:return jsonify(error="Not enough definitional/factual sentences were found in these notes to make this quiz. Add fuller notes and try again."),400
 return jsonify(note_id=r["id"],title=r["title"],subject=r["subject"],questions=qs)
@app.post("/api/quiz/submit")
def submit():
 d=request.get_json(); qs=d.get("questions",[]); ans=d.get("answers",[]); details=[];score=0
 for n,q in enumerate(qs):
  a=ans[n] if n<len(ans) else ""; ok=grade(str(a),q["answer"],q["type"]);score+=int(ok)
  details.append(dict(question=q["question"],answer=a,expected=q["answer"],correct=ok,explanation=q["explanation"]))
 total=len(qs);pct=round(score*100/total,1) if total else 0
 with conn() as c:c.execute("INSERT INTO tests(note_id,title,subject,score,total,pct,details,created) VALUES(?,?,?,?,?,?,?,?)",(d["note_id"],d["title"],d["subject"],score,total,pct,json.dumps(details),now()))
 return jsonify(score=score,total=total,pct=pct,details=details)
@app.get("/api/history")
def history():
 with conn() as c:return jsonify(recordings=[dict(x) for x in c.execute("SELECT id,title,subject,transcript,created FROM recordings ORDER BY id DESC")],tests=[dict(x) for x in c.execute("SELECT * FROM tests ORDER BY id DESC")])
@app.post("/api/transcribe")
def transcribe():
 f=request.files.get("audio")
 if not f:return jsonify(error="No audio file supplied."),400
 key=os.getenv("OPENAI_API_KEY")
 if not key:return jsonify(error="Real transcription is not configured. Add OPENAI_API_KEY to the server environment. No fake transcript has been created."),503
 name="audio_"+datetime.now().strftime("%Y%m%d%H%M%S%f")+Path(secure_filename(f.filename or "lecture.webm")).suffix
 path=UP/name;f.save(path)
 try:
  from openai import OpenAI
  with open(path,"rb") as af:r=OpenAI(api_key=key).audio.transcriptions.create(model=os.getenv("OPENAI_TRANSCRIBE_MODEL","gpt-4o-mini-transcribe"),file=af)
  transcript=r.text
  title=request.form.get("title","Recorded lecture");sub=request.form.get("subject","General")
  with conn() as c:rid=c.execute("INSERT INTO recordings(title,subject,file,transcript,created) VALUES(?,?,?,?,?)",(title,sub,name,transcript,now())).lastrowid
  return jsonify(id=rid,transcript=transcript)
 except Exception as e:
  path.unlink(missing_ok=True);return jsonify(error="Transcription failed: "+str(e)[:250]),502
@app.post("/api/recordings/<int:i>/notes")
def recnotes(i):
 d=request.get_json()
 with conn() as c:r=c.execute("SELECT * FROM recordings WHERE id=?",(i,)).fetchone()
 if not r:return jsonify(error="Recording not found."),404
 text=d.get("transcript","").strip()
 if len(text)<60:return jsonify(error="Please provide at least 60 characters of transcript."),400
 content=generate(d.get("title",r["title"]),d.get("subject",r["subject"]),text,d.get("method","Outline Method"))
 with conn() as c:nid=c.execute("INSERT INTO notes(title,subject,method,content,source,created) VALUES(?,?,?,?,?,?)",(d.get("title",r["title"]),d.get("subject",r["subject"]),d.get("method","Outline Method"),content,text,now())).lastrowid
 return jsonify(id=nid,content=content)
@app.delete("/api/recordings/<int:i>")
def delrec(i):
 with conn() as c:
  r=c.execute("SELECT file FROM recordings WHERE id=?",(i,)).fetchone()
  if r:
   (UP/r["file"]).unlink(missing_ok=True);c.execute("DELETE FROM recordings WHERE id=?",(i,))
 return jsonify(ok=True)
@app.get("/api/recordings/<int:i>/audio")
def audio(i):
 with conn() as c:r=c.execute("SELECT file FROM recordings WHERE id=?",(i,)).fetchone()
 if not r:abort(404)
 return send_file(UP/r["file"])
@app.get("/api/tests")
def testhistory():
 with conn() as c:return jsonify(tests=[dict(x) for x in c.execute("SELECT * FROM tests ORDER BY id DESC")])
@app.get("/api/notes/<int:i>/txt")
def txt(i):
 with conn() as c:r=c.execute("SELECT title,content FROM notes WHERE id=?",(i,)).fetchone()
 if not r:abort(404)
 return send_file(io.BytesIO(r["content"].encode()),as_attachment=True,download_name="lecture-notes.txt",mimetype="text/plain")
@app.get("/api/notes/<int:i>/pdf")
def pdf(i):
 with conn() as c:r=c.execute("SELECT title,content FROM notes WHERE id=?",(i,)).fetchone()
 if not r:abort(404)
 try:
  from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
  from reportlab.lib.styles import getSampleStyleSheet
  from reportlab.lib.pagesizes import A4
  b=io.BytesIO();doc=SimpleDocTemplate(b,pagesize=A4);styles=getSampleStyleSheet();story=[Paragraph(r["title"],styles["Title"])]
  for line in r["content"].splitlines():
   if line.strip():story.append(Paragraph(line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("**",""),styles["BodyText"]));story.append(Spacer(1,5))
  doc.build(story);b.seek(0);return send_file(b,as_attachment=True,download_name="lecture-notes.pdf",mimetype="application/pdf")
 except Exception as e:return jsonify(error=str(e)),500
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=True)
