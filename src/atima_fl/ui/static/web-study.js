"use strict";

// Share explicit summaries, not an entire workspace. Imported claims are descriptive.
const ATIMAStudy=(()=>{
  const finite=v=>typeof v==="number"&&Number.isFinite(v);
  const object=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
  const token=v=>typeof v==="string"&&v.length<=120&&/^[A-Za-z0-9][A-Za-z0-9_. -]*$/.test(v)&&!/^(gh[pousr]_|github_pat_|sk-|AKIA)/i.test(v);
  const fields=["dataset","model","partition","attack","training_method","evaluation_scope","aggregation"];
  const nums=["seed","clients","rounds","local_epochs","batch_size","learning_rate","num_classes","attack_start","attack_end"];
  const measures=["accuracy","macro_f1","weighted_f1","balanced_accuracy","mcc","loss"];
  const hashes=["train","validation","test","feature_schema.json","label_mapping.json","preprocessor.json"];
  function safeParams(value){
    if(!object(value))return {};
    return Object.fromEntries(Object.entries(value).filter(([k,v])=>token(k)&&(finite(v)||typeof v==="boolean"||token(v))).slice(0,64));
  }
  function observation(run,index){
    const c=run.config||{},test=run.metrics?.test||{},identity=run.dataset_identity||{};
    const config=Object.fromEntries(fields.filter(k=>token(c[k])).map(k=>[k,c[k]]));
    for(const key of nums)if(finite(c[key]))config[key]=c[key];
    for(const key of ["attack_params","partition_params","model_params"])config[key]=safeParams(c[key]);
    config.malicious_count=Array.isArray(c.malicious_clients)?c.malicious_clients.length:null;
    const metrics=Object.fromEntries(measures.filter(k=>finite(test[k])).map(k=>[k,test[k]]));
    if(Number.isSafeInteger(test.samples)&&test.samples>=0)metrics.samples=test.samples;
    return {id:"Run-"+(index+1),status:token(run.status)?run.status:"unknown",round:Number.isSafeInteger(run.round)?run.round:null,
      task:token(identity.task)?identity.task:null,config,metrics,
      dataset_hashes:Object.fromEntries(hashes.filter(k=>/^[a-f0-9]{64}$/i.test(identity.hashes?.[k]||"")).map(k=>[k,identity.hashes[k]]))};
  }
  function create(title,runs){
    if(!token(title))throw Error("Use a short study title without paths or special characters");
    if(!Array.isArray(runs)||!runs.length||runs.length>1000)throw Error("Choose 1–1000 runs");
    return {schema:"atima.study.summary",version:1,title,observations:runs.map(observation)};
  }
  function parse(value){
    if(!object(value)||value.schema!=="atima.study.summary"||value.version!==1||!token(value.title)||!Array.isArray(value.observations)||!value.observations.length||value.observations.length>1000)throw Error("Unsupported study summary");
    const ids=new Set();
    const observations=value.observations.map(r=>{
      if(!object(r)||!/^Run-[1-9]\d{0,3}$/.test(r.id)||ids.has(r.id)||!object(r.config)||!object(r.metrics))throw Error("Invalid or duplicate study observation");
      ids.add(r.id);
      // Rebuild from the allowlist rather than trusting fields or importing raw payloads.
      const cfg=r.config,run={config:{...cfg,malicious_clients:[]},metrics:{test:r.metrics},dataset_identity:{task:r.task,hashes:r.dataset_hashes},status:r.status,round:r.round};
      const clean=observation(run,ids.size);
      clean.id=r.id;
      clean.config.malicious_count=Number.isSafeInteger(cfg.malicious_count)&&cfg.malicious_count>=0&&cfg.malicious_count<=10000?cfg.malicious_count:null;
      for(const [key,v] of Object.entries(clean.metrics)){
        if(key==="samples")continue;
        if(key==="mcc"?v< -1||v>1:key==="loss"?v<0:v<0||v>1)throw Error("Study metric outside valid range: "+key);
      }
      return clean;
    });
    return {schema:value.schema,version:1,title:value.title,observations};
  }
  return Object.freeze({create,parse,measures});
})();
function setupStudyExchange(){
  const panel=$("web-study");if(!panel)return;
  const studies=new Map(),out=$("web-study-output"),status=$("web-study-status"),preview=$("web-study-preview"),metric=$("web-study-metric"),filter=$("web-study-filter");
  let pending=null,page=0;
  function render(){
    out.replaceChildren();
    const query=filter.value.trim().toLowerCase(),key=metric.value;
    const rows=[...studies.values()].flatMap(study=>study.observations.map(r=>({title:study.title,r}))).filter(({title,r})=>JSON.stringify([title,r.config,r.task]).toLowerCase().includes(query));
    const size=50,last=Math.max(0,Math.ceil(rows.length/size)-1);page=Math.min(page,last);
    out.append(node("p",studies.size+" studies · "+rows.length+" matching observations. No cross-study pooling or paired-effect claims."));
    const tableRows=rows.slice(page*size,(page+1)*size).map(({title,r})=>[title,r.id,r.task??"—",r.config.attack??"—",r.config.partition??"—",r.config.model??"—",r.config.seed??"—",r.config.malicious_count??"—",score(r.metrics[key],key!=="loss"&&key!=="mcc"),r.metrics.samples??"—"]);
    out.append(dataTable(["Study","Run","Task","Attack","Partition","Model","Seed","Malicious clients",key,"Samples"],tableRows));
    const prev=node("button","Previous","secondary"),next=node("button","Next","secondary");prev.type=next.type="button";prev.disabled=page===0;next.disabled=page>=last;
    prev.addEventListener("click",()=>{page--;render();});next.addEventListener("click",()=>{page++;render();});
    out.append(prev,node("span"," Page "+(page+1)+" / "+(last+1)+" "),next);
    const details=node("details");details.append(node("summary","Recorded conditions and dataset fingerprints (selected page)"),node("pre",JSON.stringify(rows.slice(page*size,(page+1)*size),null,2)));out.append(details);
  }
  for(const name of ATIMAStudy.measures){const option=node("option",name);option.value=name;metric.append(option);}metric.value="macro_f1";
  metric.addEventListener("change",render);filter.addEventListener("input",()=>{page=0;render();});
  $("web-study-prepare").addEventListener("click",()=>{
    pending=null;preview.textContent="";$("web-study-download").disabled=true;
    try{pending=ATIMAStudy.parse(ATIMAStudy.create($("web-study-title").value,availableResults));preview.textContent=JSON.stringify(pending,null,2);$("web-study-download").disabled=false;status.textContent="Review the exact summary before downloading. No original run names or paths are included.";}
    catch(e){status.textContent=e.message;}
  });
  $("web-study-download").addEventListener("click",()=>{
    if(!pending)return;
    const blob=new Blob([JSON.stringify(pending,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=node("a");link.href=url;link.download="atima-study-summary.json";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $("web-study-import").addEventListener("change",async()=>{
    const files=[...$("web-study-import").files],errors=[];
    for(const file of files){
      try{
        if(file.size>8*1024*1024)throw Error("Study exceeds 8 MiB");
        const parsed=ATIMAStudy.parse(JSON.parse(await file.text())),signature=JSON.stringify(parsed);
        if(studies.has(signature))continue;
        if(studies.size>=10)throw Error("Maximum 10 studies");
        studies.set(signature,parsed);
      }catch(e){errors.push(file.name+": "+e.message);}
    }
    $("web-study-import").value="";page=0;render();status.textContent=errors.length?errors.join(" · "):"Studies read on this device. No upload.";
  });
  $("web-study-clear").addEventListener("click",()=>{studies.clear();pending=null;preview.textContent="";$("web-study-download").disabled=true;page=0;render();status.textContent="Study summaries cleared from this tab.";});
  render();
}
