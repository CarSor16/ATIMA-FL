"use strict";
let catalog, defaults, token, datasetTasks = {};
let previousLabelTask = "";
let chosenComparison = {first: null, second: null};
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

const CATALOG_GROUPS = [
  {title:"Data & partitions",kinds:[["dataset","Datasets"],["partition","Partitions"]]},
  {title:"Models & learning",kinds:[["model","Models"],["optimizer","Optimizers"],["loss","Loss functions"],["metrics","Metrics"]]},
  {title:"Attacks & protections",kinds:[["attack","Attacks"],["defense","Defenses"],["aggregator","Aggregation methods"]]}
];
const TASK_TITLES = {
  prepared_5:["Prepared dataset · 5 classes","Dataset preparato · 5 classi"],
  binary:["Binary detection · 2 classes","Rilevamento binario · 2 classi"],
  family_6:["Attack families · 6 classes","Famiglie di attacco · 6 classi"],
  fine_15:["Detailed attacks · 15 classes","Attacchi dettagliati · 15 classi"]
};
const FRIENDLY_LABELS_IT = {
  Normal:"Traffico normale",Attack:"Traffico di attacco",
  "DoS/DDoS":"Denial of Service (DoS/DDoS)",
  "Information Gathering":"Raccolta di informazioni",
  MITM:"Intercettazione (MITM)",Injection:"Attacchi injection",
  benign:"Traffico normale",dos:"Denial of Service",
  infog:"Raccolta informazioni",inject:"Injection"
};
function readableClassName(raw){
  if(currentLanguage==="it" && FRIENDLY_LABELS_IT[raw])return FRIENDLY_LABELS_IT[raw];
  return String(raw).replace(/_/g," ");
}
function readableTaskName(task,info){
  const translated=TASK_TITLES[task];
  return translated?translated[currentLanguage==="it"?1:0]:
    String(task).replace(/_/g," ")+" · "+(info?.num_classes ?? "?")+" "+uiText("classes");
}
function refreshTaskOptions(){
  const dataset=$("dataset")?.value;
  const task=$("dataset_params")?.querySelector('[data-param="task"]');
  if(task)for(const option of task.options)
    option.textContent=readableTaskName(option.value,datasetTasks[dataset]?.[option.value]);
  if($("attack")?.value==="label_flip"){
    const info=selectedTaskInfo().info;
    if(info)for(const name of ["source_class","destination_class"]){
      const select=$("attack_params")?.querySelector('[data-param="'+name+'"]');
      if(select?.tagName==="SELECT")for(const option of select.options)
        option.textContent=option.value+" · "+readableClassName(info.class_names[Number(option.value)]);
    }
  }
}
function renderComponentCatalog(){
  const root=$("component-list");
  root.replaceChildren();
  for(const [index,group] of CATALOG_GROUPS.entries()){
    const section=node("details",undefined,"catalog-group");
    section.open=index===0;
    const heading=node("summary",undefined,"catalog-group-heading");
    const total=group.kinds.reduce((n,[kind])=>n+(catalog[kind]?.length||0),0);
    heading.append(node("strong",group.title),node("span",total+" "+uiText("components"),"catalog-count"));
    section.append(heading);
    const subgroups=node("div",undefined,"catalog-subgroups");
    for(const [kind,title] of group.kinds){
      const items=catalog[kind]||[];
      if(!items.length)continue;
      const subgroup=node("details",undefined,"catalog-subgroup");
      const summary=node("summary",undefined,"catalog-subheading");
      summary.append(node("strong",title),node("span",String(items.length),"catalog-count"));
      subgroup.append(summary);
      const grid=node("div",undefined,"catalog-grid");
      for(const component of items){
        const card=node("article",undefined,"card catalog-component");
        card.append(node("h3",componentLabel(component,"title")),node("p",componentLabel(component,"description")));
        for(const url of component.references||[]){
          const link=node("a","Scientific source");link.href=url;
          link.target="_blank";link.rel="noopener";
          card.append(link);
        }
        grid.append(card);
      }
      subgroup.append(grid);subgroups.append(subgroup);
    }
    section.append(subgroups);root.append(section);
  }
}

