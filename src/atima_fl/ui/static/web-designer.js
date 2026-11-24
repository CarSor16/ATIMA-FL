"use strict";

// Browser prechecks are not a substitute for the Runtime's plugin hooks.
const ATIMAWebDesigner=(()=>{
  const {defaults,catalog}=ATIMA_WEB_CATALOG;
  const kinds=[["dataset","dataset"],["partition","partition"],["model","model"],["attack","attack"],["aggregator","aggregation"],["optimizer","optimizer"],["loss","loss"],["metrics","metrics"]];
  const clone=v=>JSON.parse(JSON.stringify(v));
  const finite=v=>typeof v==="number"&&Number.isFinite(v);
  const obj=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
  function component(kind,id){const entry=catalog[kind].find(x=>x.id===id);if(!entry)throw Error("Unknown "+kind+": "+id);return entry;}
  function validateValue(spec,value,label){
    const valid={integer:Number.isSafeInteger(value),number:finite(value),boolean:typeof value==="boolean",string:typeof value==="string",array:Array.isArray(value),object:obj(value)}[spec.type];
    if(!valid||("minimum" in spec&&value<spec.minimum)||("maximum" in spec&&value>spec.maximum)||("choices" in spec&&!spec.choices.some(v=>JSON.stringify(v)===JSON.stringify(value))))throw Error("Invalid "+label);
    if(spec.type==="array"&&spec.items)value.forEach(v=>validateValue(spec.items,v,label));
    return value;
  }
  function params(entry,values={}){
    if(!obj(values)||Object.keys(values).some(k=>!Object.hasOwn(entry.parameters,k)))throw Error("Unknown parameters for "+entry.id);
    return Object.fromEntries(Object.entries(entry.parameters).map(([k,s])=>[k,validateValue(s,Object.hasOwn(values,k)?values[k]:clone(s.default),entry.id+"."+k)]));
  }
  function validate(c){
    if(typeof c.name!=="string"||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(c.name))throw Error("Use an ASCII-safe experiment name (1–96 characters)");
    for(const [key,min,max] of [["seed",0,4294967295],["clients",1,10000],["servers",1,c.clients],["rounds",1,50],["local_epochs",1,1000],["batch_size",1,1000000],["input_dim",1,1000000],["num_classes",2,100],["attack_start",1,c.rounds],["attack_end",c.attack_start,c.rounds]]){
      if(!Number.isSafeInteger(c[key])||c[key]<min||c[key]>max)throw Error("Invalid "+key);
    }
    if(!finite(c.learning_rate)||c.learning_rate<=0)throw Error("Invalid learning rate");
    if(!Array.isArray(c.malicious_clients)||new Set(c.malicious_clients).size!==c.malicious_clients.length||c.malicious_clients.some(i=>!Number.isSafeInteger(i)||i<0||i>=c.clients)||c.attack!=="none"&&!c.malicious_clients.length)throw Error("Invalid malicious client IDs");
    if(c.attack==="none")c.malicious_clients=[];
    if(!["standard","hyperfl_plus_plus"].includes(c.training_method)||!["shared","slice"].includes(c.evaluation_scope)||c.evaluation_scope==="slice"&&c.training_method!=="hyperfl_plus_plus"||c.training_method==="hyperfl_plus_plus"&&(c.model!=="lopez_cnn"||c.local_epochs<2))throw Error("Unsupported training method / model / evaluation scope");
    for(const [kind,field] of kinds)c[field+"_params"]=params(component(kind,c[field]),c[field+"_params"]);
    if(!Array.isArray(c.defenses))throw Error("Invalid defense stages");
    c.defenses=c.defenses.map(d=>({id:d.id,params:params(component("defense",d.id),d.params)}));
    if(new Set(c.defenses.map(d=>d.id)).size!==c.defenses.length)throw Error("Duplicate defense stages");
    return c;
  }
  function list(text,parse){const parts=text.split(",").map(s=>s.trim());if(parts.some(s=>!s))throw Error("Enter nonempty comma-separated values");const values=parts.map(parse);if(new Set(values).size!==values.length)throw Error("Duplicate values");return values;}
  function axes(c){
    const out=new Map();
    if(c.attack==="none")return out;
    for(const [kind,field] of [["attack","attack"],["partition","partition"]])for(const [key,s] of Object.entries(component(kind,c[field]).parameters))if(["number","integer"].includes(s.type))out.set(field+"_params."+key,s);
    for(const field of ["model","partition"])out.set(field,{type:"string",choices:catalog[field].map(x=>x.id)});
    out.set("malicious_count",{type:"integer",minimum:1,maximum:c.clients});
    for(const field of ["attack_start","attack_end"])out.set(field,{type:"integer",minimum:1,maximum:c.rounds});
    return out;
  }
  function draft(config,mode,seedText,axis,levelText){
    const c=validate(clone(config)),base={schema_version:1,mode,config:c,seeds:[],axis:null,levels:[]};
    if(mode==="single")return {document:base,count:1};
    if(!["batch","sweep"].includes(mode))throw Error("Unknown campaign mode");
    base.seeds=list(seedText,Number);
    if(base.seeds.length>50||base.seeds.some(v=>!Number.isSafeInteger(v)||v<0||v>4294967295))throw Error("Use 1–50 nonnegative integer seeds");
    if(mode==="batch")return {document:base,count:base.seeds.length*(c.attack==="none"?1:2)};
    const spec=axes(c).get(axis);
    if(!spec)throw Error("Choose a supported sweep axis");
    base.axis=axis;base.levels=list(levelText,s=>spec.type==="string"?s:Number(s));
    if(base.levels.length<2||base.levels.length>12)throw Error("Use 2–12 distinct levels");
    for(const level of base.levels){
      validateValue(spec,level,axis);
      const candidate=clone(c);
      if(axis.includes(".")){const i=axis.indexOf(".");candidate[axis.slice(0,i)][axis.slice(i+1)]=level;}
      else if(axis==="malicious_count")candidate.malicious_clients=Array.from({length:level},(_,i)=>i);
      else if(["model","partition"].includes(axis)){candidate[axis]=level;if(level!==c[axis])candidate[axis+"_params"]={};}
      else candidate[axis]=level;
      validate(candidate);
    }
    const shared=axis.startsWith("attack_params.")||["malicious_count","attack_start","attack_end"].includes(axis);
    const count=base.seeds.length*(shared?base.levels.length+1:2*base.levels.length);
    if(count>300)throw Error("Campaign exceeds 300 profiles");
    return {document:base,count};
  }
  return Object.freeze({defaults,catalog,kinds,params,component,axes,draft});
})();
function setupWebDesigner(){
  const root=$("web-designer");if(!root)return;
  const fields=$("web-design-fields"),components=$("web-design-components"),controls=new Map(),paramsByField=new Map();
  const base=ATIMAWebDesigner.defaults;
  const field=(key,label,type,options)=>{
    const wrapper=node("label",label),input=node(options?"select":"input");
    input.id="web-design-"+key;
    if(options)for(const [value,title] of options){const option=node("option",title);option.value=value;input.append(option);}
    else input.type=type;
    input.value=String(base[key]??"");wrapper.append(input);fields.append(wrapper);controls.set(key,input);
  };
  for(const [key,label] of [["name","Experiment name"],["seed","Single experiment seed"],["clients","Clients"],["servers","Servers"],["rounds","Rounds"],["local_epochs","Local epochs"],["batch_size","Batch size"],["learning_rate","Learning rate"],["input_dim","Input features"],["num_classes","Classes"],["attack_start","Attack start"],["attack_end","Attack end"]])field(key,label,key==="name"?"text":"number");
  field("training_method","Training method","text",[["standard","Standard"],["hyperfl_plus_plus","HyperFL++"]]);
  field("evaluation_scope","Evaluation scope","text",[["shared","Shared"],["slice","Slice"]]);
  const ids=node("input");ids.value="0";ids.id="web-design-malicious";const idLabel=node("label","Malicious client IDs (comma separated)");idLabel.append(ids);fields.append(idLabel);
  for(const [kind,key] of ATIMAWebDesigner.kinds){
    const section=node("section",undefined,"card"),label=node("label",kind),select=node("select"),description=node("p"),textarea=node("textarea");
    textarea.rows=4;textarea.setAttribute("aria-label",kind+" parameters (JSON)");
    for(const entry of ATIMAWebDesigner.catalog[kind]){const option=node("option",entry.title+" · "+entry.id);option.value=entry.id;select.append(option);}
    select.value=base[key];label.append(select);section.append(label,description,textarea);components.append(section);controls.set(key,select);paramsByField.set(key,textarea);
    function refresh(){
      const entry=ATIMAWebDesigner.component(kind,select.value),help=entry.help?.[currentLanguage]||entry.help?.en;
      description.textContent=(entry.translations?.[currentLanguage]?.description||entry.description)+(help?" "+(help.mechanism||"")+" "+(help.intensity||""):"");
      textarea.value=JSON.stringify(ATIMAWebDesigner.params(entry),null,2);
    }
    select.addEventListener("change",refresh);refresh();
  }
  function configuration(){
    const c=JSON.parse(JSON.stringify(base));
    for(const [key,input] of controls)c[key]=typeof base[key]==="number"?Number(input.value):input.value;
    for(const [key,input] of paramsByField)c[key+"_params"]=JSON.parse(input.value);
    c.malicious_clients=c.attack==="none"?[]:ids.value.split(",").map(s=>s.trim()).map(s=>s?Number(s):NaN);
    c.defenses=JSON.parse($("web-design-defenses").value);
    return c;
  }
  function refreshAxes(){
    const select=$("web-design-axis"),previous=select.value;select.replaceChildren();
    for(const [key,spec] of ATIMAWebDesigner.axes(configuration())){const option=node("option",key+(spec.choices?" · "+spec.choices.join(", "):""));option.value=key;select.append(option);}
    if([...select.options].some(x=>x.value===previous))select.value=previous;
  }
  $("web-design-axes").addEventListener("click",()=>{try{refreshAxes();$("web-design-status").textContent="Sweep axes updated.";}catch(e){$("web-design-status").textContent=e.message;}});
  $("web-design-download").addEventListener("click",()=>{
    const status=$("web-design-status");
    try{
      const result=ATIMAWebDesigner.draft(configuration(),$("web-design-mode").value,$("web-design-seeds").value,$("web-design-axis").value,$("web-design-levels").value);
      const blob=new Blob([JSON.stringify(result.document,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=node("a");link.href=url;link.download="atima-web-draft.json";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      status.textContent=result.count+" planned profiles. Draft downloaded; run the local web-plan command for authoritative validation. No jobs submitted.";
    }catch(error){status.textContent=error.message;}
  });
  refreshAxes();
}
