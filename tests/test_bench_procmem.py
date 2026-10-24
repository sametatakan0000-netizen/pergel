import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from src.bench.procmem import TreeSampler, pids_with_exe_prefix, tree_pids

LINUX = os.path.exists("/proc/self/smaps_rollup")


@unittest.skipUnless(LINUX, "linux only")
class ProcmemTests(unittest.TestCase):
    def test_sampler_sees_child_memory(self):
        code = ("import time\nb = bytearray(80*1024*1024)\n"
                "for i in range(0, len(b), 4096): b[i] = 1\ntime.sleep(1.2)")
        p = subprocess.Popen([sys.executable, "-c", code])
        s = TreeSampler(lambda: [p.pid], interval_s=0.05)
        s.start()
        p.wait()
        s.stop()
        self.assertGreater(s.peak_pss_kib, 60 * 1024)

    def test_tree_includes_grandchildren(self):
        p = subprocess.Popen(["sh", "-c", "sleep 1.5 & wait"])
        time.sleep(0.3)
        try:
            self.assertGreaterEqual(len(tree_pids(p.pid)), 2)
        finally:
            p.kill()
            p.wait()

    def test_cpu_seconds_for_busy_child(self):
        code = "import time\nt = time.time()\nwhile time.time() - t < 0.7: pass"
        p = subprocess.Popen([sys.executable, "-c", code])
        s = TreeSampler(lambda: [p.pid], interval_s=0.05)
        s.start()
        p.wait()
        s.stop()
        self.assertGreater(s.cpu_seconds, 0.3)

    def test_pids_with_exe_prefix_finds_top_processes_only(self):
        tmp = tempfile.mkdtemp()
        exe = os.path.join(tmp, "sleep")
        shutil.copy(os.path.realpath(shutil.which("sleep")), exe)
        os.chmod(exe, 0o755)
        p = subprocess.Popen([exe, "2"])
        time.sleep(0.2)
        try:
            self.assertEqual(pids_with_exe_prefix(tmp), [p.pid])
        finally:
            p.kill()
            p.wait()