function refreshLanguage(){
  localizeDocument();
  for(const entries of Object.values(groups))for(const [kind,field] of entries){
    const select=$(field);for(const option of select.options){const component=catalog[kind].find(c=>c.id===option.value);if(component)option.textContent=componentLabel(component,"title");}
    select.closest(".component-block").querySelector(".component-description").textContent=componentLabel(catalog[kind].find(c=>c.id===select.value),"description");
  }
  for(const component of catalog.defense){const input=$("defense-"+component.id);input.parentElement.lastChild.nodeValue=" "+componentLabel(component,"title");}
  for(const block of $("defense-components").children){const component=catalog.defense.find(c=>c.id===block.dataset.defense);block.querySelector(".defense-name").textContent=componentLabel(component,"title");}
  updateDefensePipeline();
  refreshTaskOptions();
  updateTaskUi();
  renderComponentCatalog();
  $("catalog-status").textContent=currentLanguage==="en"?`${catalog.attack.length-1} attacks · components from files`:`${catalog.attack.length-1} attacchi · componenti da file`;
  $("language").value=currentLanguage;setTheme(theme);setMode(mode);
  if($("results").classList.contains("active"))refreshResults();
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
  target.replaceChildren();
  target.append(node("strong",readableTaskName(task,info),"task-title"),
    node("span","Reference labels · not verified against cluster data","task-note"));
  const list=node("div",undefined,"task-label-grid");
  for(const [index,source] of info.class_names.entries()){
    const pill=node("span",undefined,"task-label-pill");
    pill.title=source;
    pill.append(node("span",String(index),"label-index"),node("span",readableClassName(source),"label-name"));
    list.append(pill);
  }
  target.append(list);
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
    if(labelNames) { input=node("select"); for(let i=0;i<labelNames.length;i++) { const option=node("option",i+" · "+readableClassName(labelNames[i]));option.value=String(i);input.append(option); } }
    else if(schema.choices) { input=node("select"); for(const choice of schema.choices) { const option=node("option",key==="task"?readableTaskName(choice,datasetTasks[component.id]?.[choice]):String(choice)); option.value=String(choice); input.append(option); } }
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
  select.addEventListener("change",()=>{
    refresh();
    if(kind==="attack")$("attack-enabled").checked=select.value!=="none";
    if(kind==="attack"||kind==="model")updateExperimentName();
  });refresh();
}
// Stage order is the order of active DOM list items, which config() serializes
// unchanged into the TOML defense array. Inactive stages remain in the catalog.
let draggingDefense = null;
const cachedDefenseParams = new Map();
function updateDefensePipeline(announce=false) {
  const rows = [...$("defense-components").children];
  $("defense-empty").classList.toggle("hidden",rows.length>0);
  rows.forEach((block,index)=>{
    const component=catalog.defense.find(item=>item.id===block.dataset.defense);
    block.setAttribute("aria-posinset",String(index+1));
    block.setAttribute("aria-setsize",String(rows.length));
    block.querySelector(".defense-position").textContent=String(index+1).padStart(2,"0");
    block.querySelector(".defense-grip").setAttribute("aria-label",
      `${uiText("Reorder defense")}: ${componentLabel(component,"title")} (${index+1}/${rows.length}). ${uiText("Use up and down arrow keys to move.")}`);
  });
  if(announce){
    const names=rows.map(block=>componentLabel(catalog.defense.find(item=>item.id===block.dataset.defense),"title"));
    $("defense-order-status").textContent=uiText("Defense execution order")+": "+(names.join(" → ") || uiText("None"));
  }
}
function clearDefenseDropTargets() {
  for(const block of $("defense-components").children)
    block.classList.remove("drop-before","drop-after","is-dragging");
}
function finishDefenseReorder() {
  clearDefenseDropTargets();
  draggingDefense=null;
  updateDefensePipeline(true);
  preview();
}
function setDefenseEnabled(component, enabled, initialParams=null) {
  const container=$("defense-components");
  const existing=[...container.children].find(block=>block.dataset.defense===component.id);
  if(!enabled){
    if(existing){
      cachedDefenseParams.set(component.id,readParams(existing.querySelector(".defense-params")));
      existing.remove();
    }
    updateDefensePipeline();
    return;
  }
  if(existing)return;
  const block=node("div",undefined,"defense-stage");
  block.dataset.defense=component.id;
  block.setAttribute("role","listitem");
  const heading=node("div",undefined,"defense-stage-heading");
  const position=node("span","00","defense-position");
  position.setAttribute("aria-hidden","true");
  const grip=node("button","⠿","defense-grip");
  grip.type="button";
  grip.draggable=true;
  grip.title=uiText("Drag to reorder; use arrow keys from the handle.");
  const name=node("strong",componentLabel(component,"title"),"defense-name");
  const params=node("div",undefined,"fields advanced-only defense-params");
  params.id="defense-params-"+component.id;
  parameterFields(component,params,initialParams ?? cachedDefenseParams.get(component.id) ?? {});
  heading.append(position,grip,name);
  block.append(heading,params);
  grip.addEventListener("keydown",event=>{
    const list=$("defense-components");
    let changed=false;
    if(event.key==="ArrowUp" && block.previousElementSibling){block.previousElementSibling.before(block);changed=true;}
    if(event.key==="ArrowDown" && block.nextElementSibling){block.nextElementSibling.after(block);changed=true;}
    if(event.key==="Home" && block.previousElementSibling){list.prepend(block);changed=true;}
    if(event.key==="End" && block.nextElementSibling){list.append(block);changed=true;}
    if(["ArrowUp","ArrowDown","Home","End"].includes(event.key)){
      event.preventDefault();
      if(changed){finishDefenseReorder();grip.focus();}
    }
  });
  grip.addEventListener("dragstart",event=>{
    draggingDefense=block;
    event.dataTransfer.effectAllowed="move";
    event.dataTransfer.setData("text/plain",component.id);
    block.classList.add("is-dragging");
  });
  grip.addEventListener("dragend",()=>{
    clearDefenseDropTargets();
    draggingDefense=null;
  });
  block.addEventListener("dragover",event=>{
    if(!draggingDefense || draggingDefense===block)return;
    event.preventDefault();
    event.dataTransfer.dropEffect="move";
    clearDefenseDropTargets();
    const before=event.clientY < block.getBoundingClientRect().top+block.getBoundingClientRect().height/2;
    block.classList.add(before?"drop-before":"drop-after");
  });
  block.addEventListener("drop",event=>{
    if(!draggingDefense || draggingDefense===block)return;
    event.preventDefault();
    event.stopPropagation();
    const before=event.clientY < block.getBoundingClientRect().top+block.getBoundingClientRect().height/2;
    if(before)block.before(draggingDefense);else block.after(draggingDefense);
    finishDefenseReorder();
  });
  container.append(block);
  updateDefensePipeline();
}
function initializeDefenses() {
  const picker=$("defense-picker");
  const selected=new Map((defaults.defenses||[]).map(defense=>[defense.id,defense.params]));
  for(const component of catalog.defense) {
    const label=node("label",undefined,"defense-picker-item");
    const checkbox=node("input");
    checkbox.type="checkbox";
    checkbox.id="defense-"+component.id;
    label.append(checkbox,document.createTextNode(" "+componentLabel(component,"title")));
    picker.append(label);
    checkbox.addEventListener("change",()=>{
      setDefenseEnabled(component,checkbox.checked);
      preview();
    });
  }
  // Preserve a preexisting exported stage order rather than imposing catalog order.
  for(const [id,params] of selected) {
    const component=catalog.defense.find(item=>item.id===id);
    if(!component)continue;
    $("defense-"+id).checked=true;
    setDefenseEnabled(component,true,params);
  }
  $("defense-components").addEventListener("dragover",event=>{
    if(draggingDefense){event.preventDefault();event.dataTransfer.dropEffect="move";}
  });
  $("defense-components").addEventListener("drop",event=>{
    if(!draggingDefense)return;
    event.preventDefault();
    if(event.target===$("defense-components")){
      $("defense-components").append(draggingDefense);
      finishDefenseReorder();
    }
  });
  updateDefensePipeline();
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
  value.defenses=[];for(const block of $("defense-components").children){const component=catalog.defense.find(c=>c.id===block.dataset.defense);value.defenses.push({id:component.id,params:readParams($("defense-params-"+component.id))});}
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

const PREFERRED_ATTACK_NAMES = {none:"Baseline",alie:"ALIE",ipm:"IPM",fang:"FANG"};
const PREFERRED_MODEL_NAMES = {mlp:"MLP",lopez_cnn:"CNN",linear:"Linear"};
function experimentDisplayPart(identifier){
  return String(identifier||"Unknown").split("_")
    .map(piece=>piece.charAt(0).toUpperCase()+piece.slice(1)).join("");
}
function proposedExperimentName(){
  const attack=$("attack-enabled")?.checked ? $("attack")?.value : "none";
  const model=$("model")?.value;
  return (PREFERRED_ATTACK_NAMES[attack]||experimentDisplayPart(attack))+"_"+
    (PREFERRED_MODEL_NAMES[model]||experimentDisplayPart(model));
}
function updateExperimentName(){
  const choice=$("auto-experiment-name"),field=$("name");
  if(!choice||!field)return;
  field.readOnly=choice.checked;
  if(choice.checked)field.value=proposedExperimentName();
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
async function refreshClusterStatus(){
  try {
    const status=await request("/api/cluster-status");
    $("cluster-status").textContent=status.configured
      ? `SSH configured for ${status.host}. Active workspace: ${status.workspace}. Import on demand.`
      : `Cluster not configured. ATIMA is looking for: ${status.config_path}`;
  }catch(error){$("cluster-status").textContent=error.message;}
}
async function syncClusterResults(){
  const button=$("sync-cluster-results"),output=$("cluster-sync-message");
  button.disabled=true;
  output.textContent="Connecting securely over SSH and reading result summaries…";
  try{
    const response=await request("/api/sync-cluster-results",{});
    output.textContent=`Imported ${response.imported} experiment summaries and available validation histories. Dataset files and model weights remain on the cluster.`;
    await refreshResults();
  }catch(error){output.textContent="Cluster import failed: "+error.message;}
  finally{button.disabled=false;}
}
// Results dashboard: test metrics are distinct from per-round validation metrics.
const RESULT_METRICS = [
  ["accuracy", "Accuracy", true], ["macro_f1", "Macro-F1", true],
  ["balanced_accuracy", "Balanced accuracy", true], ["weighted_f1", "Weighted F1", true],
  ["mcc", "MCC", false], ["loss", "Loss", false]
];
function numeric(v){return typeof v==="number" && Number.isFinite(v);}
function score(v, percent=true){return numeric(v) ? (percent?(100*v).toFixed(2)+"%":v.toFixed(4)) : "—";}
function deltaScore(value, reference, percent=true){
  if(!numeric(value)||!numeric(reference))return "—";
  const difference=(value-reference)*(percent?100:1);
  return (difference>0?"+":"")+difference.toFixed(percent?2:4)+(percent?" pp":"");
}
function testMetrics(value){return value?.metrics?.test || null;}
function classNames(value){
  const test=testMetrics(value);
  const listed=Array.isArray(value?.classes)?value.classes:[];
  const keys=test?.per_class && typeof test.per_class==="object"?Object.keys(test.per_class):[];
  return listed.length===keys.length && listed.every(name=>keys.includes(name))?listed:keys;
}
function dataTable(headers, rows, className=""){
  const wrapper=node("div",undefined,"result-table-scroll");
  const table=node("table",undefined,"result-table "+className);
  const head=node("thead");const headRow=node("tr");
  for(const title of headers)headRow.append(node("th",title));
  head.append(headRow);table.append(head);
  const body=node("tbody");
  for(const cells of rows){
    const tr=node("tr");for(const cell of cells)tr.append(node("td",String(cell)));
    body.append(tr);
  }
  table.append(body);wrapper.append(table);return wrapper;
}
function metricCards(metric){
  const grid=node("div",undefined,"result-kpis");
  for(const [key,label,percent] of RESULT_METRICS){
    if(!numeric(metric[key]))continue;
    const item=node("div",undefined,"result-kpi");
    item.append(node("span",label),node("strong",score(metric[key],percent)));grid.append(item);
  }
  return grid;
}
function classMetricsSection(value, baseline){
  const test=testMetrics(value);
  const classes=classNames(value);
  if(!test?.per_class || !classes.length)return null;
  const section=node("section",undefined,"result-section");
  section.append(node("h4",baseline?"Per-class test comparison":"Per-class test metrics"));
  const clean=baseline?testMetrics(baseline)?.per_class:null;
  const rows=classes.map(name=>{
    const attack=test.per_class[name]||{},ref=clean?.[name]||{};
    const common=[name,score(attack.precision),score(attack.recall),score(attack["f1-score"])];
    return baseline
      ? [name,score(ref.recall),score(attack.recall),
         deltaScore(attack.recall,ref.recall),deltaScore(attack["f1-score"],ref["f1-score"])]
      : [...common,String(attack.support??"—")];
  });
  section.append(baseline
    ? dataTable(["Class","Baseline recall","Attack recall","Δ recall","Δ F1"],rows)
    : dataTable(["Class","Precision","Recall","F1","Support"],rows));
  return section;
}
function confusionSection(value){
  const metric=testMetrics(value),classes=classNames(value);
  const matrix=metric?.confusion_matrix;
  if(!Array.isArray(matrix)||!classes.length||matrix.length!==classes.length
    ||matrix.some(row=>!Array.isArray(row)||row.length!==classes.length))return null;
  const section=node("section",undefined,"result-section");
  section.append(node("h4","Test confusion matrix"),node("p","Rows: true class · columns: predicted class"));
  const wrapper=node("div",undefined,"result-table-scroll");
  const table=node("table",undefined,"result-table confusion-matrix");
  const head=node("thead"),header=node("tr");
  header.append(node("th","True ↓ / Predicted →"));
  for(const name of classes)header.append(node("th",name));
  head.append(header);table.append(head);
  const body=node("tbody");
  for(let i=0;i<classes.length;i++){
    const tr=node("tr");tr.append(node("th",classes[i]));
    const row=matrix[i],maximum=Math.max(1,...row.map(x=>numeric(x)?x:0));
    for(let j=0;j<classes.length;j++){
      const count=numeric(row[j])?row[j]:0;
      const cell=node("td",String(count));
      cell.className="matrix-cell"+(i===j?" on-diagonal":"");
      cell.style.backgroundColor="rgba(8,126,131,"+(0.04+0.53*Math.max(0,count)/maximum).toFixed(3)+")";
      cell.title=classes[i]+" → "+classes[j]+": "+count;
      tr.append(cell);
    }
    body.append(tr);
  }
  table.append(body);wrapper.append(table);section.append(wrapper);
  return section;
}
function summarySection(value, baseline){
  const section=node("section",undefined,"result-section");
  const own=testMetrics(value),clean=testMetrics(baseline);
  if(!own||!clean)return null;
  section.append(node("h4","Paired test comparison"));
  section.append(node("p","Verified pair: "+baseline.id+" · same pair ID, runtime, source and completed rounds."));
  const rows=RESULT_METRICS.map(([key,label,percent])=>
    [label,score(clean[key],percent),score(own[key],percent),
     deltaScore(own[key],clean[key],percent)]);
  section.append(dataTable(["Metric","Baseline","Experiment","Δ experiment − baseline"],rows));
  return section;
}
function roundSeries(value,metric,classIndex){
  const list=Array.isArray(value?.history)?value.history:[];
  return list.map(row=>({round:row.round,value:metric==="class_recall"?row.recall?.[classIndex]:row[metric]}))
    .filter(point=>Number.isInteger(point.round)&&point.round>0&&numeric(point.value));
}
function svgElement(tag, attrs, textValue){
  const element=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for(const [name,value] of Object.entries(attrs||{}))element.setAttribute(name,String(value));
  if(textValue!==undefined)element.textContent=String(textValue);
  return element;
}
function roundChart(value,baseline,manual=false,alignedClasses=true){
  const section=node("section",undefined,"result-section");
  section.append(node("h4","Validation metrics by round"));
  const controls=node("div",undefined,"round-controls");
  const metricLabel=node("label","Metric"),metricSelect=node("select");
  for(const [key,label] of [...RESULT_METRICS.filter(m=>["accuracy","macro_f1","balanced_accuracy","loss"].includes(m[0])),
                              ["class_recall","Class recall"]]){
    const option=node("option",label);option.value=key;metricSelect.append(option);
  }
  metricSelect.value="macro_f1";metricLabel.append(metricSelect);
  const classLabel=node("label","Class"),classSelect=node("select");
  const classes=classNames(value);
  for(const [i,name] of classes.entries()){
    const option=node("option",name);option.value=String(i);classSelect.append(option);
  }
  if(!alignedClasses)metricSelect.querySelector('option[value="class_recall"]')?.remove();
  const dosIndex=classes.findIndex(name=>name.toLowerCase()==="dos");
  if(dosIndex>=0)classSelect.value=String(dosIndex);
  classLabel.append(classSelect);controls.append(metricLabel,classLabel);section.append(controls);
  const drawing=node("div",undefined,"round-chart");
  const dataGrid=node("details",undefined,"round-data");
  dataGrid.append(node("summary","Round data table"));
  section.append(drawing,dataGrid);
  function redraw(){
    classLabel.classList.toggle("hidden",metricSelect.value!=="class_recall");
    drawing.replaceChildren();
    const metric=metricSelect.value,index=Number(classSelect.value||0);
    const own=roundSeries(value,metric,index),ref=baseline?roundSeries(baseline,metric,index):[];
    if(!own.length&&!ref.length){
      drawing.append(node("p","No per-round validation data available. Import results from the cluster again."));
      dataGrid.replaceChildren(node("summary","Round data table"));return;
    }
    const all=[...own,...ref],maxRound=Math.max(1,...all.map(p=>p.round));
    const ymax=metric==="loss"?Math.max(0.01,...all.map(p=>p.value))*1.05:1;
    const ymin=0,left=48,right=620,top=16,bottom=194;
    const x=r=>left+(r-1)/(Math.max(2,maxRound)-1)*(right-left);
    const y=v=>bottom-(v-ymin)/(ymax-ymin)*(bottom-top);
    const svg=svgElement("svg",{viewBox:"0 0 650 233",role:"img",
      "aria-label":"Validation "+metric+" over "+maxRound+" rounds"});
    for(let step=0;step<=4;step++){
      const val=ymin+(ymax-ymin)*step/4,sy=y(val);
      svg.append(svgElement("line",{x1:left,y1:sy,x2:right,y2:sy,class:"chart-grid"}));
      svg.append(svgElement("text",{x:left-7,y:sy+4,"text-anchor":"end",class:"chart-axis"},
        metric==="loss"?val.toFixed(2):(100*val).toFixed(0)+"%"));
    }
    svg.append(svgElement("text",{x:left,y:bottom+21,class:"chart-axis"},"1"));
    svg.append(svgElement("text",{x:right,y:bottom+21,"text-anchor":"end",class:"chart-axis"},String(maxRound)));
    for(const [data,klass] of [[ref,"chart-baseline"],[own,"chart-experiment"]]){
      if(!data.length)continue;
      const pts=data.map(point=>x(point.round).toFixed(2)+","+y(point.value).toFixed(2)).join(" ");
      svg.append(svgElement("polyline",{points:pts,class:klass}));
      if(data.length===1)svg.append(svgElement("circle",{cx:x(data[0].round),cy:y(data[0].value),r:4,class:klass}));
    }
    drawing.append(svg);
    const legend=node("p",undefined,"chart-legend");
    if(ref.length)legend.append(node("span",(manual?"A · ":"Baseline · ")+baseline.id,"legend-baseline"));
    if(own.length)legend.append(node("span",(manual?"B · ":"Experiment · ")+value.id,"legend-experiment"));
    drawing.append(legend);
    const refMap=new Map(ref.map(p=>[p.round,p.value]));
    const ownMap=new Map(own.map(p=>[p.round,p.value]));
    const rounds=[...new Set([...refMap.keys(),...ownMap.keys()])].sort((a,b)=>a-b);
    const format=v=>score(v,metric!=="loss");
    dataGrid.replaceChildren(node("summary","Round data table"),
      dataTable(["Round",...(baseline?[manual?"A":"Baseline"]:[]),manual?"B":"Experiment"],rounds.map(r=>
        [String(r),...(baseline?[format(refMap.get(r))]:[]),format(ownMap.get(r))])));
  }
  metricSelect.addEventListener("change",redraw);
  classSelect.addEventListener("change",redraw);
  redraw();return section;
}

// Manual A/B comparison is intentionally distinct from verified clean/attack pairing.
// A manual comparison must use the same classification task and verified
// prepared dataset. Identical display names or the same sample count alone
// do not prove that two datasets or label projections are equivalent.
function manualWarnings(first,second){
  const warnings=[],blockers=[];
  const ca=first.config||{},cb=second.config||{};
  const da=first.dataset_identity||{},db=second.dataset_identity||{};
  const taskA=da.task,taskB=db.task;
  const namesA=classNames(first),namesB=classNames(second);
  const sameClasses=namesA.length>=2 && namesA.length===namesB.length
    && namesA.every((name,i)=>name===namesB[i]);
  const hashesA=da.hashes||{},hashesB=db.hashes||{};
  const requiredHashes=["train","validation","test","feature_schema.json",
                        "label_mapping.json","preprocessor.json"];
  if(!ca.dataset||!cb.dataset)blockers.push("Dataset identity missing in experiment configuration.");
  else if(ca.dataset!==cb.dataset)
    blockers.push("Different datasets: "+ca.dataset+" vs "+cb.dataset+".");
  if(!taskA||!taskB)blockers.push("Classification task missing from the dataset audit.");
  else if(taskA!==taskB)
    blockers.push("Different classification tasks: "+taskA+" vs "+taskB+".");
  if(ca.dataset_params?.task && taskA && ca.dataset_params.task!==taskA)
    blockers.push("Experiment A has inconsistent classification task metadata.");
  if(cb.dataset_params?.task && taskB && cb.dataset_params.task!==taskB)
    blockers.push("Experiment B has inconsistent classification task metadata.");
  if(!sameClasses)
    blockers.push("Different or missing class labels/order (binary and multiclass cannot be compared).");
  const missingHashes=requiredHashes.filter(key=>
    typeof hashesA[key]!=="string"||!hashesA[key]||
    typeof hashesB[key]!=="string"||!hashesB[key]);
  if(missingHashes.length)blockers.push("Missing audited dataset fingerprints: "+missingHashes.join(", ")+".");
  else{
    const different=requiredHashes.filter(key=>hashesA[key]!==hashesB[key]);
    if(different.length)blockers.push("Prepared dataset files/splits differ: "+different.join(", ")+".");
  }
  const metricsA=testMetrics(first),metricsB=testMetrics(second);
  if(!metricsA||!metricsB)blockers.push("Final test metrics missing in one or both experiments.");
  const samplesA=metricsA?.samples,samplesB=metricsB?.samples;
  if(!Number.isInteger(samplesA)||!Number.isInteger(samplesB))
    blockers.push("Test sample count is missing; identical test populations cannot be verified.");
  else if(samplesA!==samplesB)
    blockers.push("Test sample counts differ: "+samplesA+" vs "+samplesB+".");
  const supportMatches=sameClasses && namesA.every(name=>{
    const a=metricsA?.per_class?.[name]?.support,b=metricsB?.per_class?.[name]?.support;
    return Number.isInteger(a)&&Number.isInteger(b)&&a===b;
  });
  if(sameClasses&&!supportMatches)
    blockers.push("Class support differs or is missing; test populations cannot be verified.");
  for(const [key,description] of [["model","model"],["partition","partition"],
                                   ["seed","random seed"],["rounds","training round cap"]]){
    if(ca[key]!==undefined && cb[key]!==undefined && JSON.stringify(ca[key])!==JSON.stringify(cb[key]))
      warnings.push("Different "+description+": "+String(ca[key])+" vs "+String(cb[key])+".");
  }
  if(first.round!==second.round)warnings.push("Runs completed different numbers of rounds.");
  if(first.pair_id&&second.pair_id&&first.pair_id!==second.pair_id)
    warnings.push("Different pair identifiers: this is not a matched clean/attack experiment.");
  if(first.status!=="complete"||second.status!=="complete")
    warnings.push("At least one run is incomplete.");
  return {warnings,blockers,compatible:blockers.length===0,sameClasses,supportMatches};
}
function manualComparison(first,second){
  const root=$("manual-comparison-output");root.replaceChildren();
  if(!first||!second)return;
  if(first.id===second.id){
    root.append(node("p","Select two different experiments.","warning"));return;
  }
  root.append(node("h4","Selected experiments · final test metrics"));
  const verified=first.baseline_id===second.id || second.baseline_id===first.id;
  const validation=manualWarnings(first,second);
  if(validation.compatible)root.append(node("p",verified?
    "Verified clean/attack pair. Δ always means B minus A; reverse the selections to change direction.":
    "Exploratory comparison, not a verified paired attack effect. Δ always means B minus A."));
  for(const warning of validation.warnings)root.append(node("p",warning,"warning"));
  if(!validation.compatible){
    root.append(node("h4","Comparison blocked · incompatible experiment data"));
    for(const reason of validation.blockers)root.append(node("p",reason,"error"));
    root.append(node("p","To compare scores, use the same audited dataset, classification task, class mapping and test split. Individual experiment reports remain available below."));
    return;
  }
  root.append(node("p","Dataset compatibility verified: matching task, labels, prepared file hashes and test class support.","comparison-verified"));
  const a=testMetrics(first),b=testMetrics(second);
  if(a&&b){
    root.append(dataTable(["Metric","A · "+first.id,"B · "+second.id,"Δ B − A"],
      RESULT_METRICS.map(([key,label,percent])=>
        [label,score(a[key],percent),score(b[key],percent),deltaScore(b[key],a[key],percent)])));
    const classes=classNames(first);
    if(validation.sameClasses && a.per_class && b.per_class){
      const section=node("section",undefined,"result-section");
      section.append(node("h4","Per-class test comparison · A vs B"));
      section.append(dataTable(["Class","A precision","B precision","Δ precision",
        "A recall","B recall","Δ recall","A F1","B F1","Δ F1"],classes.map(name=>{
        const aa=a.per_class[name]||{},bb=b.per_class[name]||{};
        return [name,score(aa.precision),score(bb.precision),deltaScore(bb.precision,aa.precision),
          score(aa.recall),score(bb.recall),deltaScore(bb.recall,aa.recall),
          score(aa["f1-score"]),score(bb["f1-score"]),
          deltaScore(bb["f1-score"],aa["f1-score"])];
      })));
      root.append(section);
    }
    const matrices=node("section",undefined,"result-section");
    matrices.append(node("h4","Test confusion matrices · side by side"));
    const columns=node("div",undefined,"manual-matrix-grid");
    for(const [tag,run] of [["A",first],["B",second]]){
      const column=node("div",undefined,"manual-matrix");
      column.append(node("strong",tag+" · "+run.id));
      const matrix=confusionSection(run);
      if(matrix)column.append(matrix);
      else column.append(node("p","Confusion matrix unavailable."));
      columns.append(column);
    }
    matrices.append(columns);root.append(matrices);
  }else root.append(node("p","Final test metrics missing in at least one experiment."));
  root.append(roundChart(second,first,true,validation.sameClasses));
  root.append(node("p","Validation curves are measured per round; test metrics are final-only. This single-run comparison is descriptive, not a statistical significance test."));
}
let availableResults=[];
function refreshManualFromChoices(){
  const items=new Map(availableResults.map(run=>[run.id,run]));
  manualComparison(items.get(chosenComparison.first),items.get(chosenComparison.second));
}
function updateManualComparison(values){
  availableResults=values;
  const firstSelect=$("compare-experiment-a"),secondSelect=$("compare-experiment-b");
  const firstPrevious=chosenComparison.first,secondPrevious=chosenComparison.second;
  const available=new Map(values.map(run=>[run.id,run]));
  const ordered=[...values].sort((a,b)=>a.id.localeCompare(b.id));
  const fallbackA=ordered.find(run=>run.config?.attack==="none")?.id||ordered[0]?.id||null;
  const fallbackB=ordered.find(run=>run.baseline_id===fallbackA)?.id
    ||ordered.find(run=>run.id!==fallbackA)?.id||null;
  chosenComparison.first=available.has(firstPrevious)?firstPrevious:fallbackA;
  chosenComparison.second=available.has(secondPrevious)?secondPrevious:fallbackB;
  for(const [select,selected] of [[firstSelect,chosenComparison.first],[secondSelect,chosenComparison.second]]){
    select.replaceChildren();
    for(const run of ordered){
      const option=node("option",run.id);option.value=run.id;select.append(option);
    }
    if(selected!==null)select.value=selected;
  }
  manualComparison(available.get(chosenComparison.first),available.get(chosenComparison.second));
}

function renderResults(values){
  const target=$("results-list"),comparison=$("result-comparisons");
  target.replaceChildren();comparison.replaceChildren();
  const byId=new Map(values.map(item=>[item.id,item]));
  updateManualComparison(values);
  const paired=values.filter(item=>item.baseline_id && byId.has(item.baseline_id));
  if(paired.length){
    comparison.append(node("h3","Paired comparisons · test split"));
    comparison.append(node("p","One row per attacked run with exactly one verified compatible clean baseline. Clean baselines are references, not additional rows. These are final TEST score differences, not round-by-round attack metrics."));
    const rows=paired.map(run=>{
      const baseline=byId.get(run.baseline_id),test=testMetrics(run),clean=testMetrics(baseline);
      return [run.id,baseline.id,run.config?.model||"—",
        deltaScore(test?.accuracy,clean?.accuracy),
        deltaScore(test?.macro_f1,clean?.macro_f1)];
    });
    comparison.append(dataTable(["Attack experiment","Clean baseline","Model","Δ accuracy","Δ macro-F1"],rows));
    comparison.append(node("p","Differences are percentage points (experiment minus clean baseline). Rounds are not independent replicates."));
  }
  if(!paired.length)comparison.append(node("p","No verified clean/attack pairs available. You can still compare any two runs manually above."));
  if(!values.length)target.append(node("p","No local results available. Import from the cluster."));
  for(const value of values){
    const baseline=value.baseline_id?byId.get(value.baseline_id):null;
    const report=node("details",undefined,"result-report");
    if(values.length===1)report.open=true;
    const heading=node("summary",undefined,"result-report-heading");
    const title=node("strong",value.id);
    const meta=node("span",(value.config?.model||"Model")+" · "+
      (value.config?.attack||"unknown")+" · "+value.status+" · round "+(value.round??"—"));
    heading.append(title,meta);report.append(heading);
    const content=node("div",undefined,"result-report-content");
    const metric=testMetrics(value);
    if(metric){
      content.append(node("h4","Final test metrics"),metricCards(metric));
      if(baseline){
        const compare=summarySection(value,baseline);
        if(compare)content.append(compare);
      }else if(value.config?.attack && value.config.attack!=="none"){
        content.append(node("p","No verified paired clean baseline available for this run."));
      }
      const cls=classMetricsSection(value,baseline);
      if(cls)content.append(cls);
      const matrix=confusionSection(value);
      if(matrix)content.append(matrix);
    }else content.append(node("p","Final test metrics are not available for this run."));
    content.append(roundChart(value,baseline));
    const raw=node("details",undefined,"result-raw");
    raw.append(node("summary","Raw final metrics"),node("pre",JSON.stringify(value.metrics,null,2)));
    content.append(raw);report.append(content);target.append(report);
  }
}
async function refreshResults(){
  const target=$("results-list");target.replaceChildren();
  try{renderResults(await request("/api/results"));}
  catch(error){$("result-comparisons").replaceChildren();
    $("manual-comparison-output").replaceChildren();target.append(node("p",error.message,"error"));}
}
async function initialize(){
  const [response,initial,tasks]=await Promise.all([request("/api/catalog"),request("/api/defaults"),request("/api/dataset-tasks")]);catalog=response.catalog;token=response.token;defaults=initial;datasetTasks=tasks;
  defaults.name="Baseline_MLP";
  for(const [key,value] of Object.entries(defaults))if($(key))$(key).value=Array.isArray(value)?value.join(","):value;
  for(const [target,entries] of Object.entries(groups))for(const [kind,field] of entries)selection(kind,field,$(target));
  $("malicious-count").value=defaults.malicious_clients.length;
  $("attack-enabled").checked=defaults.attack!=="none";
  $("mode-simple").addEventListener("click",()=>setMode("simple"));$("mode-advanced").addEventListener("click",()=>setMode("advanced"));
  $("attack-enabled").addEventListener("change",()=>{
    if($("attack-enabled").checked && $("attack").value==="none"){
      const choice=catalog.attack.find(c=>c.id!=="none");
      if(choice){$("attack").value=choice.id;$("attack").dispatchEvent(new Event("change",{bubbles:true}));}
    }
    updateExperimentName();
  });
  $("auto-experiment-name").addEventListener("change",()=>{updateExperimentName();preview();});
  updateExperimentName();
  $("malicious-selection").addEventListener("change",()=>{if($("malicious-selection").value==="ids" && !$("malicious_clients").value.trim()){const n=Number($("malicious-count").value);$("malicious_clients").value=Array.from({length:n},(_,i)=>i).join(",");}});
  initializeDefenses();
  renderComponentCatalog();
  $("catalog-status").textContent=`${catalog.attack.length-1} attacchi · componenti da file`;
  $("experiment-form").addEventListener("input",preview);$("experiment-form").addEventListener("change",preview);$("experiment-form").addEventListener("submit",event=>event.preventDefault());
  $("compare-experiment-a").addEventListener("change",()=>{
    chosenComparison.first=$("compare-experiment-a").value;refreshManualFromChoices();
  });
  $("compare-experiment-b").addEventListener("change",()=>{
    chosenComparison.second=$("compare-experiment-b").value;refreshManualFromChoices();
  });
  $("compare-swap").addEventListener("click",()=>{
    [chosenComparison.first,chosenComparison.second]=[chosenComparison.second,chosenComparison.first];
    $("compare-experiment-a").value=chosenComparison.first||"";
    $("compare-experiment-b").value=chosenComparison.second||"";
    refreshManualFromChoices();
  });
  $("validate").addEventListener("click",()=>action(false));$("save").addEventListener("click",()=>action(true));$("save-study").addEventListener("click",()=>saveStudy());$("refresh-results").addEventListener("click",refreshResults);$("sync-cluster-results").addEventListener("click",syncClusterResults);refreshClusterStatus();$("inspect-labels").addEventListener("click",inspectLabels);
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
