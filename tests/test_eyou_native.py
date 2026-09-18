"""Exercise real supervisor code against a fake SDK, never against hardware."""
import json
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(shutil.which('g++'), 'g++ is required for native safety regression')
class EyouNativeTests(unittest.TestCase):
    def test_sdk_mapping_modes_stop_and_watchdog(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            binary=Path(temporary)/'eyou_fake'
            subprocess.run(['g++','-std=c++17','-O1','-pthread',str(root/'native/eyou_agent.cpp'),
                            str(root/'tests/native_fake/eyou_fake.cpp'),'-I'+str(root/'tests/native_fake'),
                            '-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary),'--self-test'],check=True,capture_output=True)
            process=subprocess.Popen([str(binary),'--run','fake'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
            selector=selectors.DefaultSelector(); selector.register(process.stdout,selectors.EVENT_READ)
            def send(line):process.stdin.write((line+'\n').encode())
            def wait_for(predicate,timeout=2):
                deadline=time.monotonic()+timeout;last=None
                while time.monotonic()<deadline:
                    if selector.select(.1):
                        last=json.loads(process.stdout.readline())
                        if predicate(last):return last
                self.fail(f'Condition not reached: {last}')
            try:
                state=wait_for(lambda s:s['healthy'])
                self.assertEqual([s['sdk_slave_id'] for s in state['slaves']],[1,2,3,4])
                self.assertEqual([s['operation_mode'] for s in state['slaves']],[10,10,9,9])
                epoch=time.monotonic_ns();send(f'ARM {epoch} {time.monotonic_ns()}')
                send(f'CMD {epoch} 1 {time.monotonic_ns()} 0 50')
                wait_for(lambda s:s['slaves'][0]['statusword']==0x27 and s['slaves'][0]['torque_raw']==50)
                state=wait_for(lambda s:not s['armed'])
                self.assertGreater(state['watchdog_count'],0)
                self.assertEqual(state['slaves'][0]['torque_raw'],0)
                send(f'CMD {epoch} 2 {time.monotonic_ns()} 0 50')
                time.sleep(.1)
                self.assertFalse(wait_for(lambda s:True)['armed'])
                epoch=time.monotonic_ns();send(f'ARM {epoch} {time.monotonic_ns()}')
                send(f'CMD {epoch} 1 {time.monotonic_ns()} 2 .05')
                wait_for(lambda s:s['slaves'][2]['statusword']==0x27 and s['slaves'][2]['velocity_raw']>0)
                send(f'STOP {time.monotonic_ns()}')
                wait_for(lambda s:not s['armed'] and all(m['statusword']!=0x27 and m['velocity_raw']==0 and m['torque_raw']==0 for m in s['slaves']))
            finally:
                process.terminate();process.wait(timeout=3);selector.close()
                process.stdin.close();process.stdout.close();process.stderr.close()
            self.assertEqual(process.returncode,0)


if __name__=='__main__':unittest.main()
