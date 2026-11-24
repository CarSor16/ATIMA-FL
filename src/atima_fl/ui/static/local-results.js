"use strict";

// Browser-only result adapter. File objects are read locally; no fetch, POST,
// cookie, network, server path, or filesystem write is used by this module.
const ATIMALocalResults=(()=>{
  const hashKeys=["train","validation","test","feature_schema.json","label_mapping.json","preprocessor.json"];
  const required=["attack","attack_params","malicious_clients","clients","servers","dataset","dataset_params","partition","partition_params","model","model_params","rounds","local_epochs","aggregation","aggregation_params","defenses","optimizer","optimizer_params","loss","loss_params","batch_size","learning_rate","attack_start","attack_end"];
  const ignored=new Set(["name","seed","dataset_root","output_root","paired_clean","plugin_directory"]);
  const object=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
  const finite=v=>typeof v==="number"&&Number.isFinite(v);
  const canonical=v=>Array.isArray(v)?v.map(canonical):object(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
  // Full canonical content is the equality key (no lossy hash or trusted imported key).
  const key=v=>JSON.stringify(canonical(v)).replace(/\|/g,"\\u007c");
  const classOrder=a=>Array.isArray(a)&&a.length>=2&&a.length<=100&&a.every(v=>typeof v==="string"&&v.length>0&&v.length<=200)&&new Set(a).size===a.length;
  function audited(m){
    const c=m.config,a=m.dataset_audit;
    if(m.status!=="complete"||!object(c)||required.some(k=>!Object.hasOwn(c,k))||!object(a)||!object(a.hashes)||!classOrder(a.classes)||typeof a.task!=="string"||!a.task||!object(c.dataset_params)||!object(c.attack_params)||!object(c.partition_params))return null;
    if(!Number.isInteger(c.seed)||c.seed<0||!Number.isInteger(c.clients)||c.clients<1||c.clients>10000||!Number.isInteger(c.rounds)||!Number.isInteger(m.last_valid_round)||m.last_valid_round<1||m.last_valid_round>c.rounds)return null;
    if(!Array.isArray(c.malicious_clients)||new Set(c.malicious_clients).size!==c.malicious_clients.length||c.malicious_clients.some(id=>!Number.isInteger(id)||id<0||id>=c.clients)||(c.attack!=="none"&&!c.malicious_clients.length))return null;
    if(c.dataset_params.task&&c.dataset_params.task!==a.task)return null;
    const keys=[...hashKeys,"assignment",...Array.from({length:c.clients},(_,i)=>"client_"+i)];
    if(keys.some(k=>typeof a.hashes[k]!=="string"||!a.hashes[k])||!object(m.source_identity)||!Object.keys(m.source_identity).length||!object(m.runtime)||!Object.keys(m.runtime).length)return null;
    return {config:Object.fromEntries(Object.entries(c).filter(([k])=>!ignored.has(k))),dataset_hashes:a.hashes,task:a.task,classes:a.classes,source:m.source_identity,runtime:m.runtime,attack_source:m.attack_source??null,round:m.last_valid_round};
  }
  function sensitivity(base,c){
    if(!base||c.attack==="none")return [];
    const axes=[];
    for(const group of ["attack_params","partition_params"])for(const [name,value] of Object.entries(c[group]))if(finite(value))axes.push([group+"."+name,value]);
    for(const field of ["model","partition","attack_start","attack_end"])axes.push([field,c[field]]);
    if([...c.malicious_clients].sort((a,b)=>a-b).every((id,i)=>id===i))axes.push(["malicious_count",c.malicious_clients.length]);
    if(axes.length>64)throw Error("Too many sensitivity axes in manifest");
    return axes.map(([axis,value])=>{
      const condition=JSON.parse(JSON.stringify(base)),cfg=condition.config;
      if(axis.includes(".")){const dot=axis.indexOf("."),group=axis.slice(0,dot),name=axis.slice(dot+1);delete cfg[group][name];}
      else if(axis==="malicious_count")delete cfg.malicious_clients;
      else {delete cfg[axis];if(["model","partition"].includes(axis))delete cfg[axis+"_params"];}
      const partition=axis==="partition"||axis.startsWith("partition_params.");
      if(partition)condition.dataset_hashes=Object.fromEntries(hashKeys.map(k=>[k,condition.dataset_hashes[k]]));
      return {axis,value,key:key([axis,condition]),descriptive:partition||axis==="model"};
    });
  }
  function historyRows(history){
    if(!Array.isArray(history)||history.length>200)throw Error("Invalid validation history");
    let previous=0;
    return history.map(r=>{
      if(!object(r)||!Number.isInteger(r.round)||r.round<=previous||r.round>1000)throw Error("Invalid validation round");
      previous=r.round;
      for(const name of ["accuracy","macro_f1","weighted_f1","balanced_accuracy","mcc","loss","seconds"]){
        if(!Object.hasOwn(r,name))continue;
        const v=r[name],valid=finite(v)&&(name==="mcc"?v>=-1&&v<=1:["loss","seconds"].includes(name)?v>=0:v>=0&&v<=1);
        if(!valid)throw Error("Invalid validation metric: "+name);
      }
      if(r.recall!==undefined&&(!Array.isArray(r.recall)||r.recall.length>100||r.recall.some(v=>!finite(v)||v<0||v>1)))throw Error("Invalid validation class recall");
      return r;
    });
  }
  function project(id,m,metrics={},history=[],updated=null){
    if(!object(m)||!object(m.config)||!object(metrics))throw Error("Invalid experiment manifest or metrics");
    const c=m.config,a=object(m.dataset_audit)?m.dataset_audit:{},base=audited(m);
    if(metrics.federated!==undefined){
      const rows=metrics.federated?.rounds;
      if(!object(metrics.federated)||(rows!==undefined&&(!Array.isArray(rows)||rows.length>200||rows.some(row=>!object(row)||!Number.isInteger(row.round)||row.round<1||row.round>1000))))throw Error("Invalid federated telemetry");
    }
    const test=metrics.test;
    if(test!==undefined){
      if(!object(test))throw Error("Invalid final test metrics");
      if(test.per_class!==undefined&&(!object(test.per_class)||Object.keys(test.per_class).length>100||Object.values(test.per_class).some(row=>!object(row))))throw Error("Invalid per-class metrics");
      if(test.samples!==undefined&&(!Number.isSafeInteger(test.samples)||test.samples<0))throw Error("Invalid test sample count");
      for(const row of Object.values(test.per_class||{})){
        if(row.support!==undefined&&(!Number.isSafeInteger(row.support)||row.support<0))throw Error("Invalid class support");
        for(const name of ["precision","recall","f1-score"])if(row[name]!==undefined&&(!finite(row[name])||row[name]<0||row[name]>1))throw Error("Invalid class metric: "+name);
      }
      if(test.confusion_matrix!==undefined&&(!Array.isArray(test.confusion_matrix)||test.confusion_matrix.length<2||test.confusion_matrix.length>100||test.confusion_matrix.some(row=>!Array.isArray(row)||row.length!==test.confusion_matrix.length||row.some(v=>!Number.isSafeInteger(v)||v<0)||!Number.isSafeInteger(row.reduce((s,v)=>s+v,0)))))throw Error("Invalid test confusion matrix");
      for(const name of ["accuracy","macro_f1","weighted_f1","balanced_accuracy","mcc","loss"]){
        if(!Object.hasOwn(test,name))continue;
        const v=test[name];
        if(!finite(v)||(name==="mcc"?v< -1||v>1:name==="loss"?v<0:v<0||v>1))throw Error("Invalid final metric: "+name);
      }
    }
    return {id,updated_at:updated,status:m.status||"unknown",round:m.last_valid_round??null,config:c,
      group:{family:c.attack==="none"?"Clean baseline":"Local experiments",attack:c.attack,distribution:c.partition==="iid"?"IID":c.partition==="dirichlet"?"Non-IID":"Unknown",partition_detail:c.partition==="dirichlet"?"Dirichlet alpha="+(c.partition_params?.alpha??"unknown"):c.partition,model:c.model,dataset:c.dataset,task:a.task,seed:c.seed},
      seed_condition:base?{key:key(base),reason:null}:{key:null,reason:"Incomplete audited local metadata"},
      sensitivity_conditions:sensitivity(base,c),metrics,classes:classOrder(a.classes)?a.classes:[],
      dataset_identity:{task:a.task??null,hashes:Object.fromEntries(hashKeys.map(k=>[k,a.hashes?.[k]??null]))},
      pair_id:typeof m.pair_id==="string"?m.pair_id:null,history:historyRows(history),baseline_id:null,
      _identity:object(m.source_identity)&&Object.keys(m.source_identity).length&&object(m.runtime)&&Object.keys(m.runtime).length?key([m.source_identity,m.runtime]):null};
  }
  function pair(values){
    const baselines=new Map();
    const identity=r=>r.status==="complete"&&r.pair_id&&r._identity&&Number.isInteger(r.config.seed)&&Number.isInteger(r.round)&&r.round>0?key([r.pair_id,r._identity,r.round,r.config.seed]):null;
    for(const r of values){const k=identity(r);if(k&&r.config.attack==="none"){if(!baselines.has(k))baselines.set(k,[]);baselines.get(k).push(r.id);}}
    return values.map(r=>{const {_identity,...run}=r,k=identity(r),candidates=baselines.get(k)||[];return {...run,baseline_id:r.config.attack!=="none"&&candidates.length===1?candidates[0]:null};});
  }
  const allowed=new Set(["manifest.json","final_metrics.json","validation_history.json","test_logits.json"]);
  function indexFiles(files){
    const dirs=new Map();
    for(const file of files){
      const path=file.webkitRelativePath||file.relativePath||file.name;
      if(typeof path!=="string"||path.length>4096)continue;
      const parts=path.split("/"),name=parts.pop();
      if(!allowed.has(name)||parts.some(p=>!p||p==="."||p===".."||p.includes("\\")))continue;
      const dir=parts.join("/")||"Selected experiment";
      if(!dirs.has(dir))dirs.set(dir,new Map());
      const entries=dirs.get(dir);
      if(entries.has(name))throw Error("Duplicate file in "+dir+": "+name);
      entries.set(name,file);
      if(dirs.size>1000)throw Error("Choose a smaller folder (maximum 1000 result directories)");
    }
    return dirs;
  }
  async function json(file,limit){
    if(!file||!Number.isSafeInteger(file.size)||file.size<1||file.size>limit)throw Error("Missing or oversized file");
    return JSON.parse(await file.text());
  }
  async function load(files){
    const dirs=indexFiles(files),runs=[],errors=[],logits=new Map();
    let total=0;
    for(const [dir,entries] of dirs){
      if(!entries.has("manifest.json"))continue;
      try{
        const manifest=entries.get("manifest.json"),final=entries.get("final_metrics.json"),history=entries.get("validation_history.json");
        const bytes=[manifest,final,history].filter(Boolean).reduce((n,f)=>n+f.size,0);
        if(total+bytes>64*1024*1024){errors.push({id:dir,reason:"Folder exceeds 64 MiB summary budget; select a smaller folder"});continue;}
        total+=bytes;
        const m=await json(manifest,2*1024*1024);
        const value=project(dir,m,final?await json(final,12*1024*1024):{},history?await json(history,2*1024*1024):[],Number.isFinite(manifest.lastModified)?new Date(manifest.lastModified).toISOString():null);
        runs.push(value);
        if(entries.has("test_logits.json"))logits.set(dir,entries.get("test_logits.json"));
      }catch(error){errors.push({id:dir,reason:error.message});}
    }
    return {runs:pair(runs),errors,logits};
  }
  // Explicit portable format, not a claim that historical ATIMA files contain logits.
  // Keep raw rows in memory only during this computation; no upload or cache.
  function summarizeLogits(doc,classes){
    if(!object(doc)||doc.schema_version!==1||doc.split!=="test"||!classOrder(classes)||key(doc.classes)!==key(classes)||!Array.isArray(doc.labels)||!Array.isArray(doc.logits)||!doc.labels.length||doc.labels.length!==doc.logits.length||doc.labels.length>250000)throw Error("Invalid test_logits.json schema or class order");
    const size=classes.length,matrix=Array.from({length:size},()=>Array(size).fill(0));
    let nll=0,confidence=0,correct=0;
    for(let i=0;i<doc.labels.length;i++){
      const y=doc.labels[i],row=doc.logits[i];
      if(!Number.isInteger(y)||y<0||y>=size||!Array.isArray(row)||row.length!==size||row.some(v=>!finite(v)))throw Error("Invalid labeled logit row");
      let pred=0;for(let j=1;j<size;j++)if(row[j]>row[pred])pred=j;
      const sum=row.reduce((s,v)=>s+Math.exp(v-row[pred]),0),loss=(row[pred]-row[y])+Math.log(sum);
      if(!finite(loss))throw Error("Logit loss exceeds numerical range");
      nll+=loss;confidence+=1/sum;matrix[y][pred]++;if(pred===y)correct++;
    }
    const n=doc.labels.length;
    if(!finite(nll))throw Error("Non-finite accumulated loss");
    return {samples:n,accuracy:correct/n,mean_confidence:confidence/n,nll:nll/n,confusion_matrix:matrix};
  }
  async function readLogits(file,classes){return summarizeLogits(await json(file,64*1024*1024),classes);}
  return Object.freeze({load,project,pair,indexFiles,summarizeLogits,readLogits});
})();
