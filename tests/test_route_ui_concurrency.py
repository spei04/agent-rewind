"""Deferred shipped-client responses cannot cross a credential generation."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
APP = Path(__file__).resolve().parents[1] / "agent_rewind/web/app.js"


@pytest.mark.skipif(NODE is None, reason="Node runtime unavailable for client regression")
@pytest.mark.parametrize("stage", ["identity", "lists", "selection", "login"])
@pytest.mark.parametrize("outcome", ["success", "failure", "network_failure"])
@pytest.mark.parametrize("order", ["old_first", "new_first"])
def test_credential_switch_invalidates_old_poll_selection_and_login(stage, outcome, order):
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const [app,stage,outcome,order]=process.argv.slice(1);
class Element {
  constructor(id) {
    this.id=id; this.children=[]; this.dataset={}; this.disabled=false; this.value='';
    const names=new Set(['hidden']);
    this.classList={add:(x)=>names.add(x),remove:(x)=>names.delete(x),
      contains:(x)=>names.has(x),toggle:(x,on)=>on?names.add(x):names.delete(x)};
  }
  replaceChildren(...items) {this.children=items;}
  append(...items) {this.children.push(...items);}
  showModal() {this.opened=true;}
  close() {this.opened=false;}
}
const nodes=new Map();
const get=(id)=>{if(!nodes.has(id)) nodes.set(id,new Element(id));return nodes.get(id);};
const deferred=()=>{
 let resolve,reject;
 const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
 return {promise,resolve,reject};
};
const response=(body,ok=true)=>({ok,json:async()=>body});
const old=deferred(), fresh=deferred(), calls=[], timers=[];
const oldIdentity={subject:'old-human',role:'operator',csrf:'old-csrf'};
const newIdentity={subject:'new-human',role:'viewer',csrf:'new-csrf'};
const oldRun={id:'old-run',name:'old protected run',status:'complete',success:true,
  steps:0,seed:1,policy:{adapter:'scripted'},branchable:true,events:[]};
let holding=false, oldCaptured=false;
const context=vm.createContext({
 document:{getElementById:get,createElement:(tag)=>new Element(tag),
  querySelectorAll:()=>[],querySelector:()=>null,addEventListener:()=>{},
  hidden:false,activeElement:{tagName:'BODY'}},
 fetch:async(url,options)=>{
   const token=options.headers.Authorization;
   calls.push([url,token]);
   if(url==='/api/me'&&token==='Bearer new-viewer') return fresh.promise;
   if(holding&&token!=='Bearer new-viewer'&&(
      (['identity','login'].includes(stage)&&url==='/api/me')||
      (stage==='lists'&&url==='/api/runs')||
      (stage==='selection'&&url==='/api/runs/old-run'))) {
     oldCaptured=true;return old.promise;
   }
   if(url==='/api/me') return response(oldIdentity);
   return response([]);
 },
 location:{reload:()=>{}},setInterval:(callback,ms)=>timers.push([callback,ms]),
 setTimeout:()=>{},URL:{},Blob:class{}
});
vm.runInContext(fs.readFileSync(app,'utf8'),context);
(async()=>{
 await new Promise(setImmediate);
 assert.equal(vm.runInContext('state.user.role',context),'operator');
 holding=true;
 let oldLogin;
 if(stage==='login') {
   get('api-key').value='old-operator';
   oldLogin=get('login-form').onsubmit({preventDefault:()=>{}});
 } else {
   if(stage==='selection')
     vm.runInContext('state.run={id:"old-run",status:"running"}',context);
   assert.equal(timers.length,1);assert.equal(timers[0][1],4000);
   timers[0][0]();
 }
 await new Promise(setImmediate);
 assert.equal(oldCaptured,true);
 assert.equal(vm.runInContext('state.busy',context),true);
 // Exercise the real key form while the older poll/selection/login is pending.
 get('api-key').value='new-viewer';
 const login=get('login-form').onsubmit({preventDefault:()=>{}});
 await new Promise(setImmediate);
 assert.equal(calls.filter(([url,token])=>
   url==='/api/me'&&token==='Bearer new-viewer').length,1);
 assert.equal(vm.runInContext('state.user',context),null);
 assert.equal(get('new-run').disabled,true);
 const releaseOld=async()=>{
   const value=outcome==='failure'?{detail:'obsolete failure'}:
     (['identity','login'].includes(stage)?oldIdentity:stage==='lists'?[oldRun]:oldRun);
   if(outcome==='network_failure') old.reject(new Error('obsolete network failure'));
   else old.resolve(response(value,outcome==='success'));
   await new Promise(setImmediate);
   if(oldLogin) await oldLogin;
 };
 if(order==='old_first') {
   await releaseOld();
   // An obsolete finally must not release the new lookup's busy state.
   assert.equal(vm.runInContext('state.busy',context),true);
   assert.equal(vm.runInContext('state.user',context),null);
   assert.equal(vm.runInContext('state.token',context),'new-viewer');
 }
 fresh.resolve(response(newIdentity));
 await login;
 await new Promise(setImmediate);
 if(order==='new_first') await releaseOld();
 assert.equal(vm.runInContext('state.token',context),'new-viewer');
 assert.equal(vm.runInContext('state.user.subject',context),'new-human');
 assert.equal(vm.runInContext('state.user.role',context),'viewer');
 assert.equal(vm.runInContext('state.csrf',context),'new-csrf');
 assert.equal(vm.runInContext('state.busy',context),false);
 assert.equal(vm.runInContext('state.run',context),null);
 assert.equal(vm.runInContext('state.runs.length',context),0);
 assert.equal(get('new-run').disabled,true);
 assert.equal(get('task-submit').disabled,true);
 assert.equal(get('logout').classList.contains('hidden'),false);
 assert.equal(get('notice').textContent,'');
 assert.equal(calls.filter(([url,token])=>
   ['/api/runs','/api/studies','/api/jobs'].includes(url)&&
   token==='Bearer new-viewer').length,3);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [NODE, "-e", script, str(APP), stage, outcome, order],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
