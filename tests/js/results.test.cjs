// Functional presentation tests. These small fixtures are never production results.
const assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const base=path.resolve(__dirname,"../../src/atima_fl/ui/static");
class Element{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.style={};this.listeners={};this.className="";this._text="";this._value="";this.checked=false;this.disabled=false;this.classList={toggle:(name,force)=>{let tokens=new Set(this.className.split(/\s+/).filter(Boolean));const enabled=force??!tokens.has(name);enabled?tokens.add(name):tokens.delete(name);this.className=[...tokens].join(" ");return enabled;},add:name=>this.classList.toggle(name,true),contains:name=>this.className.split(/\s+/).includes(name)};}
  append(...nodes){for(const child of nodes){child.parentElement=this;this.children.push(child);}}
  replaceChildren(...nodes){this.children=[];this._text="";this.append(...nodes);}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join("");}
  get firstChild(){return this.children[0];}
  get lastChild(){return this.children.at(-1);}
  get options(){return this.children.filter(child=>child.tagName==="OPTION");}
  get selectedOptions(){return this.options.filter(option=>option.value===this.value);}
  set value(value){this._value=String(value);}
  get value(){return this._value;}
  setAttribute(key,value){this.attributes[key]=String(value);if(key==="class")this.className=String(value);if(key.startsWith("data-"))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(value);}
  getAttribute(key){return this.attributes[key]??null;}
  addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);}
  dispatch(event){for(const fn of this.listeners[event]||[])fn({key:"",preventDefault(){}});}
  focus(){this.focused=true;}
  descendants(){return this.children.flatMap(child=>[child,...child.descendants()]);}
  matches(selector){if(selector.startsWith("["))return this.attributes[selector.slice(1,-1)]!==undefined;if(selector.startsWith("."))return this.classList.contains(selector.slice(1));return this.tagName===selector.toUpperCase();}
  querySelectorAll(selector){const parts=selector.split(" ");return this.descendants().filter(child=>{if(!child.matches(parts.at(-1)))return false;let parent=child.parentElement;for(let i=parts.length-2;i>=0;i--){while(parent&&!parent.matches(parts[i]))parent=parent.parentElement;if(!parent)return false;parent=parent.parentElement;}return true;});}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const ids=new Map(),body=new Element("body"),html=fs.readFileSync(path.join(base,"index.html"),"utf8");
