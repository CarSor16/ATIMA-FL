"use strict";

// Static viewer bootstrap: no Python routes, no SSH, no remote data service.
const ATIMA_WEB_ONLY=true;
const $=id=>document.getElementById(id);
let chosenComparison={first:null,second:null};
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=uiText(text);if(cls)el.className=cls;return el;}
function updateResultsOverview(values){
  const root=$("results-overview"),byId=new Map(values.map(r=>[r.id,r]));
  root.replaceChildren();
  $("web-run-count").textContent=String(values.length);
  $("web-empty-results").hidden=values.length>0;
  $("results").hidden=values.length===0;
  for(const [count,title,detail] of [[values.length,"Local runs","Selected folder"],[values.filter(r=>r.status==="complete").length,"Complete runs","Manifest status"],[values.filter(r=>verifiedPair(r,byId)).length,"Metadata-matched pairs","Not independently verified"]]){
    const card=node("article",undefined,"overview-tile");card.append(node("span",title,"overview-label"),node("strong",String(count),"overview-number"),node("small",detail));root.append(card);
  }
}
const webViews={
  results:["Results Explorer","Inspect a run or compare compatible experiments."],
  seeds:["Multi-seed analysis","Explore one recorded experimental condition across distinct seeds."],
  sensitivity:["Parameter sensitivity","Compare parameter levels using compatible experimental evidence."],
  designer:["Experiment Designer","Prepare a draft profile, seed batch or parameter sweep."],
  studies:["Study Exchange","Review and compare portable study summaries."],
  data:["Local results","Import, refresh or forget your local experiment files."]
};
let webView="results";
function openWebView(name){
  if(!Object.hasOwn(webViews,name))name="results";
  webView=name;
  for(const key of Object.keys(webViews))$("web-view-"+key).hidden=key!==name;
  for(const button of document.querySelectorAll("[data-web-view]")){
    if(button.dataset.webView===name)button.setAttribute("aria-current","page");
    else button.removeAttribute("aria-current");
  }
  $("web-view-title").textContent=uiText(webViews[name][0]);
  $("web-view-description").textContent=uiText(webViews[name][1]);
  if(name==="seeds")$("web-seed-menu").open=true;
  if(name==="sensitivity"){
    const details=$("sensitivity-explorer").querySelector("details");
    if(details)details.open=true;
  }
  if(name==="designer")$("web-designer").open=true;
  if(name==="studies")$("web-study").open=true;
}
function setupWebNavigation(){
  const data=$("web-view-data"),panels=$("results-workspace-panels");
  data.append(document.querySelector(".web-import"),$("web-folder-access"));
  const returnButton=node("button","Open Results Explorer");returnButton.type="button";
  returnButton.addEventListener("click",()=>openWebView("results"));data.append(returnButton);
  $("web-view-seeds").append($("seed-results-panel"));
  $("web-view-sensitivity").append($("sensitivity-explorer"));
  for(const id of ["performance-region","detail-region","individual-reports-region"])panels.append($(id));
  // Keep shared controls available to the local Studio but not in the focused web layout.
  document.querySelector(".results-workspace-tools").hidden=true;
  $("seed-results-panel").querySelector(".analysis-heading").hidden=true;
  const seedBody=$("seed-analysis-content"),choice=$("seed-cohort-choice").closest("label");
  const strict=$("seed-strict-provenance").closest("label"),helper=strict.nextElementSibling;
  const advanced=node("details",undefined,"web-advanced");advanced.append(node("summary","Provenance settings"),strict,helper);
  seedBody.prepend(choice,advanced);
  for(const button of document.querySelectorAll("[data-web-view]"))
    button.addEventListener("click",()=>openWebView(button.dataset.webView));
  $("web-open-data").addEventListener("click",()=>openWebView("data"));
  $("web-open-cohort").addEventListener("click",()=>{
    const run=availableResults.find(r=>r.id===chosenComparison.first);
    const {groups}=seedCohorts(availableResults);
    const match=[...groups].find(([,runs])=>runs.some(r=>r.id===run?.id));
    openWebView("seeds");
    if(match){$("seed-cohort-choice").value=match[0];refreshSeedWorkspace();}
  });
  openWebView("results");
}
function startStaticViewer(){
  setupWebNavigation();
  initializeAnalysisControls();
  $("compare-experiment-a").addEventListener("change",()=>{chosenComparison.first=$("compare-experiment-a").value;refreshManualFromChoices();});
  $("compare-experiment-b").addEventListener("change",()=>{chosenComparison.second=$("compare-experiment-b").value;refreshManualFromChoices();});
  $("compare-swap").addEventListener("click",()=>{[chosenComparison.first,chosenComparison.second]=[chosenComparison.second,chosenComparison.first];$("compare-experiment-a").value=chosenComparison.first||"";$("compare-experiment-b").value=chosenComparison.second||"";refreshManualFromChoices();});
  $("refresh-results").addEventListener("click",refreshResults);
  const themeButton=$("web-theme");
  function applyTheme(theme){document.documentElement.dataset.theme=theme;themeButton.textContent=theme==="dark"?"Light mode":"Dark mode";try{localStorage.setItem("atima-web-theme",theme);}catch{}}
  let theme="dark";try{if(localStorage.getItem("atima-web-theme")==="light")theme="light";}catch{}
  applyTheme(theme);
  themeButton.addEventListener("click",()=>applyTheme(document.documentElement.dataset.theme==="dark"?"light":"dark"));
  $("web-language").value=currentLanguage;
  $("web-language").addEventListener("change",()=>{currentLanguage=$("web-language").value;try{localStorage.setItem("atima-language",currentLanguage);}catch{}localizeDocument();renderResults(availableResults);openWebView(webView);});
  localizeDocument();
  renderResults([]);
  updateLocalResultStatus(null);
  setupWebFolderAccess();
  setupWebDesigner();
  setupStudyExchange();
}
document.addEventListener("DOMContentLoaded",startStaticViewer,{once:true});
