
from array import array

def run_native(mc, *argv):
    if len(argv) == 1 and type(argv[0]) == array:
        arg = argv[0]
    else:
        arg = array('I', argv)
    if mc[1] >= 0 and mc[1] != len(arg):
        raise Exception("Expected arg count: %d  got:%d" % (mc[1], len(arg)))
    return run_native_launcher(mc[0], len(arg), arg)  # asm_thumb calls will send adressof(arg) when arg is an array

@micropython.asm_thumb
def run_native_launcher(r0, r1, r2):
    mov(r6, 1)
    orr(r0, r6)  # Make sure we don't try to leave Thumb mode
    mov(r6, r1)
    mov(r7, r2)
    data(2, 0x4780)  # blx r0

