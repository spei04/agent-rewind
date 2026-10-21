"""Execute the shipped client without a browser or third-party DOM dependency."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
APP = Path(__file__).resolve().parents[1] / "agent_rewind/web/app.js"


@pytest.mark.skipif(NODE is None, reason="Node runtime unavailable for client regression")
@pytest.mark.parametrize("role", [None, "unknown", "operator"])
@pytest.mark.parametrize("trigger", ["manual", "poll"])
def test_current_refresh_clears_old_actions_but_keeps_csrf_logout(role, trigger):
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(id) {
    this.id=id; this.children=[]; this.dataset={}; this.disabled=false;
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
const get=(id)=>{if(!nodes.has(id)) nodes.set(id,new Element(id)); return nodes.get(id);};
const stale=new Element('stale-cancel'); stale.dataset.projectAction='cancel';
const calls=[], timers=[];
let currentRole='operator', denied=false, reloads=0;
const context=vm.createContext({
 document:{getElementById:get,createElement:(tag)=>new Element(tag),
  querySelectorAll:(selector)=>selector==='[data-project-action]'?[stale]:[],
  querySelector:()=>null,addEventListener:()=>{},hidden:false,
  activeElement:{tagName:'BODY'}},
 fetch:async(url,options)=>{calls.push([url,options]);
   if(url==='/auth/logout') return {ok:true,json:async()=>({ok:true})};
   if(url==='/api/me') return {ok:true,json:async()=>({
     subject:'own-principal',csrf:'fresh-csrf',role:currentRole})};
   return {ok:!denied,json:async()=>denied?{detail:'Not found'}:[]};},
 location:{reload:()=>reloads++},setInterval:(callback,ms)=>timers.push([callback,ms]),
 setTimeout:()=>{},URL:{},Blob:class{}
});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
(async()=>{
 await new Promise(setImmediate);
 assert.equal(vm.runInContext('state.user.role',context),'operator');
 assert.equal(get('new-run').disabled,false);
 vm.runInContext('state.run={id:"old"};state.runs=[state.run]',context);
 stale.disabled=false;
 get('task-dialog').showModal(); get('study-dialog').showModal();
 const beforeMe=calls.filter(([url])=>url==='/api/me').length;
 currentRole=JSON.parse(process.argv[2]); denied=true;
 if(process.argv[3]==='manual') await get('refresh').onclick();
 else {
   assert.equal(timers.length,1); assert.equal(timers[0][1],4000);
   timers[0][0](); await new Promise(setImmediate);
 }
 assert.equal(calls.filter(([url])=>url==='/api/me').length,beforeMe+1);
 assert.equal(vm.runInContext('state.user.role',context),null);
 assert.equal(get('notice').textContent,'Not found');
 assert.equal(vm.runInContext('state.csrf',context),'fresh-csrf');
 assert.equal(vm.runInContext('state.run',context),null);
 assert.equal(vm.runInContext('state.runs.length',context),0);
 for(const id of [
   'branch','investigate','new-run','empty-record','task-submit','study-submit'])
   assert.equal(get(id).disabled,true);
 assert.equal(stale.disabled,true);
 assert.equal(get('logout').classList.contains('hidden'),false);
 assert.equal(get('task-dialog').opened,false);
 assert.equal(get('study-dialog').opened,false);
 get('new-run').onclick(); assert.notEqual(get('task-dialog').opened,true);
 const beforeActions=calls.length;
 await get('task-form').onsubmit({preventDefault:()=>{}});
 await get('study-form').onsubmit({preventDefault:()=>{}});
 await get('branch').onclick();
 await get('investigate').onclick();
 await assert.rejects(vm.runInContext('queued("/runs",{})',context),/current operator/);
 assert.equal(calls.length,beforeActions);
 assert.equal(get('study-dialog').opened,false);
 await get('logout').onclick();
 const logout=calls.filter(([url])=>url==='/auth/logout');
 assert.equal(logout.length,1);
 assert.equal(logout[0][1].headers['X-Rewind-CSRF'],'fresh-csrf');
 assert.equal(reloads,1);
 // A later successful current-role check restores actions, including when the
 // failed refresh itself had still reported operator.
 currentRole='operator'; denied=false;
 await get('refresh').onclick();
 assert.equal(vm.runInContext('state.user.role',context),'operator');
 for(const id of ['new-run','empty-record','task-submit','study-submit'])
   assert.equal(get(id).disabled,false);
 get('new-run').onclick(); assert.equal(get('task-dialog').opened,true);
 for(const [role,expected] of [
     ['viewer',false],['administrator',false],['operator',true],['maintainer',true]]) {
   vm.runInContext(`state.user={role:${JSON.stringify(role)}}`,context);
   assert.equal(vm.runInContext('canOperate()',context),expected);
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [NODE, "-e", script, str(APP), json.dumps(role), trigger],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
