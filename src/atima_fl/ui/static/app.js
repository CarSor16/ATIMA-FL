"use strict";
let catalog, defaults, token, datasetTasks = {};
let previousLabelTask = "";
let mode="simple";
const $ = id => document.getElementById(id);

// The UI theme is a local presentation preference; it never enters experiment plans.
let theme = "light";
try {
  const saved = localStorage.getItem("atima-theme");
  theme = saved === "light" || saved === "dark" ? saved
    : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
} catch {
  // Private browsing or restricted storage must not prevent the UI from loading.
}
function setTheme(next, persist = false) {
  theme = next === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = theme;
  const text = uiText(theme === "dark" ? "Light mode" : "Dark mode");
  const button = $("theme-toggle");
  if (button) {
    button.setAttribute("aria-label", text);
    button.setAttribute("title", text);
    $("theme-label").textContent = text;
    $("theme-symbol").textContent = theme === "dark" ? "☀" : "☾";
  }
  if (persist) {
    try { localStorage.setItem("atima-theme", theme); } catch {}
  }
}
const groups = {"data-components":[["dataset","dataset"],["partition","partition"]],"model-components":[["model","model"],["optimizer","optimizer"],["loss","loss"],["metrics","metrics"]],"attack-components":[["attack","attack"],["aggregator","aggregation"]]};
const titles = {dataset:"Dataset",partition:"Partizione",model:"Modello",optimizer:"Ottimizzatore",loss:"Loss",metrics:"Metriche",attack:"Attacco",aggregator:"Aggregazione"};
function componentLabel(component,key){return component.translations?.[currentLanguage]?.[key] || component[key];}
function refreshLanguage(){
  localizeDocument();
  for(const entries of Object.values(groups))for(const [kind,field] of entries){
    const select=$(field);for(const option of select.options){const component=catalog[kind].find(c=>c.id===option.value);if(component)option.textContent=componentLabel(component,"title");}
    select.closest(".component-block").querySelector(".component-description").textContent=componentLabel(catalog[kind].find(c=>c.id===select.value),"description");
  }
  for(const component of catalog.defense){const input=$("defense-"+component.id);input.parentElement.lastChild.nodeValue=" "+componentLabel(component,"title");}
  $("component-list").replaceChildren();
  for(const [kind,components] of Object.entries(catalog))for(const component of components){const card=node("article",undefined,"card");card.append(node("span",kind,"eyebrow"),node("h2",componentLabel(component,"title")),node("p",componentLabel(component,"description")));for(const reference of component.references){const link=node("a","Scientific source");link.href=reference;link.target="_blank";link.rel="noopener";card.append(link);}$("component-list").append(card);}
  $("catalog-status").textContent=currentLanguage==="en"?`${catalog.attack.length-1} attacks · components from files`:`${catalog.attack.length-1} attacchi · componenti da file`;
  $("language").value=currentLanguage;setTheme(theme);setMode(mode);
}
function node(tag, text, cls) { const el=document.createElement(tag); if(text!==undefined)el.textContent=uiText(text); if(cls)el.className=cls; return el; }
function selectedTaskInfo() {
  const dataset=$("dataset")?.value;
  const task=$("dataset_params")?.querySelector('[data-param="task"]')?.value;
  return {task, info:datasetTasks[dataset]?.[task]};
}
function updateTaskUi() {
  const {task,info}=selectedTaskInfo();
  const target=$("dataset-label-preview");
  if(!target)return;
  if(!info){
    target.textContent="This dataset does not advertise classification tasks. Check its plugin documentation.";
    $("num_classes").readOnly=false;
    return;
  }
  $("num_classes").value=String(info.num_classes);
  $("num_classes").readOnly=true;
  target.textContent=`${task}: ${info.num_classes} classes — ${info.class_names.map((name,id)=>id+" · "+name).join(" | ")}. Reference mapping only; inspect data to verify availability.`;
  if(previousLabelTask!==$("dataset").value+":"+task){
    previousLabelTask=$("dataset").value+":"+task;
    const attack=catalog?.attack?.find(item=>item.id===$("attack")?.value);
    if(attack?.id==="label_flip"){
      const fields=$("attack_params");
      const values=readParams(fields);
      if(values.source_class>=info.num_classes)values.source_class=info.num_classes>1?1:0;
      if(values.destination_class>=info.num_classes)values.destination_class=0;
      parameterFields(attack,fields,values);
    }
  }
}
function parameterFields(component, target, values={}) {
  target.replaceChildren();
  for(const [key,schema] of Object.entries(component.parameters)) {
    const label=node("label",schema.description || key);
    let input;
    const labelNames=component.id==="label_flip" && ["source_class","destination_class"].includes(key) ? selectedTaskInfo().info?.class_names : null;
    if(labelNames) { input=node("select"); for(let i=0;i<labelNames.length;i++) { const option=node("option",i+" · "+labelNames[i]);option.value=String(i);input.append(option); } }
    else if(schema.choices) { input=node("select"); for(const choice of schema.choices) { const option=node("option",String(choice)); option.value=String(choice); input.append(option); } }
    else { input=node("input"); input.type=["integer","number"].includes(schema.type)?"number":"text"; if(input.type==="number") { input.step=schema.type==="integer"?"1":"any"; if(schema.minimum!==undefined)input.min=schema.minimum; if(schema.maximum!==undefined)input.max=schema.maximum; } }
    const value=values[key]===undefined?schema.default:values[key]; input.value=schema.type==="array"?JSON.stringify(value):String(value);
    input.dataset.param=key; input.dataset.type=schema.type; label.append(input); target.append(label);
  }
}
function selection(kind, field, target) {
  const block=node("div",undefined,"component-block"+(["optimizer","loss","metrics"].includes(kind)?" advanced-only":"")),label=node("label",titles[kind]),select=node("select"); select.id=field;
  for(const component of catalog[kind]) { const option=node("option",componentLabel(component,"title")); option.value=component.id;select.append(option); }
  select.value=defaults[field]; label.append(select);block.append(label);
  const description=node("p",undefined,"component-description"),params=node("div",undefined,kind==="dataset"?"fields":"fields advanced-only");params.id=field+"_params";block.append(description,params);target.append(block);
  function refresh(){const component=catalog[kind].find(c=>c.id===select.value);description.textContent=componentLabel(component,"description");parameterFields(component,params,select.value===defaults[field]?defaults[field+"_params"]:{});}
  select.addEventListener("change",()=>{refresh();if(kind==="attack")$("attack-enabled").checked=select.value!=="none";});refresh();
}
function readParams(target) { const value={}; for(const input of target.querySelectorAll("[data-param]")) { const type=input.dataset.type; value[input.dataset.param]=type==="array"?JSON.parse(input.value):["integer","number"].includes(type)?Number(input.value):type==="boolean"?input.value==="true":input.value; } return value; }
function integerList(text, label) {
  if(!text.trim())return [];
  const parts=text.split(",").map(x=>x.trim());
  if(parts.some(x=>!/^\d+$/.test(x)))throw new Error(uiText(label)+(currentLanguage==="en"?": use comma-separated integers.":": usa interi separati da virgola."));
  return parts.map(Number);
}
function config() {
  const value=structuredClone(defaults);
  for(const [key,initial] of Object.entries(defaults)) { const input=$(key); if(!input)continue; value[key]=typeof initial==="number"?Number(input.value):input.value; }
  for(const entries of Object.values(groups)) for(const [,field] of entries)value[field+"_params"]=readParams($(field+"_params"));
  const {info}=selectedTaskInfo();
  if(info)value.num_classes=info.num_classes;
  value.client_servers=integerList($("client_servers").value,"Assegnazione server");
  if(!$("attack-enabled").checked) {value.attack="none";value.attack_params={};value.malicious_clients=[];value.paired_clean="";value.paired_rounds=0;}
  else if($("malicious-selection").value==="ids")value.malicious_clients=integerList($("malicious_clients").value,"ID malevoli");
  else {
    const n=Number($("malicious-count").value);
    if(!Number.isInteger(n)||n<1||n>value.clients)throw new Error(uiText("Malicious client count must be between 1 and the total clients."));
    value.malicious_clients=Array.from({length:n},(_,i)=>i);
  }
  if($("attack-until-end").checked)value.attack_end=value.rounds;
  value.defenses=[];for(const block of $("defense-components").children){const component=catalog.defense.find(c=>c.id===block.dataset.defense);if($("defense-"+component.id).checked)value.defenses.push({id:component.id,params:readParams($("defense-params-"+component.id))});}
  return value;
}
function controls() {
  const enabled=$("attack-enabled").checked;
  $("attack").disabled=!enabled;
  $("attack").closest(".component-block").querySelector(".component-description").textContent=enabled?componentLabel(catalog.attack.find(c=>c.id===$("attack").value),"description"):uiText("Attack disabled; selection is preserved for later.");
  $("attack-controls").classList.toggle("hidden",!enabled);
  $("attack_params").classList.toggle("hidden",!enabled);
  const explicit=$("malicious-selection").value==="ids";
  $("malicious-ids-label").classList.toggle("hidden",!explicit);
  $("malicious-count").disabled=explicit;
  if(explicit){try{$("malicious-count").value=integerList($("malicious_clients").value,"ID malevoli").length;}catch{}}
  $("malicious-count").max=$("clients").value;
  $("servers").max=$("clients").value;$("cpu_budget").min=Number($("client_cpus").value)+Number($("servers").value)+1;
  const untilEnd=$("attack-until-end").checked;
  $("attack_end").disabled=untilEnd;
  if(untilEnd)$("attack_end").value=$("rounds").value;
  $("attack_start").max=$("rounds").value;$("attack_end").max=$("rounds").value;
}
function setMode(value){
  mode=value;$("designer").classList.toggle("simple-mode",mode==="simple");
  $("mode-simple").setAttribute("aria-pressed",String(mode==="simple"));
  $("mode-advanced").setAttribute("aria-pressed",String(mode==="advanced"));
  $("mode-description").textContent=uiText(mode==="simple"?"Simple · essential choices; advanced parameters are preserved.":"Advanced · all parameters, specific clients and server assignments.");
  preview();
}
function timeline(c){
  const target=$("attack-timeline");target.replaceChildren();
  const enabled=c.attack!=="none",first=enabled?c.attack_start:c.rounds+1,last=Math.min(c.attack_end,c.rounds);
  const parts=enabled?[[Math.max(0,first-1),"clean-rounds"],[Math.max(0,last-first+1),"active-rounds"],[Math.max(0,c.rounds-last),"clean-rounds"]]:[[c.rounds,"clean-rounds"]];
  for(const [length,cls] of parts){const segment=node("span",undefined,cls);segment.style.flexGrow=length;target.append(segment);}
  const italian=enabled?`${c.malicious_clients.length} malevoli su ${c.clients} (${(100*c.malicious_clients.length/c.clients).toFixed(1)}%). Attivo nei round ${first}–${last} inclusi; dal round ${last+1} nessun nuovo poisoning. Gli effetti precedenti possono persistere nei pesi.`:`Baseline clean: ${c.clients} client, nessun attacco attivo.`;
  const english=enabled?`${c.malicious_clients.length} malicious out of ${c.clients} (${(100*c.malicious_clients.length/c.clients).toFixed(1)}%). Active in rounds ${first}–${last} inclusive; no new poisoning from round ${last+1}. Previous effects may persist in the weights.`:`Clean baseline: ${c.clients} clients, no active attack.`;
  const text=currentLanguage==="en"?english:italian;target.setAttribute("aria-label",text);$("attack-summary").textContent=text;
}
function preview(){
  controls();
  updateTaskUi();
  try {
    const c=config();$("preview").textContent=JSON.stringify(c,null,2);
    $("selection-summary").textContent=currentLanguage==="en"?`${c.clients} clients · ${c.servers} aggregation ${c.servers===1?"server":"servers"}${c.servers>1?" + 1 coordinator":""}\n${c.malicious_clients.length} malicious · ${c.rounds} rounds\n${c.model} · ${c.partition} · ${c.attack} → ${c.aggregation}\nCPUs ${c.cpu_budget} · ${c.compute_device.toUpperCase()} · epochs ${c.local_epochs}\nOptimizer ${c.optimizer} · learning rate ${c.learning_rate}\n${c.defenses.length} defenses · ${c.server_execution}\nAdvanced parameters preserved`:`${c.clients} client · ${c.servers} server di aggregazione${c.servers>1?" + 1 coordinatore":""}\n${c.malicious_clients.length} malevoli · ${c.rounds} round\n${c.model} · ${c.partition} · ${c.attack} → ${c.aggregation}\nCPU ${c.cpu_budget} · ${c.compute_device.toUpperCase()} · epoche ${c.local_epochs}\nOttimizzatore ${c.optimizer} · learning rate ${c.learning_rate}\n${c.defenses.length} difese · ${c.server_execution}\nParametri avanzati conservati`;
    $("topology-summary").dataset.placement=c.server_execution;
    const assignment=c.client_servers.length?c.client_servers:Array.from({length:c.clients},(_,i)=>i%c.servers);
    $("topology-summary").textContent=Array.from({length:c.servers},(_,sid)=>`Server ${sid}: ${currentLanguage==="en"?"clients":"client"} ${assignment.flatMap((server,cid)=>server===sid?[cid]:[]).join(", ")}`).join(" · ");
    timeline(c);recommendations(c);$("validation-status").textContent=uiText("Configuration needs validation");$("download").classList.add("hidden");$("messages").replaceChildren();
  } catch(error){$("validation-status").textContent=error.message;$("download").classList.add("hidden");$("preview").textContent=(currentLanguage==="en"?"Incomplete configuration: ":"Configurazione incompleta: ")+error.message;}
}
async function request(path,body){const response=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json","X-ATIMA-Token":token},body:JSON.stringify(body)}:{});const result=await response.json();if(!response.ok)throw new Error(result.error || response.statusText);return result;}
async function action(save){$("messages").replaceChildren();try { const c=config();const checked=await request("/api/validate",c);$("validation-status").textContent=uiText("Valid profile · data and GPU must be checked in the job");for(const warning of checked.warnings)$("messages").append(node("p",warning,"warning"));if(save){const result=await request("/api/plans",checked.config);$("download").href=result.download;$("download").classList.remove("hidden");$("messages").append(node("p","Piano salvato. Nessun training avviato."));} } catch(error){$("validation-status").textContent=uiText("Validation failed");$("messages").append(node("p",error.message,"error"));} }
async function inspectLabels(){
  const target=$("label-inspection-results");
  target.textContent="Reading local label metadata...";
  try{
    const result=await request("/api/inspect-dataset",config());
    target.textContent=JSON.stringify({
      selected_task:result.task,
      available:result.task_availability[result.task],
      all_task_availability:result.task_availability,
      source_label_counts:result.observed_fine_labels,
      model_class_counts:result.mapped_class_counts,
      per_client_counts:result.per_client_counts,
      note:result.note
    },null,2);
  }catch(error){
    target.textContent="Inspection unavailable: "+error.message+". The dataset path must exist on the computer running this webapp.";
  }
}
async function refreshResults(){const target=$("results-list");target.replaceChildren();try{const values=await request("/api/results");if(!values.length)target.append(node("p","Nessun risultato locale disponibile."));for(const value of values){const item=node("article",undefined,"result-item");item.append(node("h3",value.id),node("p",`${value.status} · ${currentLanguage==="en"?"valid round":"round valido"} ${value.round ?? "—"}`),node("pre",JSON.stringify(value.metrics,null,2)));target.append(item);}}catch(error){target.append(node("p",error.message,"error"));}}
async function initialize(){
  const [response,initial,tasks]=await Promise.all([request("/api/catalog"),request("/api/defaults"),request("/api/dataset-tasks")]);catalog=response.catalog;token=response.token;defaults=initial;datasetTasks=tasks;
  defaults.name="Baseline_"+new Date().toLocaleDateString("sv-SE");
  for(const [key,value] of Object.entries(defaults))if($(key))$(key).value=Array.isArray(value)?value.join(","):value;
  for(const [target,entries] of Object.entries(groups))for(const [kind,field] of entries)selection(kind,field,$(target));
  $("malicious-count").value=defaults.malicious_clients.length;
  $("attack-enabled").checked=defaults.attack!=="none";
  $("mode-simple").addEventListener("click",()=>setMode("simple"));$("mode-advanced").addEventListener("click",()=>setMode("advanced"));
  $("attack-enabled").addEventListener("change",()=>{if($("attack-enabled").checked && $("attack").value==="none"){const choice=catalog.attack.find(c=>c.id!=="none");if(choice){$("attack").value=choice.id;$("attack").dispatchEvent(new Event("change",{bubbles:true}));}}});
  $("malicious-selection").addEventListener("change",()=>{if($("malicious-selection").value==="ids" && !$("malicious_clients").value.trim()){const n=Number($("malicious-count").value);$("malicious_clients").value=Array.from({length:n},(_,i)=>i).join(",");}});
  for(const component of catalog.defense){const label=node("label"),input=node("input");input.type="checkbox";input.id="defense-"+component.id;label.append(input,document.createTextNode(" "+componentLabel(component,"title")));const params=node("div",undefined,"fields");params.id="defense-params-"+component.id;parameterFields(component,params);const block=node("div",undefined,"defense-stage");block.dataset.defense=component.id;
    const up=node("button","Move up"),down=node("button","Move down");up.type=down.type="button";
    up.addEventListener("click",()=>{if(block.previousElementSibling)block.previousElementSibling.before(block);preview();});
    down.addEventListener("click",()=>{if(block.nextElementSibling)block.nextElementSibling.after(block);preview();});
    params.classList.add("advanced-only");block.append(label,up,down,params);$("defense-components").append(block);}
  for(const [kind,components] of Object.entries(catalog))for(const component of components){const card=node("article",undefined,"card");card.append(node("span",kind,"eyebrow"),node("h2",componentLabel(component,"title")),node("p",componentLabel(component,"description")));for(const reference of component.references){const link=node("a","Fonte scientifica");link.href=reference;link.target="_blank";link.rel="noopener";card.append(link);}$("component-list").append(card);}
  $("catalog-status").textContent=`${catalog.attack.length-1} attacchi · componenti da file`;
  $("experiment-form").addEventListener("input",preview);$("experiment-form").addEventListener("change",preview);$("experiment-form").addEventListener("submit",event=>event.preventDefault());
  $("validate").addEventListener("click",()=>action(false));$("save").addEventListener("click",()=>action(true));$("save-study").addEventListener("click",()=>saveStudy());$("refresh-results").addEventListener("click",refreshResults);$("inspect-labels").addEventListener("click",inspectLabels);
  const pages={designer:["Disegna il tuo esperimento","Componenti intercambiabili, un profilo riproducibile."],components:["Catalogo dei componenti","Implementazioni scoperte dalle cartelle del framework."],results:["Risultati degli esperimenti","Metriche locali e stato dei run importati."],guide:["Dal progetto al cluster","Un percorso verificabile dalla configurazione all’analisi."]};
  for(const button of document.querySelectorAll(".nav"))button.addEventListener("click",()=>{for(const item of document.querySelectorAll(".nav,.page"))item.classList.remove("active");button.classList.add("active");$(button.dataset.page).classList.add("active");[$("page-title").textContent,$("page-subtitle").textContent]=pages[button.dataset.page].map(uiText);if(button.dataset.page==="results")refreshResults();});$("language").addEventListener("change",()=>{currentLanguage=$("language").value;try{localStorage.setItem("atima-language",currentLanguage);}catch{}refreshLanguage();});refreshLanguage();
}
setTheme(theme);
$("theme-toggle").addEventListener("click",()=>setTheme(theme === "dark" ? "light" : "dark", true));
initialize().catch(error=>{$("catalog-status").textContent=uiText("Catalog unavailable");$("messages").append(node("p",error.message,"error"));});

function recommendations(c){
  const target=$("defense-recommendations");target.replaceChildren();
  if(c.attack==="none"){target.append(node("p","Enable an attack to see candidate protections."));return;}
  const attack=catalog.attack.find(x=>x.id===c.attack);
  target.append(node("p","Candidates to test, not guaranteed solutions. Effects depend on non-IID data and the malicious fraction in each server group."));
  if(attack.threats?.some(t=>["stealth_poisoning","adaptive_poisoning"].includes(t)))target.append(node("p","This attack can evade robust aggregation; a suggested method is a test hypothesis, not a known cure.","warning"));
  if(attack.threats?.includes("data_poisoning"))target.append(node("p","Server update defenses do not repair poisoned labels or features. Track recall for every class."));
  for(const component of [...catalog.defense,...catalog.aggregator]){
    if(!component.mitigates?.some(t=>attack.threats?.includes(t)))continue;
    const card=node("article",undefined,"defense-candidate");
    card.append(node("strong",componentLabel(component,"title")),node("p",componentLabel(component,"limitations")));
    for(const reference of component.references){const link=node("a","Scientific source");link.href=reference;link.target="_blank";link.rel="noopener";card.append(link);}
    target.append(card);
  }
}
async function saveStudy(){
  $("messages").replaceChildren();
  try{const result=await request("/api/defense-study",config());$("download").href=result.download;$("download").classList.remove("hidden");$("messages").append(node("p","Four-condition study exported. No training started. A common round cap disables stopping before that cap."));}
  catch(error){$("messages").append(node("p",error.message,"error"));}
}
