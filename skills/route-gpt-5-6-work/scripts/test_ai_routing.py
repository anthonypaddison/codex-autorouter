"""Zero-spend tests for configured routing and the direct API boundary."""

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
        "schema_version": 2,
        "enabled": True,
        "classifier": {"provider": "openai", "model": "future-classifier", "effort": "low",
                       "credential_env": "AUTOROUTER_TEST_API_KEY"},
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
    return {
        "status": "completed", "output": [{"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": json.dumps({
            "model": model, "effort": effort, "rationale": rationale,
        })}]}], "usage": {"input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 20}, "output_tokens": 12},
    }


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = importlib.import_module("routing_config")

    def test_future_models_need_no_family_policy_changes(self):
        self.assertEqual(self.config.validate_config(configuration(), catalogue()), configuration())

    def test_classifier_and_executor_catalogues_are_not_conflated(self):
        doc = configuration(); doc['classifier']['model'] = 'api-only-model'
        self.assertEqual(self.config.validate_config(doc, {}), doc)

    def test_trial_timeouts_are_configurable_and_bounded(self):
        for timeout in (1, 6, 10, 12.5, 30):
            with self.subTest(timeout=timeout):
                doc = configuration(); doc['timeout_seconds'] = timeout
                self.assertEqual(self.config.validate_config(doc), doc)
        for timeout in (0, -1, 30.1, 600, True, '10', float('nan'), float('inf')):
            with self.subTest(timeout=timeout):
                doc = configuration(); doc['timeout_seconds'] = timeout
                with self.assertRaises(self.config.ConfigError):
                    self.config.validate_config(doc)

    def test_invalid_fallback_and_provider_are_rejected(self):
        for path, bad in ((('classifier', 'provider'), 'unknown'), (('classifier', 'credential_env'), 'KEY=secret'),
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

    def test_legacy_config_is_readable_but_cannot_silently_start_api_spending(self):
        import ai_classifier
        doc = configuration(); doc['schema_version'] = 1; doc.pop('enabled')
        doc['classifier'] = {'model': 'future-classifier', 'effort': 'low'}
        self.assertEqual(self.config.validate_config(doc), doc)
        result = ai_classifier.classify('x', doc, runner=lambda *a: self.fail('legacy must not spend'))
        self.assertEqual(result['reason_code'], 'classifier_reconfiguration_required')
        self.assertIsNone(result['model'])

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
        def runner(payload, credential_env, timeout):
            self.calls.append((payload, credential_env, timeout))
            return answer() if events is None else events
        return self.ai.classify('Perform a read-only extraction.', configuration(), catalogue(),
                                runner=runner, **kwargs)

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

    def test_api_request_excludes_tools_and_uses_strict_schema(self):
        self.run_classifier()
        payload, credential_env, timeout = self.calls[0]
        self.assertEqual(payload['model'], 'future-classifier')
        self.assertEqual(payload['tools'], [])
        self.assertEqual(payload['tool_choice'], 'none')
        self.assertFalse(payload['store'])
        self.assertTrue(payload['text']['format']['strict'])
        self.assertFalse(payload['text']['format']['schema']['additionalProperties'])
        self.assertEqual(payload['max_output_tokens'], 256)
        self.assertIn('Perform a read-only extraction.', json.dumps(payload['input']))
        self.assertEqual(credential_env, 'AUTOROUTER_TEST_API_KEY')
        self.assertEqual(timeout, 6)

    def test_invalid_responses_use_one_fallback_without_retry(self):
        cases = [answer('outside', 'low'), answer('future-small', 'high'), answer(rationale='secret' * 100),
                 {'status': 'failed'}, {}, {**answer(), 'output': answer()['output'] * 2}]
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
        result = self.ai.classify('x', configuration(), catalogue(), runner=timeout)
        self.assertEqual(result['status'], 'fallback')
        self.assertEqual(result['reason_code'], 'classifier_timeout')
        self.assertEqual(len(self.calls), 1)

    def test_configured_trial_deadline_reaches_one_request_without_retry(self):
        doc = configuration(); doc['timeout_seconds'] = 30
        calls = []

        def runner(payload, credential_env, timeout):
            calls.append(timeout)
            return answer()

        result = self.ai.classify('Read only.', doc, runner=runner)
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(result['calls'], 1)
        self.assertEqual(calls, [30])

    def test_recursion_guard_never_invokes_api(self):
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
                                  runner=lambda *args: self.fail('must not call'))
        self.assertEqual(result['reason_code'], 'prompt_too_large')
        self.assertEqual(result['status'], 'fallback')

    def test_invalid_fallback_cannot_authorise_execution(self):
        doc = configuration(); doc['fallback']['model'] = 'outside'
        result = self.ai.classify('x', doc, {}, runner=lambda *args: self.fail('must not call'))
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['model'])

    def test_tool_activity_in_classifier_output_is_not_accepted_as_a_selection(self):
        events = answer(); events['output'].insert(0, {'type': 'function_call', 'name': 'ignored'})
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
                    runner=lambda *args: answer('future-large', 'high'))
                self.assertEqual((result['model'], result['effort']), ('future-large', 'high'))
                self.assertEqual(result['calls'], 1)
                self.assertNotIn('savings', result)

    def test_maximum_classifier_budget_has_prompt_hook_headroom(self):
        root = Path(__file__).resolve().parents[3]
        hooks = json.loads((root / 'hooks/hooks.json').read_text())['hooks']['UserPromptSubmit']
        timeout = hooks[0]['hooks'][0]['timeout']
        self.assertLess(30, timeout)

    def test_disabled_classification_does_not_spend_or_delegate(self):
        doc = configuration(); doc['enabled'] = False
        result = self.ai.classify('x', doc, {}, runner=lambda *a: self.fail('disabled'))
        self.assertEqual(result['calls'], 0)
        self.assertIsNone(result['model'])
        self.assertEqual(result['reason_code'], 'classification_disabled')

    def test_refusal_and_incomplete_output_preserve_usage_without_selecting(self):
        for response in ({**answer(), 'status': 'incomplete'},
                         {**answer(), 'output': [{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'no'}]}]}):
            result = self.run_classifier(response)
            self.assertEqual(result['status'], 'fallback')
            self.assertEqual(result['usage']['output_tokens'], 12)

    def test_non_scalar_pair_and_duplicate_json_keys_cannot_authorise(self):
        for text in ('{"model":[],"effort":{},"rationale":"x"}',
                     '{"model":"outside","model":"future-small","effort":"low","rationale":"x"}'):
            response = answer(); response['output'][0]['content'][0]['text'] = text
            result = self.run_classifier(response)
            self.assertEqual(result['status'], 'fallback')

    def test_contradictory_response_metadata_cannot_authorise_selection(self):
        responses = []
        response = answer(); response['error'] = {}; responses.append(response)
        response = answer(); response['output'][0]['role'] = 'user'; responses.append(response)
        response = answer(); response['output'][0]['status'] = 'incomplete'; responses.append(response)
        for response in responses:
            with self.subTest(response=response):
                self.assertEqual(self.run_classifier(response)['status'], 'fallback')