for(const match of html.matchAll(/<([a-z]+)([^>]*id="([^"]+)"[^>]*)>/g)){
  const element=new Element(match[1]);element.id=match[3];for(const attr of match[2].matchAll(/([\w-]+)="([^"]*)"/g))element.setAttribute(attr[1],attr[2]);ids.set(element.id,element);body.append(element);
}
for(const match of html.matchAll(/<button[^>]*(data-analysis-mode="([^"]+)"[^>]*|data-analysis-tab="([^"]+)"[^>]*)>/g)){
  if(match[3])continue;const element=new Element("button");element.setAttribute("data-analysis-mode",match[2]);body.append(element);
}
const document={body,documentElement:{dataset:{}},getElementById:id=>ids.get(id),createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelectorAll:selector=>body.querySelectorAll(selector)};
const context=vm.createContext({document,localStorage:{getItem(){return null;}},console});
vm.runInContext(fs.readFileSync(path.join(base,"i18n.js"),"utf8"),context);
const source=fs.readFileSync(path.join(base,"app.js"),"utf8").split("\nsetTheme(theme);\n")[0];vm.runInContext(source,context);
const evaluate=script=>vm.runInContext(script,context),plain=value=>JSON.parse(JSON.stringify(value));
function run(id,attack="none"){
  return {id,status:"complete",round:5,classes:["benign","dos"],config:{dataset:"edge_iiot",model:"mlp",attack,seed:1,rounds:5,dataset_params:{task:"prepared_5"}},dataset_identity:{task:"prepared_5",hashes:Object.fromEntries(["train","validation","test","feature_schema.json","label_mapping.json","preprocessor.json"].map(key=>[key,key+"-same"]))},metrics:{test:{accuracy:.6,macro_f1:.55,weighted_f1:.57,balanced_accuracy:.58,mcc:.2,loss:.9,samples:5,per_class:{benign:{precision:.7,recall:2/3,"f1-score":.6,support:3},dos:{precision:.5,recall:.5,"f1-score":.5,support:2}},confusion_matrix:[[2,1],[1,1]]}},history:[{round:1,macro_f1:.7,loss:.8},{round:3,macro_f1:.6,loss:.9},{round:4,loss:1},{round:5,macro_f1:.8,loss:.7}]};
}
context.a=run("Baseline_MLP");context.b=run("LabelFlip_MLP","label_flip");context.b.baseline_id=context.a.id;
let checks=0;function check(name,fn){fn();checks++;console.log("OK "+name);}
check("paired metadata is still subject to dataset compatibility",()=>{assert.equal(evaluate("manualWarnings(a,b).compatible"),true);context.bad=structuredClone(context.b);context.bad.dataset_identity.hashes.test="different";assert.equal(evaluate("manualWarnings(a,bad).compatible"),false);assert.equal(evaluate("verifiedPair(bad,new Map([[a.id,a]]))"),false);context.bad=structuredClone(context.b);context.bad.config.model="lopez_cnn";assert.equal(evaluate("manualWarnings(a,bad).compatible"),true);assert.equal(evaluate("verifiedPair(bad,new Map([[a.id,a]]))"),false);});
check("missing audit, task/order/support/sample mismatches fail closed",()=>{
  for(const mutate of [r=>delete r.dataset_identity.task,r=>r.dataset_identity.task="binary",r=>r.classes.reverse(),r=>delete r.classes,r=>r.metrics.test.samples=6,r=>r.metrics.test.per_class.dos.support=3,r=>delete r.dataset_identity.hashes.train]){
    context.bad=structuredClone(context.b);mutate(context.bad);assert.equal(evaluate("manualWarnings(a,bad).compatible"),false);
  }
});
check("matching wrong support totals are blocked",()=>{context.aa=structuredClone(context.a);context.bb=structuredClone(context.b);context.aa.metrics.test.samples=context.bb.metrics.test.samples=10;assert.equal(evaluate("manualWarnings(aa,bb).compatible"),false);});
check("percentage points, numeric MCC/loss, improvement directions and absent values",()=>{assert.equal(evaluate("deltaScore(.7,.8)"),"-10.00 pp");assert.equal(evaluate("deltaScore(.9,.8,false)"),"+0.1000");assert.equal(evaluate("metricDirection('loss',.9,.7)"),"improved");assert.equal(evaluate("metricDirection('macro_f1',.9,.7)"),"degraded");assert.equal(evaluate("metricDirection('mcc',null,.2)"),"unavailable");assert.equal(evaluate("deltaScore(null,.8)"),"—");});
check("search/filter matches recorded metadata only",()=>{assert.equal(evaluate("resultMatches(b,'LABELFLIP',{model:'mlp'})"),true);assert.equal(evaluate("resultMatches(b,'',{model:'lopez_cnn'})"),false);assert.equal(evaluate("resultMatches(b,'',{task:'binary'})"),false);});
check("missing validation observations create gaps and delta uses common rounds",()=>{assert.deepEqual(plain(evaluate("roundSegments(roundSeries(a,'macro_f1',0)).map(segment=>segment.map(p=>p.round))")),[[1],[3],[5]]);assert.deepEqual(plain(evaluate("roundDelta([{round:1,value:.8},{round:3,value:.7}],[{round:2,value:.9},{round:3,value:.5}])")),[{round:3,value:-.19999999999999996}]);});
check("validation chart has separate delta scale, range checks, keyboard points and real controls",()=>{
  const chart=evaluate("roundChart(b,a,true,true)");assert.equal(chart.querySelectorAll("polyline").length,6);assert.equal(chart.querySelectorAll("circle").length,6);
  const boxes=chart.querySelectorAll("input");boxes[2].checked=true;boxes[2].dispatch("change");assert.equal(chart.querySelectorAll("svg").length,2);
  boxes[3].value="3";boxes[4].value="3";boxes[4].dispatch("change");assert.equal(chart.querySelectorAll("circle").length,3);
  const point=chart.querySelector("circle");point.dispatch("focus");assert.ok(chart.textContent.includes("Round 3: 60.00%"));
  boxes[3].value="4";boxes[4].dispatch("change");assert.equal(chart.querySelectorAll("svg").length,0);assert.ok(chart.textContent.includes("valid round range"));
});
check("normalized zero rows remain missing, matrix differences are neutral and gated",()=>{
  assert.deepEqual(plain(evaluate("matrixCells([[0,0],[1,3]],true)")),[[null,null],[.25,.75]]);
  let view=evaluate("matrixAnalysis(a,b,true)");assert.equal(view.querySelectorAll("table").length,3);assert.ok(view.textContent.includes("Difference matrix"));view.querySelector("input").checked=true;view.querySelector("input").dispatch("change");assert.ok(view.textContent.includes("pp"));
  view=evaluate("matrixAnalysis(a,b,false)");assert.equal(view.querySelectorAll("table").length,2);assert.ok(!view.textContent.includes("Difference matrix"));
  context.bad=structuredClone(context.b);context.bad.metrics.test.confusion_matrix[0][0]=900;assert.equal(evaluate("validMatrix(bad)"),false);
});
check("per-class plot uses audited order and selectable precision/recall/F1/support",()=>{const view=evaluate("perClassAnalysis(a,b,true)");assert.equal(view.querySelectorAll("select")[0].options.length,4);assert.ok(view.querySelectorAll("strong").find(item=>item.textContent==="dos"));const select=view.querySelector("select");select.value="support";select.dispatch("change");assert.ok(view.textContent.includes("A · 3"));const support=evaluate("perClassAnalysis(a,null,false,true)");assert.equal(support.querySelectorAll("select").length,0);assert.ok(support.textContent.includes("Recorded test support only"));});
check("mode/filter/verified pair opens real A/B and incompatible imports stay individual",()=>{
  evaluate("analysisMode='ab';availableResults=[a,b];chosenComparison={first:a.id,second:b.id};updateFilterChoices();initializeAnalysisControls();updateManualComparison(availableResults)");assert.ok(ids.get("performance-overview").textContent.includes("Δ B − A"));
  const pair=ids.get("result-comparisons").querySelector("button");pair.dispatch("click");assert.equal(evaluate("analysisMode"),"ab");assert.equal(evaluate("chosenComparison.first"),context.a.id);
  context.third=structuredClone(context.a);context.third.id="Other_Clean";
  evaluate("availableResults=[a,b,third];chosenComparison={first:b.id,second:third.id};updateManualComparison(availableResults)");assert.ok(ids.get("manual-comparison-output").textContent.includes("descriptive A/B"));
  ids.get("filter-model").value="no-model";evaluate("refreshManualFromChoices()");assert.equal(ids.get("compare-experiment-a").options.length,1);assert.ok(ids.get("analysis-panel").textContent.includes("Select an imported"));
  delete context.bad.dataset_identity.task;
  evaluate("clearResultFilters();availableResults=[a,bad];chosenComparison={first:a.id,second:bad.id};updateManualComparison(availableResults)");assert.ok(ids.get("manual-comparison-output").textContent.includes("Comparison blocked"));assert.equal(ids.get("analysis-panel").querySelectorAll("svg").length,2);assert.ok(!ids.get("analysis-panel").textContent.includes("Δ B − A"));
});
check("Italian renders current controls and numeric semantics without modifying runs",()=>{const before=JSON.stringify(context.a);evaluate("currentLanguage='it';performanceOverview(a,b,true)");assert.ok(ids.get("performance-overview").textContent.includes("Prestazioni del classificatore"));assert.ok(ids.get("performance-overview").textContent.includes("migliorate")||ids.get("performance-overview").textContent.includes("invariate"));assert.equal(JSON.stringify(context.a),before);});
check("only-compatible filter and saved view controls survive local refresh",()=>{
  context.bad=structuredClone(context.b);context.bad.id="Other_Task";context.bad.dataset_identity.task="binary";
  evaluate("currentLanguage='en';clearResultFilters();analysisMode='ab';availableResults=[a,b,bad];chosenComparison={first:a.id,second:bad.id};updateFilterChoices();updateManualComparison(availableResults)");
  ids.get("only-compatible").checked=true;evaluate("refreshManualFromChoices()");assert.equal(evaluate("chosenComparison.second"),context.b.id);assert.equal(ids.get("compare-experiment-b").options.length,2);
  const tab=ids.get("tab-classes");tab.dispatch("click");let choice=ids.get("analysis-panel").querySelector("select");choice.value="precision";choice.dispatch("change");evaluate("renderAnalysis()");assert.equal(ids.get("analysis-panel").querySelector("select").value,"precision");
  evaluate("matrixNormalized=true");assert.equal(evaluate("matrixAnalysis(a,b,true)").querySelector("input").checked,true);
});
console.log(checks+" functional Results checks passed.");
