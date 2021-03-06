""" unit test """
import os

from bzt.engine import ScenarioExecutor
from bzt.six import string_types
from bzt.utils import BetterDict, EXE_SUFFIX, is_windows
from tests import BZTestCase, __dir__, local_paths_config
from tests.mocks import EngineEmul
from bzt import TaurusConfigError


class TestEngine(BZTestCase):
    def setUp(self):
        super(TestEngine, self).setUp()
        self.obj = EngineEmul()
        self.paths = local_paths_config()

    def test_missed_config(self):
        configs = ['difinitely_missed.file']
        try:
            self.obj.configure(configs)
            self.fail()
        except TaurusConfigError as exc:
            self.assertIn('reading config file', str(exc))

    def test_requests(self):
        configs = [
            __dir__() + "/../bzt/10-base.json",
            __dir__() + "/json/get-post.json",
            __dir__() + "/json/reporting.json",
            self.paths
        ]
        self.obj.configure(configs)
        self.obj.prepare()

        for executor in self.obj.provisioning.executors:
            executor._env['TEST_MODE'] = 'files'

        self.obj.run()
        self.obj.post_process()

    def test_double_exec(self):
        configs = [
            __dir__() + "/../bzt/10-base.json",
            __dir__() + "/yaml/triple.yml",
            __dir__() + "/json/reporting.json",
            self.paths
        ]
        self.obj.configure(configs)
        self.obj.prepare()

        for executor in self.obj.provisioning.executors:
            executor._env['TEST_MODE'] = 'files'

        self.obj.run()
        self.obj.post_process()

    def test_unknown_module(self):
        configs = [
            __dir__() + "/../bzt/10-base.json",
            __dir__() + "/json/gatling.json",
            self.paths
        ]
        self.obj.configure(configs)
        self.obj.config["provisioning"] = "unknown"
        self.obj.config["modules"]["unknown"] = BetterDict()

        self.assertRaises(TaurusConfigError, self.obj.prepare)



class TestScenarioExecutor(BZTestCase):
    def setUp(self):
        super(TestScenarioExecutor, self).setUp()
        self.engine = EngineEmul()
        self.executor = ScenarioExecutor()
        self.executor.engine = self.engine

    def test_scenario_extraction_script(self):
        self.engine.config.merge({
            "execution": [{
                "scenario": {
                    "script": "tests/selenium/python/test_blazemeter_fail.py",
                    "param": "value"
                }}]})
        self.executor.execution = self.engine.config.get('execution')[0]
        self.executor.get_scenario()
        config = self.engine.config
        self.assertEqual(config['execution'][0]['scenario'], 'test_blazemeter_fail.py')
        self.assertIn('test_blazemeter_fail.py', config['scenarios'])

    def test_body_files(self):
        body_file1 = __dir__() + "/jmeter/body-file.dat"
        body_file2 = __dir__() + "/jmeter/jmx/http.jmx"
        self.engine.config.merge({
            'execution': [{
                'iterations': 1,
                'executor': 'siege',
                'scenario': 'bf'}],
            'scenarios': {
                'bf': {
                    "requests": [
                        {
                            'url': 'http://first.com',
                            'body-file': body_file1
                        }, {
                            'url': 'http://second.com',
                            'body': 'body2',
                            'body-file': body_file2}]}}})
        self.executor.execution = self.engine.config.get('execution')[0]
        scenario = self.executor.get_scenario()

        # check body fields in get_requests() results
        reqs = list(scenario.get_requests())
        body_fields = [req.body for req in reqs]
        self.assertIn('sample of body', body_fields[0])
        self.assertIn('body2', body_fields[1])

        # check body fields and body-files fields after get_requests()
        scenario = self.executor.get_scenario()
        body_files = [req.get('body-file') for req in scenario.get('requests')]
        body_fields = [req.get('body') for req in scenario.get('requests')]
        self.assertTrue(all(body_files))
        self.assertEqual(None, body_fields[0])
        self.assertIn('body2', body_fields[1])

    def test_scenario_is_script(self):
        self.engine.config.merge({
            "execution": [{
                "scenario": "tests/selenium/python/test_blazemeter_fail.py"
            }]})
        self.executor.execution = self.engine.config.get('execution')[0]
        self.executor.get_scenario()
        config = self.engine.config
        self.assertEqual(config['execution'][0]['scenario'], 'test_blazemeter_fail.py')
        self.assertIn('test_blazemeter_fail.py', config['scenarios'])

    def test_scenario_extraction_request(self):
        self.engine.config.merge({
            "execution": [{
                "scenario": {
                    "requests": [{"url": "url.example"}],
                    "param": "value"
                }}]})
        self.executor.execution = self.engine.config.get('execution')[0]
        self.executor.get_scenario()
        config = self.engine.config
        scenario = config['execution'][0]['scenario']
        self.assertTrue(isinstance(scenario, string_types))
        self.assertIn(scenario, config['scenarios'])

    def test_scenario_not_found(self):
        self.engine.config.merge({
            "execution": [{
                "scenario": "non-existent"
            }]})
        self.executor.execution = self.engine.config.get('execution')[0]
        self.assertRaises(TaurusConfigError, self.executor.get_scenario)

    def test_scenario_no_requests(self):
        self.engine.config.merge({
            "execution": [{
                "scenario": ["url1", "url2"]
            }]})
        self.executor.execution = self.engine.config.get('execution')[0]
        self.assertRaises(TaurusConfigError, self.executor.get_scenario)

    def test_creates_hostaliases_file(self):
        self.engine.config.merge({
            "settings": {
                "hostaliases": {
                    "demo": "blazedemo.com"}}})

        path = os.path.join(__dir__(), "data", "hostaliases" + EXE_SUFFIX)
        process = self.executor.execute([path])
        stdout, _ = process.communicate()
        hosts_file = os.path.join(self.engine.artifacts_dir, "hostaliases")

        self.assertTrue(os.path.exists(hosts_file))
        self.assertIn(hosts_file, str(stdout))

    def test_doesnt_create_hostaliases(self):
        self.executor.execute(["echo"], shell=True)
        hosts_file = os.path.join(self.engine.artifacts_dir, "hostaliases")
        self.assertFalse(os.path.exists(hosts_file))

    def test_passes_artifacts_dir(self):
        cmdline = "echo %TAURUS_ARTIFACTS_DIR%" if is_windows() else "echo $TAURUS_ARTIFACTS_DIR"
        process = self.executor.execute(cmdline, shell=True)
        stdout, _ = process.communicate()
        self.assertEquals(self.engine.artifacts_dir, stdout.decode().strip())
