"""Download only fixed, hash-checked public data into a new work directory and rebuild split."""
import argparse
import json
from pathlib import Path
import urllib.request
from engine.common import sha,write_json
from engine.dataset import prepare

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();output=a.output.resolve()
    if not output.is_relative_to(ROOT/'work') or output==ROOT/'work':p.error('Use a new work subdirectory')
    output.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((ROOT/'configs/protocol.json').read_text());source=protocol['source']
    base=f"https://raw.githubusercontent.com/{source['repo']}/{source['revision']}/squad-style-data/"
    for name,expected in [('cmrc2018_train.json',source['sha256']),('cmrc2018_dev.json',source['old_dev_sha256'])]:
        urllib.request.urlretrieve(base+name,output/name)
        if sha(output/name)!=expected:raise ValueError('Source changed: '+name)
    prepare(output/'cmrc2018_train.json',output/'cmrc2018_dev.json',output/'prepared')
    checks={p.name:sha(p)==sha(ROOT/'data/source-v1'/p.name) for p in (output/'prepared').iterdir() if p.is_file()}
    write_json(output/'comparison.json',checks)
    if not all(checks.values()):raise ValueError('Rebuilt dataset differs')
    print('Pinned source downloaded and all prepared files matched.')
