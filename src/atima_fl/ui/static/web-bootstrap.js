"use strict";

// Static viewer bootstrap: no Python routes, no SSH, no remote data service.
const ATIMA_WEB_ONLY=true;
const $=id=>document.getElementById(id);
let chosenComparison={first:null,second:null};
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=uiText(text);if(cls)el.className=cls;return el;}
function updateResultsOverview(values){
  const root=$("results-overview"),byId=new Map(values.map(r=>[r.id,r]));
  root.replaceChildren();
  for(const [count,title,detail] of [[values.length,"Local runs","Selected folder"],[values.filter(r=>r.status==="complete").length,"Complete runs","Manifest status"],[values.filter(r=>verifiedPair(r,byId)).length,"Metadata-matched pairs","Not independently verified"]]){
    const card=node("article",undefined,"overview-tile");card.append(node("span",title,"overview-label"),node("strong",String(count),"overview-number"),node("small",detail));root.append(card);
  }
}
function startStaticViewer(){
  // Results first; advanced panels keep the same IDs and controls.
  const panels=$("results-workspace-panels");
  for(const id of ["performance-region","detail-region","seed-results-panel","individual-reports-region"])panels.append($(id));
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
  $("web-language").addEventListener("change",()=>{currentLanguage=$("web-language").value;try{localStorage.setItem("atima-language",currentLanguage);}catch{}localizeDocument();renderResults(availableResults);});
  localizeDocument();
  renderResults([]);
  updateLocalResultStatus(null);
  setupWebFolderAccess();
  setupWebDesigner();
  setupStudyExchange();
}
document.addEventListener("DOMContentLoaded",startStaticViewer,{once:true});
