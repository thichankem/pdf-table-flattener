import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

out_dir = "output"
for f in os.listdir(out_dir):
    print(f"File in output: {f} ({os.path.getsize(os.path.join(out_dir, f)) / 1024:.1f} KB)")
