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
 console.log("Study evidence, compatibility and separate seed statistics checks passed.");
})().catch(e=>{console.error(e);process.exitCode=1;});
