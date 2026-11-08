import copy
import io
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import detective as d
from server import Handler


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.example = d.samples()[0]
        self.case = self.example['input']
        self.result = copy.deepcopy(self.example['result'])

    def envelope(self, result=None):
        return {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(result or self.result)}]}]}

    def test_authored_examples_have_grounded_quotes(self):
        for example in d.samples():
            d.validate_input(example['input'])
            d.validate_result(example['result'], example['input'])

    def test_rejects_invented_evidence(self):
        self.result['checks'][0]['candidate_quote'] = 'QA independently approved.'
        with self.assertRaisesRegex(ValueError, 'Unverifiable'):
            d.validate_result(self.result, self.case)

    def test_rejects_malformed_check(self):
        self.result['checks'][0]['baseline'] = 'excellent'
        with self.assertRaises(ValueError):
            d.validate_result(self.result, self.case)

    def test_omission_can_have_no_quote(self):
        self.result['checks'][0]['candidate_quote'] = ''
        d.validate_result(self.result, self.case)

    def test_invalid_input_never_calls_api(self):
        for invalid in ({}, [], dict(self.case, task=' '), dict(self.case, expected='x' * 12001)):
            with patch('urllib.request.urlopen') as call:
                with self.assertRaises(ValueError):
                    d.judge(invalid)
                call.assert_not_called()

    def test_missing_key_is_actionable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                d.judge(self.case)

    def test_refusal_and_incomplete_are_not_verdicts(self):
        for response in ({'status': 'incomplete'}, {'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'refusal'}]}]}):
            with self.assertRaises(ValueError):
                d.parse_response(response, self.case)

    def test_request_and_response_contract(self):
        response = io.BytesIO(json.dumps(self.envelope()).encode())
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-key'}):
            with patch('urllib.request.urlopen', return_value=response) as call:
                self.assertEqual(d.judge(self.case), self.result)
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertFalse(payload['store'])
        self.assertTrue(payload['text']['format']['strict'])
        self.assertEqual(json.loads(payload['input'][1]['content']), self.case)
        self.assertNotIn('test-only-key', request.data.decode())

    def test_http_error_does_not_leak_provider_body(self):
        error = HTTPError('https://api.openai.com', 401, 'unauthorized', {}, None)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-key'}):
            with patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaisesRegex(ValueError, 'HTTP 401'):
                    d.judge(self.case)
        error.close()

    def test_markdown_contains_evidence(self):
        report = d.markdown(self.result)
        self.assertIn('planned for Friday', report)
        self.assertIn('Limitations:', report)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_static_allowlist_blocks_source_and_secrets(self):
        for path in ('/.env', '/detective.py', '/../README.md'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.url + path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_ui_and_examples_are_served(self):
        with urlopen(self.url) as response:
            self.assertIn(b'Eval Detective', response.read())
        with urlopen(self.url + '/examples.json') as response:
            self.assertEqual(len(json.load(response)), 4)

    def test_cross_origin_request_does_not_call_judge(self):
        request = Request(self.url + '/api/compare', data=b'{}',
                          headers={'Host': '127.0.0.1:4173', 'Origin': 'https://other.example'})
        with patch('server.judge') as call:
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
            call.assert_not_called()

    def test_same_origin_comparison(self):
        example = d.samples()[0]
        request = Request(self.url + '/api/compare', data=json.dumps(example['input']).encode(),
                          headers={'Host': '127.0.0.1:4173', 'Origin': 'http://127.0.0.1:4173'})
        with patch('server.judge', return_value=example['result']):
            with urlopen(request) as response:
                self.assertEqual(json.load(response)['verdict'], 'baseline')


if __name__ == '__main__':
    unittest.main()
