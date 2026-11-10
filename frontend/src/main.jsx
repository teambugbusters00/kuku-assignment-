import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API_BASE = (import.meta.env.VITE_API_URL || (import.meta.env.PROD ? 'https://kukufm-assignment-api.onrender.com' : '')).trim().replace(/\/+$/, '');
const repo = 'https://github.com/teambugbusters00/kuku-assignment-';
const demoA = "Maya entered the hospital with a blood-stained letter. She told her brother Arjun their father was alive and hid evidence in the mansion. Arjun owns the silver key. Maya promised to return before midnight.";
const demoB = "The next morning Maya arrives at the police station. Arjun says their father died years ago and the silver key was stolen. Maya asks the detective to find the letter.";

const docs = {
  PS1: { filename: 'KukuFM_PS1_Content_Understanding_Tagging.md', title: 'PS1 — AI Content Understanding & Tagging', body: 'Input: transcript, optional title and language. Endpoint: POST /api/ps1/tag. The user-triggered Analyze action routes to the configured AI provider and returns transcript-grounded summary, genre, tags, themes, characters, emotions, content warnings, language, confidence, and evidence notes. Review outputs for hallucinations and evidence grounding.' },
  PS2: { filename: 'KukuFM_PS2_Personalized_Recommendation.md', title: 'PS2 — Personalized Audio Recommendation', body: 'Input: listener profile, supplied catalog, and top_n. Endpoint: POST /api/ps2/recommend. The user-triggered recommendation action routes to the configured AI provider and returns ranked catalog recommendations, match scores, reasons, profile signals, and diversity notes. Current catalog-only constraint is prompt-based; validate returned IDs against the submitted catalog before production.' },
  PS3: { filename: 'KukuFM_PS3_StoryBridge_Continuity.md', title: 'PS3 — StoryBridge Episode Continuity Checker', body: 'Input: previous and next episode text or dataset episode IDs. Endpoints: POST /api/analyze, POST /api/analyze-episodes, GET /api/analyze-series. Gemini is preferred for one-call episode-pair comparison, with Groq as alternate provider. Local deterministic checks run if both providers are unavailable. Findings are editorial review signals, not definitive judgments.' }
};

async function apiFetch(path, options={}) {
  const url = `${API_BASE}${path}`;
  let response;
  try {
    response = await fetch(url, {
      ...options,
      signal: options.signal || AbortSignal.timeout(90000),
      headers: { ...(options.headers || {}) }
    });
  } catch (error) {
    if (error.name === 'TimeoutError' || error.name === 'AbortError') {
      throw new Error(`Backend request timed out after 90 seconds. Render may be waking up; retry once. API: ${API_BASE || '(same origin)'}`);
    }
    throw new Error(`Cannot reach backend API (${API_BASE || window.location.origin}). Check Render backend status, VITE_API_URL, and CORS. Browser detail: ${error.message || 'network error'}`);
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || JSON.stringify(payload);
    } catch {
      const text = await response.text().catch(() => '');
      if (text) detail = text.slice(0, 700);
    }
    throw new Error(detail);
  }
  return response;
}

function downloadFile(filename, content, type='application/json') {
  const blob = new Blob([content], {type});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
function downloadJson(filename, data) {
  downloadFile(filename, JSON.stringify(data, null, 2), 'application/json');
}
function displayValue(value, empty='—') {
  if (value === null || value === undefined || value === '') return empty;
  if (Array.isArray(value)) return value.map(item => displayValue(item, '')).filter(Boolean).join(', ');
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

class AppErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { failed: false }; }
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.error('KukuFM UI render error:', error); }
  render() {
    if (this.state.failed) return <main style={{maxWidth:720,margin:'48px auto',padding:24,fontFamily:'sans-serif'}}>
      <h2>Something went wrong while showing this result.</h2>
      <p>Your analysis request may have completed. Reload the page and check Run History.</p>
      <button onClick={() => window.location.reload()}>Reload app</button>
    </main>;
    return this.props.children;
  }
}

