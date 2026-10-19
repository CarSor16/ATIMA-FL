/* Federated diagnostics from audited compact server summaries. No invented samples. */
function federatedAnalysis(first, second){
  const section=node("section",undefined,"result-section fl-diagnostics");
  section.append(node("h4","Federated training · client/aggregation evidence"),
    node("p","Logical-client simulation metrics recorded by the server. Update L2 is descriptive; it does not prove a successful attack. Missing legacy data stays unavailable.","helper"));
  const runs=[["A",first],...(second?[["B",second]]:[])];
  const roundRows=run=>Array.isArray(run?.metrics?.federated?.rounds)?run.metrics.federated.rounds:[];
  if(!runs.some(([,run])=>roundRows(run).length)){
    section.append(node("p","No federated telemetry was recorded for these runs. Historical experiments are not retroactively reconstructed.","fl-empty"));
    return section;
  }
  const summaries=node("div",undefined,"fl-summary");
  for(const [tag,run] of runs){
    const rounds=roundRows(run),last=rounds.at(-1);
    const card=node("div",undefined,"fl-audit-card");
    card.append(node("strong",tag+" · "+run.id));
    if(!last){card.append(node("p","No round-level server audit available."));summaries.append(card);continue;}
    const cells=[
      ["Active malicious mass",score(last.reported_malicious_mass_fraction)],
      ["Actual malicious mass",score(last.actual_malicious_mass_fraction)],
      ["Claim mismatches",String(last.count_mismatch_clients??"—")],
      ["Attacking clients",String(last.attack_applied_clients??"—")],
      ["Last global step L2",numeric(last.global_step_l2)?last.global_step_l2.toFixed(4):"—"]
    ];
    const dl=node("dl",undefined,"fl-metric-grid");
    for(const [label,value] of cells)dl.append(node("dt",label),node("dd",value));
    card.append(dl);summaries.append(card);
  }
  section.append(summaries);

  const fields=[
    ["reported_malicious_mass_fraction","Reported malicious sample mass",true],
    ["actual_malicious_mass_fraction","Actual malicious sample mass",true],
    ["global_step_l2","Global model step L2",false],
    ["mean_client_update_l2","Mean client update L2",false],
    ["max_client_update_l2","Max client update L2",false],
    ["attack_applied_clients","Attack-active client count",false],
    ["count_mismatch_clients","Unverified count mismatch",false]
  ];
  const select=choiceControl("FL diagnostic",fields.map(([key,label])=>[key,label]),fields[0][0]);
  const all= runs.flatMap(([,run])=>roundRows(run));
  const maximum=Math.max(1,...all.map(r=>r.round).filter(Number.isInteger));
  const controls=node("div",undefined,"round-controls fl-controls");
  const fromLabel=node("label","From round"),toLabel=node("label","To round");
  const from=node("input"),to=node("input");
  for(const input of [from,to]){input.type="number";input.min="1";input.max=String(maximum);input.step="1";}
  from.value="1";to.value=String(maximum);fromLabel.append(from);toLabel.append(to);
  const zoomIn=node("button","Zoom +","chart-action"),zoomOut=node("button","Zoom −","chart-action"),
    reset=node("button","Reset zoom","chart-action"),download=node("button","Export CSV","chart-action");
  for(const b of [zoomIn,zoomOut,reset,download])b.type="button";
  controls.append(select.label,fromLabel,toLabel,zoomIn,zoomOut,reset,download);
  const drawing=node("div",undefined,"round-chart"),message=node("p","Focus a point to inspect a recorded round.","chart-tooltip"),
    details=node("details",undefined,"round-data");
  message.setAttribute("role","status");
  section.append(controls,drawing,message,details);
  function points(run,key,start,end){
    return roundRows(run).filter(row=>Number.isInteger(row.round)&&row.round>=start&&row.round<=end&&numeric(row[key]))
      .map(row=>({round:row.round,value:row[key]}));
  }
  function draw(){
    drawing.replaceChildren();details.replaceChildren(node("summary","Recorded FL round values"));
    const start=Number(from.value),end=Number(to.value),key=select.select.value;
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end>maximum||start>end){
      drawing.append(node("p","Invalid round selection.","warning"));return;
    }
    const percent=fields.find(row=>row[0]===key)?.[2]||false;
    const traces=runs.map(([tag,run])=>({tag,points:points(run,key,start,end)}));
    const present=traces.flatMap(trace=>trace.points);
    if(!present.length){drawing.append(node("p","No recorded FL values in this range."));return;}
    const min=Math.min(...present.map(point=>point.value)),max=Math.max(...present.map(point=>point.value));
    const pad=Math.max((max-min)*.15,.0001);
    const low=Math.max(0,min-pad),high=percent?Math.min(1,Math.max(low+.0001,max+pad)):Math.max(low+.0001,max+pad);
    const left=78,right=940,top=26,bottom=260;
    const x=r=>left+(r-start)/Math.max(1,end-start)*(right-left);
    const y=v=>bottom-(v-low)/(high-low)*(bottom-top);
    const svg=svgElement("svg",{viewBox:"0 0 970 312",role:"group",
      "aria-label":"Federated "+select.select.value+" by round"});
    for(let i=0;i<=4;i++){
      const v=low+(high-low)*i/4,yy=y(v);
      svg.append(svgElement("line",{x1:left,y1:yy,x2:right,y2:yy,class:"chart-grid"}));
      svg.append(svgElement("text",{x:left-8,y:yy+4,"text-anchor":"end",class:"chart-axis"},percent?(100*v).toFixed(1)+"%":v.toFixed(3)));
      const round=Math.round(start+(end-start)*i/4);
      svg.append(svgElement("text",{x:x(round),y:bottom+23,"text-anchor":"middle",class:"chart-axis"},String(round)));
    }
    for(const trace of traces){
      const klass=trace.tag==="A"?"chart-baseline":"chart-experiment";
      for(const segment of roundSegments(trace.points)){
        svg.append(svgElement("polyline",{points:segment.map(p=>x(p.round)+","+y(p.value)).join(" "),class:klass}));
      }
      for(const item of trace.points){
        const label=trace.tag+" · round "+item.round+": "+(percent?score(item.value):item.value.toFixed(4));
        const circle=svgElement("circle",{cx:x(item.round),cy:y(item.value),r:3.3,class:"chart-point "+klass,tabindex:0,"aria-label":label});
        circle.append(svgElement("title",{},label));
        for(const evt of ["mouseenter","focus"])circle.addEventListener(evt,()=>{message.textContent=label;});
        svg.append(circle);
      }
    }
    drawing.append(svg);
    const legend=node("div",undefined,"chart-legend");
    for(const trace of traces)legend.append(node("span",trace.tag+" · "+runs.find(([tag])=>tag===trace.tag)[1].id,
      trace.tag==="A"?"legend-baseline":"legend-experiment"));
    drawing.append(legend);
    const a=new Map(traces[0].points.map(p=>[p.round,p.value]));
    const b=new Map((traces[1]?.points||[]).map(p=>[p.round,p.value]));
    const indices=[...new Set([...a.keys(),...b.keys()])].sort((x,y)=>x-y);
    details.append(dataTable(["Round","A",...(second?["B","Δ B − A"]:[])],
      indices.map(r=>[r,percent?score(a.get(r)):numeric(a.get(r))?a.get(r).toFixed(4):"—",
        ...(second?[percent?score(b.get(r)):numeric(b.get(r))?b.get(r).toFixed(4):"—",
        deltaScore(b.get(r),a.get(r),percent)]:[])])));
  }
  function zoom(factor){
    const start=Number(from.value),end=Number(to.value);
    if(!Number.isInteger(start)||!Number.isInteger(end)||start>end)return;
    const span=Math.max(1,Math.min(maximum,Math.round((end-start+1)*factor)));
    const center=(start+end)/2;let nextFrom=Math.max(1,Math.round(center-(span-1)/2));
    nextFrom=Math.min(nextFrom,maximum-span+1);
    from.value=String(nextFrom);to.value=String(nextFrom+span-1);draw();
  }
  select.select.addEventListener("change",draw);from.addEventListener("change",draw);to.addEventListener("change",draw);
  zoomIn.addEventListener("click",()=>zoom(.5));zoomOut.addEventListener("click",()=>zoom(2));
  reset.addEventListener("click",()=>{from.value="1";to.value=String(maximum);draw();});
  download.addEventListener("click",()=>{
    const key=select.select.value,header=["round",...runs.map(([tag])=>tag+"_"+key)];
    const byRun=runs.map(([,run])=>new Map(roundRows(run).map(r=>[r.round,r[key]])));
    const rounds=[...new Set(byRun.flatMap(m=>[...m.keys()]))].sort((a,b)=>a-b);
    const csv=[header.join(","),...rounds.map(r=>[r,...byRun.map(m=>numeric(m.get(r))?m.get(r):"")].join(","))].join("\n")+"\n";
    const blob=new Blob([csv],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob);
    const link=document.createElement("a");link.href=url;link.download="atima_federated_"+key+".csv";
    document.body.append(link);link.click();link.remove();URL.revokeObjectURL(url);
  });
  draw();return section;
}
