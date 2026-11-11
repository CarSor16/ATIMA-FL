"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor(tag="div") { this.tagName=tag; this.children=[]; this.dataset={}; this.listeners={}; this._text=""; }
  set textContent(text) {this._text=String(text); this.children=[];}
  get textContent() {return this._text+this.children.map(x=>x.textContent).join("");}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this._text="";this.children=children;}
  addEventListener(name,fn) {(this.listeners[name]??=[]).push(fn);}
  setAttribute(name,value) {this[name]=value;}
}
const ids=new Map();
for(const key of ["dash-datasets","dash-clients","dash-attacks","dash-aggregators",
  "dash-recent-body","dash-recent-status","dash-health","dash-settings-theme"]) ids.set(key,new Element());
const listeners=new Map();
const document={
  getElementById:key=>ids.get(key),
  querySelectorAll:()=>[],
  createElement:tag=>new Element(tag),
  createTextNode:text=>({textContent:String(text)}),
  addEventListener:(name,fn)=>listeners.set(name,fn),
};
const requests=[];
const records={
  "/api/catalog":{catalog:{dataset:[{id:"edge_iiot"},{id:"custom"}],attack:[{id:"none"},{id:"sign_flip"},{id:"min_max"}],aggregator:[{id:"fedavg"}]}},
  "/api/defaults":{clients:7},
  "/api/results":[{id:"real_run",config:{attack:"sign_flip",dataset:"edge_iiot",clients:7},status:"complete",round:2}]
};
const context={document,fetch:async url=>{requests.push(url);return {ok:true,json:async()=>records[url]};},console,navigateTo:page=>requests.push("nav:"+page)};
const source=fs.readFileSync(path.resolve(__dirname,"../../src/atima_fl/ui/static/dashboard.js"),"utf8");
vm.runInNewContext(source,context);
setImmediate(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ids.get("dash-datasets").textContent,"2");
  assert.equal(ids.get("dash-attacks").textContent,"2");
  assert.equal(ids.get("dash-aggregators").textContent,"1");
  assert.equal(ids.get("dash-clients").textContent,"7");
  assert.equal(ids.get("dash-health").textContent,"Studio ready");
  const table=ids.get("dash-recent-body");
  assert.equal(table.children.length,1);
  assert.equal(table.children[0].children[0].textContent,"real_run");
  assert(requests.includes("/api/results"));
  records["/api/results"]=[];
  listeners.get("atima:navigate")({detail:{page:"dashboard"}});
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(ids.get("dash-recent-body").textContent,/No imported experiments/);
  assert(!source.includes("exp_001"));
  console.log("OK dashboard real metadata, empty state, and navigation refresh");
});