function App() {
  const [view,setView]=useState('home');
  const [episodes,setEpisodes]=useState([]);
  const [prevId,setPrevId]=useState('');
  const [nextId,setNextId]=useState('');
  const [show,setShow]=useState('KukuFM episode dataset');
  const [a,setA]=useState(demoA);
  const [b,setB]=useState(demoB);
  const [out,setOut]=useState(null);
  const [series,setSeries]=useState(null);
  const [busy,setBusy]=useState(false);
  const [loadingEpisodes,setLoadingEpisodes]=useState(true);
  const [err,setErr]=useState('');
  const [mode,setMode]=useState('dataset');
  const [activeProblem,setActiveProblem]=useState('PS3');
  const [runs,setRuns]=useState([]);
  const [ps1Text,setPs1Text]=useState('A radio operator in a remote mountain station receives a distress signal just before midnight. The signal repeats a name she recognizes from a case that was closed ten years ago. As a storm cuts off the station, she searches old logs and discovers that the caller may be someone who was officially declared missing. She must decide whether to alert the authorities or investigate the signal herself.');
  const [ps1Title,setPs1Title]=useState('The Missing Signal');
  const [ps1Language,setPs1Language]=useState('English');
  const [ps2Profile,setPs2Profile]=useState('Listener enjoys short mystery and suspense audio stories, strong female leads, remote settings, and plot twists. Prefers episodes under 25 minutes and avoids graphic violence.');
  const [ps2Catalog,setPs2Catalog]=useState('ID: KFM-101 | Title: The Last Frequency | Genre: Mystery | Synopsis: A radio host investigates a strange late-night broadcast.\nID: KFM-102 | Title: Desert Files | Genre: Crime | Synopsis: A detective reopens an old missing-person case in Rajasthan.\nID: KFM-103 | Title: The Silent Orbit | Genre: Sci-Fi | Synopsis: An engineer receives a signal from an abandoned satellite.\nID: KFM-104 | Title: House of Shadows | Genre: Horror | Synopsis: A family encounters disturbing events in an old mansion.');
  const [topN,setTopN]=useState(5);
  const [audioLoading,setAudioLoading]=useState(false);
  const audioRef=useRef(null);

  useEffect(()=>{
    apiFetch('/api/episodes').then(r=>r.json())
      .then(data=>{setEpisodes(data.episodes||[]);if(data.episodes?.length>1){setPrevId(data.episodes[0].id);setNextId(data.episodes[1].id);}})
      .catch(e=>setErr(`Episode library unavailable: ${e.message}`)).finally(()=>setLoadingEpisodes(false));
  },[]);

  function recordRun(problem,input,data,started){
    const run={id:Date.now(),problem,input,status:'Success',duration:Math.max(1,Math.round((Date.now()-started)/1000))+'s',timestamp:new Date().toISOString(),output:data};
    setRuns(old=>[run,...old]);
  }
  async function requestAnalysis(endpoint,body,label,inputLabel){
    setBusy(true);setErr('');setOut(null);setSeries(null);const started=Date.now();
    try{
      const r=await apiFetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await r.json();setOut(data);recordRun(label,inputLabel,data,started);
    }catch(e){setErr(`Request failed: ${e.message}`);}
    finally{setBusy(false);}
  }
  async function runPS1(){
    if(ps1Text.trim().length<20){setErr('Transcript must contain at least 20 characters.');return;}
    await requestAnalysis('/api/ps1/tag',{text:ps1Text,title:ps1Title,language:ps1Language},'PS1 · Content tagging',ps1Title||'Transcript');
  }
  async function runPS2(){
    if(ps2Profile.trim().length<5||ps2Catalog.trim().length<10){setErr('Please provide a listener profile and a catalog.');return;}
    await requestAnalysis('/api/ps2/recommend',{user_profile:ps2Profile,catalog:ps2Catalog,top_n:Number(topN)},'PS2 · Recommendations','Listener profile + catalog');
  }
  async function compareDataset(){
    if(!prevId||!nextId||prevId===nextId){setErr('Choose two different episodes.');return;}
    await requestAnalysis('/api/analyze-episodes',{show_name:show,previous_episode_id:prevId,next_episode_id:nextId},'PS3 · Continuity','Dataset episode pair');
  }
  async function compareManual(){
    await requestAnalysis('/api/analyze',{show_name:show,previous_episode:a,next_episode:b},'PS3 · Continuity','Manual episode pair');
  }
  async function analyzeSeries(){
    setBusy(true);setErr('');setOut(null);setSeries(null);const started=Date.now();
    try{const r=await apiFetch('/api/analyze-series');const data=await r.json();setSeries(data);recordRun('PS3 · Full series scan','Episode library',data,started);}
    catch(e){setErr(`Series scan failed: ${e.message}`);}finally{setBusy(false);}
  }
  async function playVoicePreview(problem){
    if(audioRef.current){audioRef.current.pause();audioRef.current=null;}
    setErr('');setAudioLoading(true);
    try{
      const text=`${problem.id}: ${problem.title}. ${problem.desc}`.slice(0,200);
      const r=await apiFetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,voice:'autumn'})});
      const url=URL.createObjectURL(await r.blob());const audio=new Audio(url);audioRef.current=audio;
      audio.onended=()=>{URL.revokeObjectURL(url);if(audioRef.current===audio)audioRef.current=null;};
      await audio.play();
    }catch(e){setErr(`Groq voice preview failed: ${e.message}`);}finally{setAudioLoading(false);}
  }
  const nav=[['home','⌂','Home'],['problems','▦','Problems'],['results','▥','Results'],['docs','▤','Docs']];
  const problems=[
    {id:'PS1',title:'Content Understanding & Tagging',desc:'Analyze transcript content and generate metadata.',icon:'♫'},
    {id:'PS2',title:'Personalized Recommendation',desc:'Recommend catalog items using listener preferences.',icon:'◉'},
    {id:'PS3',title:'StoryBridge — Microdrama Episode Continuity',desc:'Review story continuity across episode pairs.',icon:'▣'}
  ];
  const activeRun=activeProblem==='PS1'?runPS1:activeProblem==='PS2'?runPS2:compareManual;

  return <div className="app-shell">
    <header className="topbar">
      <button className="brand" onClick={()=>setView('home')} aria-label="KukuFM home"><span className="brand-mark">✣</span><span>Kuku<span>FM</span></span><small>ASSIGNMENT</small></button>
      <nav className="topnav">{nav.map(([id,icon,label])=><button key={id} className={view===id?'nav-active':''} onClick={()=>setView(id)}><span>{icon}</span>{label}</button>)}</nav>
      <div className="top-actions"><a className="github-icon" href={repo} target="_blank" rel="noreferrer" aria-label="GitHub repository">◉</a><a className="deploy-btn" href="https://kukufm-assignment-frontend-kwao.onrender.com" target="_blank" rel="noreferrer">↗ Live app</a><span className="profile-dot">K</span></div>
    </header>
    <main className="dashboard">
      {(view==='home'||view==='problems')&&<>
        <section className="hero-banner"><div className="hero-copy"><small className="eyebrow">KUKUFM ASSIGNMENT</small><h1>AI-Powered Audio<br/>Intelligence Suite</h1><p>Three problem statements. Analyze content, recommend stories, and review episode continuity.</p><div className="hero-tags"><span>Audio AI</span><span>NLP</span><span>Recommendation</span></div></div><div className="hero-art"><div className="soundwave">{Array.from({length:25},(_,i)=><i key={i} style={{height:(14+Math.abs(Math.sin(i*.73))*75)+'px'}}/>)}</div></div></section>
        <div className="section-title"><div><h2>Problem Statements</h2><span className="title-underline"/></div><div className="filters"><button className={activeProblem==='ALL'?'selected':''} onClick={()=>setActiveProblem('ALL')}>All (3)</button>{['PS1','PS2','PS3'].map(x=><button key={x} className={activeProblem===x?'selected':''} onClick={()=>setActiveProblem(x)}>{x}</button>)}</div></div>
        <section className="problem-cards">{problems.filter(p=>activeProblem==='ALL'||p.id===activeProblem).map(p=><article className="problem-card" key={p.id}><div className={'card-art '+p.id.toLowerCase()}><span>{p.icon}</span></div><div className="card-main"><span className="problem-badge">{p.id}</span><h3>{p.title}</h3><p>{p.desc}</p></div><div className="fake-player"><button aria-label={'Play '+p.id+' voice preview'} disabled={audioLoading} onClick={()=>playVoicePreview(p)}>{audioLoading?'…':'▶'}</button><div className="waveform">{Array.from({length:42},(_,i)=><i key={i} style={{height:(5+Math.abs(Math.sin(i*1.3))*24)+'px'}}/>)}</div><small>Groq voice</small></div><div className="card-actions"><button className="view-details" onClick={()=>{setActiveProblem(p.id);setView('problems')}}>Open workspace ›</button><button className="run-btn" onClick={()=>{setActiveProblem(p.id);setView('problems')}}>Run {p.id} →</button></div></article>)}</section>
        <section className="lower-grid"><div className="recent-panel"><div className="panel-heading"><h3>Recent Runs</h3><button onClick={()=>setView('results')}>View all ›</button></div>{runs.length?<div className="table-wrap"><table><thead><tr><th>Problem</th><th>Input</th><th>Status</th><th>Time</th></tr></thead><tbody>{runs.slice(0,5).map(r=><tr key={r.id}><td>{r.problem}</td><td>{r.input}</td><td><span className="success-pill">✓ {r.status}</span></td><td>{r.duration}</td></tr>)}</tbody></table></div>:<div className="empty-runs"><b>No runs yet</b><p>Run any PS to create downloadable output history.</p></div>}</div><div className="status-panel"><h3>Project links</h3><a className="status-row" href={repo} target="_blank" rel="noreferrer"><b>GitHub repository</b> ↗</a><a className="status-row" href="https://kukufm-assignment-frontend-kwao.onrender.com" target="_blank" rel="noreferrer"><b>Frontend (Render)</b> ↗</a><a className="status-row" href="https://kukufm-assignment-api.onrender.com" target="_blank" rel="noreferrer"><b>Backend API</b> ↗</a></div></section>
      </>}
      {view==='problems'&&<section className="workspace" id="problem-workspace">
        <div className="workspace-header"><div><small>{activeProblem} WORKSPACE</small><h2>{problems.find(p=>p.id===activeProblem)?.title}</h2><p>Run the selected problem, inspect the complete response, and download its output.</p></div><button className="outline-btn" onClick={()=>setView('home')}>← Dashboard</button></div>
        <div className="mode-tabs">{['PS1','PS2','PS3'].map(id=><button key={id} className={activeProblem===id?'active':''} onClick={()=>{setActiveProblem(id);setOut(null);setSeries(null);setErr('')}}>{id}</button>)}</div>
        {activeProblem==='PS1'&&<div className="form-panel"><h3>Transcript metadata extraction</h3><label>Episode title<input value={ps1Title} onChange={e=>setPs1Title(e.target.value)}/></label><label>Language hint<input value={ps1Language} onChange={e=>setPs1Language(e.target.value)}/></label><label>Transcript (20–30,000 characters)<textarea rows="9" value={ps1Text} onChange={e=>setPs1Text(e.target.value)}/></label><button className="run-btn" disabled={busy} onClick={runPS1}>{busy?'Analyzing…':'Analyze PS1 →'}</button></div>}
        {activeProblem==='PS2'&&<div className="form-panel"><h3>Listener profile + catalog</h3><label>Listener profile<textarea rows="4" value={ps2Profile} onChange={e=>setPs2Profile(e.target.value)}/></label><label>Catalog (paste catalog entries)<textarea rows="8" value={ps2Catalog} onChange={e=>setPs2Catalog(e.target.value)}/></label><label>Number of recommendations<select value={topN} onChange={e=>setTopN(e.target.value)}>{[1,3,5,7,10].map(n=><option key={n} value={n}>{n}</option>)}</select></label><button className="run-btn" disabled={busy} onClick={runPS2}>{busy?'Analyzing…':'Analyze PS2 →'}</button></div>}
        {activeProblem==='PS3'&&<><div className="mode-tabs"><button className={mode==='dataset'?'active':''} onClick={()=>setMode('dataset')}>Episode library</button><button className={mode==='manual'?'active':''} onClick={()=>setMode('manual')}>Paste text manually</button></div>{mode==='dataset'?<div className="form-panel"><div className="dataset-head"><div><h3>Episode library</h3><p>{loadingEpisodes?'Loading episode files…':episodes.length+' episodes available'}</p></div><button className="outline-btn" disabled={busy||loadingEpisodes||episodes.length<2} onClick={analyzeSeries}>Scan entire series</button></div><label>Show / project name<input value={show} onChange={e=>setShow(e.target.value)}/></label><div className="grid"><label>Previous episode<select value={prevId} onChange={e=>setPrevId(e.target.value)}>{episodes.map(ep=><option key={ep.id} value={ep.id}>{ep.name||ep.id}</option>)}</select></label><label>Next episode<select value={nextId} onChange={e=>setNextId(e.target.value)}>{episodes.map(ep=><option key={ep.id} value={ep.id}>{ep.name||ep.id}</option>)}</select></label></div><button className="run-btn" disabled={busy||loadingEpisodes||episodes.length<2} onClick={compareDataset}>Compare selected episodes →</button></div>:<div className="form-panel"><label>Show / project name<input value={show} onChange={e=>setShow(e.target.value)}/></label><div className="grid"><label>Previous episode<textarea rows="7" value={a} onChange={e=>setA(e.target.value)}/></label><label>Next episode<textarea rows="7" value={b} onChange={e=>setB(e.target.value)}/></label></div><button className="run-btn" disabled={busy} onClick={compareManual}>Run continuity review →</button></div>}</>}
        {err&&<p className="error">{err}</p>}{out&&<ResultPanel out={out} problem={activeProblem}/>}
        {series&&<div className="result-card"><div className="panel-heading"><h3>Full series scan · {series.total_flags} flags</h3><button className="outline-btn" onClick={()=>downloadJson('PS3_series_scan.json',series)}>Download scan JSON</button></div><p>{displayValue(series.note, '')}</p>{(series.pairs||[]).map((pair,i)=><details key={i}><summary>{pair.previous} → {pair.next} ({pair.flags} flags)</summary>{(pair.findings||[]).map((f,j)=><article key={j}><b>{f.severity} · {f.title}</b><p style={{whiteSpace:'pre-wrap'}}>{displayValue(f.evidence)}</p></article>)}</details>)}</div>}
      </section>}
      {view==='results'&&<section className="content-page"><div className="panel-heading"><div><h1>Run History & Outputs</h1><p>Each successful run stores its full response in this browser session.</p></div><button className="run-btn" disabled={!runs.length} onClick={()=>downloadJson('KukuFM_all_runs.json',runs)}>Download all runs</button></div>{runs.length===0?<p>No runs yet. Run PS1, PS2, or PS3 first.</p>:runs.map((r,i)=><article className="result-card" key={r.id}><div className="panel-heading"><div><h3>{r.problem}</h3><small>{r.timestamp} · {r.duration} · {r.input}</small></div><button className="outline-btn" onClick={()=>downloadJson(`${r.problem.replace(/[^a-z0-9]+/gi,'_')}_output.json`,r.output)}>Download output JSON</button></div><details><summary>View raw response</summary><pre>{JSON.stringify(r.output,null,2)}</pre></details></article>)}</section>}
      {view==='docs'&&<section className="content-page"><h1>Documentation & Downloads</h1><p>Download an individual solution brief for each PS, or the combined three-PS solution document.</p><div className="problem-cards">{Object.entries(docs).map(([id,d])=><article className="problem-card" key={id}><span className="problem-badge">{id}</span><h3>{d.title}</h3><p>{d.body}</p><button className="run-btn" onClick={()=>downloadFile(d.filename,`# ${d.title}\n\n${d.body}\n\nPrototype: https://kukufm-assignment-frontend-kwao.onrender.com\nBackend: https://kukufm-assignment-api.onrender.com\nRepository: ${repo}\n`,'text/markdown')}>Download {id} solution (.md)</button></article>)}</div><button className="run-btn" onClick={()=>downloadFile('KukuFM_Combined_Solution_Document.md',Object.values(docs).map(d=>`# ${d.title}\n\n${d.body}\n`).join('\n'),'text/markdown')}>Download combined solution document</button><p className="small-note">Generated downloads are Markdown documents. The PDF solution document is also available in the assignment submission materials.</p></section>}
      <footer className="footer"><span>KukuFM Assignment</span><span>Audio intelligence · Human review stays in the loop</span></footer>
    </main>
  </div>;
}
function ResultPanel({out,problem}){
  const downloadName=`${problem||'PS'}_output.json`;
  return <div className="result-card"><div className="panel-heading"><h3>Analysis output</h3><div className="action-row"><button className="outline-btn" onClick={()=>downloadJson(downloadName,out)}>Download JSON</button><button className="outline-btn" onClick={()=>navigator.clipboard?.writeText(JSON.stringify(out,null,2))}>Copy JSON</button></div></div>
    {problem==='PS1'&&<><div className="summary-grid"><div><small>Title</small><p>{displayValue(out.title)}</p></div><div><small>Language</small><p>{displayValue(out.language)}</p></div><div><small>Summary</small><p>{displayValue(out.summary)}</p></div><div><small>Genre</small><p>{Array.isArray(out.genre)?out.genre.join(', '):out.genre||'—'}</p></div></div>{['tags','themes','emotions','content_warnings'].map(k=><section key={k}><h4>{k.replace('_',' ')}</h4><p>{displayValue(out[k], 'None returned')}</p></section>)}{out.characters&&<section><h4>Characters</h4><pre>{JSON.stringify(out.characters,null,2)}</pre></section>}{out.evidence_notes&&<section><h4>Evidence notes</h4><pre>{JSON.stringify(out.evidence_notes,null,2)}</pre></section>}</>}
    {problem==='PS2'&&<><h4>Recommendations</h4>{(out.recommendations||[]).map((rec,i)=><article key={i}><div className="panel-heading"><b>{displayValue(rec.rank, String(i+1))}. {displayValue(rec.title||rec.id_or_catalog_reference, 'Recommendation')}</b><span className="success-pill">{rec.match_score??'—'} / 100</span></div><p>{displayValue(rec.why_this_fits, '')}</p><p>{displayValue(rec.reasons, '')}</p><small>Catalog reference: {rec.id_or_catalog_reference||'Not supplied'}</small></article>)}<section><h4>Profile signals</h4><p>{displayValue(out.profile_signals)}</p><p>{displayValue(out.diversity_note, '')}</p></section><button className="outline-btn" onClick={()=>{const rows=[['rank','title','catalog_reference','score','why_this_fits'],...(out.recommendations||[]).map(x=>[x.rank,x.title,x.id_or_catalog_reference,x.match_score,x.why_this_fits])];downloadFile('PS2_recommendations.csv',rows.map(row=>row.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\n'),'text/csv')}}>Download recommendations CSV</button></>}
    {problem==='PS3'&&<><div className="summary-grid"><div><small>Flags</small><p>{out.summary?.flags??out.findings?.length??0}</p></div><div><small>Recurring names</small><p>{displayValue(out.summary?.recurring_names, 'None detected')}</p></div><div><small>New names</small><p>{displayValue(out.summary?.new_names, 'None detected')}</p></div></div>{(out.findings||[]).map((f,i)=><article key={i}><small>{f.severity} · {f.category}</small><h4>{displayValue(f.title, 'Finding')}</h4><p style={{whiteSpace:'pre-wrap'}}>{displayValue(f.evidence)}</p><p>{displayValue(f.recommendation, '')}</p></article>)}{out.review_checklist&&<section><h4>Human review checklist</h4>{out.review_checklist.map((x,i)=><label className="check" key={i}><input type="checkbox"/>{x}</label>)}</section>}{out.limitations&&<details><summary>Limitations</summary><ul>{out.limitations.map((x,i)=><li key={i}>{x}</li>)}</ul></details>}</>}
    {!['PS1','PS2','PS3'].includes(problem)&&<pre>{JSON.stringify(out,null,2)}</pre>}
  </div>;
}
createRoot(document.getElementById('root')).render(<AppErrorBoundary><App/></AppErrorBoundary>);
