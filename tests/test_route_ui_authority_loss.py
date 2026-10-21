"""Pending presentations cannot repopulate data cleared after current access loss."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
APP = Path(__file__).resolve().parents[1] / "agent_rewind/web/app.js"


@pytest.mark.skipif(NODE is None, reason="Node runtime unavailable for client regression")
@pytest.mark.parametrize("stage", ["detail", "file_list", "file_content", "compare"])
@pytest.mark.parametrize("loss", ["null_role", "data_failure"])
def test_current_refresh_invalidates_pending_protected_presentations(stage, loss):
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const [app,stage,loss]=process.argv.slice(1);
class Element {
  constructor(id) {
    this.id=id;this.children=[];this.dataset={};this.disabled=false;this.value='';
    const names=new Set(['hidden']);
    this.classList={add:(x)=>names.add(x),remove:(x)=>names.delete(x),
      contains:(x)=>names.has(x),toggle:(x,on)=>on?names.add(x):names.delete(x)};
  }
  replaceChildren(...items) {this.children=items;}
  append(...items) {this.children.push(...items);}
  replaceWith() {}
  setAttribute() {}
  showModal() {this.opened=true;}
  close() {this.opened=false;}
}
const nodes=new Map();
const get=(id)=>{if(!nodes.has(id)) nodes.set(id,new Element(id));return nodes.get(id);};
const filesTab=new Element('files-tab-button');filesTab.dataset.tab='files';
let release;
const delayed=new Promise(resolve=>release=resolve);
const response=(body,ok=true)=>({ok,json:async()=>body});
const run={id:'old-run',name:'protected capture',status:'complete',success:false,
  steps:1,seed:1,policy:{adapter:'scripted'},branchable:true,parent_id:'parent',fork_step:1,
  events:[{step:1,action:{tool:'finish'},checkpoint:'c'.repeat(64),
    observed_result:{},actual_result:{exit_code:1},changes:[]}]};
const files=[{path:'private.txt'}];
const file={content:'old protected file',truncated:false};
const comparison={oldProtectedComparison:'private'};
let holding=false,captured=false,denied=false,currentRole='operator',csrf='initial-csrf';
const calls=[];
const context=vm.createContext({
 document:{getElementById:get,createElement:(tag)=>new Element(tag),
  querySelectorAll:(selector)=>selector==='[data-tab]'?[filesTab]:[],
  querySelector:()=>null,addEventListener:()=>{},hidden:false,
  activeElement:{tagName:'BODY'}},
 fetch:async(url,options)=>{
   calls.push([url,options]);
   if(url==='/auth/logout') return response({ok:true});
   if(url==='/api/me')
     return response({subject:'same-human',role:currentRole,csrf});
   if(holding&&(
      (stage==='detail'&&url==='/api/runs/old-run')||
      (stage==='file_list'&&url==='/api/runs/old-run/files/1')||
      (stage==='file_content'&&url.includes('?path=private.txt'))||
      (stage==='compare'&&url.startsWith('/api/compare?')))) {
     captured=true;return delayed;
   }
   if(denied) return response({detail:'Not found'},false);
   if(url==='/api/runs') return response([run]);
   if(url==='/api/runs/old-run') return response(run);
   if(url==='/api/runs/old-run/files/1') return response(files);
   if(url.includes('?path=private.txt')) return response(file);
   if(url.startsWith('/api/compare?')) return response(comparison);
   return response([]);
 },
 location:{reload:()=>{}},setInterval:()=>{},setTimeout:()=>{},URL:{},Blob:class{}
});
vm.runInContext(fs.readFileSync(app,'utf8'),context);
(async()=>{
 await new Promise(setImmediate);
 assert.equal(vm.runInContext('state.user.role',context),'operator');
 const identityGeneration=vm.runInContext('state.identityGeneration',context);
 let pending;
 if(stage==='detail') {
   holding=true;
   pending=get('run-list').children[0].onclick();
 } else {
   // The selection is reached through its real rendered list action.
   await get('run-list').children[0].onclick();
   assert.equal(vm.runInContext('state.run.id',context),'old-run');
   if(stage==='file_content') await filesTab.onclick();
   holding=true;
   if(stage==='file_list') pending=filesTab.onclick();
   if(stage==='file_content') pending=get('file-list').children[0].onclick();
   if(stage==='compare') pending=get('compare').onclick();
 }
 await new Promise(setImmediate);
 assert.equal(captured,true);
 currentRole=loss==='null_role'?null:'operator';denied=true;csrf='fresh-own-csrf';
 await get('refresh').onclick();
 assert.equal(vm.runInContext('state.identityGeneration',context),identityGeneration);
 assert.equal(vm.runInContext('state.user.subject',context),'same-human');
 assert.equal(vm.runInContext('state.user.role',context),null);
 assert.equal(vm.runInContext('state.csrf',context),'fresh-own-csrf');
 assert.equal(vm.runInContext('state.run',context),null);
 assert.equal(get('run-detail').classList.contains('hidden'),true);
 const staleBody=stage==='detail'?run:stage==='file_list'?files:
   stage==='file_content'?file:comparison;
 release(response(staleBody));
 await pending;
 await new Promise(setImmediate);
 // Successful old detail/file/compare responses must not undo access clearing.
 assert.equal(vm.runInContext('state.run',context),null);
 assert.equal(get('run-detail').classList.contains('hidden'),true);
 assert.equal(get('file-list').children.length,0);
 assert.equal(get('file-content').textContent,'');
 assert.equal(get('compare-output').textContent,'');
 assert.equal(get('compare-dialog').opened,false);
 assert.equal(get('new-run').disabled,true);
 assert.equal(get('notice').textContent,'Not found');
 assert.equal(get('logout').classList.contains('hidden'),false);
 await get('logout').onclick();
 const logout=calls.find(([url])=>url==='/auth/logout');
 assert.equal(logout[1].headers['X-Rewind-CSRF'],'fresh-own-csrf');
 // This invalidation cannot permanently disable later, newly authorized reads.
 holding=false;denied=false;currentRole='operator';
 await get('refresh').onclick();
 assert.equal(get('new-run').disabled,false);
 await get('run-list').children[0].onclick();
 assert.equal(vm.runInContext('state.run.id',context),'old-run');
 assert.equal(get('run-detail').classList.contains('hidden'),false);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [NODE, "-e", script, str(APP), stage, loss],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
