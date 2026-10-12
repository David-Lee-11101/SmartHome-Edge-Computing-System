import json
import subprocess
import sys
import tempfile
import unittest
import hashlib
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from run_cold_system import assert_checkout, verify_session, verify_proof
from validate_contracts import validate_document, ContractError


class ColdRunnerTest(unittest.TestCase):
    def passed_shape(self):
        manifest = json.loads((ROOT / 'components.json').read_text())
        roles = ['communication', 'logic-engine', 'traffic-profiling', 'thread-safe-scheduler', 'integrated-logic-management']
        commands = ['build.communication', 'build.logic', 'build.scheduler', 'test.profiling', 'build.generator', 'install.management', 'test.management', 'compile.callbacks', 'test.callback-process-cleanup', 'causal.session']
        artifacts = ['traffic-trace', 'profile-evidence', 'scheduling-decision', 'feedback-journal', 'management-readback', 'session-result', 'generation-manifest', 'feedback-profile']
        proof = json.loads((ROOT / 'contracts/fixtures/v1/valid/system-proof.json').read_text())
        proof.update(status='passed', components=[{'role':'integration-hub','repositoryId':manifest['hub']['repositoryId'],'commit':'1'*40}]+[
            {key:item[key] for key in ('role','repositoryId','commit')} for item in manifest['components'] if item['role'] in roles],
            commands=[{'commandId':name,'durationMs':1,'status':'passed','environment':{'os':'test','arch':'test','runtime':'test'}} for name in commands],
            outcomes=[{'checkId':'artifact.'+name,'status':'passed','evidenceHash':hashlib.sha256(b'{}').hexdigest()} for name in artifacts],
            contractVersions={name:'1.0.1' for name in ['TrafficTrace','ProfileEvidence','SchedulingDecision','LogicDefinition','GenerationManifest']})
        return proof, manifest

    def test_passed_shape_rejects_failed_command_and_pending_outcome(self):
        for kind in ['commands','outcomes']:
            proof, _ = self.passed_shape()
            proof[kind][0]['status'] = 'failed'
            with self.assertRaises(ContractError): validate_document('SystemProof',proof)

    def test_proof_verifier_rejects_tampered_artifact(self):
        proof, manifest = self.passed_shape()
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory); evidence=workspace/'runtime/evidence'; evidence.mkdir(parents=True)
            for outcome in proof['outcomes']:
                (evidence/(outcome['checkId'].removeprefix('artifact.')+'.json')).write_text('{}')
            (evidence/'traffic-trace.json').write_text('{"tampered":true}')
            with patch('run_cold_system.assert_checkout'), patch('run_cold_system.verify_session'):
                with self.assertRaisesRegex(ValueError,'artifact digest'):
                    verify_proof(proof,workspace,manifest)

    def test_empty_passed_proof_is_rejected(self):
        document = json.loads((ROOT / "contracts/fixtures/v1/valid/system-proof.json").read_text())
        document["status"] = "passed"
        with self.assertRaises(ContractError):
            validate_document("SystemProof", document)

    def test_checkout_rejects_dirty_or_wrong_head(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'seed'], cwd=source, check=True)
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
            assert_checkout(source, commit)
            with self.assertRaises(ValueError):
                assert_checkout(source, '0' * 40)
            (source / 'untracked.txt').write_text('dirty')
            with self.assertRaises(ValueError):
                assert_checkout(source, commit)

    def test_required_checks_cannot_be_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            (evidence / 'session-result.json').write_text(json.dumps({'status': 'passed', 'checks': []}))
            with self.assertRaisesRegex(ValueError, 'required causal checks'):
                verify_session(evidence)

    def test_fixture_trace_cannot_pass_live_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            checks = ['generated-source-build-register', 'live-logic-tinyrpc-trace', 'profile-before-decision', 'decision-before-action', 'independent-state-count', 'policy-counterfactuals', 'invalid-major-rejected', 'management-readback', 'profiler-feedback']
            (evidence / 'session-result.json').write_text(json.dumps({'status': 'passed', 'checks': checks}))
            fixture = ROOT / 'contracts/fixtures/v1/valid'
            for name in ['traffic-trace', 'profile-evidence', 'scheduling-decision']:
                value = json.loads((fixture / (name + '.json')).read_text())
                if name == 'traffic-trace': value['sourceKind'] = 'synthetic-fixture'
                (evidence / (name + '.json')).write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'live transport'):
                verify_session(evidence)

    def test_management_graph_identity_must_match_actual_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence=Path(directory)
            checks=['generated-source-build-register','live-logic-tinyrpc-trace','profile-before-decision','decision-before-action','independent-state-count','policy-counterfactuals','invalid-major-rejected','management-readback','profiler-feedback']
            (evidence/'session-result.json').write_text(json.dumps({'status':'passed','checks':checks}))
            fixture=ROOT/'contracts/fixtures/v1/valid'
            documents={name:json.loads((fixture/(name+'.json')).read_text()) for name in ['traffic-trace','profile-evidence','scheduling-decision','logic-definition']}
            documents['traffic-trace']['sourceKind']='instrumented-rpc'
            documents['profile-evidence']['traceId']=documents['traffic-trace']['traceId']
            documents['scheduling-decision']['profileEvidenceId']=documents['profile-evidence']['profileId']
            documents['scheduling-decision']['decision']='proceed'
            for name,document in documents.items(): (evidence/(name+'.json')).write_text(json.dumps(document))
            (evidence/'preaction-invocation.json').write_text(json.dumps({'graphId':'graph.different','logicDefinition':documents['logic-definition']}))
            with self.assertRaisesRegex(ValueError,'actual executed graph'):
                verify_session(evidence)


if __name__ == '__main__':
    unittest.main()
