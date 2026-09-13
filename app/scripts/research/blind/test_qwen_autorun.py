"""Check the driver shared-status race without launching any model work."""
import concurrent.futures,json,pathlib,tempfile,unittest
from unittest.mock import patch
import qwen_autorun as driver

class DriverStatusTests(unittest.TestCase):
    def test_parallel_branches_use_distinct_temporary_files(self):
        original=driver.os.replace;names=[]
        def replace(src,dest):names.append(src);return original(src,dest)
        with tempfile.TemporaryDirectory() as directory,patch.object(driver.q,'ROOT',pathlib.Path(directory)),patch('builtins.print'),patch.object(driver.os,'replace',side_effect=replace):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda i:driver.status(str(i),'test'),range(8)))
            final=json.loads((pathlib.Path(directory)/'DRIVER-PROGRESS.json').read_text())
            self.assertIn(final['phase'],[str(i) for i in range(8)])
            self.assertEqual(list(pathlib.Path(directory).glob('*.tmp')),[])
        self.assertEqual(len(set(names)),8)

if __name__=='__main__':unittest.main()
