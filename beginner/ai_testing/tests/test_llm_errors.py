import os
import unittest
from unittest.mock import patch, Mock
import requests
from beginner.ai_testing.llm import generate, LLMUnavailable, LLMCallError

class ErrorTests(unittest.TestCase):
    def test_missing_key_does_not_call_network(self):
        with patch.dict(os.environ,{},clear=True), patch('requests.post') as post:
            with self.assertRaisesRegex(LLMUnavailable,'未读取到'): generate('a','b')
            post.assert_not_called()

    def test_status_is_actionable_and_never_exposes_key_or_response(self):
        for code in (400,401,402,403,404,429,500):
            with self.subTest(code=code), patch.dict(os.environ,{'AI_TEST_API_KEY':'private-test-key'}), patch('requests.post',return_value=Mock(status_code=code,text='private-test-key')):
                with self.assertRaises(LLMCallError) as error: generate('a','b')
                self.assertIn(str(code),str(error.exception)); self.assertNotIn('private-test-key',str(error.exception))

    def test_timeout_has_no_raw_details(self):
        with patch.dict(os.environ,{'AI_TEST_API_KEY':'private-test-key'}), patch('requests.post',side_effect=requests.exceptions.Timeout('private-test-key')):
            with self.assertRaisesRegex(LLMCallError,'超时'): generate('a','b')

    def test_valid_response(self):
        with patch.dict(os.environ,{'AI_TEST_API_KEY':'private-test-key'}), patch('requests.post',return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':'ok'}}]})):
            self.assertEqual(generate('a','b'),'ok')

if __name__ == '__main__': unittest.main()
