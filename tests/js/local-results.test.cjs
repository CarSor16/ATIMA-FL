"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.resolve(__dirname,"../../src/atima_fl/ui/static/local-results.js"),"utf8"),context);
const reader=vm.runInContext("ATIMALocalResults",context);
const plain=value=>JSON.parse(JSON.stringify(value));
function fixture(seed=0,attack="update_scaling"){
  return {status:"complete",last_valid_round:5,pair_id:"pair-"+seed,
    config:{seed,attack,attack_params:attack==="none"?{}:{factor:2},malicious_clients:attack==="none"?[]:[0],
      clients:2,servers:1,dataset:"edge_iiot",dataset_params:{task:"binary"},partition:"iid",partition_params:{},
      model:"mlp",model_params:{},rounds:5,local_epochs:3,aggregation:"fedavg",aggregation_params:{},
      defenses:[],optimizer:"adam",optimizer_params:{},loss:"cross_entropy",loss_params:{},batch_size:128,learning_rate:.001,attack_start:1,attack_end:5},
    dataset_audit:{task:"binary",classes:["benign","dos"],hashes:Object.fromEntries(
      ["train","validation","test","feature_schema.json","label_mapping.json","preprocessor.json","assignment","client_0","client_1"].map(k=>[k,"fixture-"+k]))},
    source_identity:{version:"fixture"},runtime:{device:"cpu"},attack_source:attack};
}
function file(dir,name,value){
  const data=JSON.stringify(value);
  return {name,webkitRelativePath:dir+"/"+name,size:Buffer.byteLength(data),lastModified:0,text:async()=>data};
}
async function main(){
  const a=fixture(),b=fixture(1),clean=fixture(0,"none");
  const ar=reader.project("a",a),br=reader.project("b",b);
  assert.ok(ar.seed_condition.key);assert.equal(ar.seed_condition.key,br.seed_condition.key);
  b.config.attack_params.factor=3;
  const changed=reader.project("b",b);
  assert.notEqual(ar.seed_condition.key,changed.seed_condition.key);
  assert.equal(ar.sensitivity_conditions.find(v=>v.axis==="attack_params.factor").key,changed.sensitivity_conditions.find(v=>v.axis==="attack_params.factor").key);
  const pairs=reader.pair([ar,reader.project("clean",clean)]);
  assert.equal(pairs[0].baseline_id,"clean");
  const wrong=fixture(1,"none");wrong.pair_id=a.pair_id;
  assert.equal(reader.pair([ar,reader.project("wrong",wrong)])[0].baseline_id,null);
  assert.equal(reader.pair([ar,reader.project("c1",clean),reader.project("c2",clean)])[0].baseline_id,null);
  const incomplete=fixture();delete incomplete.dataset_audit.hashes.assignment;
  assert.equal(reader.project("legacy",incomplete).seed_condition.key,null);
  assert.throws(()=>reader.project("bad",a,{test:{accuracy:2}}),/Invalid final metric/);
  assert.throws(()=>reader.project("bad",a,{},[{round:2},{round:1}]),/Invalid validation round/);
  assert.throws(()=>reader.project("bad",a,{federated:{rounds:[null]}}),/Invalid federated telemetry/);
  assert.throws(()=>reader.project("bad",a,{},[{round:1,recall:[2]}]),/Invalid validation class recall/);
  assert.throws(()=>reader.project("bad",a,{test:{per_class:{dos:null}}}),/Invalid per-class metrics/);
  const logits={schema_version:1,split:"test",classes:["benign","dos"],labels:[0,1,1],logits:[[1000,-1000],[0,0],[-1000,1000]]};
  const summary=reader.summarizeLogits(logits,["benign","dos"]);
  assert.equal(summary.accuracy,2/3);assert.deepEqual(plain(summary.confusion_matrix),[[1,0],[1,1]]);
  assert.ok(Math.abs(summary.nll-Math.log(2)/3)<1e-12);
  assert.throws(()=>reader.summarizeLogits({...logits,classes:["dos","benign"]},["benign","dos"]),/class order/);
  assert.throws(()=>reader.summarizeLogits({...logits,labels:[0,2,1]},["benign","dos"]),/Invalid labeled logit row/);
  const broken={name:"manifest.json",webkitRelativePath:"root/broken/manifest.json",size:3,text:async()=>"{!!"};
  const forbidden={name:"trajectory.h5",webkitRelativePath:"root/a/trajectory.h5",size:1,text:async()=>{throw Error("must not read HDF5")}};
  const deferred={...file("root/a","test_logits.json",logits),text:async()=>{throw Error("must not eagerly read logits")}};
  const result=await reader.load([file("root/a","manifest.json",a),file("root/clean","manifest.json",clean),broken,forbidden,deferred]);
  assert.equal(result.runs.length,2);assert.equal(result.errors.length,1);assert.equal(result.logits.size,1);
  assert.equal(result.runs.find(r=>r.id==="root/a").baseline_id,"root/clean");
  assert.equal(reader.indexFiles([file("root/../bad","manifest.json",a)]).size,0);
  assert.throws(()=>reader.indexFiles([file("root/a","manifest.json",a),file("root/a","manifest.json",a)]),/Duplicate/);
  console.log("Local folder and logit reader checks passed (no network API in test context).");
}
main().catch(error=>{console.error(error);process.exitCode=1;});
