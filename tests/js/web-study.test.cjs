"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const {webcrypto}=require("node:crypto");
const context=vm.createContext({crypto:webcrypto,TextEncoder});
for(const name of ["analysis-core.js","web-study.js"])vm.runInContext(fs.readFileSync(path.resolve(__dirname,"../../src/atima_fl/ui/static",name),"utf8"),context);
const study=vm.runInContext("ATIMAStudy",context);
const fixture=(seed,score,key="audited")=>({id:"private/path",status:"complete",round:5,classes:["benign","dos"],seed_condition:{key},config:{
dataset:"edge_iiot",model:"mlp",partition:"iid",attack:"update_scaling",training_method:"standard",evaluation_scope:"shared",aggregation:"fedavg",
seed,clients:10,rounds:5,local_epochs:3,batch_size:128,learning_rate:.001,num_classes:2,attack_start:1,attack_end:5,malicious_clients:[0],attack_params:{factor:2},output_root:"secret/path"
},metrics:{test:{macro_f1:score,samples:4,per_class:{benign:{support:2},dos:{support:2}}}},dataset_identity:{task:"binary",hashes:Object.fromEntries(["train","validation","test","feature_schema.json","label_mapping.json","preprocessor.json"].map(k=>[k,"a".repeat(64)]))}});
(async()=>{
 const a=study.parse(await study.createWithEvidence("Study A",[fixture(0,.5),fixture(1,.7),fixture(2,.4),fixture(2,.6)]));
 const b=study.parse(await study.createWithEvidence("Study B",[fixture(0,.6),fixture(1,.8)]));
 assert.equal(a.version,2);
 assert.equal(a.observations[0].condition_sha256,b.observations[1].condition_sha256);
 assert.ok(!JSON.stringify(a).includes("private/path"));
 assert.ok(!JSON.stringify(a).includes("secret/path"));
 const result=study.comparisonGroups([a,b],"macro_f1");
 assert.equal(result.matches.length,1);
 assert.equal(result.matches[0].rows[0].stats.n,2);
 assert.equal(result.matches[0].rows[0].duplicateSeeds,1);
 assert.equal(result.matches[0].rows[0].stats.mean,.6);
 assert.ok(Math.abs(result.matches[0].rows[0].stats.sd-Math.sqrt(.02))<1e-12);
 const different=study.parse(await study.createWithEvidence("Study C",[fixture(0,.6,"different software")]));
 assert.equal(study.comparisonGroups([a,different],"macro_f1").matches.length,0);
 const legacy=study.parse(study.create("Legacy",[fixture(0,.6)]));
 assert.equal(study.comparisonGroups([a,legacy],"macro_f1").matches.length,0);
 const missing=fixture(0,.5);delete missing.dataset_identity.hashes.test;
 const incomplete=study.parse(await study.createWithEvidence("Incomplete",[missing]));
 assert.equal(study.comparisonGroups([a,incomplete],"macro_f1").excluded.length,1);
 const invalid=JSON.parse(JSON.stringify(a));invalid.observations[0].metrics.macro_f1=2;
 assert.throws(()=>study.parse(invalid),/outside valid range/);
 const pairedRuns=(cleanValues,attackValues)=>cleanValues.flatMap((value,i)=>{
   const clean=fixture(i,value,"clean-condition");clean.id="clean-"+i;
   clean.config.attack="none";clean.config.attack_params={};clean.config.malicious_clients=[];
   const attack=fixture(i,attackValues[i],"attack-condition");attack.id="attack-"+i;attack.baseline_id=clean.id;
   return [clean,attack];
 });
 const certify=(run,byId)=>run.config.attack!=="none"&&byId.get(run.baseline_id)?.config.attack==="none";
 const p=study.parse(await study.createWithEvidence("Paired A",pairedRuns([.9,.8],[.5,.6]),certify));
 const q=study.parse(await study.createWithEvidence("Paired B",pairedRuns([.8,.8],[.4,.6]),certify));
 assert.equal(p.observations.filter(r=>r.matched_clean_id).length,2);
 const effect=study.comparisonGroups([p,q],"macro_f1").matches.find(g=>g.condition.attack==="update_scaling");
 assert.equal(effect.rows[0].paired.delta.n,2);
 assert.ok(Math.abs(effect.rows[0].paired.delta.mean+.3)<1e-12);
 assert.ok(Math.abs(effect.rows[0].paired.clean.mean-.85)<1e-12);
 assert.equal(effect.baselineConditions.length,1);
 const badPair=JSON.parse(JSON.stringify(p));badPair.observations[1].matched_clean_id="Run-3";
 assert.throws(()=>study.parse(badPair),/Incompatible declared baseline/);
 const ambiguous=JSON.parse(JSON.stringify(p));ambiguous.observations.push({...ambiguous.observations[0],id:"Run-5"});
 const ambiguousEffect=study.comparisonGroups([study.parse(ambiguous),q],"macro_f1").matches.find(g=>g.condition.attack==="update_scaling");
 assert.equal(ambiguousEffect.rows[0].paired.delta.n,1);
 console.log("Study evidence, compatibility and separate seed statistics checks passed.");
})().catch(e=>{console.error(e);process.exitCode=1;});
