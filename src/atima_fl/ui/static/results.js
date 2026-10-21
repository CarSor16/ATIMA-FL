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

