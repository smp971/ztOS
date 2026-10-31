#!/usr/bin/env python3
"""Check the private firmware inputs collected from this Crown's VENDOR."""
import hashlib
import sys
from pathlib import Path

expected = {
    'bcm4361B2_semco.hcd': '11f8161603ad77228b3f6f7c85427d09bc0f0c19518687181e8717590bf426ea',
    'bcmdhd_sta.bin_b2': 'e3c66440a4a6c3d30918f922c20ccd0fbecaa1aaa0460b4458b48e202473f452',
    'bcmdhd_clm.blob': '1c1477864b0858bd0ad8700a766318c2f7220e4766dba0e8ee15d8bf13435356',
    'nvram.txt_r02b_b2': '68cb903937a5c2af055bee36141047df9cf5e7d79a23a24a0677e2faf85ccba2',
}
directory = Path(sys.argv[1])
for name, digest in expected.items():
    if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Crown firmware input differs: {name}')
print('Crown vendor firmware and CROWN-EU NVRAM inputs verified')
