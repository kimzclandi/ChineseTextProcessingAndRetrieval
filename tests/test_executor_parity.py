import os
from pathlib import Path
import subprocess
import sys
import pytest
from scripts.check_executor_parity import compare_snapshots


def test_parity_requires_same_file_set_and_bytes(tmp_path):
    left,right=tmp_path/'left',tmp_path/'right'
    left.mkdir();right.mkdir()
    (left/'a').write_text('original');(right/'a').write_text('changed')
    with pytest.raises(ValueError,match='bytes differ'):compare_snapshots(left,right)
    (right/'a').write_text('original')
    assert compare_snapshots(left,right)=={'a':True}
    (right/'extra').write_text('extra')
    with pytest.raises(ValueError,match='file sets differ'):compare_snapshots(left,right)


def test_optimized_python_cannot_disable_mismatch_detection(tmp_path):
    left,right=tmp_path/'left',tmp_path/'right'
    left.mkdir();right.mkdir()
    (left/'a').write_text('original');(right/'a').write_text('changed')
    root=Path(__file__).resolve().parents[1]
    code='from pathlib import Path; from scripts.check_executor_parity import compare_snapshots; import sys; compare_snapshots(Path(sys.argv[1]),Path(sys.argv[2]))'
    result=subprocess.run([sys.executable,'-O','-c',code,str(left),str(right)],cwd=root,
                          env={**os.environ,'PYTHONPATH':str(root)},capture_output=True,text=True)
    assert result.returncode != 0 and 'snapshot bytes differ' in result.stderr
