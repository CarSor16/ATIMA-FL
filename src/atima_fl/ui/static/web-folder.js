"use strict";

// Optional browser-only directory handles. Never persist file contents.
const ATIMAFolderAccess=(()=>{
  const names=["manifest.json","final_metrics.json","validation_history.json","test_logits.json"];
  async function scan(handle){
    const files=[];let visited=0;
    async function fileAt(dir,name){
      try{return await dir.getFileHandle(name);}catch(error){if(error.name==="NotFoundError"||error.name==="TypeMismatchError")return null;throw error;}
    }
    async function walk(dir,path,depth){
      if(++visited>2000||depth>16)throw Error("Directory scan limit reached. Choose a narrower campaign folder.");
      const manifest=await fileAt(dir,names[0]);
      if(manifest){
        for(const name of names){
          const h=name===names[0]?manifest:await fileAt(dir,name);
          if(!h)continue;
          const file=await h.getFile();
          files.push({name,relativePath:path+"/"+name,size:file.size,lastModified:file.lastModified,text:()=>file.text()});
        }
        // Never descend into trajectory/client-artifact folders of a recognized run.
        return;
      }
      for await(const [name,entry] of dir.entries()){
        if(entry.kind==="directory"&&![".git","client_artifacts","__pycache__"].includes(name))
          await walk(entry,path+"/"+name,depth+1);
      }
    }
    await walk(handle,handle.name||"Selected folder",0);
    return files;
  }
  function database(){
    return new Promise((resolve,reject)=>{
      const request=indexedDB.open("atima-web-folder-access",1);
      request.onupgradeneeded=()=>request.result.createObjectStore("references");
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(Error("Folder reference storage is blocked"));
    });
  }
  async function storage(mode,operation){
    const db=await database();
    try{return await new Promise((resolve,reject)=>{
      const tx=db.transaction("references",mode),request=operation(tx.objectStore("references"));
      tx.oncomplete=()=>resolve(request.result);
      tx.onerror=()=>reject(tx.error);
      tx.onabort=()=>reject(tx.error||Error("Folder reference operation cancelled"));
    });}finally{db.close();}
  }
  return Object.freeze({scan,recall:()=>storage("readonly",store=>store.get("folder")),
    remember:handle=>storage("readwrite",store=>store.put(handle,"folder")),
    forget:()=>storage("readwrite",store=>store.delete("folder"))});
})();
function setupWebFolderAccess(){
  const panel=$("web-folder-access"),status=$("web-folder-status");
  if(!panel||typeof window.showDirectoryPicker!=="function")return;
  panel.classList.remove("hidden");
  const open=$("web-folder-open"),reconnect=$("web-folder-reconnect"),refresh=$("web-folder-refresh"),remember=$("web-folder-remember");
  let handle=null,saved=null,busy=false,revision=0;
  function buttons(){open.disabled=busy;reconnect.disabled=busy||!saved;refresh.disabled=busy||!handle;}
  async function read(selected){
    const ticket=++revision;busy=true;buttons();
    try{
      if(await selected.queryPermission({mode:"read"})!=="granted"&&await selected.requestPermission({mode:"read"})!=="granted")throw Error("Read permission not granted");
      const files=await ATIMAFolderAccess.scan(selected);
      if(ticket!==revision)return;
      handle=selected;localResultFiles=files;
      status.textContent="Authorized folder read locally. No file contents are stored.";
      if(remember.checked){
        try{await ATIMAFolderAccess.remember(selected);saved=selected;}
        catch{status.textContent+=" Browser could not save the folder reference.";}
      }
      if(ticket===revision)await refreshResults();
    }catch(error){if(ticket===revision)status.textContent=error.message;}
    finally{if(ticket===revision){busy=false;buttons();}}
  }
  open.addEventListener("click",async()=>{
    try{const selected=await window.showDirectoryPicker({mode:"read"});await read(selected);}
    catch(error){if(error.name!=="AbortError")status.textContent=error.message;}
  });
  reconnect.addEventListener("click",()=>{if(saved)read(saved);});
  refresh.addEventListener("click",()=>{if(handle)read(handle);});
  remember.addEventListener("change",async()=>{
    if(!remember.checked){saved=null;buttons();try{await ATIMAFolderAccess.forget();}catch{status.textContent="Could not remove the stored folder reference; review browser site storage.";}}
    else if(handle){try{await ATIMAFolderAccess.remember(handle);saved=handle;buttons();}catch{status.textContent="Browser could not save the folder reference.";}}
  });
  $("local-results-reset").addEventListener("click",async()=>{
    revision++;handle=null;saved=null;busy=false;remember.checked=false;buttons();
    try{await ATIMAFolderAccess.forget();status.textContent="Folder reference removed.";}
    catch{status.textContent="Could not remove stored reference; review browser site storage.";}
  });
  $("local-results-folder").addEventListener("change",()=>{revision++;handle=null;busy=false;buttons();});
  const startup=revision;
  ATIMAFolderAccess.recall().then(value=>{if(startup===revision&&value?.kind==="directory"){saved=value;remember.checked=true;buttons();status.textContent="A folder reference is remembered. Reconnect explicitly to read it.";}}).catch(()=>{});
  buttons();
}
