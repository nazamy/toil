# Copyright (C) 2015 Curoverse, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import
from __future__ import print_function
import json
import os
import subprocess
import re
import shutil
import urllib
import zipfile

# Python 3 compatibility imports
from six.moves import StringIO
from six import u as unicode

from toil.test import ToilTest, needs_cwl

@needs_cwl
class CWLTest(ToilTest):

    def _tester(self, cwlfile, jobfile, outDir, expect):
        from toil.cwl import cwltoil
        rootDir = self._projectRootPath()
        st = StringIO()
        cwltoil.main(['--outdir', outDir,
                            os.path.join(rootDir, cwlfile),
                            os.path.join(rootDir, jobfile)],
                     stdout=st)
        out = json.loads(st.getvalue())
        # locations are internal objects in output for CWL
        out["output"].pop("location", None)
        self.assertEquals(out, expect)

    def test_run_revsort(self):
        outDir = self._createTempDir()
        self._tester('src/toil/test/cwl/revsort.cwl',
                     'src/toil/test/cwl/revsort-job.json',
                     outDir, {
            # Having unicode string literals isn't necessary for the assertion but makes for a
            # less noisy diff in case the assertion fails.
            u'output': {
                u'path': unicode(os.path.join(outDir, 'output.txt')),
                u'basename': unicode("output.txt"),
                u'size': 1111,
                u'class': u'File',
                u'checksum': u'sha1$b9214658cc453331b62c2282b772a5c063dbd284'}})

    def test_restart(self):
        """Enable restarts with CWLtoil -- run failing test, re-run correct test.
        """
        from toil.cwl import cwltoil
        from toil.jobStores.abstractJobStore import NoSuchJobStoreException
        from toil.leader import FailedJobsException
        outDir = self._createTempDir()
        cwlDir = os.path.join(self._projectRootPath(), "src", "toil", "test", "cwl")
        cmd = ['--outdir', outDir, '--jobStore', os.path.join(outDir, 'jobStore'), "--no-container",
               os.path.join(cwlDir, "revsort.cwl"), os.path.join(cwlDir, "revsort-job.json")]
        def path_without_rev():
            return ":".join([d for d in os.environ["PATH"].split(":")
                             if not os.path.exists(os.path.join(d, "rev"))])
        orig_path = os.environ["PATH"]
        # Force a failure and half finished job by removing `rev` from the PATH
        os.environ["PATH"] = path_without_rev()
        try:
            cwltoil.main(cmd)
            self.fail("Expected problem job with incorrect PATH did not fail")
        except FailedJobsException:
            pass
        # Finish the job with a correct PATH
        os.environ["PATH"] = orig_path
        cwltoil.main(cmd + ["--restart"])
        # Should fail because previous job completed successfully
        try:
            cwltoil.main(cmd + ["--restart"])
            self.fail("Restart with missing directory did not fail")
        except NoSuchJobStoreException:
            pass

    def test_run_conformance(self):
        rootDir = self._projectRootPath()
        cwlSpec = os.path.join(rootDir, 'src/toil/test/cwl/spec')
        testhash = "7f510ec768b424601beb8c86700343afe722ac76"
        url = "https://github.com/common-workflow-language/common-workflow-language/archive/%s.zip" % testhash
        if not os.path.exists(cwlSpec):
            urllib.urlretrieve(url, "spec.zip")
            with zipfile.ZipFile('spec.zip', "r") as z:
                z.extractall()
            shutil.move("common-workflow-language-%s" % testhash, cwlSpec)
            os.remove("spec.zip")
        try:
            subprocess.check_output(["bash", "run_test.sh", "RUNNER=cwltoil", "DRAFT=v1.0"], cwd=cwlSpec,
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            only_unsupported = False
            # check output -- if we failed but only have unsupported features, we're okay
            p = re.compile(r"(?P<failures>\d+) failures, (?P<unsupported>\d+) unsupported features")
            for line in e.output.split("\n"):
                m = p.search(line)
                if m:
                    if int(m.group("failures")) == 0 and int(m.group("unsupported")) > 0:
                        only_unsupported = True
                        break
            if not only_unsupported:
                print(e.output)
                raise e
