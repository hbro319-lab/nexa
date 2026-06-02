from nexa_dispatcher import dispatch

cmd = {"module":"system_control","action":"execute_command","parameters":{"command":"echo","args":["hello from nexa"]}}
res = dispatch(cmd)
print('DISPATCH RESULT:\n', res)