class SetupCommandTests(unittest.TestCase):
    def test_interactive_setup_can_include_the_root_pair_without_catalogue_proof(self):
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location('autorouter_setup_test', root / 'scripts/autorouter.py')
        tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'routing.json'
            output, errors = StringIO(), StringIO()
            inputs = ['openai', 'future-classifier', 'low', 'AUTOROUTER_TEST_API_KEY',
                      'future-small=low future-large=medium,high', 'future-large=high', '', 'y']
            with mock.patch.object(tool, 'available_models', return_value={}), \
                    mock.patch.object(tool.sys.stdin, 'isatty', return_value=True), \
                    mock.patch('builtins.input', side_effect=inputs), \
                    redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(tool.main(['setup', '--config', str(path)]), 0)
            doc = json.loads(path.read_text())
            self.assertIn({'model': 'future-small', 'efforts': ['low']}, doc['executors'])
            self.assertTrue(doc['enabled'])
            self.assertEqual(doc['timeout_seconds'], 10)
            self.assertIn('current root model and effort', errors.getvalue())
            self.assertEqual(json.loads(output.getvalue())['live_classifier_calls'], 0)

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
                    '--provider', 'openai', '--credential-env', 'AUTOROUTER_TEST_API_KEY', '--enabled',
                    '--classifier', 'future-classifier', '--classifier-effort', 'low',
                    '--allow', 'future-small=low', '--allow', 'future-large=medium,high',
                    '--fallback', 'future-large=high']
            for iteration in range(2):
                result = subprocess.run(args, capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data['status'], 'configured')
                self.assertEqual(data['model_access'], 'catalogue_only_not_inference_verified')
                self.assertEqual(data.get('runtime_routing'), 'configured_not_runtime_verified')
                self.assertEqual(data.get('executor_compatibility'), 'codex_native_validation')
                self.assertEqual(bool(data['backup']), bool(iteration))
            path = home / 'autorouter/config.json'
            expected = configuration(); expected['timeout_seconds'] = 10
            self.assertEqual(json.loads(path.read_text()), expected)
            before = path.read_bytes()
            invalid = args.copy(); invalid[invalid.index('openai')] = 'unknown'
            self.assertNotEqual(subprocess.run(invalid, capture_output=True, env=env).returncode, 0)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((home / 'config.toml').exists())

    def test_setup_accepts_an_explicit_timeout_without_inference(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = {**os.environ, 'CODEX_HOME': str(home), 'PYTHONDONTWRITEBYTECODE': '1'}
            args = [sys.executable, '-B', str(root / 'scripts/autorouter.py'), 'setup',
                    '--provider', 'openai', '--credential-env', 'AUTOROUTER_TEST_API_KEY', '--enabled',
                    '--classifier', 'future-classifier', '--classifier-effort', 'low',
                    '--allow', 'future-small=low', '--allow', 'future-large=medium,high',
                    '--fallback', 'future-large=high', '--timeout-seconds', '12.5']
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = home / 'autorouter/config.json'
            self.assertEqual(json.loads(path.read_text())['timeout_seconds'], 12.5)
            self.assertEqual(json.loads(result.stdout)['live_classifier_calls'], 0)
            before = path.read_bytes()
            invalid = args.copy(); invalid[-1] = '31'
            self.assertEqual(subprocess.run(invalid, capture_output=True, env=env).returncode, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_status_reports_credential_presence_without_its_value(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            import routing_config
            path = Path(tmp) / 'routing.json'
            routing_config.save_config(path, configuration())
            args = [sys.executable, '-B', str(root / 'scripts/autorouter.py'), 'status', '--config', str(path)]
            for value in (None, '', 'fake-key-must-not-appear'):
                env = {k: v for k, v in os.environ.items() if k != 'AUTOROUTER_TEST_API_KEY'}
                if value is not None:
                    env['AUTOROUTER_TEST_API_KEY'] = value
                result = subprocess.run(args, capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIs(json.loads(result.stdout).get('credential_environment_present'), bool(value))
                self.assertNotIn('fake-key-must-not-appear', result.stdout + result.stderr)

    def test_status_separates_configured_routing_from_execution_proof(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'routing.json'
            base = [sys.executable, '-B', str(root / 'scripts/autorouter.py'), 'status', '--config', str(path)]
            missing = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 0)
            self.assertEqual(json.loads(missing.stdout).get('runtime_routing'), 'legacy_compatibility')
            import routing_config
            routing_config.save_config(path, configuration())
            configured = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(configured.returncode, 0)
            status = json.loads(configured.stdout)
            self.assertEqual(status['runtime_routing'], 'configured_not_runtime_verified')
            self.assertEqual(status['classifier_isolation'], 'api_tools_disabled')
            self.assertEqual(status['executor_compatibility'], 'codex_native_validation')
            self.assertFalse(status['execution_verified'])


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

    def test_configured_selection_plans_one_native_validated_request_not_execution(self):
        with mock.patch.object(self.hook, 'classify_prompt', side_effect=AssertionError('legacy path')):
            result = self.hook.handle(self.data)
        state = self.state(); decision = state['decision']
        self.assertEqual(decision['classification']['model'], 'future-large')
        self.assertTrue(decision['route'].startswith('configured_'))
        self.assertTrue(decision['delegate'])
        self.assertEqual(decision['executor_compatibility'], 'codex_native_validation')
        self.assertEqual(state['agents'], {})
        self.assertEqual(state['status'], 'ROUTED')
        self.assertFalse(decision['announce_route'])
        self.assertIn('execution is pending', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(sum(decision['orchestration']['required_agents'].values()), 1)
        self.assertEqual(decision['classification']['duration_ms'], 12)
        self.assertNotIn(self.data['prompt'], json.dumps(state))

    def test_duplicate_root_delivery_does_not_classify_again(self):
        self.hook.handle(self.data)
        self.hook.handle(self.data)
        self.assertEqual(self.classifier.call_count, 1)
        self.assertEqual(len(list((self.home / 'state').glob('configured-session--*.json'))), 1)

    def test_duplicate_delivery_does_not_issue_another_child_contract(self):
        self.hook.handle(self.data)
        result = self.hook.handle(self.data)
        context = result['hookSpecificOutput']['additionalContext']
        self.assertIn('no spawn is permitted', context)
        self.assertNotIn('spawn exactly one', context)
        self.assertEqual(sum(self.state()['decision']['orchestration']['required_agents'].values()), 1)

    def test_interrupted_classifier_reserves_turn_before_any_billable_attempt(self):
        self.classifier.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.hook.handle(self.data)
        self.classifier.side_effect = None
        self.hook.handle(self.data)
        self.assertEqual(self.classifier.call_count, 1)
        self.assertFalse(self.state()['decision']['delegate'])
        self.assertEqual(self.state()['decision']['classification']['reason_code'], 'interrupted_classification_unknown')
        self.assertIsNone(self.state()['decision']['classification']['calls'])

    def test_disabled_configured_mode_cannot_report_healthy(self):
        import check_hooks
        import routing_config
        self.addCleanup(lambda: check_hooks.refresh_configured_capabilities(self.home / 'absent'))
        doc = configuration(); doc['enabled'] = False
        routing_config.save_config(self.home / 'autorouter/config.json', doc)
        check_hooks.refresh_configured_capabilities(self.home)
        health = check_hooks._routing_health({'available': True, 'model': 'unknown-root'},
            self.hook.PLUGIN_VERSION, self.home / 'health', current_session_id=self.data['session_id'])
        self.assertEqual(health['status'], 'UNAVAILABLE')

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

    def test_closed_interval_merge_can_complete_on_the_allowlisted_root_without_a_child(self):
        self.classifier.return_value.update(model='future-small', effort='low')
        prompt = (
            'Write a JavaScript function that merges overlapping closed intervals without mutating the input. '
            'Include two small test cases, one with unsorted intervals and one with intervals that share an endpoint. '
            'Reply in chat only. Don’t edit files or run commands.'
        )
        data = {**self.data, 'model': 'future-small', 'model_reasoning_effort': 'low', 'prompt': prompt}
        self.hook.handle(data)
        self.assertEqual(self.classifier.call_args.args[0], prompt)
        decision = self.state()['decision']
        self.assertEqual(decision['route'], 'current')
        self.assertFalse(decision['delegate'])
        self.assertEqual(decision['profile_satisfaction'], 'satisfied')
        self.assertEqual(decision['executor_compatibility'], 'not_required')
        self.hook.handle({**data, 'hook_event_name': 'Stop'})
        self.assertEqual(self.classifier.call_count, 1)
        state = self.state()
        self.assertEqual(state['agents'], {})
        self.assertEqual(state['status'], 'COMPLETE')
        self.assertEqual(state['violations'], [])

    def test_same_model_with_different_effort_is_not_a_direct_match(self):
        self.hook.handle({**self.data, 'model': 'future-large', 'model_reasoning_effort': 'medium'})
        decision = self.state()['decision']
        self.assertTrue(decision['delegate'])
        self.assertEqual(decision['effort'], 'high')
        self.assertEqual(decision['executor_compatibility'], 'codex_native_validation')

    def test_guard_returns_before_ledger_or_classifier(self):
        with mock.patch.dict(os.environ, {'AUTOROUTER_CLASSIFIER_ACTIVE': '1'}):
            self.assertIsNone(self.hook.handle(self.data))
        self.assertFalse((self.home / 'state').exists())
        self.assertEqual(self.classifier.call_count, 0)

    def test_configured_spawn_contract_checks_allowlist_without_self_attesting_execution(self):
        import spawn_compat
        self.hook.handle(self.data)
        args = {'model': 'future-large', 'reasoning_effort': 'high', 'fork_turns': 'none',
                'task_name': 'bounded', 'message': 'Read only.'}
        self.assertTrue(spawn_compat.validate_arguments(args)['spawn_contract_valid'])
        self.assertEqual(self.state()['agents'], {})
        self.assertFalse(spawn_compat.validate_arguments({**args, 'model': 'gpt-6-sol'})['spawn_contract_valid'])

    def test_tool_events_never_reclassify(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'hook_event_name': 'PostToolUse', 'tool_name': 'Read', 'tool_input': {}})
        self.assertEqual(self.classifier.call_count, 1)

    def test_configured_mode_does_not_accept_model_from_invalid_classifier_boundary(self):
        self.classifier.return_value = {'model': 'outside', 'effort': 'high', 'status': 'selected'}
        self.hook.handle(self.data)
        self.assertFalse(self.state()['decision']['delegate'])

    def test_configured_fallback_can_request_one_native_validated_child(self):
        self.classifier.return_value['status'] = 'fallback'
        self.hook.handle(self.data)
        decision = self.state()['decision']
        self.assertTrue(decision['delegate'])
        self.assertEqual(decision['executor_compatibility'], 'codex_native_validation')
        self.assertEqual(sum(decision['orchestration']['required_agents'].values()), 1)
        self.assertEqual(decision['catalogue_availability'], 'available')

    def test_short_continuation_reuses_decision_without_another_classifier_call(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'turn_id': 'continued-turn', 'prompt': 'Continue.'})
        state = json.loads((self.home / 'state/configured-session--continued-turn.json').read_text())
        self.assertEqual(self.classifier.call_count, 1)
        self.assertEqual(state['decision']['classification']['calls'], 0)
        self.assertEqual(state['decision']['classification']['model'], 'future-large')
        self.assertFalse(state['decision']['delegate'])

    def test_hook_completion_continuation_does_not_reenter_legacy_model_policy(self):
        self.hook.handle(self.data)
        with mock.patch.object(self.hook, '_apply_actual_root_policy', side_effect=AssertionError('legacy policy')):
            self.hook.handle({**self.data, 'turn_id': 'gate-turn', 'prompt': 'Router completion gate: finish verification.'})
        state = json.loads((self.home / 'state/configured-session--gate-turn.json').read_text())
        self.assertEqual(state['decision']['classification']['model'], 'future-large')
        self.assertFalse(state['decision']['delegate'])
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

    def test_completed_delegation_supplies_context_for_a_presentation_only_follow_up(self):
        import spawn_compat
        self.hook.handle(self.data)
        base = {**self.data, 'model': 'future-large', 'model_reasoning_effort': 'high',
                'agent_id': 'future-child'}
        self.hook.handle({**base, 'hook_event_name': 'SubagentStart'})
        self.assertEqual(self.classifier.call_count, 1)
        state = self.state()
        args = {'model': 'future-large', 'reasoning_effort': 'high', 'fork_turns': 'none',
                'task_name': 'bounded', 'message': 'Read only.'}
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
        self.assertEqual(state['status'], 'COMPLETE')
        self.assertTrue(state['agent_attestations']['future-child']['matched'])
        self.assertEqual(state['agent_attestations']['future-child']['effort_evidence'], 'direct_spawn_intent')
        self.assertEqual(self.classifier.call_count, 1)
        self.assertFalse((self.home / 'health/capability-v3.json').exists())

        follow_up = {**self.data, 'turn_id': 'continued-turn',
                     'prompt': 'Make that explanation one sentence while keeping the same argument.'}
        self.hook.handle(follow_up)
        replay = self.hook.handle(follow_up)
        self.assertEqual(self.classifier.call_count, 1)
        continued = json.loads((self.home / 'state/configured-session--continued-turn.json').read_text())
        self.assertEqual(continued['inherited_from_turn'], self.data['turn_id'])
        decision = continued['decision']
        self.assertEqual(decision['classification']['calls'], 0)
        self.assertTrue(decision['classification']['execution_reused'])
        self.assertEqual(decision['classification']['model'], 'future-large')
        self.assertFalse(decision['delegate'])
        self.assertEqual(decision['orchestration']['required_agents'], {})
        self.assertEqual(continued['agents'], {})
        self.assertEqual(continued['agent_attestations'], {})
        self.assertIn('no spawn is permitted', replay['hookSpecificOutput']['additionalContext'])

        independent = {**follow_up, 'turn_id': 'independent-turn',
                       'prompt': 'Make that explanation one sentence, then design an async scheduler.'}
        self.hook.handle(independent)
        self.assertEqual(self.classifier.call_count, 2)
        self.assertEqual(self.classifier.call_args.args[0], independent['prompt'])

    def test_presentation_only_follow_up_without_a_completed_turn_classifies_normally(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'turn_id': 'continued-turn',
                          'prompt': 'Make that explanation one sentence while keeping the same argument.'})
        self.assertEqual(self.classifier.call_count, 2)

    def test_presentation_only_follow_up_after_settings_change_classifies_normally(self):
        import routing_config
        self.classifier.return_value.update(model='future-small', effort='low')
        data = {**self.data, 'model': 'future-small', 'prompt': 'Explain why binary search terminates.'}
        self.hook.handle(data)
        self.hook.handle({**data, 'hook_event_name': 'Stop'})
        self.assertEqual(self.state()['status'], 'COMPLETE')

        changed = configuration()
        changed['timeout_seconds'] = 12
        routing_config.save_config(self.home / 'autorouter/config.json', changed)
        self.hook.handle({**data, 'turn_id': 'continued-turn',
                          'prompt': 'Make that explanation one sentence while keeping the same argument.'})
        self.assertEqual(self.classifier.call_count, 2)

    def test_native_model_rejection_retains_parent_and_never_completes_or_retries(self):
        self.hook.handle(self.data)
        event = {**self.data, 'hook_event_name': 'PostToolUse', 'tool_name': 'spawn_agent',
                 'call_id': 'native-reject',
                 'tool_input': {'model': 'future-large', 'reasoning_effort': 'high', 'fork_turns': 'none',
                                'task_name': 'bounded', 'message': 'Return only 42.'},
                 'tool_response': 'Unknown model `future-large` for spawn_agent. Available models: future-small'}
        result = self.hook.handle(event)
        self.hook.handle(event)
        state = self.state()
        self.assertEqual(state['delegation_attempts']['native-reject']['outcome'], 'rejected_before_creation')
        self.assertEqual(len(state['delegation_attempts']), 1)
        self.assertEqual(state['agents'], {})
        self.assertIn('current parent', result['systemMessage'])
        self.assertNotIn('Available models', json.dumps(state))
        self.hook.handle({**self.data, 'hook_event_name': 'Stop'})
        self.assertEqual(self.state()['status'], 'FAILED_OPEN')
        self.assertEqual(self.classifier.call_count, 1)

    def test_error_after_child_start_is_not_reported_as_precreation_rejection(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'hook_event_name': 'SubagentStart', 'agent_id': 'child-started',
                          'model': 'future-large', 'reasoning_effort': 'high'})
        self.hook.handle({**self.data, 'hook_event_name': 'PostToolUse', 'tool_name': 'spawn_agent',
                          'call_id': 'post-start', 'tool_response': {'error': 'worker unavailable'}})
        self.assertEqual(self.state()['delegation_attempts']['post-start']['outcome'], 'failed_after_creation')

    def test_creation_acknowledgement_without_lifecycle_cannot_complete(self):
        self.hook.handle(self.data)
        self.hook.handle({**self.data, 'hook_event_name': 'PostToolUse', 'tool_name': 'spawn_agent',
                          'call_id': 'reported', 'tool_response': {'agent_id': 'reported-child'}})
        self.assertEqual(self.state()['delegation_attempts']['reported']['outcome'], 'creation_reported')
        self.assertEqual(self.state()['agents'], {})
        self.hook.handle({**self.data, 'hook_event_name': 'Stop'})
        self.assertEqual(self.state()['status'], 'FAILED_OPEN')

    def test_transcript_call_and_returned_id_do_not_invent_a_started_child(self):
        self.hook.handle(self.data)
        state = self.state()
        args = {'model': 'future-large', 'reasoning_effort': 'high', 'fork_turns': 'none',
                'task_name': 'bounded', 'message': 'Return only 42.'}
        metadata = {'turn_id': self.data['turn_id']}
        records = [
            {'payload': {'type': 'function_call', 'name': 'spawn_agent', 'call_id': 'call-reported',
                         'arguments': json.dumps(args), 'internal_chat_message_metadata_passthrough': metadata}},
            {'payload': {'type': 'function_call_output', 'call_id': 'call-reported',
                         'output': json.dumps({'agent_id': 'reported-child'}),
                         'internal_chat_message_metadata_passthrough': metadata}},
        ]
        transcript = self.home / 'synthetic-parent.jsonl'
        transcript.write_text(''.join(json.dumps(item) + '\n' for item in records))
        self.hook._reconcile_subagent_transcript({'transcript_path': str(transcript)}, state)
        self.assertEqual(state['subagents_started'], [])
        self.assertEqual(state['agents']['reported-child']['status'], 'creation_reported')
        self.assertFalse(state.get('agent_attestations', {}).get('reported-child', {}).get('matched'))
        records.append({'payload': {'type': 'item_completed', 'thread_id': self.data['session_id'],
            'turn_id': self.data['turn_id'], 'item': {'type': 'SubAgentActivity', 'id': 'call-reported',
            'agent_thread_id': 'reported-child', 'kind': 'started', 'model': 'future-large',
            'reasoning_effort': 'high'}}})
        transcript.write_text(''.join(json.dumps(item) + '\n' for item in records))
        self.hook._reconcile_subagent_transcript({'transcript_path': str(transcript)}, state)
        self.assertEqual(state['agents']['reported-child']['status'], 'started')

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
        self.assertEqual(health['status'], 'DEGRADED')

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



class RuntimeSafetyTests(unittest.TestCase):
    def test_https_auth_is_sent_only_to_fixed_endpoint_and_reads_are_bounded(self):
        import ai_classifier
        connection = mock.Mock(); response = connection.getresponse.return_value
        response.status = 200; response.read.return_value = json.dumps(answer()).encode()
        with mock.patch.object(ai_classifier.http.client, 'HTTPSConnection', return_value=connection) as connect:
            result = ai_classifier._http_request({'tools': []}, 'fake-test-key', 2)
        self.assertEqual(result['status'], 'completed')
        connect.assert_called_once_with('api.openai.com', timeout=2)
        self.assertEqual(connection.request.call_args.args[:2], ('POST', '/v1/responses'))
        self.assertEqual(connection.request.call_args.kwargs['headers']['Authorization'], 'Bearer fake-test-key')
        response.read.assert_called_once_with(128 * 1024 + 1)
        connection.close.assert_called_once()

    def test_http_errors_and_redirects_do_not_read_bodies_or_retry(self):
        import ai_classifier
        for status, expected in ((401, 'classifier_authentication_failed'), (403, 'classifier_authentication_failed'),
                                 (302, 'classifier_api_failed'), (429, 'classifier_api_failed'), (500, 'classifier_api_failed')):
            with self.subTest(status=status):
                connection = mock.Mock(); connection.getresponse.return_value.status = status
                with mock.patch.object(ai_classifier.http.client, 'HTTPSConnection', return_value=connection):
                    with self.assertRaises(ai_classifier.ClassifierError) as error:
                        ai_classifier._http_request({}, 'fake-test-key', 1)
                self.assertEqual(error.exception.code, expected)
                connection.getresponse.return_value.read.assert_not_called()
                self.assertEqual(connection.request.call_count, 1)

    def test_oversized_or_malformed_http_response_never_authorises(self):
        import ai_classifier
        for body in (b'x' * (128 * 1024 + 1), b'{malformed', b'[' * 2000):
            connection = mock.Mock(); response = connection.getresponse.return_value
            response.status = 200; response.read.return_value = body
            with mock.patch.object(ai_classifier.http.client, 'HTTPSConnection', return_value=connection):
                with self.assertRaises((ai_classifier.ClassifierError, ValueError, RecursionError)):
                    ai_classifier._http_request({}, 'fake-test-key', 1)
            connection.close.assert_called_once()

    def test_worker_uses_reference_only_and_no_codex_subprocess(self):
        import ai_classifier
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (json.dumps({'response': answer()}).encode(), b'')
        with mock.patch.dict(os.environ, {'AUTOROUTER_TEST_API_KEY': 'fake-test-key', 'UNRELATED_SECRET': 'not-forwarded'}), \
             mock.patch('subprocess.Popen', return_value=process) as launch:
            result = ai_classifier.run_api({'input': 'sensitive task'}, 'AUTOROUTER_TEST_API_KEY', 1)
        self.assertEqual(result['status'], 'completed')
        argv = launch.call_args.args[0]
        self.assertEqual(argv[:3], [sys.executable, '-I', '-B'])
        self.assertNotIn('sensitive task', repr(argv))
        self.assertNotIn('fake-test-key', repr(argv))
        self.assertNotIn('UNRELATED_SECRET', launch.call_args.kwargs['env'])
        self.assertNotIn('shell', launch.call_args.kwargs)
        self.assertNotIn(b'fake-test-key', process.communicate.call_args.args[0])

    def test_missing_api_credential_stops_before_process_creation(self):
        import ai_classifier
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch('subprocess.Popen', side_effect=AssertionError('no process')):
            result = ai_classifier.classify('Classify a harmless calculation.', configuration(), catalogue())
        self.assertEqual(result['reason_code'], 'classifier_credential_missing')
        self.assertEqual(result['calls'], 0)
        self.assertEqual(result['status'], 'fallback')

    def test_http_worker_timeout_is_killed_and_not_retried(self):
        import ai_classifier
        process = mock.Mock()
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 1), (b'', b'')]
        with mock.patch.dict(os.environ, {'AUTOROUTER_TEST_API_KEY': 'fake-test-key'}), \
             mock.patch('subprocess.Popen', return_value=process) as launch:
            with self.assertRaises(ai_classifier.ClassifierError) as error:
                ai_classifier.run_api({}, 'AUTOROUTER_TEST_API_KEY', 1)
        self.assertEqual(error.exception.code, 'classifier_timeout')
        process.kill.assert_called_once()
        self.assertEqual(launch.call_count, 1)
        self.assertNotIn('fake-test-key', repr(launch.call_args.args))

    def test_configured_allowlist_is_contract_validation_not_child_execution(self):
        import spawn_compat
        spawn_compat.configure_models(configuration())
        self.addCleanup(lambda: spawn_compat.configure_models(None))
        result = spawn_compat.validate_arguments({'model': 'future-large', 'reasoning_effort': 'high',
            'fork_turns': 'none', 'task_name': 'bounded', 'message': 'Read only.'})
        self.assertTrue(result['spawn_contract_valid'])
        self.assertEqual(result['model'], 'future-large')
        self.assertNotIn('execution_verified', result)


if __name__ == '__main__':
    unittest.main()
