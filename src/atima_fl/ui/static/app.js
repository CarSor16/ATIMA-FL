"use strict";
let catalog, defaults, token;
const $ = id => document.getElementById(id);
const groups = {"data-components":[["dataset","dataset"],["partition","partition"]],"model-components":[["model","model"],["optimizer","optimizer"],["loss","loss"],["metrics","metrics"]],"attack-components":[["attack","attack"],["aggregator","aggregation"]]};
const titles = {dataset:"Dataset",partition:"Partizione",model:"Modello",optimizer:"Ottimizzatore",loss:"Loss",metrics:"Metriche",attack:"Attacco",aggregator:"Aggregazione"};
function node(tag, text, cls) { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(cls)el.className=cls; return el; }
function parameterFields(component, target, values={}) {
  target.replaceChildren();
  for(const [key,schema] of Object.entries(component.parameters)) {
    const label=node("label",schema.description || key);
    let input;
    if(schema.choices) { input=node("select"); for(const choice of schema.choices) { const option=node("option",String(choice)); option.value=String(choice); input.append(option); } }
    else { input=node("input"); input.type=["integer","number"].includes(schema.type)?"number":"text"; if(input.type==="number") { input.step=schema.type==="integer"?"1":"any"; if(schema.minimum!==undefined)input.min=schema.minimum; if(schema.maximum!==undefined)input.max=schema.maximum; } }
    const value=values[key]===undefined?schema.default:values[key]; input.value=schema.type==="array"?JSON.stringify(value):String(value);
    input.dataset.param=key; input.dataset.type=schema.type; label.append(input); target.append(label);
  }
}
function selection(kind, field, target) {
  const block=node("div",undefined,"component-block"),label=node("label",titles[kind]),select=node("select"); select.id=field;
  for(const component of catalog[kind]) { const option=node("option",component.title); option.value=component.id;select.append(option); }
  select.value=defaults[field]; label.append(select);block.append(label);
  const description=node("p",undefined,"component-description"),params=node("div",undefined,"fields");params.id=field+"_params";block.append(description,params);target.append(block);
  function refresh(){const component=catalog[kind].find(c=>c.id===select.value);description.textContent=component.description;parameterFields(component,params,select.value===defaults[field]?defaults[field+"_params"]:{});}
  select.addEventListener("change",refresh);refresh();
}
function readParams(target) { const value={}; for(const input of target.querySelectorAll("[data-param]")) { const type=input.dataset.type; value[input.dataset.param]=type==="array"?JSON.parse(input.value):["integer","number"].includes(type)?Number(input.value):type==="boolean"?input.value==="true":input.value; } return value; }
function config() {
  const value=structuredClone(defaults);
  for(const [key,initial] of Object.entries(defaults)) { const input=$(key); if(!input)continue; value[key]=typeof initial==="number"?Number(input.value):input.value; }
  value.malicious_clients=$("malicious_clients").value.trim()?$("malicious_clients").value.split(",").map(x=>Number(x.trim())):[];
  for(const entries of Object.values(groups)) for(const [,field] of entries)value[field+"_params"]=readParams($(field+"_params"));
  value.defenses=[];for(const component of catalog.defense)if($("defense-"+component.id).checked)value.defenses.push({id:component.id,params:readParams($("defense-params-"+component.id))});
  return value;
}
function preview(){try { const c=config();$("preview").textContent=JSON.stringify(c,null,2);$("selection-summary").textContent=`${c.clients} client · ${c.rounds} round · ${c.model}\n${c.attack} → ${c.aggregation}`;$("validation-status").textContent="Configurazione da verificare";$("download").classList.add("hidden"); } catch(error){$("validation-status").textContent=error.message;} }
async function request(path,body){const response=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json","X-ATIMA-Token":token},body:JSON.stringify(body)}:{});const result=await response.json();if(!response.ok)throw new Error(result.error || response.statusText);return result;}
async function action(save){$("messages").replaceChildren();try { const c=config();const checked=await request("/api/validate",c);$("validation-status").textContent="Profilo valido · dati e GPU da verificare nel job";for(const warning of checked.warnings)$("messages").append(node("p",warning,"warning"));if(save){const result=await request("/api/plans",checked.config);$("download").href=result.download;$("download").classList.remove("hidden");$("messages").append(node("p","Piano salvato. Nessun training avviato."));} } catch(error){$("validation-status").textContent="Verifica non superata";$("messages").append(node("p",error.message,"error"));} }
async function refreshResults(){const target=$("results-list");target.replaceChildren();try{const values=await request("/api/results");if(!values.length)target.append(node("p","Nessun risultato locale disponibile."));for(const value of values){const item=node("article",undefined,"result-item");item.append(node("h3",value.id),node("p",`${value.status} · round valido ${value.round ?? "—"}`),node("pre",JSON.stringify(value.metrics,null,2)));target.append(item);}}catch(error){target.append(node("p",error.message,"error"));}}
async function initialize(){
  const [response,initial]=await Promise.all([request("/api/catalog"),request("/api/defaults")]);catalog=response.catalog;token=response.token;defaults=initial;
  defaults.name="Baseline_"+new Date().toLocaleDateString("sv-SE");
  for(const [key,value] of Object.entries(defaults))if($(key))$(key).value=Array.isArray(value)?value.join(","):value;
  for(const [target,entries] of Object.entries(groups))for(const [kind,field] of entries)selection(kind,field,$(target));
  for(const component of catalog.defense){const label=node("label"),input=node("input");input.type="checkbox";input.id="defense-"+component.id;label.append(input,document.createTextNode(" "+component.title));const params=node("div",undefined,"fields");params.id="defense-params-"+component.id;parameterFields(component,params);$("defense-components").append(label,params);}
  for(const [kind,components] of Object.entries(catalog))for(const component of components){const card=node("article",undefined,"card");card.append(node("span",kind,"eyebrow"),node("h2",component.title),node("p",component.description));for(const reference of component.references){const link=node("a","Fonte scientifica");link.href=reference;link.target="_blank";link.rel="noopener";card.append(link);}$("component-list").append(card);}
  $("catalog-status").textContent=`${catalog.attack.length-1} attacchi · componenti da file`;
  $("experiment-form").addEventListener("input",preview);$("experiment-form").addEventListener("change",preview);$("experiment-form").addEventListener("submit",event=>event.preventDefault());
  $("validate").addEventListener("click",()=>action(false));$("save").addEventListener("click",()=>action(true));$("refresh-results").addEventListener("click",refreshResults);
  const pages={designer:["Disegna il tuo esperimento","Componenti intercambiabili, un profilo riproducibile."],components:["Catalogo dei componenti","Implementazioni scoperte dalle cartelle del framework."],results:["Risultati degli esperimenti","Metriche locali e stato dei run importati."],guide:["Dal progetto al cluster","Un percorso verificabile dalla configurazione all’analisi."]};
  for(const button of document.querySelectorAll(".nav"))button.addEventListener("click",()=>{for(const item of document.querySelectorAll(".nav,.page"))item.classList.remove("active");button.classList.add("active");$(button.dataset.page).classList.add("active");[$("page-title").textContent,$("page-subtitle").textContent]=pages[button.dataset.page];if(button.dataset.page==="results")refreshResults();});preview();
}
initialize().catch(error=>{$("catalog-status").textContent="Catalogo non disponibile";$("messages").append(node("p",error.message,"error"));});
