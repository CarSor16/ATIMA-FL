"use strict";
// Standalone figures are exported locally; no external fonts, images or services.
function attachWebChartExports(svg,container){
  const actions=node("div",undefined,"web-chart-export"),status=node("span",undefined,"helper");
  const title=svg.getAttribute("aria-label")||"ATIMA chart";
  const name="atima-"+title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,64);
  function save(blob,ext){const url=URL.createObjectURL(blob),link=node("a");link.href=url;link.download=name+"."+ext;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function standalone(){
    const copy=svg.cloneNode(true),originals=[svg,...svg.querySelectorAll("*")],clones=[copy,...copy.querySelectorAll("*")];
    const props=["color","fill","fill-opacity","stroke","stroke-width","stroke-opacity","stroke-dasharray","stroke-linecap","stroke-linejoin","opacity","font-family","font-size","font-weight","text-anchor"];
    originals.forEach((element,i)=>{const style=getComputedStyle(element);for(const prop of props)clones[i].style.setProperty(prop,style.getPropertyValue(prop));});
    const view=svg.viewBox.baseVal;
    if(!view.width||!view.height)throw Error("Chart has no valid dimensions");
    copy.setAttribute("width",String(view.width));copy.setAttribute("height",String(view.height));
    const bg=document.createElementNS("http://www.w3.org/2000/svg","rect");
    bg.setAttribute("x",String(view.x));bg.setAttribute("y",String(view.y));bg.setAttribute("width",String(view.width));bg.setAttribute("height",String(view.height));
    bg.setAttribute("fill",document.documentElement.dataset.theme==="dark"?"#111827":"#ffffff");copy.insertBefore(bg,copy.firstChild);
    return {xml:new XMLSerializer().serializeToString(copy),width:view.width,height:view.height};
  }
  for(const ext of ["svg","png"]){
    const button=node("button",ext.toUpperCase(),"secondary");button.type="button";button.setAttribute("aria-label","Export "+title+" as "+ext.toUpperCase());
    button.addEventListener("click",async()=>{
      button.disabled=true;status.textContent="";
      try{
        const {xml,width,height}=standalone();
        if(ext==="svg")save(new Blob([xml],{type:"image/svg+xml;charset=utf-8"}),ext);
        else{
          const img=new Image();
          await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error("Could not render chart"));img.src="data:image/svg+xml;charset=utf-8,"+encodeURIComponent(xml);});
          const canvas=document.createElement("canvas");canvas.width=Math.ceil(width*3);canvas.height=Math.ceil(height*3);
          canvas.getContext("2d").drawImage(img,0,0,canvas.width,canvas.height);
          const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));if(!blob)throw Error("Could not encode PNG");save(blob,ext);
        }
        status.textContent="Figure exported locally.";
      }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
    });actions.append(button);
  }
  actions.append(status);container.append(actions);
}
