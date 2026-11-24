"use strict";

// Pure analysis primitives, shared by local and future browser-only views.
// No DOM, storage, network, credentials or access to the filesystem.
const ATIMAAnalysis = (() => {
  const finite = value => typeof value === "number" && Number.isFinite(value);
  function stats(values) {
    const valid = values.filter(finite);
    if (!valid.length) return {n:0,mean:null,sd:null,min:null,max:null};
    const mean = valid.reduce((sum,value)=>sum+value,0)/valid.length;
    return {n:valid.length,mean,sd:valid.length>1
      ?Math.sqrt(valid.reduce((sum,value)=>sum+(value-mean)**2,0)/(valid.length-1)):null,
      min:Math.min(...valid),max:Math.max(...valid)};
  }
  // Deterministic exploratory bootstrap, resampling complete seed observations.
  function bootstrapMean(values,resamples=10000){
    if(!Array.isArray(values)||values.length<3||values.length>1000||values.some(v=>!finite(v)))return null;
    let state=2026;
    const means=[];
    for(let b=0;b<resamples;b++){
      let sum=0;
      for(let i=0;i<values.length;i++){state=(Math.imul(1664525,state)+1013904223)>>>0;sum+=values[Math.floor(state/4294967296*values.length)];}
      means.push(sum/values.length);
    }
    means.sort((a,b)=>a-b);
    const quantile=p=>{const i=p*(means.length-1),lo=Math.floor(i),hi=Math.ceil(i);return means[lo]+(i-lo)*(means[hi]-means[lo]);};
    return {n:values.length,mean:stats(values).mean,lower:quantile(.025),upper:quantile(.975),resamples};
  }
  function pairedStats(observations) {
    const pairs=observations.filter(([a,b])=>finite(a)&&finite(b));
    return {clean:stats(pairs.map(p=>p[0])),attack:stats(pairs.map(p=>p[1])),
      delta:stats(pairs.map(([a,b])=>b-a))};
  }
  function normalizeMatrix(matrix) {
    if(!Array.isArray(matrix)||matrix.length<2||!matrix.every(row=>Array.isArray(row)
      &&row.length===matrix.length&&row.every(v=>Number.isSafeInteger(v)&&v>=0)))
      throw new Error("Invalid confusion matrix");
    return matrix.map(row=>{
      const total=row.reduce((sum,value)=>sum+value,0);
      if(!Number.isSafeInteger(total))throw new Error("Invalid row total");
      return row.map(value=>total?value/total:null);
    });
  }
  function meanMatrices(matrices) {
    if(!matrices.length)return null;
    const normalized=matrices.map(normalizeMatrix);
    const size=normalized[0].length;
    if(normalized.some(m=>m.length!==size))throw new Error("Matrix dimensions differ");
    return normalized[0].map((row,i)=>row.map((_,j)=>stats(normalized.map(m=>m[i][j]))));
  }
  function pairedMatrices(pairs) {
    if(!pairs.length)return null;
    const normalized=pairs.map(([a,b])=>[normalizeMatrix(a),normalizeMatrix(b)]);
    const size=normalized[0][0].length;
    if(normalized.some(([a,b])=>a.length!==size||b.length!==size))
      throw new Error("Matrix dimensions differ");
    return normalized[0][0].map((row,i)=>row.map((_,j)=>pairedStats(normalized.map(([a,b])=>[a[i][j],b[i][j]]))));
  }
  function campaignCoverage(expected, observed) {
    if(!Array.isArray(expected)||!expected.length||expected.length>50
      ||expected.some(s=>!Number.isInteger(s)||s<0||s>4294967295)
      ||new Set(expected).size!==expected.length)throw new Error("Choose 1–50 distinct non-negative integer seeds");
    const bySeed=new Map();
    for(const item of observed){
      if(!Number.isInteger(item.seed)||item.seed<0)continue;
      if(!bySeed.has(item.seed))bySeed.set(item.seed,[]);
      bySeed.get(item.seed).push(item);
    }
    return {
      rows:[...expected].sort((a,b)=>a-b).map(seed=>{
        const items=bySeed.get(seed)||[];
        const chosen=items.filter(item=>item.selected);
        return {seed,observed:items.length,selected:chosen.length===1,
          matched:chosen.length===1&&chosen[0].matched===true};
      }),
      unexpected:[...bySeed.keys()].filter(seed=>!expected.includes(seed)).sort((a,b)=>a-b)
    };
  }
  // Quote every cell. Untrusted text cannot become a spreadsheet formula.
  function csv(rows){
    const cell=value=>{
      if(value===null||value===undefined)return '""';
      let raw=finite(value)?String(value):String(value);
      if(typeof value!=="number"&&/^[\s]*[=+\-@]/.test(raw))raw="'"+raw;
      return '"'+raw.replace(/"/g,'""')+'"';
    };
    return rows.map(row=>row.map(cell).join(",")).join("\r\n")+"\r\n";
  }
  return Object.freeze({stats,pairedStats,meanMatrices,pairedMatrices,campaignCoverage,csv,bootstrapMean});
})();
