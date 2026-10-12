import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const require = createRequire(import.meta.url);
const {startGeneratedService} = require(path.join(config.management, 'electron_gui/dist/generator_bridge.js'));
const {readEvidenceSnapshot} = require(path.join(config.management, 'electron_gui/dist/evidence_store.js'));
const evidence = path.join(config.workspace, 'evidence');
fs.mkdirSync(evidence, {recursive:true});
const write = (name, value) => { const file=path.join(evidence,name); fs.writeFileSync(file, JSON.stringify(value,null,2)+'\n',{flag:'wx'}); return file; };
const read = file => JSON.parse(fs.readFileSync(file,'utf8'));
const records=[];
const commandLogs=path.join(config.workspace,'command-logs');
fs.mkdirSync(commandLogs,{recursive:true});
function run(id, command, args, options={}) {
  const start=performance.now();
  const result=spawnSync(command,args,{encoding:'utf8',timeout:180000,maxBuffer:1024*1024,...options});
  records.push({commandId:id,durationMs:Math.round(performance.now()-start),status:result.status===0?'passed':'failed'});
  fs.writeFileSync(path.join(commandLogs,`${records.length}-${id}.log`),JSON.stringify({
    ...records[records.length-1],stdoutBytes:Buffer.byteLength(result.stdout??''),stderrBytes:Buffer.byteLength(result.stderr??'')
  })+'\n',{flag:'wx'});
  if (result.status!==0) throw new Error(`${id} failed; inspect the bounded command summary`);
  return result.stdout;
}
function validate(contract,file) { run(`validate.${contract}`,config.python,[path.join(config.hub,'tools/validate_contracts.py'),'--contract',contract,'--document',file]); }
const session=await startGeneratedService(path.join(config.management,'electron_gui'),config.workspace,{
  behavior:'STATEFUL_BOOLEAN_DEVICE_V1',projectName:'virtual-switch',serviceId:'device.virtual-switch',packageName:'io.smarthome.generated.device',className:'VirtualSwitch'
});
try {
  const project=path.join(config.workspace,'generated-services/virtual-switch');
  const logicCp=[path.join(project,'target/classes'),path.join(project,'target/dependency/*')].join(path.delimiter);
  const java=config.java;
  const invoke=(operation,graph=false,trace) => {
    const args=['-cp',logicCp,'io.smarthome.logic.tinyrpc.TinyRpcLogicCli',graph?'invoke-graph':'invoke','127.0.0.1',String(session.provider.port),'device.virtual-switch',operation,'[]'];
    if(graph) args.push('--descriptor-file',path.join(project,'service-descriptor.json'),'--trace-file',trace ?? path.join(evidence,`graph-${operation}-${Date.now()}.json`));
    return JSON.parse(run(`rpc.${operation}`,java,args));
  };
  const descriptor=path.join(project,'service-descriptor.json');
  validate('ServiceDescriptor',descriptor);
  const generated=read(descriptor);
  assert.equal(generated.transport.kind,'tiny-rpc-netty');
  write('service-descriptor.json',generated);
  const registered=read(path.join(config.workspace,'catalog/local-catalog.json'));
  assert.equal(registered.catalogId,session.catalogId);
  for(const operation of ['setEnabled','readEnabled','readActionCount']) {
    const entry=registered.services.find(item=>item.serviceId===generated.serviceId && item.operation===operation);
    assert.ok(entry); assert.equal(entry.port,session.provider.port); assert.equal(entry.host,'127.0.0.1');
    assert.equal(entry.transport,'tiny-rpc-netty');
  }
  const digest = data => createHash('sha256').update(data).digest('hex');
  const generationManifest=write('generation-manifest.json',{
    schemaVersion:'1.0.1',generationId:`generation.${session.generationManifest.generationId}`,generatorVersion:'management.generator.v1',
    templateHash:session.generationManifest.templateHash,serviceContractHash:digest(fs.readFileSync(descriptor)),
    outputFiles:Object.entries(session.generationManifest.files).map(([relativePath,sha256])=>{
      assert.equal(digest(fs.readFileSync(path.join(project,relativePath))),sha256); return {relativePath,sha256};
    }),build:{commandId:'management.generated.package',status:'passed'},registration:{catalogId:session.catalogId,status:'registered'}
  });
  validate('GenerationManifest',generationManifest);
  assert.equal(invoke('readEnabled').value.value,false);
  assert.equal(invoke('readActionCount').value.value,0);
  const calibration=path.join(evidence,'calibration-trace.json');
  invoke('readEnabled',true,calibration); validate('TrafficTrace',calibration);
  const calibrationTrace=read(calibration); assert.equal(calibrationTrace.sourceKind,'instrumented-rpc');
  const training=write('training.json',{schemaVersion:'1.0.0',modelVersion:'traffic-profile-live-v1',threshold:1,ambiguityMargin:0,labels:[{
    label:'sensor-read',traces:[calibrationTrace],patterns:[{kind:'ordering',status:'matched',details:'Calibration observes a loopback read request before its response.'}]
  }]});
  const model=path.join(evidence,'live-model.json');
  const pythonEnv={...process.env,PYTHONPATH:config.profiling};
  run('profiler.train',config.python,['-m','smart_rule_analyzer.model_cli','--training',training,'--output',model],{env:pythonEnv});
  const trace=path.join(evidence,'traffic-trace.json');
  const preaction=invoke('readEnabled',true,trace); assert.equal(preaction.value.value,false); validate('TrafficTrace',trace);
  const profile=path.join(evidence,'profile-evidence.json');
  run('profiler.classify',config.python,['-m','smart_rule_analyzer.profile_cli','--trace',trace,'--model',model,'--output',profile,'--produced-at',new Date().toISOString()],{env:pythonEnv});
  validate('ProfileEvidence',profile);
  const normal=read(profile);
  const planDocument=(id,tasks=1) => ({schemaVersion:'1.0.1',planId:id,tasks:Array.from({length:tasks},(_,i)=>({taskId:`task.action.${i}`,dependencies:[],readResources:[],writeResources:['resource.virtual-switch'],action:{serviceId:'device.virtual-switch',operation:'setEnabled',arguments:[]}})),conditions:[],deadlineEpochMs:Date.now()+60000});
  const scenarios=[];
  function schedule(name, profileFile, expected, taskCount, delta) {
    const plan=write(`${name}-plan.json`,planDocument(`plan.${name}`,taskCount)); validate('SchedulePlan',plan);
    const decision=path.join(evidence,`${name}-decision.json`), events=path.join(evidence,`${name}-events.jsonl`), actions=path.join(evidence,`${name}-actions.jsonl`);
    const before=invoke('readActionCount').value.value;
    run(`scheduler.${name}`,java,['-cp',config.schedulerCp,'concurrency.adapter.SchedulerCli','--plan',plan,'--evidence',profileFile,'--decision',decision,'--trusted-model-hash',normal.modelHash,'--trusted-model-version',normal.modelVersion,'--handler-class','integration.HubRpcBridge','--condition-class','integration.HubRpcBridge','--events',events],{env:{...process.env,HUB_JAVA:java,HUB_LOGIC_CP:logicCp,HUB_PROVIDER_PORT:String(session.provider.port),HUB_SERVICE_ID:'device.virtual-switch',HUB_DECISION_FILE:decision,HUB_ACTION_JOURNAL:actions,HUB_DESCRIPTOR_FILE:descriptor,HUB_TRACE_ROOT:evidence}});
    validate('SchedulingDecision',decision);
    const d=read(decision); assert.equal(d.decision,expected); assert.equal(d.profileEvidenceId,read(profileFile).profileId);
    assert.ok(Date.parse(d.persistedAt)>=Date.parse(read(profileFile).producedAt));
    const actionRecords=fs.existsSync(actions)?fs.readFileSync(actions,'utf8').trim().split('\n').map(JSON.parse):[];
    for(const a of actionRecords) { assert.equal(a.decisionId,d.decisionId); assert.ok(a.decisionBytesPresentBeforeAction>0); assert.ok(Date.parse(a.actionStartedAt)>=Date.parse(d.persistedAt)); }
    const eventRecords=fs.readFileSync(events,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
    for(const [i,event] of eventRecords.entries()) { const f=write(`${name}-event-${i}.json`,event); validate('ExecutionEvent',f); assert.equal(event.decisionId,d.decisionId); }
    const after=invoke('readActionCount').value.value;
    assert.equal(after-before,delta); assert.equal(actionRecords.length,delta);
    scenarios.push({name,decision:d,independentCountBefore:before,independentCountAfter:after,actionRecords,eventRecords});
  }
  schedule('proceed',profile,'proceed',1,1);
  assert.equal(invoke('readEnabled').value.value,true);
  // Explicit policy counterfactuals hold the observed trace/model identity constant.
  // They test decision sensitivity, not real-home anomaly or conflict detection.
  for(const [name,change,expected,tasks,delta] of [
    ['anomaly',{anomaly:{detected:true,reason:'controlled anomaly-policy probe'}},'defer',1,0],
    ['ambiguity',{ambiguity:{detected:true,candidateLabels:['sensor-read','other-read']}},'abstain',1,0],
    ['conflict',{patterns:[{kind:'conflict',status:'violated',details:'controlled conflict-policy probe'}]},'reorder',2,2],
  ]) {
    const f=write(`${name}-profile.json`,{...normal,...change,profileId:`profile.control.${name}`}); validate('ProfileEvidence',f); schedule(name,f,expected,tasks,delta);
  }
  const finalEnabled=invoke('readEnabled'), finalCount=invoke('readActionCount');
  assert.equal(finalEnabled.value.value,true); assert.equal(finalCount.value.value,3);
  const malformed=write('malformed-profile.json',{...normal,schemaVersion:'2.0.0'});
  const rejectPlan=write('reject-plan.json',planDocument('plan.reject'));
  const rejected=spawnSync(java,['-cp',config.schedulerCp,'concurrency.adapter.SchedulerCli','--plan',rejectPlan,'--evidence',malformed,'--decision',path.join(evidence,'rejected-decision.json'),'--trusted-model-hash',normal.modelHash,'--trusted-model-version',normal.modelVersion,'--policy-only'],{encoding:'utf8',timeout:15000,maxBuffer:65536});
  assert.notEqual(rejected.status,0); assert.ok(!fs.existsSync(path.join(evidence,'rejected-decision.json')));
  assert.equal(invoke('readActionCount').value.value,3);
  const logic=write('logic-definition.json',{schemaVersion:'1.0.1',graphId:'graph.generated.read',nodes:[{nodeId:'node.read',kind:'service-call',resultType:'boolean',inputs:[],serviceId:'device.virtual-switch',operation:'readEnabled'}],outputs:[{name:'enabled',nodeId:'node.read'}],timeoutPolicy:{graphTimeoutMs:4000,nodeTimeoutMs:3000}}); validate('LogicDefinition',logic);
  write('scheduling-decision.json',scenarios[0].decision);
  write('execution-events.json',scenarios.flatMap(s=>s.eventRecords));
  const feedback=write('feedback-journal.json',{schemaVersion:'1.0.0',source:'actual-scheduler-execution',scenarios,finalEnabled,finalCount});
  const snapshot=readEvidenceSnapshot(config.workspace);
  for(const item of Object.values(snapshot)) assert.equal(item.status,'available');
  assert.deepEqual(snapshot.profileEvidence.value,normal); assert.deepEqual(snapshot.schedulingDecision.value,scenarios[0].decision);
  write('management-readback.json',snapshot);
  // Reclassification consumes the actual post-action read trace as profiler feedback.
  const feedbackTrace=path.join(evidence,'feedback-trace.json'); invoke('readActionCount',true,feedbackTrace); validate('TrafficTrace',feedbackTrace);
  const feedbackProfile=path.join(evidence,'feedback-profile.json');
  run('profiler.feedback',config.python,['-m','smart_rule_analyzer.profile_cli','--trace',feedbackTrace,'--model',model,'--output',feedbackProfile,'--produced-at',new Date().toISOString()],{env:pythonEnv}); validate('ProfileEvidence',feedbackProfile);
  write('session-result.json',{status:'passed',records,checks:['generated-source-build-register','live-logic-tinyrpc-trace','profile-before-decision','decision-before-action','independent-state-count','policy-counterfactuals','invalid-major-rejected','management-readback','profiler-feedback'],profileEvidenceId:normal.profileId,feedbackJournal:path.basename(feedback)});
} finally { await session.close(); }
