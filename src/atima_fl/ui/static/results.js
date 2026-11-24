"use strict";

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
function supportedClassEntries(test){
  return Object.entries(test.per_class||{}).filter(([,v])=>numeric(v?.support)&&v.support>0&&numeric(v?.recall));
}
function average(values){
  return values.length ? values.reduce((sum,value)=>sum+value,0)/values.length : null;
}
// Additional scores are derived from recorded test evidence, never fabricated.
const DERIVED_METRICS = [
  ["macro_precision","Macro precision",true],
  ["worst_supported_recall","Worst class recall",true],
  ["intrusion_miss_rate","Macro intrusion classification error",true],
  ["benign_false_alarm_rate","Benign false-alarm rate",true]
];
const FINAL_METRICS = [...RESULT_METRICS,...DERIVED_METRICS];
function testMetrics(value){
  const test=value?.metrics?.test||null;
  if(!test)return null;
  const entries=Object.entries(test.per_class||{});
  const supported=supportedClassEntries(test);
  const intrusions=supported.filter(([name])=>!/^(benign|normal)$/i.test(name));
  const benign=entries.find(([name])=>/^(benign|normal)$/i.test(name));
  return {...test,
    macro_precision:average(entries.filter(([,v])=>numeric(v?.precision)).map(([,v])=>v.precision)),
    worst_supported_recall:supported.length?Math.min(...supported.map(([,v])=>v.recall)):null,
    // Legacy key: 1-recall includes confusion between different intrusion families.
    intrusion_miss_rate:benign&&intrusions.length
      ?average(intrusions.map(([,v])=>1-v.recall)):null,
    benign_false_alarm_rate:benign&&numeric(benign[1]?.support)&&benign[1].support>0&&numeric(benign[1]?.recall)
      ?1-benign[1].recall:null
  };
}
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
  for(const [key,label,percent] of FINAL_METRICS){
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
  const zoomIn=node("button","Zoom +","chart-action"),zoomOut=node("button","Zoom −","chart-action"),
    zoomReset=node("button","Reset zoom","chart-action");
  for(const b of [zoomIn,zoomOut,zoomReset])b.type="button";
  const autoscale=checkControl("Focus Y axis",previous.autoscale??false);
  controls.append(zoomIn,zoomOut,zoomReset,autoscale.label);
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
    else if(autoscale.input.checked){
      const lo=Math.min(...all.map(p=>p.value)),hi=Math.max(...all.map(p=>p.value));
      const padding=Math.max(1e-4,(hi-lo)*.12);
      ymin=lo-padding;ymax=hi+padding;
      if(key!=="mcc"&&key!=="loss"){ymin=Math.max(0,ymin);ymax=Math.min(1,ymax);}
      if(ymax<=ymin)ymax=ymin+1e-4;
    }
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
    chartPreferences.set(preferenceKey,{metric:metricSelect.value,classIndex:classChoice.select.value,showA:showA.input.checked,showB:showB.input.checked,showDelta:showDelta.input.checked,from:start,to:end,autoscale:autoscale.input.checked});
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
  for(const input of [metricSelect,classChoice.select,showA.input,showB.input,showDelta.input,from,to,autoscale.input])input.addEventListener("change",redraw);
  function zoom(ratio){
    const start=Number(from.value),end=Number(to.value);
    if(!Number.isInteger(start)||!Number.isInteger(end)||start>end)return;
    const span=Math.max(1,Math.min(maxRound,Math.round((end-start+1)*ratio)));
    const center=(start+end)/2;
    let nextFrom=Math.max(1,Math.round(center-(span-1)/2));
    nextFrom=Math.min(nextFrom,maxRound-span+1);
    from.value=String(nextFrom);to.value=String(nextFrom+span-1);redraw();
  }
  zoomIn.addEventListener("click",()=>zoom(.5));
  zoomOut.addEventListener("click",()=>zoom(2));
  zoomReset.addEventListener("click",()=>{from.value="1";to.value=String(maxRound);redraw();});
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
  return (["loss","intrusion_miss_rate","benign_false_alarm_rate"].includes(key)?difference<0:difference>0)?"improved":"degraded";
}
function selectedRun(root,run,tag){
  root.replaceChildren();if(!run){root.append(node("p","No experiment selected."));return;}
  root.append(node("strong",run.id));
  const metadata=node("dl",undefined,"run-metadata");
  const fields=[["Dataset",run.config?.dataset],["Task",run.dataset_identity?.task],
    ["Classes",classNames(run).length||null],["Model",run.config?.model],
     ["Partition",run.config?.partition],["Aggregator",run.config?.aggregation],
     ["Clients",run.config?.clients],["Attack",run.config?.attack],
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
  for(const [key,label,percent] of FINAL_METRICS){
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
    &&matrix.every((row,i)=>Array.isArray(row)&&row.length===classes.length&&row.every(value=>Number.isSafeInteger(value)&&value>=0)
      &&Number.isSafeInteger(row.reduce((a,b)=>a+b,0))
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
    }else if(analysisTab==="federated")root.append(federatedAnalysis(a,b));
    else if(analysisTab==="classes")root.append(perClassAnalysis(a,b,compatible));
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
// Research-focus scope comes from the supplied 3-task comparison graphs.
// It is an *optional view* and does not change the runtime attack catalog.
// ClientDropout appears in the figure notes as an availability outcome,
// not an ordinary final-classification attack; it remains visible with focus off.
const RESEARCH_GRAPH_ATTACKS=[
  ["class_withholding","ClassWithholding"],
  ["local_class_gradient","LocalClassGradient"],
  ["model_replacement","ModelReplacement"],
  ["sample_weight_hijack","SampleWeightHijack"],
  ["stale_replay","StaleReplay"],
  ["update_scaling","UpdateScaling x5"],
  ["poisoned_fl","PoisonedFL (historical adaptation)"],
  ["free_rider","FreeRider"],
  ["label_flip","LabelFlip to benign"]
];
let researchFocusInitialized=false;
const researchFocusSelected=new Set(RESEARCH_GRAPH_ATTACKS.map(([id])=>id));
function setupResearchFocus(){
  if(researchFocusInitialized)return;
  researchFocusInitialized=true;
  const list=$("research-focus-choices");
  for(const [id,label] of RESEARCH_GRAPH_ATTACKS){
    const line=node("label",undefined,"research-focus-choice");
    const checkbox=node("input");checkbox.type="checkbox";checkbox.checked=true;
    checkbox.setAttribute("aria-label","Include "+label+" in research focus");
    checkbox.addEventListener("change",()=>{
      if(checkbox.checked)researchFocusSelected.add(id);
      else researchFocusSelected.delete(id);
      renderResults(availableResults);
    });
    line.append(checkbox,node("span",label));list.append(line);
  }
  $("research-focus-enabled").addEventListener("change",()=>renderResults(availableResults));
  $("group-results-enabled").addEventListener("change",()=>renderResults(availableResults));
}
function researchFocusedRun(run){
  if(!$("research-focus-enabled").checked)return true;
  const id=String(run.group?.attack||run.config?.attack||"").toLowerCase();
  // Clean remains visible to inspect the original baseline. Verified pairing
  // and manual A/B comparisons do not inherit this presentation-only filter.
  return id==="none"||researchFocusSelected.has(id);
}
// Multi-seed evidence is descriptive and never substitutes for trajectory-verified CLI statistics.
function seedStats(values){return ATIMAAnalysis.stats(values);}
function seedCohorts(values){
  const groups=new Map(),excluded=[];
  for(const run of values){
    const condition=run.seed_condition;
    if(run.status!=="complete"||!condition?.key||!Number.isInteger(run.config?.seed)
      ||!manualWarnings(run,run).compatible){
      excluded.push({id:run.id,reason:condition?.reason||"Missing or invalid final test evidence"});
      continue;
    }
    const test=testMetrics(run);
    const population=JSON.stringify([test.samples,classNames(run).map(name=>test.per_class[name].support)]);
    const key=condition.key+"|"+population;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(run);
  }
  return {groups,excluded};
}
function seedBuckets(runs){
  const buckets=new Map();
  for(const run of runs){
    const seed=run.config.seed;
    if(!buckets.has(seed))buckets.set(seed,[]);
    buckets.get(seed).push(run);
  }
  return [...buckets].sort((a,b)=>a[0]-b[0]);
}
function seedRoundStats(runs,metric){
  const byRound=new Map();
  for(const run of runs){
    const distinct=new Map(roundSeries(run,metric,0).map(p=>[p.round,p.value]));
    for(const [round,value] of distinct){
      if(!byRound.has(round))byRound.set(round,[]);
      byRound.get(round).push(value);
    }
  }
  return [...byRound].sort((a,b)=>a[0]-b[0]).map(([round,values])=>({round,...seedStats(values)}));
}
function seedEvasion(run,name=null){
  if(!validMatrix(run))return null;
  const classes=classNames(run),benign=classes.findIndex(c=>/^(benign|normal)$/i.test(c));
  if(benign<0)return null;
  const matrix=testMetrics(run).confusion_matrix;
  const rows=classes.map((c,i)=>i).filter(i=>i!==benign&&(name===null||classes[i]===name));
  const total=rows.reduce((sum,i)=>sum+matrix[i].reduce((a,b)=>a+b,0),0);
  return total?rows.reduce((sum,i)=>sum+matrix[i][benign],0)/total:null;
}
function seedMetricRows(runs,descriptors,delta=false){
  return descriptors.map(([label,get,percent])=>{
    const v=seedStats(runs.map(get));
    const format=value=>delta&&percent?(numeric(value)?(100*value).toFixed(2)+" pp":"—"):score(value,percent);
    return [label,format(v.mean),format(v.sd),format(v.min),format(v.max),v.n+"/"+runs.length];
  });
}
function seedCurve(runs,cleans=[]){
  const root=node("section",undefined,"seed-block");
  root.append(node("h4",cleans.length?"Matched mean validation trajectories: clean vs attack":"Mean validation trajectory"));
  const metrics=RESULT_METRICS.map(([key,label])=>[key,label]);
  const metric=choiceControl("Validation metric",metrics,"macro_f1"),body=node("div");
  const bands=checkControl("Show variability (±1 sample SD)",true);
  root.append(metric.label,bands.label,body);
  function redraw(){
    body.replaceChildren();
    const key=metric.select.value,percent=key!=="loss"&&key!=="mcc";
    const rows=seedRoundStats(runs,key);
    if(!rows.length){body.append(node("p","No recorded validation observations for this metric."));return;}
    // Plot only full-cohort points; partial observations remain visible in the table.
    const cleanRows=seedRoundStats(cleans,key),cleanByRound=new Map(cleanRows.map(row=>[row.round,row]));
    const full=rows.filter(row=>row.n===runs.length&&(!cleans.length||cleanByRound.get(row.round)?.n===cleans.length));
    const cleanFull=full.map(row=>cleanByRound.get(row.round)).filter(Boolean);
    const bounds=[...rows,...cleanRows];
    const extent=bounds.flatMap(row=>bands.input.checked&&numeric(row.sd)?[row.min,row.max,row.mean-row.sd,row.mean+row.sd]:[row.min,row.max]);
    const lo=percent?0:Math.min(0,...extent);
    const hi=percent?1:Math.max(lo+.001,...extent);
    const maxRound=Math.max(1,...rows.map(r=>r.round));
    const x=round=>52+(round-1)/Math.max(1,maxRound-1)*710;
    const y=value=>232-(value-lo)/(hi-lo)*194;
    const svg=svgElement("svg",{viewBox:"0 0 800 260",role:"img","aria-label":"Mean validation trajectory for rounds with all selected seeds",class:"seed-curve"});
    svg.append(svgElement("line",{x1:52,y1:38,x2:52,y2:232,stroke:"currentColor"}),
      svgElement("line",{x1:52,y1:232,x2:762,y2:232,stroke:"currentColor"}),
      svgElement("text",{x:6,y:42,fill:"currentColor","font-size":11},score(hi,percent)),
      svgElement("text",{x:6,y:232,fill:"currentColor","font-size":11},score(lo,percent)),
      svgElement("text",{x:52,y:250,fill:"currentColor","font-size":11},"1"),
      svgElement("text",{x:738,y:250,fill:"currentColor","font-size":11},String(maxRound)));
    if(bands.input.checked){
      for(const [series,color] of [[full,"currentColor"],[cleanFull,"#64748b"]]){
        const byRound=new Map(series.map(row=>[row.round,row]));
        for(const segment of roundSegments(series.filter(row=>numeric(row.sd)).map(row=>({round:row.round,value:row.mean})))){
          const clip=value=>Math.max(lo,Math.min(hi,value));
          const upper=segment.map(p=>x(p.round)+","+y(clip(p.value+byRound.get(p.round).sd)));
          const lower=[...segment].reverse().map(p=>x(p.round)+","+y(clip(p.value-byRound.get(p.round).sd)));
          if(segment.length>1)svg.append(svgElement("polygon",{points:[...upper,...lower].join(" "),fill:color,opacity:.13}));
          else{const p=segment[0],sd=byRound.get(p.round).sd;svg.append(svgElement("line",{x1:x(p.round),x2:x(p.round),y1:y(clip(p.value-sd)),y2:y(clip(p.value+sd)),stroke:color,opacity:.4,"stroke-width":4}));}
        }
      }
    }
    for(const segment of roundSegments(full.map(r=>({round:r.round,value:r.mean})))){
      svg.append(svgElement("polyline",{points:segment.map(p=>x(p.round)+","+y(p.value)).join(" "),fill:"none",stroke:"currentColor","stroke-width":2.5}));
      for(const p of segment)svg.append(svgElement("circle",{cx:x(p.round),cy:y(p.value),r:2.5,fill:"currentColor"}));
    }
    for(const segment of roundSegments(cleanFull.map(r=>({round:r.round,value:r.mean})))){
      svg.append(svgElement("polyline",{points:segment.map(p=>x(p.round)+","+y(p.value)).join(" "),fill:"none",stroke:"#64748b","stroke-width":2.5,"stroke-dasharray":"6 4"}));
      for(const p of segment)svg.append(svgElement("circle",{cx:x(p.round),cy:y(p.value),r:2.5,fill:"#64748b"}));
    }
    if(full.length)body.append(svg);
    if(cleans.length)body.append(node("p","Solid: attacked mean. Dashed: clean mean. Same matched seeds and common rounds."));
    body.append(node("p","Only rounds observed in every selected seed are plotted. Missing observations are not interpolated. "+(bands.input.checked?"Shading: mean ± one sample SD (not a confidence interval); proportion bands are clipped to 0–100%.":"")));
    const details=node("details"),table=cleans.length
      ?dataTable(["Round","Clean mean","Attack mean","Attack − clean","Clean n","Attack n"],rows.map(row=>{
        const clean=cleanByRound.get(row.round),matched=row.n===runs.length&&clean?.n===cleans.length;
        return [row.round,score(clean?.mean,percent),score(row.mean,percent),matched?deltaScore(row.mean,clean.mean,percent):"—",(clean?.n||0)+"/"+cleans.length,row.n+"/"+runs.length];
      }))
      :dataTable(["Round","Mean","SD","Min","Max","n"],rows.map(row=>[row.round,score(row.mean,percent),score(row.sd,percent),score(row.min,percent),score(row.max,percent),row.n+"/"+runs.length]));
    details.append(node("summary","Round-by-round values and sample counts"),table);body.append(details);
  }
  metric.select.addEventListener("change",redraw);bands.input.addEventListener("change",redraw);redraw();return root;
}
function seedLabel(r){
  const c=r.config||{},names={local_class_gradient:"LCG",model_replacement:"ModelReplacement",class_withholding:"ClassWithholding",sample_weight_hijack:"SampleWeightHijack",update_scaling:"UpdateScaling",stale_replay:"StaleReplay",free_rider:"FreeRider",label_flip:"LabelFlip",none:"Clean"};
  const distribution=c.partition==="iid"?"IID":c.partition==="dirichlet"?"Non-IID · α="+(c.partition_params?.alpha??"?"):r.group?.distribution||c.partition||"Unknown partition";
  return [names[c.attack]||c.attack,distribution,classNames(r).length+" classes",c.attack==="none"?"0 malicious":(c.malicious_clients?.length??"?")+" malicious",c.model,c.training_method||"standard"].filter(Boolean).join(" · ");
}
function seedChosen(key,runs){
  // Equal weight per distinct seed. Conflicting replicas must not silently bias the mean.
  return seedBuckets(runs).flatMap(([,items])=>items.length===1?items:[]);
}
function seedMatched(runs,allRuns){
  const byId=new Map(allRuns.map(r=>[r.id,r]));
  return runs.flatMap(run=>{
    const clean=byId.get(run.baseline_id);
    return clean&&Number.isInteger(run.config?.seed)&&clean.config?.seed===run.config.seed&&verifiedPair(run,byId)?[{run,clean}]:[];
  });
}
function seedComparisonRows(pairs,descriptors){
  return descriptors.map(([label,get,percent])=>{
    const {clean:a,attack:b,delta:d}=ATIMAAnalysis.pairedStats(pairs.map(({run,clean})=>[get(clean),get(run)]));
    return [label,score(a.mean,percent),score(b.mean,percent),deltaScore(b.mean,a.mean,percent),
      numeric(d.sd)?(percent?(100*d.sd).toFixed(2)+" pp":score(d.sd,false)):"—",d.n+"/"+pairs.length];
  });
}
// Sensitivity: keep exact conditions separate and match the same seeds at every level.
function sensitivityFamilies(values){
  const {groups}=seedCohorts(values),families=new Map();
  for(const [cohort,runs] of groups){
    for(const axis of runs[0].sensitivity_conditions||[]){
      if(!axis.key||!axis.axis)continue;
      const key=axis.key+"|"+cohort.slice(cohort.indexOf("|")+1);
      if(!families.has(key))families.set(key,{axis:axis.axis,descriptive:axis.descriptive,levels:new Map(),ambiguous:false});
      const family=families.get(key),level=JSON.stringify(axis.value);
      if(family.levels.has(level)){family.ambiguous=true;continue;}
      family.levels.set(level,{value:axis.value,cohort,runs});
    }
  }
  return [...families].filter(([,f])=>!f.ambiguous&&f.levels.size>1);
}
function sensitivitySummary(family,allRuns,get){
  const levels=[...family.levels.values()].sort((a,b)=>typeof a.value==="number"&&typeof b.value==="number"?a.value-b.value:String(a.value).localeCompare(String(b.value)));
  const evidence=levels.map(level=>{
    const chosen=seedChosen(level.cohort,level.runs);
    const pairs=seedMatched(chosen,allRuns).filter(({run,clean})=>numeric(get(run))&&numeric(get(clean)));
    return {...level,chosen,pairs};
  });
  const common=evidence.length?evidence[0].pairs.map(p=>p.run.config.seed).filter(seed=>evidence.every(level=>level.pairs.some(p=>p.run.config.seed===seed))):[];
  return {common,rows:evidence.map(level=>{
    const pairs=level.pairs.filter(p=>common.includes(p.run.config.seed));
    return {...level,stats:ATIMAAnalysis.pairedStats(pairs.map(({run,clean})=>[get(clean),get(run)])),observed:seedStats(level.chosen.map(get))};
  })};
}
let sensitivityChoice="";
function renderSensitivityExplorer(root,values){
  root.replaceChildren();
  const details=node("details",undefined,"seed-block");details.append(node("summary","Parameter Sensitivity Explorer"));
  root.append(details);
  const families=sensitivityFamilies(values);
  details.append(node("p","Compare recorded parameter levels using the same matched clean/attack seeds at every level. Conditions with ambiguous levels are not pooled.","helper"));
  if(!families.length){details.append(node("p","No audited sensitivity family with at least two distinct levels is available."));return;}
  const selector=choiceControl("Comparison family",families.map(([key,f])=>[key,f.axis+" · "+seedLabel([...f.levels.values()][0].runs[0])+" · "+f.levels.size+" levels · "+key.slice(0,8)]),families.some(([key])=>key===sensitivityChoice)?sensitivityChoice:families[0][0]);
  const labels=[...new Set(families.flatMap(([,f])=>classNames([...f.levels.values()][0].runs[0])))];
  const metric=choiceControl("Metric",[...FINAL_METRICS.map(([key,label])=>[key,label]),["intrusion_to_benign","Intrusions predicted benign"],...labels.map(name=>["recall:"+name,name+" · Recall"]),...labels.filter(name=>!/^(benign|normal)$/i.test(name)).map(name=>["evasion:"+name,name+" · Predicted benign"])],"macro_f1");
  const output=node("div");details.append(selector.label,metric.label,output);
  function redraw(){
    output.replaceChildren();sensitivityChoice=selector.select.value;
    const family=families.find(([key])=>key===sensitivityChoice)?.[1];if(!family)return;
    const key=metric.select.value,percent=key!=="loss"&&key!=="mcc";
    const get=key==="intrusion_to_benign"?r=>seedEvasion(r)
      :key.startsWith("recall:")?r=>{const row=testMetrics(r)?.per_class?.[key.slice(7)];return row?.support>0?row.recall:null;}
      :key.startsWith("evasion:")?r=>seedEvasion(r,key.slice(8)):r=>testMetrics(r)?.[key];
    const {common,rows}=sensitivitySummary(family,values,get);
    output.append(node("p",family.descriptive?"Descriptive condition contrast: architecture or shard assignments can differ.":"Fixed audited partition and other recorded parameters; only the selected variable differs."));
    output.append(node("p",common.length?"Common matched seeds: "+common.join(", "):"No common matched seed population. Only descriptive observed means are shown."));
    output.append(dataTable(["Level","Observed mean","Selected seeds","Available pairs","Common clean mean","Common attack mean","Attack − clean","SD of delta"],rows.map(r=>[String(r.value),score(r.observed.mean,percent),r.observed.n+"/"+r.chosen.length,r.pairs.length,score(r.stats.clean.mean,percent),score(r.stats.attack.mean,percent),deltaScore(r.stats.attack.mean,r.stats.clean.mean,percent),numeric(r.stats.delta.sd)?(percent?(100*r.stats.delta.sd).toFixed(2)+" pp":score(r.stats.delta.sd,false)):"—"])));
    if(!common.length)return;
    const all=rows.flatMap(r=>[r.stats.clean.mean,r.stats.attack.mean]),lo=percent?0:Math.min(0,...all),hi=percent?1:Math.max(lo+.001,...all);
    const x=i=>65+i*660/Math.max(1,rows.length-1),y=v=>210-(v-lo)/(hi-lo)*175;
    const svg=svgElement("svg",{viewBox:"0 0 800 250",role:"img","aria-label":"Matched means by parameter level",class:"seed-curve"});
    svg.append(svgElement("line",{x1:65,y1:210,x2:725,y2:210,stroke:"currentColor"}),svgElement("line",{x1:65,y1:35,x2:65,y2:210,stroke:"currentColor"}),svgElement("text",{x:5,y:39,fill:"currentColor","font-size":11},score(hi,percent)),svgElement("text",{x:5,y:210,fill:"currentColor","font-size":11},score(lo,percent)));
    for(const [field,color,dash] of [["attack","currentColor","none"],["clean","#64748b","6 4"]]){
      svg.append(svgElement("polyline",{points:rows.map((r,i)=>x(i)+","+y(r.stats[field].mean)).join(" "),fill:"none",stroke:color,"stroke-width":2.5,"stroke-dasharray":dash}));
      rows.forEach((r,i)=>svg.append(svgElement("circle",{cx:x(i),cy:y(r.stats[field].mean),r:3,fill:color})));
    }
    rows.forEach((r,i)=>svg.append(svgElement("text",{x:x(i),y:230,"text-anchor":"middle","font-size":10,fill:"currentColor"},String(i+1))));
    output.append(svg,node("p","Solid: attacked · dashed: clean. Equally spaced level indices refer to the table, not a continuous numerical scale.","helper"));
  }
  selector.select.addEventListener("change",redraw);metric.select.addEventListener("change",redraw);redraw();
}
function seedMatrixSummary(runs,pairs){
  const section=node("section",undefined,"seed-block");
  section.append(node("h4","Mean normalized confusion matrices"));
  const classes=classNames(runs[0]),sameOrder=r=>JSON.stringify(classNames(r))===JSON.stringify(classes);
  const usable=runs.filter(r=>validMatrix(r)&&sameOrder(r));
  const matched=pairs.filter(({run,clean})=>validMatrix(run)&&validMatrix(clean)&&sameOrder(run)&&sameOrder(clean));
  if(!usable.length){section.append(node("p","No valid confusion matrices."));return section;}
  const matrix=r=>testMetrics(r).confusion_matrix;
  const mean=ATIMAAnalysis.meanMatrices(usable.map(matrix));
  const grid=node("div",undefined,"manual-matrix-grid");
  grid.append(matrixView(classes,mean.map(row=>row.map(cell=>cell.mean)),
    "Selected runs · "+usable.length+"/"+runs.length+" seeds",true));
  section.append(node("p","Each seed has equal weight. Rows are normalized before averaging; zero-support rows are unavailable, never zero.","helper"),grid);
  if(matched.length){
    const cells=ATIMAAnalysis.pairedMatrices(matched.map(({run,clean})=>[matrix(clean),matrix(run)]));
    for(const [label,key,difference] of [["Clean","clean",false],["Attack","attack",false],["Attack − clean","delta",true]]){
      grid.append(matrixView(classes,cells.map(row=>row.map(cell=>cell[key].mean)),
        label+" · "+matched.length+" matched seeds",true,difference));
    }
    section.append(node("p","Matched matrix means and differences use only seed pairs with support on both sides of each row.","helper"));
    const counts=node("details");
    counts.append(node("summary","Matched seed counts per true class"),
      dataTable(["True class","Matched seeds with support"],classes.map((name,i)=>[name,cells[i][0].delta.n+"/"+matched.length])));
    section.append(counts);
  }
  return section;
}
const seedExpectedByCondition=new Map();
function campaignCoveragePanel(key,runs,chosen,allRuns){
  const section=node("details",undefined,"seed-block");
  section.append(node("summary","Campaign completeness"));
  const field=node("input");field.type="text";field.value=seedExpectedByCondition.get(key)||"";
  field.placeholder="0,1,2,…,10";
  const label=node("label","Expected seeds (from your campaign plan)");label.append(field);
  const apply=node("button","Check coverage","secondary"),preset=node("button","Use 0–10","secondary"),output=node("div");
  apply.type=preset.type="button";
  const render=()=>{
    output.replaceChildren();seedExpectedByCondition.set(key,field.value);
    if(!field.value.trim()){output.append(node("p","Enter planned seeds to identify missing runs; an observed seed list alone cannot prove completeness."));return;}
    try{
      const parts=field.value.split(",").map(s=>s.trim());
      if(parts.some(s=>!/^\d+$/.test(s)))throw new Error("Enter comma-separated integers.");
      const selected=new Set(chosen.map(r=>r.id)),matched=new Set(seedMatched(chosen,allRuns).map(p=>p.run.id));
      const coverage=ATIMAAnalysis.campaignCoverage(parts.map(Number),runs.map(r=>({seed:r.config.seed,selected:selected.has(r.id),matched:matched.has(r.id)})));
      const cleanOnly=runs[0]?.config?.attack==="none";
      const missing=coverage.rows.filter(row=>!row.observed).length,unselected=coverage.rows.filter(row=>row.observed&&!row.selected).length;
      output.append(node("p",missing+" planned seeds not observed in this compatible completed cohort · "+unselected+" observed seeds not selected"+(cleanOnly?"":" · "+coverage.rows.filter(row=>row.selected&&!row.matched).length+" selected seeds without matched clean")));
      output.append(dataTable(["Seed","Compatible complete runs","Selection","Clean baseline"],coverage.rows.map(row=>[row.seed,row.observed,row.selected?"Selected":row.observed?"Not selected":"Not observed",cleanOnly?"Not applicable":row.matched?"Matched":row.selected?"Missing / incompatible":"—"])));
      if(coverage.unexpected.length)output.append(node("p","Observed outside plan: "+coverage.unexpected.join(", ")));
    }catch(error){output.append(node("p",error.message,"error"));}
  };
  apply.addEventListener("click",render);preset.addEventListener("click",()=>{field.value=Array.from({length:11},(_,i)=>i).join(",");render();});
  section.append(node("p","Coverage is scoped to this exact compatible completed condition. Failed or excluded runs remain available in individual reports.","helper"),label,apply,preset,output);
  render();return section;
}
function seedSummary(root,runs,allRuns){
  root.replaceChildren();
  if(!runs.length){root.append(node("p","No unambiguous compatible seed is available. Inspect individual runs below."));return;}
  if(runs.length===1)root.append(node("p","Only one seed available; this is a single observation, not a replicated estimate."));
  const headings=["Metric","Mean","SD","Min","Max","Available seeds"];
  const final=node("section",undefined,"seed-block");
  final.append(node("h4","Final test metrics across seeds"),dataTable(headings,seedMetricRows(runs,[
    ...FINAL_METRICS.map(([key,label,percent])=>[label,r=>testMetrics(r)?.[key],percent]),
    ["Intrusions predicted benign",r=>seedEvasion(r),true]
  ])));
  root.append(final);
  const classes=node("section",undefined,"seed-block"),labels=classNames(runs[0]);
  classes.append(node("h4","Per-class recall and intrusion-to-benign rate"),dataTable(headings,seedMetricRows(runs,
    labels.flatMap(name=>[[name+" · Recall",r=>testMetrics(r)?.per_class?.[name]?.support>0?testMetrics(r).per_class[name].recall:null,true],
      ...(!/^(benign|normal)$/i.test(name)?[[name+" · Predicted benign",r=>seedEvasion(r,name),true]]:[])]))));
  root.append(classes,seedCurve(runs));
  const pairs=seedMatched(runs,allRuns);
  const paired=node("section",undefined,"seed-block");
  paired.append(node("h4","Metadata-matched attack minus clean"));
  if(pairs.length){
    const descriptors=[...FINAL_METRICS.map(([key,label,percent])=>[label,r=>testMetrics(r)?.[key],percent]),
      ["Intrusions predicted benign",r=>seedEvasion(r),true],
      ...labels.map(name=>[name+" · Recall",r=>testMetrics(r)?.per_class?.[name]?.support>0?testMetrics(r).per_class[name].recall:null,true])];
    paired.append(node("p",pairs.length+"/"+runs.length+" selected seeds have compatible clean baselines. Both means use exactly the same matched observations. Initial weights are not verified from imported summaries."),
      dataTable(["Metric","Clean mean","Attack mean","Attack − clean","SD of paired delta","Matched seeds"],seedComparisonRows(pairs,descriptors)),
      seedCurve(pairs.map(p=>p.run),pairs.map(p=>p.clean)));
  }else paired.append(node("p",runs[0]?.config?.attack==="none"?"Clean cohort: no attacked reference is needed.":"No verified matching clean baseline. The attack averages above remain descriptive."));
  root.append(paired,seedMatrixSummary(runs,pairs));
}
let seedWorkspaceReady=false;
function refreshSeedWorkspace(){
  const enabled=$("seed-analysis-enabled"),body=$("seed-analysis-content");
  if(!enabled||!body)return;
  body.classList.toggle("hidden",!enabled.checked);
  if(!enabled.checked)return;
  renderSensitivityExplorer($("sensitivity-explorer"),availableResults);
  const {groups,excluded}=seedCohorts(availableResults);
  const select=$("seed-cohort-choice"),previous=select.value;
  select.replaceChildren();
  const empty=node("option","Choose a condition");empty.value="";select.append(empty);
  for(const [key,runs] of groups){
    const r=runs[0],c=r.config,n=seedBuckets(runs).length;
    const detail=seedLabel(r)+" · "+n+" seeds · "+key.slice(0,8);
    const option=node("option",detail);option.value=key;select.append(option);
  }
  const first=[...groups.entries()].sort((a,b)=>Number(a[1][0].config.attack==="none")-Number(b[1][0].config.attack==="none")||seedBuckets(b[1]).length-seedBuckets(a[1]).length)[0];
  select.value=groups.has(previous)?previous:first?.[0]||"";
  const overview=$("seed-cohort-overview");overview.replaceChildren();
  for(const [key,runs] of groups){
    const chosen=seedChosen(key,runs),pairs=seedMatched(chosen,availableResults);
    const metric=r=>testMetrics(r)?.macro_f1;
    const avg=seedStats(chosen.map(metric)),valid=pairs.filter(p=>numeric(metric(p.clean))&&numeric(metric(p.run)));
    const clean=seedStats(valid.map(p=>metric(p.clean))),attack=seedStats(valid.map(p=>metric(p.run)));
    const card=node("article",undefined,"seed-cohort-card"),button=node("button",seedLabel(runs[0]),"text-button");button.type="button";
    button.addEventListener("click",()=>{select.value=key;refreshSeedWorkspace();});
    card.append(button,node("p",chosen.length+"/"+seedBuckets(runs).length+" seeds included · Mean macro-F1 "+score(avg.mean)),node("p",runs[0].config.attack==="none"?"Clean reference":valid.length?"Matched "+valid.length+" seeds: clean "+score(clean.mean)+" · attack "+score(attack.mean)+" · Δ "+deltaScore(attack.mean,clean.mean):"No matched clean evidence"));
    overview.append(card);
  }
  $("seed-analysis-status").textContent=groups.size+" compatible conditions · "+excluded.length+" excluded runs. Conditions require identical audited shards, configuration and source/runtime identities.";
  const selection=$("seed-analysis-selection"),output=$("seed-analysis-output");
  selection.replaceChildren();output.replaceChildren();
  if(excluded.length){
    const details=node("details");details.append(node("summary","Excluded runs and reasons"),dataTable(["Experiment","Reason"],excluded.map(r=>[r.id,r.reason])));selection.append(details);
  }
  const runs=groups.get(select.value);
  if(!runs)return;
  const configDetail=node("details");
  const cfg={...runs[0].config};delete cfg.seed;delete cfg.name;delete cfg.paired_clean;
  configDetail.append(node("summary","Recorded condition and parameters"),node("pre",JSON.stringify(cfg,null,2)));selection.append(configDetail);
  const buckets=seedBuckets(runs),chosen=seedChosen(select.value,runs);
  const duplicates=buckets.filter(([,items])=>items.length>1);
  selection.append(node("p",chosen.length+" distinct compatible seeds included automatically. SD is sample standard deviation; missing metrics are not zero."));
  if(duplicates.length){
    const details=node("details");
    details.append(node("summary","Ambiguous duplicate seeds excluded"),node("p","Use the individual experiment view to inspect a specific replica. No replica is chosen arbitrarily."));
    details.append(dataTable(["Seed","Run IDs"],duplicates.map(([seed,items])=>[seed,items.map(r=>r.id).join(", ")])));
    selection.append(details);
  }
  selection.append(campaignCoveragePanel(select.value,runs,chosen,availableResults));
  seedSummary(output,chosen,availableResults);
}
const RESULTS_LAYOUT_DEFAULT=["seed-results-panel","performance-region","detail-region","individual-reports-region"];
let resultsPanelOrder=[...RESULTS_LAYOUT_DEFAULT];
function validResultsOrder(order){
  return Array.isArray(order)&&order.length===RESULTS_LAYOUT_DEFAULT.length
    &&new Set(order).size===order.length&&order.every(id=>RESULTS_LAYOUT_DEFAULT.includes(id));
}
function moveResultsPanel(order,id,step){
  const next=[...order],i=next.indexOf(id),j=i+step;
  if(i>=0&&j>=0&&j<next.length)[next[i],next[j]]=[next[j],next[i]];
  return next;
}
function applyResultsLayout(){
  const enabled=$("custom-results-layout"),controls=$("results-layout-controls"),container=$("results-workspace-panels");
  if(!enabled||!controls||!container)return;
  controls.classList.toggle("hidden",!enabled.checked);controls.replaceChildren();
  const order=enabled.checked?resultsPanelOrder:RESULTS_LAYOUT_DEFAULT;
  // Move existing DOM nodes rather than redraw; preserves charts and selection state.
  for(const id of order){const panel=$(id);if(panel&&panel.parentElement===container)container.append(panel);}
  if(!enabled.checked)return;
  const labels={"seed-results-panel":"Multi-seed analysis","performance-region":"Performance overview","detail-region":"Detailed analysis / graphs","individual-reports-region":"Individual reports"};
  const save=()=>{
    try{localStorage.setItem("atima-results-panel-order",JSON.stringify(resultsPanelOrder));}catch{}
    applyResultsLayout();
  };
  for(const [index,id] of resultsPanelOrder.entries()){
    const row=node("div",undefined,"layout-control-row"),up=node("button","↑","secondary"),down=node("button","↓","secondary");
    up.type=down.type="button";up.disabled=index===0;down.disabled=index===resultsPanelOrder.length-1;
    up.setAttribute("aria-label","Move "+labels[id]+" up");down.setAttribute("aria-label","Move "+labels[id]+" down");
    up.addEventListener("click",()=>{resultsPanelOrder=moveResultsPanel(resultsPanelOrder,id,-1);save();});
    down.addEventListener("click",()=>{resultsPanelOrder=moveResultsPanel(resultsPanelOrder,id,1);save();});
    row.append(node("span",labels[id]),up,down);controls.append(row);
  }
  const reset=node("button","Reset panel order","text-button");reset.type="button";
  reset.addEventListener("click",()=>{resultsPanelOrder=[...RESULTS_LAYOUT_DEFAULT];save();});controls.append(reset);
}
function setupResultsWorkspace(){
  if(seedWorkspaceReady)return;
  seedWorkspaceReady=true;
  $("seed-analysis-enabled")?.addEventListener("change",refreshSeedWorkspace);
  $("seed-cohort-choice")?.addEventListener("change",refreshSeedWorkspace);
  $("custom-results-layout")?.addEventListener("change",applyResultsLayout);
  try{const saved=JSON.parse(localStorage.getItem("atima-results-panel-order")||"null");if(validResultsOrder(saved))resultsPanelOrder=saved;}catch{}
}

function renderResults(values){
  setupResearchFocus();setupResultsWorkspace();
  const target=$("results-list");target.replaceChildren();
  availableResults=values;updateResultsOverview(values);updateFilterChoices();updateManualComparison(values);refreshSeedWorkspace();
  if(!values.length)target.append(node("p","No local results available. Import from the cluster."));
  const focused=values.filter(researchFocusedRun);
  $("research-focus-status").textContent=$("research-focus-enabled").checked
    ?"Showing "+focused.length+" of "+values.length+" runs (clean baselines included). Selected graph attacks: "+researchFocusSelected.size+"."
    :"Disabled — all experiments remain visible.";
  if(values.length&&!focused.length)target.append(node("p","No experiments match this optional research selection."));
  // Organize imports for browsing, not for scientific comparison. Only the
  // separately verified pairing logic may authorize clean/attack deltas.
  const familyGroups=new Map(),campaignGroups=new Map();
  const ordered=$("group-results-enabled").checked?[...focused].sort((a,b)=>{
    const label=r=>[r.group?.family,r.group?.attack,r.group?.campaign_date,
      r.group?.distribution,r.group?.partition_detail,r.group?.model,
      r.group?.dataset,r.group?.task,r.id].join("|");
    return label(a).localeCompare(label(b));
  }):focused;
  for(const value of ordered){
    const info=value.group||{},family=info.family||"Other / unclassified";
    let reportParent=target;
    if($("group-results-enabled").checked){
      let familyGroup=familyGroups.get(family);
      if(!familyGroup){
        const wrapper=node("details",undefined,"result-report");
        const summary=node("summary",undefined,"result-report-heading");
        const familyBody=node("div",undefined,"result-report-content");
        summary.append(node("strong",family));
        wrapper.append(summary,familyBody);target.append(wrapper);
        familyGroup={body:familyBody,summary,count:0};
        familyGroups.set(family,familyGroup);
      }
      familyGroup.count++;
      // Different Dirichlet alphas must never silently appear as one scenario.
      const description=[info.attack||value.config?.attack||"unknown",
        info.campaign_date||"Date unknown",info.distribution||"Unknown",
        info.partition_detail||"Unknown",info.model||"Unknown",
        info.dataset||"Unknown",info.task||"Unknown"];
      const key=family+"|"+JSON.stringify(description);
      let campaign=campaignGroups.get(key);
      if(!campaign){
        const wrapper=node("details",undefined,"result-report");
        const summary=node("summary",undefined,"result-report-heading");
        summary.append(node("strong",description.slice(0,3).join(" · ")),
          node("span",description.slice(3).join(" · ")));
        const campaignBody=node("div",undefined,"result-report-content");
        wrapper.append(summary,campaignBody);
        familyGroup.body.append(wrapper);
        campaign={body:campaignBody,summary,count:0};
        campaignGroups.set(key,campaign);
      }
      campaign.count++;
  
      reportParent=campaign.body;
    }
    const report=node("details",undefined,"result-report"),heading=node("summary",undefined,"result-report-heading");
    heading.append(node("strong",value.id),node("span",[value.config?.model,value.config?.attack,Number.isInteger(value.group?.seed)?"Seed "+value.group.seed:null,value.status,uiText("Round")+" "+(value.round??"—")].filter(Boolean).join(" · ")));report.append(heading);
    let rendered=false;
    report.addEventListener("toggle",()=>{
      if(!report.open||rendered)return;rendered=true;
      const content=node("div",undefined,"result-report-content"),metric=testMetrics(value);
      if(metric)content.append(node("h4","Final test metrics"),metricCards(metric));
      else content.append(node("p","Final test metrics are not available for this run."));
      content.append(perClassAnalysis(value,null,false),matrixAnalysis(value,null,false),roundChart(value,null));
      const configuration=node("details",undefined,"result-raw");
      configuration.append(node("summary","Recorded configuration (including attack parameters)"),
        node("pre",JSON.stringify(value.config||{},null,2)));content.append(configuration);
      const raw=node("details",undefined,"result-raw");raw.append(node("summary","Raw final metrics"),node("pre",JSON.stringify(value.metrics,null,2)));content.append(raw);report.append(content);
    });reportParent.append(report);
  }
  for(const group of familyGroups.values())group.summary.append(node("span",group.count+" runs"));
  for(const group of campaignGroups.values())group.summary.append(node("span",group.count+" runs"));
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

