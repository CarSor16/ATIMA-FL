"use strict";
let catalog, defaults, token, datasetTasks = {};
let clusterDatasetInventory = null;
let previousLabelTask = "";
let chosenComparison = {first: null, second: null};
let mode="simple";
const $ = id => document.getElementById(id);

// The UI theme is a local presentation preference; it never enters experiment plans.
let theme = "dark";
try {
  const saved = localStorage.getItem("atima-theme");
  theme = saved === "light" || saved === "dark" ? saved : "dark";
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

// Common shell shared by every page. Navigation preserves existing form state.
const PAGE_META={
  designer:{heading:"Create a federated learning security experiment",subtitle:"Configure an FL security experiment and export a reproducible TOML plan.",crumb:"DESIGNER"},
  components:{heading:"Components",subtitle:"Registered plugins and their capabilities.",crumb:"LIBRARY"},
  results:{heading:"Results",subtitle:"Compare experiments and model performance.",crumb:"ANALYTICS"},
  guide:{heading:"Guide",subtitle:"From configuration to research evidence.",crumb:"WORKFLOW"}
};
function navigateTo(page,focusHeading=false){
  const meta=PAGE_META[page];
  if(!meta)return;
  for(const button of document.querySelectorAll(".nav")){
    const active=button.dataset.page===page;
    button.classList.toggle("active",active);
    if(active)button.setAttribute("aria-current","page");
    else button.removeAttribute("aria-current");
  }
  for(const section of document.querySelectorAll(".page"))
    section.classList.toggle("active",section.id===page);
  $("page-title").textContent=uiText(meta.heading);
  $("page-subtitle").textContent=uiText(meta.subtitle);
  $("page-breadcrumb").textContent="ATIMA-FL / "+meta.crumb;
  const icon=document.querySelector('.nav[data-page="'+page+'"] .nav-icon');
  if(icon)$("page-glyph").replaceChildren(icon.cloneNode(true));
  $("quick-new-experiment").classList.toggle("hidden",page==="designer");
  if(page==="results")refreshResults();
  if(focusHeading){
    window.scrollTo({top:0,behavior:"auto"});
    $("page-title").tabIndex=-1;
    $("page-title").focus({preventScroll:true});
  }
}
function updateResultsOverview(values){
  const root=$("results-overview");root.replaceChildren();
  const metrics=[
    [values.length,"Imported runs","Local summaries only"],
    [values.filter(run=>run.status==="complete").length,"Complete runs","Training finished"],
    [values.filter(run=>verifiedPair(run,new Map(values.map(item=>[item.id,item])))).length,"Verified pairs","Clean vs attacked"]
  ];
  for(const [count,title,detail] of metrics){
    const item=node("article",undefined,"overview-tile");
    item.append(node("span",title,"overview-label"),node("strong",String(count),"overview-number"),node("small",detail));
    root.append(item);
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
  prepared_5:["Edge-IIoT · 5 classes · Prepared macro-classes","Edge-IIoT · 5 classi · Macroclassi preparate"],
  binary:["Edge-IIoT · 2 classes · Binary","Edge-IIoT · 2 classi · Binario"],
  family_6:["Edge-IIoT · 6 classes · Attack families","Edge-IIoT · 6 classi · Famiglie di attacco"],
  fine_15:["Edge-IIoT · 15 classes · Detailed attacks","Edge-IIoT · 15 classi · Tipi di attacco"]
};
const NF_DATASETS = [
  ["nf_cicids2018","NF-CSE-CIC-IDS2018-v2"],
  ["nf_unsw_nb15","NF-UNSW-NB15-v2"],
  ["nf_botiot","NF-BoT-IoT-v2"],
  ["nf_toniot","NF-ToN-IoT-v2"]
];
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
  if(task)for(const option of task.options){
    option.textContent=readableTaskName(option.value,datasetTasks[dataset]?.[option.value]);
    if(dataset==="edge_iiot"){
      const allowed=clusterDatasetInventory?.datasets?.edge_iiot?.task_availability?.[option.value];
      option.disabled=Boolean(allowed && !allowed.available && option.value!==task.value);
      if(allowed && !allowed.available)option.textContent+=" · "+uiText("Unavailable on cluster");
    }
  }
  if($("attack")?.value==="label_flip"){
    const info=selectedTaskInfo().info;
    if(info)for(const name of ["source_class","destination_class"]){
      const select=$("attack_params")?.querySelector('[data-param="'+name+'"]');
      if(select?.tagName==="SELECT")for(const option of select.options)
        option.textContent=option.value+" · "+readableClassName(info.class_names[Number(option.value)]);
    }
  }
}

function addResearchDatasetOptions(){
  // Visible reference options are disabled until a compatible, audited ATIMA
  // data plugin exists. An NF-V2 raw CSV cannot be passed to the Edge plugin.
  const select=$("dataset");
  const group=document.createElement("optgroup");
  group.label=uiText("NF-V2 datasets · not yet executable");
  for(const [,title] of NF_DATASETS){
    for(const variant of ["Binary · 2 classes","Macro-classes · based on source Attack labels"]){
      const option=node("option",title+" · "+variant+" · "+uiText("Adapter required"));
      option.disabled=true;
      option.value="";
      group.append(option);
    }
  }
  select.append(group);
}
function renderClusterDatasetInventory(){
  const target=$("cluster-dataset-inventory");
  target.replaceChildren();
  if(!clusterDatasetInventory)return;
  const records=clusterDatasetInventory.datasets||{};
  for(const [key,title] of [["edge_iiot","Edge-IIoT"],
      ...NF_DATASETS]){
    const info=records[key];
    const card=node("article",undefined,"dataset-inventory-item");
    card.append(node("strong",title));
    if(!info){
      card.append(node("p","Path not configured in cluster workspace.","task-note"));
      if(key!=="edge_iiot")
        card.append(node("p","Binary (2 classes) · Macro-classes (Attack column) · adapter required.","task-note"));
    }else{
      card.append(node("p",info.found?"File or prepared directory found on cluster.":
        "Configured path not found on cluster.","task-note"));
      if(key==="edge_iiot"){
        const labels=info.prepared_classes;
        if(labels?.length)card.append(node("p","Prepared labels: "+labels.join(", "),"task-note"));
        if(info.source_complete){
          card.append(node("p","All split fine_label columns inspected · "+
            info.rows_scanned+" records.","task-note"));
          const available=Object.entries(info.task_availability||{}).filter(([,state])=>state.available)
            .map(([name])=>readableTaskName(name,datasetTasks.edge_iiot?.[name]));
          card.append(node("p","Verified tasks: "+(available.join(" · ")||"none"),"task-note"));
        }else card.append(node("p","Fine-label projections not verified; check remote Python pandas/pyarrow.","task-note"));
      }else{
        card.append(node("p","Binary (2 classes) and source Attack macro-labels; training adapter not installed.","task-note"));
        if(info.source_labels?.length)
          card.append(node("p","Observed in first "+info.rows_scanned+" rows: "+
            info.source_labels.join(", "),"task-note"));
      }
      if(info.note)card.append(node("p",info.note,"task-note"));
    }
    target.append(card);
  }
}
async function discoverClusterDatasets(){
  const button=$("discover-cluster-datasets"),message=$("cluster-dataset-message");
  button.disabled=true;
  message.textContent=uiText("Reading dataset metadata from the cluster over SSH…");
  try{
    clusterDatasetInventory=await request("/api/discover-cluster-datasets",{});
    renderClusterDatasetInventory();
    refreshTaskOptions();
    updateTaskUi();
    message.textContent=uiText("Cluster dataset metadata loaded. No dataset files transferred.");
  }catch(error){
    message.textContent=uiText("Cluster metadata inspection unavailable")+": "+error.message;
  }finally{button.disabled=false;}
}

function renderComponentCatalog(){
  const query=String($("component-search")?.value||"").trim().toLocaleLowerCase();
  let visible=0;
  const root=$("component-list");
  root.replaceChildren();
  for(const [index,group] of CATALOG_GROUPS.entries()){
    const section=node("details",undefined,"catalog-group");
    section.open=Boolean(query)||index===0;
    const heading=node("summary",undefined,"catalog-group-heading");
    const total=group.kinds.reduce((n,[kind])=>n+(catalog[kind]?.length||0),0);
    heading.append(node("strong",group.title),node("span",total+" "+uiText("components"),"catalog-count"));
    section.append(heading);
    const subgroups=node("div",undefined,"catalog-subgroups");
    for(const [kind,title] of group.kinds){
      const items=(catalog[kind]||[]).filter(component=>{
        if(!query)return true;
        const haystack=[component.id,component.title,component.description,
          component.translations?.it?.title,component.translations?.it?.description,
          title,group.title,...(component.threats||[])].filter(Boolean).join(" ").toLocaleLowerCase();
        return haystack.includes(query);
      });
      if(!items.length)continue;
      visible+=items.length;
      const subgroup=node("details",undefined,"catalog-subgroup");
      subgroup.open=Boolean(query);
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
        const parameters=Object.entries(component.parameters||{});
        if(parameters.length){
          const details=node("details",undefined,"plugin-parameters");details.append(node("summary","Parameters"));
          details.append(dataTable(["Parameter","Type","Default"],parameters.map(([name,parameter])=>[name,parameter.type,JSON.stringify(parameter.default)??"—"])));card.append(details);
        }
        grid.append(card);
      }
      subgroup.append(grid);subgroups.append(subgroup);
    }
    if(subgroups.children.length){section.append(subgroups);root.append(section);}
  }
  const status=$("component-search-status");
  if(status)status.textContent=uiText("Showing")+" "+visible+" "+uiText("components")+
    (query?" "+uiText("for search")+" “"+query+"”":"")+".";
  if(!visible)root.append(node("p","No components match your search.","catalog-empty"));
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
  const nfGroup=$("dataset")?.querySelector("optgroup");
  if(nfGroup){nfGroup.label=uiText("NF-V2 datasets · not yet executable");
    for(const option of nfGroup.children)if(option.value==="")option.textContent=uiText(option.textContent);
  }
  renderClusterDatasetInventory();
  renderComponentCatalog();
  $("catalog-status").textContent=currentLanguage==="en"?`${catalog.attack.length-1} attacks · components from files`:`${catalog.attack.length-1} attacchi · componenti da file`;
  $("language").value=currentLanguage;setTheme(theme);setMode(mode);
  if($("results").classList.contains("active"))renderResults(availableResults);
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
  const inspected=clusterDatasetInventory?.datasets?.[$("dataset").value];
  const state=inspected?.task_availability?.[task];
  const verified=Boolean(inspected?.source_complete && state?.available);
  const note=verified?"Labels checked against training/validation/test on cluster":
    state&&!state.available?"Task not supported by observed source labels on cluster":
    "Reference label names only · inspect the cluster to verify";
  target.append(node("strong",readableTaskName(task,info),"task-title"),
    node("span",note,"task-note"));
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
    $("cluster-indicator").classList.toggle("configured",Boolean(status.configured));
    $("side-connection-title").textContent=uiText(status.configured?"Cluster configured":"Local workspace");
    $("side-connection-detail").textContent=uiText(status.configured?
      "SSH settings present · import on demand":"SSH not configured in active workspace");
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
// Consecutive observations only: missing rounds or values create real gaps.
function roundSegments(points){
  const segments=[];
  for(const point of [...points].sort((a,b)=>a.round-b.round)){
    const last=segments.at(-1);
    if(!last || point.round!==last.at(-1).round+1)segments.push([point]);
    else last.push(point);
  }
  return segments;
}
function roundDelta(first,second){
  const reference=new Map(first.map(point=>[point.round,point.value]));
  return second.filter(point=>reference.has(point.round))
    .map(point=>({round:point.round,value:point.value-reference.get(point.round)}));
}
function choiceControl(title,choices,selected){
  const label=node("label",title),select=node("select");
  select.setAttribute("aria-label",uiText(title));
  for(const [key,text] of choices){const option=node("option",text);option.value=key;select.append(option);}
  select.value=selected;label.append(select);return {label,select};
}
function checkControl(title,checked){
  const label=node("label",undefined,"chart-check"),input=node("input");
  input.type="checkbox";input.checked=checked;label.append(input,node("span",title));
  return {label,input};
}
const chartPreferences=new Map(),classMetricPreferences=new Map();
let matrixNormalized=false;
function roundChart(value,baseline,manual=false,alignedClasses=true){
  const section=node("section",undefined,"result-section");
  section.append(node("h4","Validation metrics by round"),node("p","Validation history only · no smoothing or interpolation."));
  const controls=node("div",undefined,"round-controls");
  const metric=choiceControl("Metric",[...RESULT_METRICS.map(([key,label])=>[key,label]),
    ...(alignedClasses?[["class_recall","Class recall"]]:[])],"macro_f1");
  const preferenceKey=(baseline?.id||value.id)+"|"+(baseline?value.id:"");
  const previous=chartPreferences.get(preferenceKey)||{};
  const metricSelect=metric.select;metricSelect.value="macro_f1";
  if([...metricSelect.options].some(option=>option.value===previous.metric))metricSelect.value=previous.metric;
  const classes=classNames(baseline||value);
  const classChoice=choiceControl("Class",classes.map((name,i)=>[String(i),name]),String(Math.max(0,classes.findIndex(name=>name.toLowerCase()==="dos"))));
  if([...classChoice.select.options].some(option=>option.value===previous.classIndex))classChoice.select.value=previous.classIndex;
  const showA=checkControl("Show A",previous.showA??true),showB=checkControl("Show B",previous.showB??true),showDelta=checkControl("Show delta",previous.showDelta??false);
  showB.input.disabled=!baseline;showDelta.input.disabled=!baseline;
  if(!baseline){showB.input.checked=false;showB.label.classList.add("hidden");showDelta.label.classList.add("hidden");}
  const maxRound=Math.max(1,...[...(value?.history||[]),...(baseline?.history||[])].map(row=>row.round).filter(Number.isInteger));
  const fromLabel=node("label","From round"),toLabel=node("label","To round");
  const from=node("input"),to=node("input");
  for(const input of [from,to]){input.type="number";input.min="1";input.max=String(maxRound);input.step="1";}
  from.value=String(Math.min(maxRound,previous.from||1));to.value=String(Math.min(maxRound,previous.to||maxRound));from.setAttribute("aria-label",uiText("From round"));to.setAttribute("aria-label",uiText("To round"));
  fromLabel.append(from);toLabel.append(to);
  controls.append(metric.label,classChoice.label,showA.label,showB.label,showDelta.label,fromLabel,toLabel);
  const drawing=node("div",undefined,"round-chart"),tooltip=node("p","Hover or focus a point for its recorded value.","chart-tooltip");
  tooltip.setAttribute("role","status");
  const dataGrid=node("details",undefined,"round-data");
  section.append(controls,drawing,tooltip,dataGrid);
  function plot(series,delta=false){
    const all=series.flatMap(item=>item.points);
    if(!all.length){drawing.append(node("p","No recorded values in this range."));return;}
    const key=metricSelect.value,percent=key!=="loss"&&key!=="mcc";
    let ymin=key==="mcc"?-1:0,ymax=key==="loss"?Math.max(.01,...all.map(p=>p.value))*1.05:1;
    if(delta){const extent=Math.max(.001,...all.map(p=>Math.abs(p.value)))*1.12;ymin=-extent;ymax=extent;}
    const start=Number(from.value),end=Number(to.value),left=72,right=940,top=24,bottom=270;
    const x=r=>left+(r-start)/Math.max(1,end-start)*(right-left),y=v=>bottom-(v-ymin)/(ymax-ymin)*(bottom-top);
    const title=delta?"Validation delta · B − A":"Recorded validation values";
    const svg=svgElement("svg",{viewBox:"0 0 970 324",role:"group","aria-label":uiText(title)});
    for(let step=0;step<=4;step++){
      const val=ymin+(ymax-ymin)*step/4,sy=y(val);
      svg.append(svgElement("line",{x1:left,y1:sy,x2:right,y2:sy,class:"chart-grid"}));
      const unit=percent?(delta?" pp":"%"):"";
      svg.append(svgElement("text",{x:left-8,y:sy+4,"text-anchor":"end",class:"chart-axis"},(val*(percent?100:1)).toFixed(percent?1:2)+unit));
    }
    for(let step=0;step<=4;step++){
      const r=Math.round(start+(end-start)*step/4);
      if(step && r===Math.round(start+(end-start)*(step-1)/4))continue;
      svg.append(svgElement("text",{x:x(r),y:bottom+24,"text-anchor":"middle",class:"chart-axis"},String(r)));
    }
    svg.append(svgElement("text",{x:500,y:316,"text-anchor":"middle",class:"chart-axis"},uiText("Round")));
    svg.append(svgElement("text",{x:left,y:14,class:"chart-axis"},uiText(title)+" · "+uiText(metricSelect.selectedOptions[0].textContent)));
    for(const item of series){
      for(const segment of roundSegments(item.points))
        svg.append(svgElement("polyline",{points:segment.map(p=>x(p.round)+","+y(p.value)).join(" "),class:item.klass}));
      for(const point of item.points){
        const caption=item.label+" · "+uiText("Round")+" "+point.round+": "+(delta?deltaScore(point.value,0,percent):score(point.value,percent));
        const dot=svgElement("circle",{cx:x(point.round),cy:y(point.value),r:3,tabindex:0,class:"chart-point "+item.klass,"aria-label":caption});
        dot.append(svgElement("title",{},caption));
        for(const event of ["mouseenter","focus"])dot.addEventListener(event,()=>{tooltip.textContent=caption;});
        svg.append(dot);
      }
    }
    drawing.append(svg);
  }
  function redraw(){
    classChoice.label.classList.toggle("hidden",metricSelect.value!=="class_recall");drawing.replaceChildren();
    dataGrid.replaceChildren(node("summary","Round data table"));
    const start=Number(from.value),end=Number(to.value);
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end>maxRound||start>end){drawing.append(node("p","Choose a valid round range.","warning"));return;}
    chartPreferences.set(preferenceKey,{metric:metricSelect.value,classIndex:classChoice.select.value,showA:showA.input.checked,showB:showB.input.checked,showDelta:showDelta.input.checked,from:start,to:end});
    const select=run=>roundSeries(run,metricSelect.value,Number(classChoice.select.value||0)).filter(p=>p.round>=start&&p.round<=end);
    const a=select(baseline||value),b=baseline?select(value):[],difference=baseline?roundDelta(a,b):[];
    const series=[];
    if(showA.input.checked)series.push({label:"A · "+(baseline||value).id,klass:"chart-baseline",points:a});
    if(showB.input.checked&&baseline)series.push({label:"B · "+value.id,klass:"chart-experiment",points:b});
    if(series.length)plot(series);
    if(showDelta.input.checked&&baseline)plot([{label:"Δ B − A",klass:"chart-delta",points:difference}],true);
    if(!series.length&&!showDelta.input.checked)drawing.append(node("p","Select a series to display."));
    const legend=node("p",undefined,"chart-legend");
    for(const item of series)legend.append(node("span",item.label,item.klass==="chart-baseline"?"legend-baseline":"legend-experiment"));
    if(showDelta.input.checked)legend.append(node("span","Δ B − A","legend-delta"));drawing.append(legend);
    const am=new Map(a.map(p=>[p.round,p.value])),bm=new Map(b.map(p=>[p.round,p.value]));
    const rounds=[...new Set([...am.keys(),...bm.keys()])].sort((x,y)=>x-y);
    const percent=metricSelect.value!=="loss"&&metricSelect.value!=="mcc";
    dataGrid.append(dataTable(["Round","A",...(baseline?["B","Δ B − A"]:[])],rounds.map(r=>[r,score(am.get(r),percent),...(baseline?[score(bm.get(r),percent),deltaScore(bm.get(r),am.get(r),percent)]:[])])));
  }
  for(const input of [metricSelect,classChoice.select,showA.input,showB.input,showDelta.input,from,to])input.addEventListener("change",redraw);
  redraw();return section;
}
function manualWarnings(first,second){
  const warnings=[],blockers=[];
  const ca=first.config||{},cb=second.config||{};
  const da=first.dataset_identity||{},db=second.dataset_identity||{};
  const taskA=da.task,taskB=db.task;
  const namesA=classNames(first),namesB=classNames(second);
  const sameClasses=Array.isArray(first.classes)&&Array.isArray(second.classes)
    && first.classes.length===namesA.length && second.classes.length===namesB.length
    && first.classes.every((name,i)=>name===namesA[i]) && second.classes.every((name,i)=>name===namesB[i])
    && namesA.length>=2 && namesA.length===namesB.length
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
  if(!Number.isInteger(samplesA)||!Number.isInteger(samplesB)||samplesA<=0||samplesB<=0)
    blockers.push("Test sample count is missing; identical test populations cannot be verified.");
  else if(samplesA!==samplesB)
    blockers.push("Test sample counts differ: "+samplesA+" vs "+samplesB+".");
  const supportMatches=sameClasses && namesA.every(name=>{
    const a=metricsA?.per_class?.[name]?.support,b=metricsB?.per_class?.[name]?.support;
    return Number.isInteger(a)&&Number.isInteger(b)&&a>=0&&b>=0&&a===b;
  });
  if(sameClasses&&!supportMatches)
    blockers.push("Class support differs or is missing; test populations cannot be verified.");
  if(supportMatches && (namesA.reduce((sum,name)=>sum+metricsA.per_class[name].support,0)!==samplesA
    ||namesB.reduce((sum,name)=>sum+metricsB.per_class[name].support,0)!==samplesB))
    blockers.push("Recorded class support does not sum to the test sample count.");
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
let availableResults=[];
let analysisMode="single",analysisTab="overview";
const FILTER_KEYS=["dataset","task","model","attack","status"];
function runField(run,key){return key==="task"?run.dataset_identity?.task:key==="status"?run.status:run.config?.[key];}
function resultMatches(run,query,filters){
  const haystack=[run.id,...FILTER_KEYS.map(key=>runField(run,key))].join(" ").toLocaleLowerCase();
  return haystack.includes(query.trim().toLocaleLowerCase()) && FILTER_KEYS.every(key=>!filters[key]||runField(run,key)===filters[key]);
}
function verifiedPair(run,byId){
  const baseline=byId.get(run.baseline_id);
  if(!baseline || baseline.config?.attack!=="none" || !run.config?.attack || run.config.attack==="none"
    ||run.status!=="complete" ||baseline.status!=="complete")return false;
  const verification=manualWarnings(baseline,run);
  return verification.compatible && verification.warnings.length===0;
}
function metricDirection(key,first,second){
  if(!numeric(first)||!numeric(second))return "unavailable";
  const difference=second-first;if(Math.abs(difference)<1e-12)return "unchanged";
  return (key==="loss"?difference<0:difference>0)?"improved":"degraded";
}
function selectedRun(root,run,tag){
  root.replaceChildren();if(!run){root.append(node("p","No experiment selected."));return;}
  root.append(node("strong",run.id));
  const metadata=node("dl",undefined,"run-metadata");
  const fields=[["Dataset",run.config?.dataset],["Task",run.dataset_identity?.task],
    ["Classes",classNames(run).length||null],["Model",run.config?.model],["Attack",run.config?.attack],
    ["Status",run.status],["Rounds",run.round],["Accuracy",score(testMetrics(run)?.accuracy)],
    ["Macro-F1",score(testMetrics(run)?.macro_f1)]];
  for(const [title,value] of fields){metadata.append(node("dt",title),node("dd",value===null||value===undefined?"—":String(value)));}
  root.classList.toggle("run-b",tag==="B");root.append(metadata);
}
function performanceOverview(first,second,compatible){
  const root=$("performance-overview");root.replaceChildren();
  if(!first&&!second){root.append(node("p","Select an imported experiment to inspect its results."));return;}
  const table=node("table",undefined,"result-table performance-table"),head=node("thead"),tr=node("tr");
  for(const label of ["Metric","A",...(second?["B","Δ B − A","Classifier performance"]:[])])tr.append(node("th",label));
  head.append(tr);table.append(head);const body=node("tbody");
  for(const [key,label,percent] of RESULT_METRICS){
    const a=testMetrics(first)?.[key],b=testMetrics(second)?.[key],row=node("tr");
    row.append(node("th",label),node("td",score(a,percent)));
    if(second){
      row.append(node("td",score(b,percent)));
      const change=node("td",compatible?deltaScore(b,a,percent):"—",compatible?"metric-"+metricDirection(key,a,b):"");
      row.append(change,node("td",compatible?metricDirection(key,a,b):"Comparison blocked"));
    }
    body.append(row);
  }
  table.append(body);const wrapper=node("div",undefined,"result-table-scroll");wrapper.append(table);root.append(wrapper);
  root.append(node("p","Final test metrics · percentage deltas are percentage points; MCC and loss use numeric differences.","helper"));
  if(second)root.append(node("p","Colors describe classifier performance, not adversarial success. A single pair does not establish causality or significance.","helper"));
}
function perClassAnalysis(first,second,compatible,supportOnly=false){
  const section=node("section",undefined,"result-section");
  const choice=choiceControl("Per-class metric",[["recall","Recall"],["precision","Precision"],["f1-score","F1"],["support","Support"]],supportOnly?"support":"recall");
  const preferenceKey=first.id+"|"+(second?.id||"");
  if(!supportOnly){choice.select.value=classMetricPreferences.get(preferenceKey)||"recall";section.append(choice.label);}
  const drawing=node("div",undefined,"class-bars"),grid=node("div");section.append(drawing,grid);
  function redraw(){
    drawing.replaceChildren();grid.replaceChildren();const key=choice.select.value,percent=key!=="support";
    if(!supportOnly)classMetricPreferences.set(preferenceKey,key);
    const classes=classNames(first),a=testMetrics(first)?.per_class,b=testMetrics(second)?.per_class;
    if(!classes.length||!a){drawing.append(node("p","Recorded per-class test metrics are unavailable."));return;}
    const maximum=percent?1:Math.max(1,...classes.flatMap(name=>[a[name]?.support,...(second?[b?.[name]?.support]:[])]).filter(numeric));
    const rows=[];
    for(const name of classes){
      const aa=a[name]?.[key],bb=b?.[name]?.[key];
      const row=node("div",undefined,"class-bar-row"+(name.toLowerCase()==="dos"?" class-dos":""));
      row.append(node("strong",name));
      for(const [tag,value] of [["A",aa],...(second?[["B",bb]]:[])]){
        const track=node("div",undefined,"class-bar-track"),fill=node("span",undefined,"class-bar-fill series-"+tag.toLowerCase());
        fill.style.width=numeric(value)?Math.max(0,Math.min(100,100*value/maximum))+"%":"0%";
        track.append(fill,node("span",tag+" · "+(percent?score(value):numeric(value)?String(value):"—"),"bar-caption"));
        track.setAttribute("aria-label",name+" · "+tag+": "+(numeric(value)?String(value):uiText("unavailable")));row.append(track);
      }
      drawing.append(row);
      rows.push([name,percent?score(aa):numeric(aa)?String(aa):"—",...(second?[percent?score(bb):numeric(bb)?String(bb):"—",compatible?deltaScore(bb,aa,percent):"—"]:[])]);
    }
    const comparison=dataTable(["Class","A",...(second?["B","Δ B − A"]:[])],rows);
    if(second&&compatible&&percent){
      let worst=0,worstName=null;
      for(const [i,name] of classes.entries()){
        const aa=a[name]?.[key],bb=b?.[name]?.[key];
        if(!numeric(aa)||!numeric(bb))continue;
        const row=comparison.querySelectorAll("tbody tr")[i];
        row.lastChild.className="metric-"+metricDirection(key,aa,bb);
        if(bb-aa<worst){worst=bb-aa;worstName=name;}
      }
      if(worstName)grid.append(node("p",uiText("Largest recorded decrease")+": "+worstName+" · "+deltaScore(worst,0),"metric-degraded"));
    }
    grid.append(comparison);
    if(!supportOnly){
      const headers=["Class","Precision","Recall","F1","Support"];
      for(const [tag,run] of [["A",first],...(second?[["B",second]]:[])]){
        const metrics=testMetrics(run)?.per_class;
        grid.append(node("h4",tag+" · "+run.id),dataTable(headers,classNames(run).map(name=>[name,score(metrics?.[name]?.precision),score(metrics?.[name]?.recall),score(metrics?.[name]?.["f1-score"]),metrics?.[name]?.support??"—"])));
      }
    }
  }
  choice.select.addEventListener("change",redraw);redraw();
  section.append(node("p",supportOnly?"Recorded test support only. Training and validation distributions are not inferred.":"Recorded final test metrics. Class order follows the audited labels; DoS is highlighted when present.","helper"));
  return section;
}
function validMatrix(run){
  const classes=classNames(run),matrix=testMetrics(run)?.confusion_matrix;
  return classes.length>=2 && Array.isArray(matrix)&&matrix.length===classes.length
    &&matrix.every((row,i)=>Array.isArray(row)&&row.length===classes.length&&row.every(value=>Number.isInteger(value)&&value>=0)
      &&row.reduce((a,b)=>a+b,0)===testMetrics(run)?.per_class?.[classes[i]]?.support);
}
function matrixCells(matrix,normalized){
  return matrix.map(row=>{const total=row.reduce((a,b)=>a+b,0);return row.map(value=>normalized?(total?value/total:null):value);});
}
function matrixView(classes,matrix,title,normalized=false,difference=false){
  const column=node("section",undefined,"manual-matrix");column.append(node("h4",title));
  const wrapper=node("div",undefined,"result-table-scroll"),table=node("table",undefined,"result-table confusion-matrix");
  const head=node("thead"),header=node("tr");header.append(node("th","Real ↓ / Predicted →"));
  for(const name of classes)header.append(node("th",name));head.append(header);table.append(head);
  const maximum=Math.max(.001,...matrix.flat().filter(numeric).map(Math.abs)),body=node("tbody");
  for(const [i,row] of matrix.entries()){
    const tr=node("tr");tr.append(node("th",classes[i]));
    for(const [j,value] of row.entries()){
      const text=numeric(value)?(normalized?((value>0&&difference?"+":"")+(100*value).toFixed(1)+(difference?" pp":"%")):(value>0&&difference?"+":"")+String(value)):"—";
      const cell=node("td",text,"matrix-cell");
      // Neutral blue/purple differences: cell changes are not classifier judgments.
      const rgb=difference?(value<0?"153,126,192":"83,153,198"):"82,159,151";
      cell.style.backgroundColor=numeric(value)?"rgba("+rgb+","+(.06+.6*Math.abs(value)/maximum).toFixed(3)+")":"transparent";
      cell.title=classes[i]+" → "+classes[j]+": "+text;
      cell.setAttribute("aria-label",cell.title);cell.tabIndex=0;tr.append(cell);
    }
    body.append(tr);
  }
  table.append(body);wrapper.append(table);column.append(wrapper);return column;
}
function matrixAnalysis(first,second,compatible){
  const section=node("section",undefined,"result-section"),normal=checkControl("Normalize by true class",matrixNormalized);
  section.append(normal.label,node("p","Rows: real class · columns: predicted class. Zero-support normalized rows remain unavailable.","helper"));
  const drawing=node("div",undefined,"manual-matrix-grid");section.append(drawing);
  function redraw(){
    drawing.replaceChildren();const normalized=normal.input.checked;matrixNormalized=normalized;
    for(const [tag,run] of [["A",first],...(second?[["B",second]]:[])]){
      if(validMatrix(run))drawing.append(matrixView(classNames(run),matrixCells(testMetrics(run).confusion_matrix,normalized),tag+" · "+run.id,normalized));
      else drawing.append(node("p",tag+" · "+uiText("Confusion matrix unavailable.")));
    }
    if(second&&compatible&&validMatrix(first)&&validMatrix(second)){
      const a=matrixCells(testMetrics(first).confusion_matrix,normalized),b=matrixCells(testMetrics(second).confusion_matrix,normalized);
      const difference=b.map((row,i)=>row.map((value,j)=>numeric(value)&&numeric(a[i][j])?value-a[i][j]:null));
      drawing.append(matrixView(classNames(first),difference,"Difference matrix · B − A",normalized,true));
    }
  }
  normal.input.addEventListener("change",redraw);redraw();
  section.append(node("p","Difference colors indicate count changes, not improvement or degradation.","helper"));return section;
}
function analysisContext(){
  const byId=new Map(availableResults.map(run=>[run.id,run]));
  const first=byId.get(chosenComparison.first),second=analysisMode==="single"?null:byId.get(chosenComparison.second);
  return {first,second,compatible:Boolean(first&&second&&first.id!==second.id&&manualWarnings(first,second).compatible)};
}
function renderAnalysis(){
  const root=$("analysis-panel");root.replaceChildren();
  for(const button of document.querySelectorAll("[data-analysis-tab]")){
    const active=button.dataset.analysisTab===analysisTab;
    button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;
  }
  root.setAttribute("aria-labelledby","tab-"+analysisTab);
  const {first,second,compatible}=analysisContext();
  if(!first){root.append(node("p","Select an imported experiment to inspect its results."));return;}
  const runs=second&&!compatible?[[first,null],[second,null]]:[[first,second]];
  if(second&&!compatible)root.append(node("p","Comparison blocked · individual evidence only. No deltas or overlaid curves.","warning"));
  for(const [a,b] of runs){
    if(second&&!compatible)root.append(node("h4",a.id));
    if(analysisTab==="overview"||analysisTab==="rounds"){
      if(analysisTab==="overview")root.append(node("p","Validation curves are measured per round; test metrics are final-only. This single-run comparison is descriptive, not a statistical significance test."));
      root.append(b?roundChart(b,a,true,true):roundChart(a,null));
    }else if(analysisTab==="classes")root.append(perClassAnalysis(a,b,compatible));
    else if(analysisTab==="matrices")root.append(matrixAnalysis(a,b,compatible));
    else root.append(perClassAnalysis(a,b,compatible,true));
  }
}
function manualComparison(first,second){
  const root=$("manual-comparison-output");root.replaceChildren();
  if(!first){performanceOverview(null,null,false);renderAnalysis();return;}
  if(!second){root.append(node("p",analysisMode==="single"?"Single experiment · recorded evidence only.":"Select experiment B to compare. Only individual A evidence is shown."));performanceOverview(first,null,false);renderAnalysis();return;}
  if(first.id===second.id){root.append(node("p","Select two different experiments.","warning"));performanceOverview(first,null,false);renderAnalysis();return;}
  const validation=manualWarnings(first,second);
  const byId=new Map(availableResults.map(run=>[run.id,run]));
  const verified=(first.baseline_id===second.id && verifiedPair(first,byId))
    ||(second.baseline_id===first.id && verifiedPair(second,byId));
  if(!validation.compatible){
    root.append(node("strong","Comparison blocked · incompatible experiment data"));
    for(const reason of validation.blockers)root.append(node("p",reason,"error"));
    performanceOverview(first,second,false);renderAnalysis();return;
  }
  root.append(node("strong",verified?"Verified clean/attack pair":"Compatible dataset · descriptive A/B comparison","comparison-verified"));
  root.append(node("p",verified?"Verified clean/attack pair. Δ always means B minus A; reverse the selections to change direction.":"Exploratory comparison, not a verified paired attack effect. Δ always means B minus A."));
  for(const warning of validation.warnings)root.append(node("p",warning,"warning"));
  performanceOverview(first,second,true);renderAnalysis();
}
function currentFilters(){return Object.fromEntries(FILTER_KEYS.map(key=>[key,$("filter-"+key).value]));}
function updateFilterChoices(){
  for(const key of FILTER_KEYS){
    const select=$("filter-"+key),previous=select.value;select.replaceChildren();
    const all=node("option","All");all.value="";select.append(all);
    for(const value of [...new Set(availableResults.map(run=>runField(run,key)).filter(Boolean))].sort()){
      const option=node("option",value);option.value=value;select.append(option);
    }
    if([...select.options].some(option=>option.value===previous))select.value=previous;
  }
}
function refreshManualFromChoices(){
  updateManualComparison(availableResults);
}
function updateManualComparison(values){
  availableResults=values;const filters=currentFilters(),query=$("experiment-search").value;
  const ordered=[...values].sort((a,b)=>a.id.localeCompare(b.id));
  const visible=ordered.filter(run=>resultMatches(run,query,filters));
  const byId=new Map(values.map(run=>[run.id,run]));
  if(!visible.some(run=>run.id===chosenComparison.first))chosenComparison.first=visible.find(run=>run.config?.attack==="none")?.id||visible[0]?.id||null;
  const a=byId.get(chosenComparison.first);
  const compatibleOnly=$("only-compatible").checked;
  const optionsB=visible.filter(run=>run.id!==a?.id&&(!compatibleOnly||(a&&manualWarnings(a,run).compatible)));
  if(!optionsB.some(run=>run.id===chosenComparison.second))chosenComparison.second=optionsB.find(run=>run.baseline_id===a?.id)?.id||optionsB[0]?.id||null;
  for(const [select,items,selected] of [[$("compare-experiment-a"),visible,chosenComparison.first],[$("compare-experiment-b"),optionsB,chosenComparison.second]]){
    select.replaceChildren();const empty=node("option",items.length?"Select experiment":"No matching experiments");empty.value="";empty.disabled=true;select.append(empty);
    for(const run of items){
      const text=run.id+" · "+(run.config?.model||"—")+" · "+(run.dataset_identity?.task||"—")+" · "+uiText(run.status||"unknown");
      const option=node("option",text);option.value=run.id;select.append(option);
    }
    select.value=selected||"";
  }
  const single=analysisMode==="single",paired=analysisMode==="paired";
  $("experiment-choices").classList.toggle("single",single);
  $("experiment-b-slot").classList.toggle("hidden",single||paired);$("compare-swap").classList.toggle("hidden",single||paired);
  $("experiment-choices").classList.toggle("hidden",paired);
  $("only-compatible").disabled=single||paired;
  $("result-comparisons").classList.toggle("hidden",!paired);
  for(const button of document.querySelectorAll("[data-analysis-mode]"))button.setAttribute("aria-pressed",String(button.dataset.analysisMode===analysisMode));
  $("experiment-filter-status").textContent=visible.length+" / "+values.length+" "+uiText("experiments")+(compatibleOnly&&!single&&!paired?" · "+optionsB.length+" "+uiText("compatible with A"):"");
  const b=byId.get(chosenComparison.second);selectedRun($("experiment-a-metadata"),a,"A");selectedRun($("experiment-b-metadata"),b,"B");
  if(paired){$("manual-comparison-output").replaceChildren(node("p","Choose a verified pair to open its A/B analysis."));performanceOverview(null,null,false);$("analysis-panel").replaceChildren(node("p","Choose a verified pair to open its A/B analysis."));}
  else manualComparison(a,single?null:b);
  renderPairedTable(visible,byId);
}
function clearResultFilters(){
  $("experiment-search").value="";for(const key of FILTER_KEYS)$("filter-"+key).value="";$("only-compatible").checked=false;
}
function renderPairedTable(values,byId){
  const root=$("result-comparisons");root.replaceChildren();
  const paired=values.filter(run=>verifiedPair(run,byId));
  if(!paired.length){root.append(node("p","No verified clean/attack pairs available. Individual reports remain available."));return;}
  root.append(node("p","Delta = attacked − clean baseline. Only backend-associated, dataset-compatible pairs are listed."));
  const classes=[...new Set(paired.flatMap(classNames))];
  const metric=choiceControl("Per-class metric",[["recall","Recall"],["precision","Precision"],["f1-score","F1"]],"recall");
  const cls=choiceControl("Class",classes.map(name=>[name,name]),classes.find(name=>name.toLowerCase()==="dos")||classes[0]);
  const controls=node("div",undefined,"round-controls"),tableRoot=node("div");controls.append(metric.label,cls.label);root.append(controls,tableRoot);
  function redraw(){
    tableRoot.replaceChildren();const table=dataTable(["Attack experiment","Clean baseline","Model","Dataset / task","Δ accuracy","Δ macro-F1","Per-class delta","Verification"],paired.map(run=>{
      const clean=byId.get(run.baseline_id),a=testMetrics(clean),b=testMetrics(run);
      return [run.id,clean.id,run.config?.model||"—",[run.config?.dataset,run.dataset_identity?.task].filter(Boolean).join(" / "),deltaScore(b?.accuracy,a?.accuracy),deltaScore(b?.macro_f1,a?.macro_f1),cls.select.value+" · "+deltaScore(b?.per_class?.[cls.select.value]?.[metric.select.value],a?.per_class?.[cls.select.value]?.[metric.select.value]),"Verified"];
    }));
    for(const [i,row] of [...table.querySelectorAll("tbody tr")].entries()){
      const run=paired[i],button=node("button",run.id,"pair-link");button.type="button";
      button.addEventListener("click",()=>{
        clearResultFilters();analysisMode="ab";chosenComparison={first:run.baseline_id,second:run.id};refreshManualFromChoices();
        $("performance-heading").tabIndex=-1;$("performance-heading").focus();
      });row.firstChild.replaceChildren(button);
    }
    tableRoot.append(table);
  }
  metric.select.addEventListener("change",redraw);cls.select.addEventListener("change",redraw);redraw();
}
function renderResults(values){
  const target=$("results-list");target.replaceChildren();
  availableResults=values;updateResultsOverview(values);updateFilterChoices();updateManualComparison(values);
  if(!values.length)target.append(node("p","No local results available. Import from the cluster."));
  for(const value of values){
    const report=node("details",undefined,"result-report"),heading=node("summary",undefined,"result-report-heading");
    heading.append(node("strong",value.id),node("span",[value.config?.model,value.config?.attack,value.status,uiText("Round")+" "+(value.round??"—")].filter(Boolean).join(" · ")));report.append(heading);
    let rendered=false;
    report.addEventListener("toggle",()=>{
      if(!report.open||rendered)return;rendered=true;
      const content=node("div",undefined,"result-report-content"),metric=testMetrics(value);
      if(metric)content.append(node("h4","Final test metrics"),metricCards(metric));
      else content.append(node("p","Final test metrics are not available for this run."));
      content.append(perClassAnalysis(value,null,false),matrixAnalysis(value,null,false),roundChart(value,null));
      const raw=node("details",undefined,"result-raw");raw.append(node("summary","Raw final metrics"),node("pre",JSON.stringify(value.metrics,null,2)));content.append(raw);report.append(content);
    });target.append(report);
  }
}
function initializeAnalysisControls(){
  for(const button of document.querySelectorAll("[data-analysis-mode]"))button.addEventListener("click",()=>{analysisMode=button.dataset.analysisMode;refreshManualFromChoices();});
  for(const key of FILTER_KEYS)$("filter-"+key).addEventListener("change",refreshManualFromChoices);
  $("experiment-search").addEventListener("input",refreshManualFromChoices);
  $("only-compatible").addEventListener("change",refreshManualFromChoices);
  $("clear-result-filters").addEventListener("click",()=>{clearResultFilters();refreshManualFromChoices();});
  const tabs=[...document.querySelectorAll("[data-analysis-tab]")];
  for(const [index,button] of tabs.entries()){
    button.addEventListener("click",()=>{analysisTab=button.dataset.analysisTab;renderAnalysis();});
    button.addEventListener("keydown",event=>{
      const next=event.key==="ArrowRight"?(index+1)%tabs.length:event.key==="ArrowLeft"?(index+tabs.length-1)%tabs.length:event.key==="Home"?0:event.key==="End"?tabs.length-1:null;
      if(next===null)return;event.preventDefault();analysisTab=tabs[next].dataset.analysisTab;renderAnalysis();tabs[next].focus();
    });
  }
}
let resultsRequestId=0;
async function refreshResults(){
  const requestId=++resultsRequestId,target=$("results-list"),button=$("refresh-results");
  button.disabled=true;$("results").setAttribute("aria-busy","true");
  $("experiment-filter-status").textContent=uiText("Loading results…");
  try{
    const values=await request("/api/results");
    if(requestId===resultsRequestId)renderResults(values);
  }catch(error){
    if(requestId!==resultsRequestId)return;
    renderResults([]);target.replaceChildren(node("p",error.message,"error"));
    $("manual-comparison-output").replaceChildren(node("p",error.message,"error"));
  }finally{
    if(requestId===resultsRequestId){button.disabled=false;$("results").setAttribute("aria-busy","false");}
  }
}
async function initialize(){
  const [response,initial,tasks]=await Promise.all([request("/api/catalog"),request("/api/defaults"),request("/api/dataset-tasks")]);catalog=response.catalog;token=response.token;defaults=initial;datasetTasks=tasks;
  defaults.name="Baseline_MLP";
  for(const [key,value] of Object.entries(defaults))if($(key))$(key).value=Array.isArray(value)?value.join(","):value;
  for(const [target,entries] of Object.entries(groups))for(const [kind,field] of entries)selection(kind,field,$(target));
  addResearchDatasetOptions();
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
  $("discover-cluster-datasets").addEventListener("click",discoverClusterDatasets);
  $("auto-experiment-name").addEventListener("change",()=>{updateExperimentName();preview();});
  updateExperimentName();
  $("malicious-selection").addEventListener("change",()=>{if($("malicious-selection").value==="ids" && !$("malicious_clients").value.trim()){const n=Number($("malicious-count").value);$("malicious_clients").value=Array.from({length:n},(_,i)=>i).join(",");}});
  initializeDefenses();
  renderComponentCatalog();
  initializeAnalysisControls();
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
  $("component-search").addEventListener("input",renderComponentCatalog);
  for(const button of document.querySelectorAll(".nav"))
    button.addEventListener("click",()=>navigateTo(button.dataset.page,true));
  for(const button of document.querySelectorAll("[data-page-target]"))
    button.addEventListener("click",()=>navigateTo(button.dataset.pageTarget,true));
  $("quick-new-experiment").addEventListener("click",()=>navigateTo("designer",true));$("language").addEventListener("change",()=>{currentLanguage=$("language").value;try{localStorage.setItem("atima-language",currentLanguage);}catch{}refreshLanguage();});refreshLanguage();
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
