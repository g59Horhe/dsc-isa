#!/usr/bin/env python3
"""Convert a flat binary from objcopy into the harness's hex format."""
import sys
data = open(sys.argv[1], 'rb').read()
if len(data) % 4:
    data += b'\x00' * (4 - len(data) % 4)
for i in range(0, len(data), 4):
    print("%08x" % int.from_bytes(data[i:i+4], 'little'))
