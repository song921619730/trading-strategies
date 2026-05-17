import subprocess
r = subprocess.run(['bash', '-c', 'which python3; which python; python3 --version 2>&1; python --version 2>&1'], capture_output=True, text=True)
print(r.stdout)
print("STDERR:", r.stderr)
