"""Zero-spend tests for configured routing and the external CLI boundary."""

import copy
import importlib
import json
import os
import sys
import tempfile
import unittest
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


def configuration():
    return {
        "schema_version": 1,
        "classifier": {"model": "future-classifier", "effort": "low"},
        "executors": [
            {"model": "future-small", "efforts": ["low"]},
            {"model": "future-large", "efforts": ["medium", "high"]},
        ],
        "fallback": {"model": "future-large", "effort": "high"},
        "timeout_seconds": 6,
    }


def catalogue():
    return {
        "future-classifier": ["low", "medium"],
        "future-small": ["low"],
        "future-large": ["medium", "high"],
    }


def answer(model="future-small", effort="low", rationale="A bounded extraction."):
    return [
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({
            "model": model, "effort": effort, "rationale": rationale,
        })}},
        {"type": "turn.completed", "usage": {
            "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 12,
        }},
    ]


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = importlib.import_module("routing_config")

    def test_future_models_need_no_family_policy_changes(self):
        self.assertEqual(self.config.validate_config(configuration(), catalogue()), configuration())

    def test_model_and_effort_must_be_in_current_catalogue(self):
        for path, bad in ((('classifier', 'model'), 'missing'), (('classifier', 'effort'), 'ultra'),
                          (('fallback', 'model'), 'future-classifier'), (('fallback', 'effort'), 'low')):
            with self.subTest(path=path, value=bad):
                doc = configuration()
                doc[path[0]][path[1]] = bad
                with self.assertRaises(self.config.ConfigError):
                    self.config.validate_config(doc, catalogue())

    def test_rejects_duplicates_pathlike_identifiers_and_unknown_fields(self):
        docs = []
        for model in ('../model', '*', '', 'a' * 129):
            doc = configuration(); doc['executors'][0]['model'] = model; docs.append(doc)
        doc = configuration(); doc['executors'].append(copy.deepcopy(doc['executors'][0])); docs.append(doc)
        doc = configuration(); doc['api_key'] = 'must-not-be-stored'; docs.append(doc)
        doc = configuration(); doc['timeout_seconds'] = 600; docs.append(doc)
        doc = configuration(); doc['timeout_seconds'] = True; docs.append(doc)
        for doc in docs:
            with self.subTest(doc=doc):
                with self.assertRaises(self.config.ConfigError):
                    self.config.validate_config(doc, catalogue())

    def test_repeated_setup_preserves_exact_previous_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'routing.json'
            self.assertIsNone(self.config.save_config(path, configuration()))
            original = path.read_bytes()
            doc = configuration(); doc['classifier']['effort'] = 'medium'
            backup = self.config.save_config(path, doc)
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(self.config.load_config(path), doc)
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_configuration_is_distinct_from_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'routing.json'
            self.assertIsNone(self.config.load_config(path))
            path.write_text('{broken')
            with self.assertRaises(self.config.ConfigError):
                self.config.load_config(path)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlink support required')
    def test_does_not_read_or_replace_linked_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target.json'; target.write_text(json.dumps(configuration()))
            link = Path(tmp) / 'link.json'
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable')
            original = target.read_bytes()
            for operation in (lambda: self.config.load_config(link),
                              lambda: self.config.save_config(link, configuration())):
                with self.assertRaises(self.config.ConfigError):
                    operation()
            self.assertEqual(target.read_bytes(), original)


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.ai = importlib.import_module('ai_classifier')
        self.calls = []

    def run_classifier(self, events=None, **kwargs):
        def runner(argv, payload, timeout):
            self.calls.append((argv, payload, timeout))
            return answer() if events is None else events
        return self.ai.classify('Perform a read-only extraction.', configuration(), catalogue(),
                                runner=runner, executable=sys.executable, **kwargs)

    def test_schema_result_selects_only_permitted_model_effort(self):
        result = self.run_classifier()
        self.assertEqual((result['model'], result['effort'], result['status']),
                         ('future-small', 'low', 'selected'))
        self.assertEqual(result['usage'], {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 12})
        self.assertEqual(result['calls'], 1)
        self.assertGreaterEqual(result['duration_ms'], 0)
        self.assertNotIn('extraction', json.dumps(result))

    def test_failed_selection_still_reports_observed_classifier_token_overhead(self):
        result = self.run_classifier(answer('outside', 'low'))
        self.assertEqual(result['usage']['input_tokens'], 100)

    def test_cli_uses_saved_auth_without_credentials_or_prompt_in_argv(self):
        self.run_classifier()
        argv, payload, timeout = self.calls[0]
        self.assertIn('--ignore-user-config', argv)
        self.assertIn('--ephemeral', argv)
        self.assertIn('--output-schema', argv)
        self.assertEqual(argv[argv.index('--model') + 1], 'future-classifier')
        for feature in ('hooks', 'multi_agent', 'shell_tool', 'unified_exec', 'apps', 'code_mode_host'):
            self.assertIn(['--disable', feature], [argv[i:i+2] for i in range(len(argv)-1)])
        self.assertNotIn('Perform a read-only extraction.', ' '.join(argv))
        self.assertIn('Perform a read-only extraction.', payload)
        self.assertEqual(timeout, 6)

    def test_invalid_responses_use_one_fallback_without_retry(self):
        cases = [answer('outside', 'low'), answer('future-small', 'high'), answer(rationale='secret' * 100),
                 [{'type': 'turn.failed'}], [], answer() + answer()]
        for events in cases:
            with self.subTest(events=events):
                result = self.run_classifier(events)
                self.assertEqual((result['model'], result['effort'], result['status']),
                                 ('future-large', 'high', 'fallback'))
                self.assertEqual(result['calls'], 1)

    def test_explicit_preference_is_enforced_not_merely_prompted(self):
        result = self.run_classifier(preferred_model='future-large')
        self.assertEqual(result['status'], 'fallback')
        result = self.run_classifier(answer('future-large', 'medium'), preferred_model='future-large')
        self.assertEqual((result['model'], result['effort']), ('future-large', 'medium'))

    def test_unsupported_explicit_preference_does_not_fall_back_to_another_model(self):
        result = self.run_classifier(preferred_model='outside')
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['model'])
        self.assertEqual(self.calls, [])

    def test_timeout_uses_fallback_once(self):
        def timeout(*args):
            self.calls.append(args)
            raise TimeoutError
        result = self.ai.classify('x', configuration(), catalogue(), runner=timeout, executable=sys.executable)
        self.assertEqual(result['status'], 'fallback')
        self.assertEqual(result['reason_code'], 'classifier_timeout')
        self.assertEqual(len(self.calls), 1)

    def test_recursion_guard_never_invokes_cli(self):
        with mock.patch.dict(os.environ, {'AUTOROUTER_CLASSIFIER_ACTIVE': '1'}):
            result = self.run_classifier()
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(self.calls, [])

    def test_exact_user_model_directive_skips_classification(self):
        result = self.ai.classify('Use model future-large at medium effort.\nReview the supplied design.',
                                  configuration(), catalogue(), runner=lambda *args: self.fail('no classification needed'))
        self.assertEqual((result['model'], result['effort']), ('future-large', 'medium'))
        self.assertEqual(result['calls'], 0)
        self.assertEqual(result['reason_code'], 'explicit_user_preference')

    def test_unsupported_user_model_directive_is_not_silently_substituted(self):
        result = self.ai.classify('Use model outside at ultra effort.\nReview.', configuration(), catalogue(),
                                  runner=lambda *args: self.fail('no classification allowed'))
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['model'])

    def test_large_prompt_uses_valid_fallback_without_truncating_input(self):
        result = self.ai.classify('x' * 32769, configuration(), catalogue(),
                                  runner=lambda *args: self.fail('must not call'), executable=sys.executable)
        self.assertEqual(result['reason_code'], 'prompt_too_large')
        self.assertEqual(result['status'], 'fallback')

    def test_missing_catalogue_or_invalid_fallback_cannot_authorise_execution(self):
        result = self.ai.classify('x', configuration(), {}, runner=lambda *args: self.fail('must not call'))
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['model'])

    def test_tool_activity_in_classifier_output_is_not_accepted_as_a_selection(self):
        events = [{'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'ignored'}}] + answer()
        result = self.run_classifier(events)
        self.assertEqual(result['reason_code'], 'classifier_attempted_tool_use')
        self.assertEqual(result['status'], 'fallback')

    def test_mocked_existing_benchmark_prompts_do_not_claim_measured_quality(self):
        root = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(root))
        from benchmarks.autorouter_bench import ROUTE_PROBES
        self.assertEqual(len(ROUTE_PROBES), 10)
        for name, prompt, old_route, old_plan in ROUTE_PROBES:
            with self.subTest(case=name):
                result = self.ai.classify(prompt, configuration(), catalogue(),
                    runner=lambda *args: answer('future-large', 'high'), executable=sys.executable)
                self.assertEqual((result['model'], result['effort']), ('future-large', 'high'))
                self.assertEqual(result['calls'], 1)
                self.assertNotIn('savings', result)

    def test_six_second_classifier_budget_is_below_existing_hook_timeout(self):
        root = Path(__file__).resolve().parents[3]
        hooks = json.loads((root / 'hooks/hooks.json').read_text())['hooks']['UserPromptSubmit']
        timeout = hooks[0]['hooks'][0]['timeout']
        self.assertLess(configuration()['timeout_seconds'], timeout)

    def test_local_fake_process_exercises_bounded_output_and_timeout(self):
        cases = [('import time; time.sleep(3)', 0.1, 'classifier_timeout'),
                 ('import sys; sys.stdout.write("x" * 200000)', 1, 'classifier_output_limit')]
        for code, timeout, expected in cases:
            with self.subTest(code=code):
                with self.assertRaises(self.ai.ClassifierError) as raised:
                    self.ai.run_cli([sys.executable, '-c', code], '{}', timeout)
                self.assertEqual(raised.exception.code, expected)

    def test_local_fake_process_parses_jsonl_not_arbitrary_status_text(self):
        code = 'import sys; sys.stdin.read(); print(' + repr(json.dumps(answer()[0])) + '); print(' + repr(json.dumps(answer()[1])) + ')'
        events = self.ai.run_cli([sys.executable, '-c', code], '{}', 2)
        self.assertEqual(events, answer())


class SetupCommandTests(unittest.TestCase):
    def test_noninteractive_setup_and_repeat_use_catalogue_and_backup(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cache = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'client_version': 'test',
                     'models': [{'slug': m, 'visibility': 'list',
                                 'supported_reasoning_levels': [{'effort': e} for e in efforts]}
                                for m, efforts in catalogue().items()]}
            (home / 'models_cache.json').write_text(json.dumps(cache))
            env = {**os.environ, 'CODEX_HOME': str(home), 'PYTHONDONTWRITEBYTECODE': '1'}
            args = [sys.executable, '-B', str(root / 'scripts/autorouter.py'), 'setup',
                    '--classifier', 'future-classifier', '--classifier-effort', 'low',
                    '--allow', 'future-small=low', '--allow', 'future-large=medium,high',
                    '--fallback', 'future-large=high']
            for iteration in range(2):
                result = subprocess.run(args, capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data['status'], 'configured')
                self.assertEqual(data['model_access'], 'catalogue_only_not_inference_verified')
                self.assertEqual(bool(data['backup']), bool(iteration))
            path = home / 'autorouter/config.json'
            self.assertEqual(json.loads(path.read_text()), configuration())
            before = path.read_bytes()
            invalid = args.copy(); invalid[invalid.index('future-classifier')] = 'missing'
            self.assertNotEqual(subprocess.run(invalid, capture_output=True, env=env).returncode, 0)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((home / 'config.toml').exists())


class ConfiguredHookTests(unittest.TestCase):
    def setUp(self):
        import router_hook
        import routing_config
        import ai_classifier
        self.hook = router_hook
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        for name, value in {
            'CODEX_HOME': self.home, 'STATE_ROOT': self.home / 'state',
            'CONFIG_PATH': self.home / 'config.toml', 'HEALTH_ROOT': self.home / 'health',
            'ROOT_OBSERVATION_PATH': self.home / 'health/root-observation-v1.json',
            'CAPABILITY_PATH': self.home / 'health/capability-v3.json',
        }.items():
            patch = mock.patch.object(router_hook, name, value); patch.start(); self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, {'CODEX_HOME': str(self.home)})
        patch.start(); self.addCleanup(patch.stop)
        routing_config.save_config(self.home / 'autorouter/config.json', configuration())
        self.addCleanup(lambda: router_hook._configure_ai_runtime(None))
        patch = mock.patch.object(router_hook, '_ai_catalogue', return_value=catalogue(), create=True)
        patch.start(); self.addCleanup(patch.stop)
        self.classifier = mock.Mock(return_value={'model': 'future-large', 'effort': 'high',
            'status': 'selected', 'reason_code': 'classifier_selected', 'duration_ms': 12, 'calls': 1, 'usage': {}})
        patch = mock.patch.object(ai_classifier, 'classify', self.classifier)
        patch.start(); self.addCleanup(patch.stop)
        self.data = {'hook_event_name': 'UserPromptSubmit', 'session_id': 'configured-session',
                     'turn_id': 'configured-turn', 'model': 'unknown-root', 'model_reasoning_effort': 'low',
                     'prompt': 'Investigate a difficult problem without modifying anything.'}

    def state(self):
        return json.loads((self.home / 'state/configured-session--configured-turn.json').read_text())

    def test_configured_selection_uses_existing_adapter_without_keyword_classification(self):
        with mock.patch.object(self.hook, 'classify_prompt', side_effect=AssertionError('legacy path')):
            result = self.hook.handle(self.data)
        state = self.state(); decision = state['decision']
        self.assertEqual(decision['model'], 'future-large')
        self.assertEqual(decision['effort'], 'high')
        self.assertTrue(decision['delegate'])
        self.assertEqual(state['agents'], {})
        self.assertEqual(state['status'], 'ROUTED')
        self.assertFalse(decision['announce_route'])
        self.assertIn('execution is pending', result['hookSpecificOutput']['additionalContext'])
        self.assertIn('"model":"future-large"', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(decision['classification']['duration_ms'], 12)
        self.assertNotIn(self.data['prompt'], json.dumps(state))

    def test_duplicate_root_delivery_does_not_classify_again(self):
        self.hook.handle(self.data)
        self.hook.handle(self.data)
        self.assertEqual(self.classifier.call_count, 1)
        self.assertEqual(len(list((self.home / 'state').glob('configured-session--*.json'))), 1)

    def test_unreadable_existing_turn_state_does_not_repeat_a_billable_attempt(self):
        self.hook.handle(self.data)
        path = self.home / 'state/configured-session--configured-turn.json'
        path.write_text('{corrupt')
        result = self.hook.handle(self.data)
        self.assertEqual(self.classifier.call_count, 1)
        self.assertEqual(path.read_text(), '{corrupt')
        self.assertIn('unreadable', result['systemMessage'])

    def test_changed_root_identity_cannot_reuse_the_previous_turn_contract(self):
        self.hook.handle(self.data)
        result = self.hook.handle({**self.data, 'model': 'different-root'})
        self.assertEqual(self.classifier.call_count, 1)
        self.assertIn('root identity', result['systemMessage'])

    def test_same_selected_model_and_effort_stays_current(self):
        self.hook.handle({**self.data, 'model': 'future-large', 'model_reasoning_effort': 'high'})
        decision = self.state()['decision']
        self.assertEqual(decision['route'], 'current')
        self.assertFalse(decision['delegate'])
        self.assertEqual(decision['orchestration']['required_agents'], {})

    def test_guard_returns_before_ledger_or_classifier(self):
        with mock.patch.dict(os.environ, {'AUTOROUTER_CLASSIFIER_ACTIVE': '1'}):
            self.assertIsNone(self.hook.handle(self.data))
        self.assertFalse((self.home / 'state').exists())
        self.assertEqual(self.classifier.call_count, 0)

    def test_configured_spawn_contract_accepts_new_model_and_rejects_outside_allowlist(self):
        import spawn_compat
        self.hook.handle(self.data)
        args = spawn_compat.build_arguments(model='future-large', effort='high', task_name='bounded', message='Read only.')
        self.assertTrue(spawn_compat.validate_arguments(args)['spawn_contract_valid'])
        self.assertFalse(spawn_compat.validate_arguments({**args, 'model': 'gpt-6-sol'})['spawn_contract_valid'])

    def test_tool_events_never_reclassify(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'hook_event_name': 'PostToolUse', 'tool_name': 'Read', 'tool_input': {}})
        self.assertEqual(self.classifier.call_count, 1)

    def test_configured_mode_does_not_accept_model_from_invalid_classifier_boundary(self):
        self.classifier.return_value = {'model': 'outside', 'effort': 'high', 'status': 'selected'}
        self.hook.handle(self.data)
        self.assertFalse(self.state()['decision']['delegate'])

    def test_short_continuation_reuses_decision_without_another_classifier_call(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'turn_id': 'continued-turn', 'prompt': 'Continue.'})
        state = json.loads((self.home / 'state/configured-session--continued-turn.json').read_text())
        self.assertEqual(self.classifier.call_count, 1)
        self.assertEqual(state['decision']['classification']['calls'], 0)
        self.assertEqual(state['decision']['model'], 'future-large')

    def test_hook_completion_continuation_does_not_reenter_legacy_model_policy(self):
        self.hook.handle(self.data)
        with mock.patch.object(self.hook, '_apply_actual_root_policy', side_effect=AssertionError('legacy policy')):
            self.hook.handle({**self.data, 'turn_id': 'gate-turn', 'prompt': 'Router completion gate: finish verification.'})
        state = json.loads((self.home / 'state/configured-session--gate-turn.json').read_text())
        self.assertEqual(state['decision']['model'], 'future-large')
        self.assertEqual(self.classifier.call_count, 1)

    def test_missing_authoritative_root_does_not_spend_on_classification(self):
        self.hook.handle({**self.data, 'model': ''})
        self.assertEqual(self.classifier.call_count, 0)
        self.assertFalse(self.state()['decision']['delegate'])

    def test_configured_context_does_not_instruct_hardcoded_model_ladder(self):
        result = self.hook.handle(self.data)
        text = result['hookSpecificOutput']['additionalContext']
        self.assertNotIn('Sol Medium → Sol High', text)

    def test_changed_configuration_cannot_reuse_a_stale_decision(self):
        import routing_config
        self.hook.handle(self.data)
        changed = configuration(); changed['executors'] = [changed['executors'][0]]
        changed['fallback'] = {'model': 'future-small', 'effort': 'low'}
        routing_config.save_config(self.home / 'autorouter/config.json', changed)
        result = self.hook.handle(self.data)
        self.assertEqual(self.classifier.call_count, 1)
        self.assertNotIn('"model":"future-large"', json.dumps(result))
        self.assertEqual(self.state()['status'], 'FAILED_OPEN')

    def test_new_model_child_completes_only_with_exact_existing_lifecycle_evidence(self):
        import spawn_compat
        self.hook.handle(self.data)
        base = {**self.data, 'model': 'future-large', 'model_reasoning_effort': 'high',
                'agent_id': 'future-child'}
        self.hook.handle({**base, 'hook_event_name': 'SubagentStart'})
        self.hook.handle({**base, 'turn_id': 'child-turn', 'hook_event_name': 'UserPromptSubmit'})
        self.assertEqual(self.classifier.call_count, 1)
        state = self.state()
        args = spawn_compat.build_arguments(model='future-large', effort='high', task_name='bounded', message='Read only.')
        transcript = self.home / 'synthetic-parent.jsonl'
        metadata = {'turn_id': self.data['turn_id']}
        records = [
            {'payload': {'type': 'function_call', 'name': 'spawn_agent', 'call_id': 'call-future',
                         'arguments': json.dumps(args), 'internal_chat_message_metadata_passthrough': metadata}},
            {'payload': {'type': 'sub_agent_activity', 'event_id': 'call-future',
                         'agent_thread_id': 'future-child', 'kind': 'started',
                         'internal_chat_message_metadata_passthrough': metadata}},
        ]
        transcript.write_text(''.join(json.dumps(item) + '\n' for item in records))
        self.hook._reconcile_subagent_transcript({'transcript_path': str(transcript)}, state)
        self.hook._write_existing_state(self.data, state)
        self.hook.handle({**base, 'turn_id': 'child-turn', 'hook_event_name': 'SubagentStop',
                          'last_assistant_message': 'Evidence: checked\nVerification: checked\nUncertainty: none'})
        self.hook.handle({**self.data, 'hook_event_name': 'Stop'})
        state = self.state()
        self.assertEqual(state['agents']['future-child']['status'], 'completed')
        self.assertTrue(state['agent_attestations']['future-child']['matched'])
        self.assertEqual(state['status'], 'COMPLETE')
        self.assertEqual(self.classifier.call_count, 1)
        receipts = json.loads((self.home / 'health/capability-v3.json').read_text())['capabilities']
        self.assertEqual(len(receipts), 1)
        receipt = next(iter(receipts.values()))
        self.assertEqual(receipt['observed_child_model'], 'future-large')
        self.assertTrue(receipt['spawn_contract_valid'])
        self.assertTrue(receipt['attestation_matched'])

    def test_removed_configuration_does_not_repeat_classification_or_authorise_stale_model(self):
        self.hook.handle(self.data)
        (self.home / 'autorouter/config.json').unlink()
        result = self.hook.handle(self.data)
        self.assertEqual(self.classifier.call_count, 1)
        self.assertIn('settings changed', result['systemMessage'])

    def test_malformed_configuration_fails_open_without_using_legacy_classifier(self):
        (self.home / 'autorouter/config.json').write_text('{broken')
        with mock.patch.object(self.hook, 'classify_prompt', side_effect=AssertionError('legacy bypass')):
            self.hook.handle(self.data)
        self.assertFalse(self.state()['decision']['delegate'])
        self.assertEqual(self.classifier.call_count, 0)

    def test_contradictory_child_model_does_not_complete_plan(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'hook_event_name': 'SubagentStart', 'agent_id': 'bad-child',
                          'model': 'outside', 'reasoning_effort': 'high'})
        self.hook.handle({**self.data, 'hook_event_name': 'Stop'})
        self.assertEqual(self.state()['status'], 'FAILED_OPEN')

    def test_configured_receipt_keys_are_visible_to_checker_without_model_source_edit(self):
        import check_hooks
        self.hook.handle(self.data)
        check_hooks.refresh_configured_capabilities(self.home)
        self.assertTrue(any(key.startswith('future-large|configured_') for key in check_hooks.CAPABILITY_SPECS))
        check_hooks.refresh_configured_capabilities(Path(self.temp.name) / 'absent')

    def test_configured_health_does_not_impose_a_hardcoded_luna_root(self):
        import check_hooks
        self.addCleanup(lambda: check_hooks.refresh_configured_capabilities(self.home / 'absent'))
        self.hook.handle(self.data)
        check_hooks.refresh_configured_capabilities(self.home)
        health = check_hooks._routing_health({'available': True, 'model': 'unknown-root'},
            self.hook.PLUGIN_VERSION, self.home / 'health', plugin_identity=self.hook.PLUGIN_IDENTITY,
            current_session_id=self.data['session_id'])
        self.assertFalse(any('not Luna' in reason for reason in health['reasons']))
        self.assertFalse(health['ready'])  # A configured selection is not runtime capability proof.

    def test_invalid_configuration_cannot_leave_health_ready(self):
        import check_hooks
        self.addCleanup(lambda: check_hooks.refresh_configured_capabilities(self.home / 'absent'))
        (self.home / 'autorouter/config.json').write_text('{broken')
        check_hooks.refresh_configured_capabilities(self.home)
        health = check_hooks._routing_health({'available': True, 'model': 'gpt-6-luna'},
            self.hook.PLUGIN_VERSION, self.home / 'health', current_session_id=self.data['session_id'])
        self.assertEqual(health['status'], 'UNAVAILABLE')

    def test_launcher_guard_does_not_load_plugin_or_create_state(self):
        import hook_launcher
        import io
        from contextlib import redirect_stdout
        output = io.StringIO()
        with mock.patch.dict(os.environ, {'AUTOROUTER_CLASSIFIER_ACTIVE': '1'}), redirect_stdout(output):
            result = hook_launcher.launch(self.home / 'nonexistent-plugin', self.home / 'no-state')
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), {})
        self.assertFalse((self.home / 'no-state').exists())

    def test_first_use_guidance_does_not_start_classifier_or_overwrite_settings(self):
        (self.home / 'autorouter/config.json').unlink()
        result = self.hook.handle({**self.data, 'model': 'gpt-6-luna', 'prompt': 'Return only 42.'})
        self.assertIn('autorouter.py setup', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.classifier.call_count, 0)



if __name__ == '__main__':
    unittest.main()
