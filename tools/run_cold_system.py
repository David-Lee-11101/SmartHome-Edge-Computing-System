#!/usr/bin/env python3
"""Fetch immutable sources and build an isolated, real loopback causal integration."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from validate_contracts import validate_component_manifest, validate_document

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('communication', 'logic-engine', 'traffic-profiling', 'thread-safe-scheduler', 'integrated-logic-management')
CAUSAL_ORDER = ['instrumented-rpc-trace', 'profile-evidence', 'scheduling-decision', 'optional-action', 'feedback-journal']


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def assert_checkout(source, commit):
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=source, text=True)
    if actual != commit or dirty:
        raise ValueError('source checkout is not the clean pinned commit')


def verify_session(evidence):
    result = json.loads((evidence / 'session-result.json').read_text())
    expected = {'generated-source-build-register', 'live-logic-tinyrpc-trace', 'profile-before-decision',
                'decision-before-action', 'independent-state-count', 'policy-counterfactuals',
                'invalid-major-rejected', 'management-readback', 'profiler-feedback'}
    if result['status'] != 'passed' or set(result['checks']) != expected:
        raise ValueError('required causal checks did not pass')
    trace = json.loads((evidence / 'traffic-trace.json').read_text())
    profile = json.loads((evidence / 'profile-evidence.json').read_text())
    decision = json.loads((evidence / 'scheduling-decision.json').read_text())
    validate_document('TrafficTrace', trace)
    validate_document('ProfileEvidence', profile)
    validate_document('SchedulingDecision', decision)
    if trace['sourceKind'] != 'instrumented-rpc' or profile['traceId'] != trace['traceId']:
        raise ValueError('profile is not correlated to live transport evidence')
    if decision['profileEvidenceId'] != profile['profileId'] or decision['decision'] != 'proceed':
        raise ValueError('scheduler did not consume the observed profile')
    logic = json.loads((evidence / 'logic-definition.json').read_text())
    invocation = json.loads((evidence / 'preaction-invocation.json').read_text())
    validate_document('LogicDefinition', logic)
    if logic != invocation['logicDefinition'] or logic['graphId'] != invocation['graphId']:
        raise ValueError('management graph differs from actual executed graph')
    if invocation['requestId'] != trace['observations'][0]['requestId']:
        raise ValueError('executed graph invocation differs from observed trace')
    snapshot = json.loads((evidence / 'management-readback.json').read_text())
    if snapshot['logicDefinition']['value'] != logic:
        raise ValueError('management graph readback differs from executed graph')
    feedback = json.loads((evidence / 'feedback-journal.json').read_text())
    if feedback['finalCount']['value'] != {'type': 'integer', 'value': 3}:
        raise ValueError('independent action count failed')
    if feedback['finalEnabled']['value'] != {'type': 'boolean', 'value': True}:
        raise ValueError('independent state read failed')
    return result


def verify_proof(proof, workspace, manifest):
    """Verify identities and actual artifact bytes, beyond schema shape."""
    validate_document('SystemProof', proof)
    if proof['status'] != 'passed':
        raise ValueError('system proof is not passed')
    identities = {item['role']: item for item in proof['components']}
    for role in ROLES:
        expected = next(item for item in manifest['components'] if item['role'] == role)
        if identities[role]['commit'] != expected['commit'] or identities[role]['repositoryId'] != expected['repositoryId']:
            raise ValueError('proof component identity differs from immutable manifest')
    if identities['integration-hub']['repositoryId'] != manifest['hub']['repositoryId']:
        raise ValueError('proof hub identity differs from manifest')
    assert_checkout(ROOT, identities['integration-hub']['commit'])
    evidence = workspace / 'runtime/evidence'
    verify_session(evidence)
    files = [file for file in evidence.iterdir() if file.is_file()]
    if any(file.is_symlink() for file in files):
        raise ValueError('proof evidence cannot use symbolic links')
    inventory = ['artifact.' + file.stem.replace('_', '-') for file in files]
    if len(inventory) != len(set(inventory)) or set(inventory) != {item['checkId'] for item in proof['outcomes']}:
        raise ValueError('proof artifact inventory does not match actual evidence')
    for outcome in proof['outcomes']:
        candidates = [file for file in evidence.iterdir() if 'artifact.' + file.stem.replace('_', '-') == outcome['checkId']]
        if len(candidates) != 1 or hashlib.sha256(candidates[0].read_bytes()).hexdigest() != outcome['evidenceHash']:
            raise ValueError('proof artifact digest does not match actual evidence')
    for contract, name in [('TrafficTrace', 'traffic-trace'), ('ProfileEvidence', 'profile-evidence'),
                           ('SchedulingDecision', 'scheduling-decision'), ('LogicDefinition', 'logic-definition'),
                           ('GenerationManifest', 'generation-manifest'), ('ServiceDescriptor', 'service-descriptor'), ('SchedulePlan', 'proceed-plan'), ('ExecutionEvent', 'proceed-event-0')]:
        actual = json.loads((evidence / (name + '.json')).read_text())['schemaVersion']
        if proof['contractVersions'][contract] != actual:
            raise ValueError('proof contract version differs from consumed artifact')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True, help='new, nonexistent runner directory')
    parser.add_argument('--maven-settings', type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    validate_component_manifest()
    hub_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert_checkout(ROOT, hub_commit)
    manifest = json.loads((ROOT / 'components.json').read_text())
    components = {item['role']: item for item in manifest['components']}
    commands = []
    environment = {'os': platform.system().lower(), 'arch': platform.machine(), 'runtime': 'Python ' + platform.python_version()}
    logs = workspace / 'logs'
    logs.mkdir()
    def run(command_id, command, cwd=workspace, env=None, timeout=900):
        start = time.monotonic()
        with (logs / (command_id + '.log')).open('wb') as log:
            process = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout)
        commands.append({'commandId': command_id, 'environment': environment,
                         'durationMs': round((time.monotonic() - start) * 1000),
                         'status': 'passed' if process.returncode == 0 else 'failed'})
        if process.returncode:
            raise RuntimeError(command_id + ' failed; inspect local command log')
    proof = {'manifestVersion': '1.0.0', 'proofId': 'proof.cold-source.' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'),
             'generatedAt': utc_now(), 'status': 'failed',
             'components': [{'role': 'integration-hub', 'repositoryId': manifest['hub']['repositoryId'], 'commit': hub_commit}] + [{key: components[role][key] for key in ('role', 'repositoryId', 'commit')} for role in ROLES],
             'contractVersions': {},
             'commands': commands, 'outcomes': [], 'skips': [], 'causalOrder': CAUSAL_ORDER}
    try:
        sources = {}
        for role in ROLES:
            source = workspace / 'sources' / role
            source.parent.mkdir(exist_ok=True)
            run('source.' + role, ['git', 'clone', '--no-checkout', components[role]['repository'], str(source)])
            run('checkout.' + role, ['git', 'checkout', '--detach', components[role]['commit']], source)
            assert_checkout(source, components[role]['commit'])
            sources[role] = source
        settings = workspace / 'maven-settings.xml'
        if args.maven_settings:
            settings.write_bytes(args.maven_settings.read_bytes())
        else:
            settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><interactiveMode>false</interactiveMode></settings>\n')
        repository = workspace / 'maven-repository'
        maven = os.environ.get('MANAGEMENT_MAVEN', 'mvn')
        java = os.environ.get('MANAGEMENT_JAVA', 'java')
        mvn = [maven, '-B', '-s', str(settings), '-Dmaven.repo.local=' + str(repository)]
        run('build.communication', mvn + ['install'], sources['communication'])
        run('build.logic', mvn + ['-DtinyRpcAdapter', 'install'], sources['logic-engine'])
        run('build.scheduler', mvn + ['package', 'dependency:build-classpath', '-Dmdep.outputFile=target/runtime-classpath.txt'], sources['thread-safe-scheduler'])
        run('test.profiling', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], sources['traffic-profiling'])
        management = sources['integrated-logic-management']
        run('build.generator', mvn + ['package'], management / 'services/code-generator')
        gui = management / 'electron_gui'
        run('install.management', ['npm', 'ci'], gui, timeout=900)
        run('test.management', ['npm', 'test'], gui)
        scheduler = sources['thread-safe-scheduler']
        cp = os.pathsep.join([str(scheduler / 'target/classes'), (scheduler / 'target/runtime-classpath.txt').read_text().strip()])
        callbacks = workspace / 'callback-classes'
        callbacks.mkdir()
        run('compile.callbacks', ['javac', '-cp', cp, '-d', str(callbacks), str(ROOT / 'tools/java/HubRpcBridge.java'), str(ROOT / 'tools/java/HubRpcBridgeProcessTest.java')])
        run('test.callback-process-cleanup', [java, '-cp', os.pathsep.join([str(callbacks), cp]), 'integration.HubRpcBridgeProcessTest'])
        config = workspace / 'session-config.json'
        config.write_text(json.dumps({'hub': str(ROOT), 'management': str(management), 'profiling': str(sources['traffic-profiling']),
                                     'workspace': str(workspace / 'runtime'), 'schedulerCp': os.pathsep.join([str(callbacks), cp]),
                                     'python': sys.executable, 'java': java}))
        env = {**os.environ, 'MANAGEMENT_MAVEN_SETTINGS': str(settings), 'MANAGEMENT_MAVEN_REPOSITORY': str(repository)}
        run('causal.session', ['node', str(ROOT / 'tools/run_causal_session.mjs'), str(config)], env=env, timeout=900)
        evidence = workspace / 'runtime/evidence'
        session = verify_session(evidence)
        for contract, name in [('TrafficTrace', 'traffic-trace'), ('ProfileEvidence', 'profile-evidence'), ('SchedulingDecision', 'scheduling-decision'), ('LogicDefinition', 'logic-definition'), ('GenerationManifest', 'generation-manifest'), ('ServiceDescriptor', 'service-descriptor'), ('SchedulePlan', 'proceed-plan'), ('ExecutionEvent', 'proceed-event-0')]:
            document = json.loads((evidence / (name + '.json')).read_text())
            validate_document(contract, document)
            proof['contractVersions'][contract] = document['schemaVersion']
        commands.extend({**record, 'environment': environment} for record in session['records'])
        for file in sorted(evidence.glob('*')):
            if file.is_file():
                proof['outcomes'].append({'checkId': 'artifact.' + file.stem.replace('_', '-'), 'status': 'passed',
                                          'evidenceHash': hashlib.sha256(file.read_bytes()).hexdigest()})
        proof['status'] = 'passed'
        verify_proof(proof, workspace, manifest)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        proof['status'] = 'failed'
        print(str(error), file=sys.stderr)
    finally:
        proof['generatedAt'] = utc_now()
        validate_document('SystemProof', proof)
        (workspace / 'system-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print('System proof: ' + proof['status'])
    return 0 if proof['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
