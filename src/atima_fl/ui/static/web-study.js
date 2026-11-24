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
  async function createWithEvidence(title,runs,pairCheck=()=>false){
    const doc=create(title,runs);doc.version=2;
    for(let i=0;i<runs.length;i++){
      const run=runs[i],r=doc.observations[i],test=run.metrics?.test;
      const order=run.classes,source=run.seed_condition?.key;
      if(!source||typeof source!=="string"||!Array.isArray(order)||order.length<2||!order.every(name=>Number.isSafeInteger(test?.per_class?.[name]?.support)&&test.per_class[name].support>=0))continue;
      const support=order.map(name=>test.per_class[name].support);
      if(support.reduce((a,b)=>a+b,0)!==test.samples||!globalThis.crypto?.subtle)continue;
      const bytes=new TextEncoder().encode(JSON.stringify([source,order,support,test.samples]));
      const digest=await crypto.subtle.digest("SHA-256",bytes);
      r.condition_sha256=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
    }
    const byId=new Map(runs.map(run=>[run.id,run]));
    const indices=new Map(runs.map((run,i)=>[run.id,i]));
    if(byId.size===runs.length)for(let i=0;i<runs.length;i++){
      const run=runs[i],cleanIndex=indices.get(run.baseline_id);
      if(cleanIndex===undefined||!pairCheck(run,byId))continue;
      const attack=doc.observations[i],clean=doc.observations[cleanIndex];
      if(declaredPair(attack,clean))attack.matched_clean_id=clean.id;
    }
    return doc;
  }
  function parse(value){
    if(!object(value)||value.schema!=="atima.study.summary"||![1,2].includes(value.version)||!token(value.title)||!Array.isArray(value.observations)||!value.observations.length||value.observations.length>1000)throw Error("Unsupported study summary");
    const ids=new Set();
    const observations=value.observations.map(r=>{
      if(!object(r)||!/^Run-[1-9]\d{0,3}$/.test(r.id)||ids.has(r.id)||!object(r.config)||!object(r.metrics))throw Error("Invalid or duplicate study observation");
      ids.add(r.id);
      // Rebuild from the allowlist rather than trusting fields or importing raw payloads.
      const cfg=r.config,run={config:{...cfg,malicious_clients:[]},metrics:{test:r.metrics},dataset_identity:{task:r.task,hashes:r.dataset_hashes},status:r.status,round:r.round};
      const clean=observation(run,ids.size);
      clean.id=r.id;
      if(value.version===2&&typeof r.condition_sha256==="string"&&/^[a-f0-9]{64}$/.test(r.condition_sha256))clean.condition_sha256=r.condition_sha256;
      if(value.version===2&&r.matched_clean_id!==undefined){
        if(typeof r.matched_clean_id!=="string"||!/^Run-[1-9]\d{0,3}$/.test(r.matched_clean_id))throw Error("Invalid declared baseline reference");
        clean.matched_clean_id=r.matched_clean_id;
      }
      clean.config.malicious_count=Number.isSafeInteger(cfg.malicious_count)&&cfg.malicious_count>=0&&cfg.malicious_count<=10000?cfg.malicious_count:null;
      for(const [key,v] of Object.entries(clean.metrics)){
        if(key==="samples")continue;
        if(key==="mcc"?v< -1||v>1:key==="loss"?v<0:v<0||v>1)throw Error("Study metric outside valid range: "+key);
      }
      return clean;
    });
    const byId=new Map(observations.map(r=>[r.id,r]));
    for(const r of observations)if(r.matched_clean_id&&!declaredPair(r,byId.get(r.matched_clean_id)))throw Error("Incompatible declared baseline reference");
    return {schema:value.schema,version:value.version,title:value.title,observations};
  }
  // Comparability is a statement about supplied summary metadata, never proof of independence.
  const canonical=v=>Array.isArray(v)?v.map(canonical):object(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
  const signature=v=>JSON.stringify(canonical(v));
  function declaredPair(attack,clean){
    if(!attack||!clean||attack.status!=="complete"||clean.status!=="complete"||attack.config.attack==="none"||clean.config.attack!=="none"||clean.config.malicious_count!==0||
      !attack.condition_sha256||!clean.condition_sha256||!Number.isSafeInteger(attack.config.seed)||attack.config.seed!==clean.config.seed||!Number.isSafeInteger(attack.round)||attack.round<=0||attack.round!==clean.round||
      !attack.task||attack.task!==clean.task||!Number.isSafeInteger(attack.metrics.samples)||attack.metrics.samples<=0||attack.metrics.samples!==clean.metrics.samples||hashes.some(k=>!attack.dataset_hashes[k]||attack.dataset_hashes[k]!==clean.dataset_hashes[k]))return false;
    const comparable=c=>Object.fromEntries(Object.entries(c).filter(([k])=>!["attack","attack_params","malicious_count","attack_start","attack_end"].includes(k)));
    return signature(comparable(attack.config))===signature(comparable(clean.config));
  }
  function comparisonGroups(studies,metric){
    if(!measures.includes(metric))throw Error("Unknown study metric");
    const groups=new Map(),excluded=[];
    for(const [studyId,study] of studies.entries()){
      const byId=new Map(study.observations.map(r=>[r.id,r])),cleanCounts=new Map();
      const cleanKey=r=>signature([r.condition_sha256,r.config.seed]);
      for(const r of study.observations)if(r.status==="complete"&&r.config.attack==="none"&&r.condition_sha256){
        const k=cleanKey(r);cleanCounts.set(k,(cleanCounts.get(k)||0)+1);
      }
      for(const r of study.observations){
        const c=r.config;
        const missing=hashes.filter(k=>!r.dataset_hashes[k]);
        if(r.status!=="complete"||!finite(r.metrics[metric])||missing.length||!r.task||!Number.isSafeInteger(r.metrics.samples)||r.metrics.samples<=0||!Number.isSafeInteger(r.round)||r.round<=0||
          fields.some(k=>!token(c[k]))||nums.some(k=>!finite(c[k]))||!Number.isSafeInteger(c.seed)||c.seed<0||!Number.isSafeInteger(c.malicious_count)||c.malicious_count<0){
          excluded.push({study:study.title,id:r.id});continue;
        }
        const {seed,...condition}=c;
        const key=signature({condition,task:r.task,hashes:r.dataset_hashes,round:r.round,samples:r.metrics.samples,condition_sha256:r.condition_sha256??null});
        if(!groups.has(key))groups.set(key,{condition,task:r.task,round:r.round,samples:r.metrics.samples,identity:r.condition_sha256?"Declared full-condition fingerprint match":"Reduced-summary match only",studies:new Map()});
        const group=groups.get(key);
        if(!group.studies.has(studyId))group.studies.set(studyId,{title:study.title,seeds:new Map()});
        const seeds=group.studies.get(studyId).seeds;
        if(!seeds.has(seed))seeds.set(seed,[]);
        const clean=byId.get(r.matched_clean_id);
        const paired=declaredPair(r,clean)&&cleanCounts.get(cleanKey(clean))===1&&finite(clean.metrics[metric]);
        seeds.get(seed).push({value:r.metrics[metric],clean:paired?clean.metrics[metric]:null,baseline:paired?clean.condition_sha256:null});
      }
    }
    const matches=[];
    for(const group of groups.values()){
      if(group.studies.size<2)continue;
      const rows=[...group.studies.values()].map(s=>{
        const valid=[...s.seeds.values()].filter(v=>v.length===1).map(v=>v[0]);
        const paired=ATIMAAnalysis.pairedStats(valid.map(v=>[v.clean,v.value]));
        return {title:s.title,stats:ATIMAAnalysis.stats(valid.map(v=>v.value)),paired,
          baselineConditions:[...new Set(valid.map(v=>v.baseline).filter(Boolean))],
          duplicateSeeds:[...s.seeds.values()].filter(v=>v.length>1).length};
      });
      matches.push({...group,rows,baselineConditions:[...new Set(rows.flatMap(r=>r.baselineConditions))]});
    }
    return {matches,excluded};
  }
  return Object.freeze({create,createWithEvidence,parse,measures,comparisonGroups});
})();
function setupStudyExchange(){
  const panel=$("web-study");if(!panel)return;
  const studies=new Map(),out=$("web-study-output"),status=$("web-study-status"),preview=$("web-study-preview"),metric=$("web-study-metric"),filter=$("web-study-filter");
  let pending=null,page=0,revision=0;
  function render(){
    out.replaceChildren();
    const query=filter.value.trim().toLowerCase(),key=metric.value;
    const rows=[...studies.values()].flatMap(study=>study.observations.map(r=>({title:study.title,r}))).filter(({title,r})=>JSON.stringify([title,r.config,r.task]).toLowerCase().includes(query));
    const size=50,last=Math.max(0,Math.ceil(rows.length/size)-1);page=Math.min(page,last);
    out.append(node("p",studies.size+" studies · "+rows.length+" matching observations. No cross-study pooling; reported clean/attack pairs stay within each study."));
    const tableRows=rows.slice(page*size,(page+1)*size).map(({title,r})=>[title,r.id,r.task??"—",r.config.attack??"—",r.config.partition??"—",r.config.model??"—",r.config.seed??"—",r.config.malicious_count??"—",score(r.metrics[key],key!=="loss"&&key!=="mcc"),r.metrics.samples??"—"]);
    out.append(dataTable(["Study","Run","Task","Attack","Partition","Model","Seed","Malicious clients",key,"Samples"],tableRows));
    const prev=node("button","Previous","secondary"),next=node("button","Next","secondary");prev.type=next.type="button";prev.disabled=page===0;next.disabled=page>=last;
    prev.addEventListener("click",()=>{page--;render();});next.addEventListener("click",()=>{page++;render();});
    out.append(prev,node("span"," Page "+(page+1)+" / "+(last+1)+" "),next);
    const audit=node("details");audit.append(node("summary","Cross-study condition audit and separate seed statistics"));
    const comparison=ATIMAStudy.comparisonGroups([...studies.values()],key);
    audit.append(node("p",comparison.matches.length+" matching recorded conditions across studies; "+comparison.excluded.length+" observations lack complete comparison metadata."));
    audit.append(node("p","Matching summary fields do not verify full configuration, software, sample identity or study independence. Means and sample SD are computed separately within each study. Reported within-study pairs use only compatible declared clean references. No pooled estimates, causal effects or significance tests."));
    for(const group of comparison.matches.slice(0,50)){
      const detail=node("details"),condition=group.condition;
      detail.append(node("summary",[condition.attack,condition.model,condition.partition,group.task,"round "+group.round].join(" · ")));
      detail.append(node("p",group.identity));
      detail.append(dataTable(["Study","Distinct seeds","Mean","Sample SD","Duplicate seeds excluded"],group.rows.map(r=>[r.title,r.stats.n,score(r.stats.mean,key!=="mcc"&&key!=="loss"),score(r.stats.sd,key!=="mcc"&&key!=="loss"),r.duplicateSeeds])));
      if(condition.attack!=="none"){
        const percent=key!=="mcc"&&key!=="loss";
        detail.append(node("p",group.baselineConditions.length>1?"Different declared clean-condition fingerprints: do not interpret differences between studies as controlled effects.":"Within-study reported clean/attack pairs only; missing or ambiguous pairs are not estimated."));
        detail.append(dataTable(["Study","Matched seeds","Clean mean","Attack mean","Attack − clean","SD of paired delta"],group.rows.map(r=>[r.title,r.paired.delta.n,score(r.paired.clean.mean,percent),score(r.paired.attack.mean,percent),deltaScore(r.paired.attack.mean,r.paired.clean.mean,percent),numeric(r.paired.delta.sd)?percent?(100*r.paired.delta.sd).toFixed(2)+" pp":score(r.paired.delta.sd,false):"—"])));
      }
      const metadata=node("details");metadata.append(node("summary","Recorded condition"),node("pre",JSON.stringify(condition,null,2)));detail.append(metadata);audit.append(detail);
    }
    if(comparison.matches.length>50)audit.append(node("p","Showing first 50 matching conditions."));
    out.append(audit);

    const details=node("details");details.append(node("summary","Recorded conditions and dataset fingerprints (selected page)"),node("pre",JSON.stringify(rows.slice(page*size,(page+1)*size),null,2)));out.append(details);
  }
  for(const name of ATIMAStudy.measures){const option=node("option",name);option.value=name;metric.append(option);}metric.value="macro_f1";
  metric.addEventListener("change",render);filter.addEventListener("input",()=>{page=0;render();});
  $("web-study-prepare").addEventListener("click",async()=>{
    const ticket=++revision;
    pending=null;preview.textContent="";$("web-study-download").disabled=true;
    try{const prepared=ATIMAStudy.parse(await ATIMAStudy.createWithEvidence($("web-study-title").value,availableResults,verifiedPair));if(ticket!==revision)return;pending=prepared;preview.textContent=JSON.stringify(pending,null,2);$("web-study-download").disabled=false;status.textContent="Review the exact summary before downloading. No original run names or paths are included.";}
    catch(e){status.textContent=e.message;}
  });
  $("web-study-download").addEventListener("click",()=>{
    if(!pending)return;
    const blob=new Blob([JSON.stringify(pending,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=node("a");link.href=url;link.download="atima-study-summary.json";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $("web-study-import").addEventListener("change",async()=>{
    const files=[...$("web-study-import").files],errors=[],ticket=revision;
    for(const file of files){
      try{
        if(file.size>8*1024*1024)throw Error("Study exceeds 8 MiB");
        const parsed=ATIMAStudy.parse(JSON.parse(await file.text())),signature=JSON.stringify(parsed);
        if(ticket!==revision)return;
        if(studies.has(signature))continue;
        if(studies.size>=10)throw Error("Maximum 10 studies");
        studies.set(signature,parsed);
      }catch(e){errors.push(file.name+": "+e.message);}
    }
    $("web-study-import").value="";page=0;render();status.textContent=errors.length?errors.join(" · "):"Studies read on this device. No upload.";
  });
  $("web-study-clear").addEventListener("click",()=>{revision++;studies.clear();pending=null;preview.textContent="";$("web-study-download").disabled=true;page=0;render();status.textContent="Study summaries cleared from this tab.";});
  render();
}
