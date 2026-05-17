# Execute the verify script
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts')
with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts/_run_verify.py') as f:
    code = compile(f.read(), '_run_verify.py', 'exec')
exec(code)
