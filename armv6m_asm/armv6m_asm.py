
from array import array

#==============================================================================
# Library armv6m_asm
#
# This library defines an assembler decorator for ARMv6-M.
# Syntax is close to @micropython.asm_thumb, but it implements the full
# assembler instruction set, and can use python variables and python code as
# a preprocessor for the assembler.
#

# ==== base ====
def eval_polymorf(args, asm_def):
    global pc
    global mc
    align(2)
    for asm_variant in asm_def[1]:
        if len(args) != len(asm_variant[0]):
            continue
        par = [t(a) for t, a in zip(asm_variant[0], args)]
        if None in par:
            continue
        mc_temp = asm_variant[2](asm_variant[1], *par)
        pc += 2 * len(mc_temp)
        mc += mc_temp
        return
    raise Exception("Can't find match for parameters to instruction: %s" % asm_def[0])

def asm_instr_gen(asm_def):
    def asm(*args):
        eval_polymorf(args, asm_def)
    return asm

def asm_thumb(func):
    global pc
    global mc
    global labels
    global missing_labels
    global argc
    argc = -1
    # Export lib globals to main globals
    func_globs  = func.__globals__
    exp_globs   = (get_directives() |
                   get_macros() |
                   def_tokens() |
                   def_instructions() |
                   {'pc':0, 'mc':[], 'labels':{}, 'missing_labels':[]})
    old_globs   = update_dict(func_globs, exp_globs)
    # Copy some main globals to lib globals.
    for k in ['push', 'pop', 'ldr']:
        globals()[k] = func_globs[k]
    try:
        labels = {}
        for i in range(2):
            missing_labels = []
            pc = 0
            mc = []
            push({lr})  # Emit push to make the array callable
            func()
            pop({pc})   # Emit pop to make the array callable
        loc_mc = mc
        if missing_labels:
            raise Exception("Missing labels: ", missing_labels)
    except Exception:
        restore_dict(func_globs, exp_globs, old_globs)
        raise
    restore_dict(func_globs, exp_globs, old_globs)
    return (array('H', loc_mc), argc)

# ==== global helpers ====
# To make the assembler function look simple, we want to put it in a context where
# it can reach the assembler emitting functions like globals. It would be nice if
# it was possible to inject them into the assembler functions local scope, but
# that's not possible AFAIK.
# Instead, inject the needed functions temporarily in the global scope, and
# clean up when the machine code has been generated.
# This is not thread safe since we are messing with globals, but this is an
# operation that could be done in an initialization step, before threads are started.
#
# Here are a set of functions to store a dict of objects into globals, and then
# restore the globals to prevous values.
#
def update_dict(globs, new_globs):
    old_globs = {k:v for k, v in globs.items() if k in new_globs}
    for k, v in new_globs.items():
        globs[k] = v
    return old_globs

def restore_dict(globs, new_globs, old_globs):
    for k, v in new_globs.items():
        del globs[k]
    for k, v in old_globs.items():
        globs[k] = old_globs[k]
    old_globs.clear()

# ==== assembler directives ====
def label(lab):
    global pc
    global labels
    if type(lab) != type(''):
        raise Exception("Labels must be strings")
    labels[lab] = pc

def align(n):
    global pc
    global mc
    if pc % n:
        mc += [0]
    pc = (pc + n - 1) // n * n

def data(size, *arg):
    global mc
    global pc
    if size not in (1, 2, 4):
        raise Exception("Unsupported data size: %d" % size)
    align(size)
    if [d for d in arg if d < -(1 << size * 8 -1) or d >= 1 << (size * 8)]:
        raise Exception("Data out of bound")
    n = len(arg)
    if size == 1:
        arg += [0]
        for i in range(0, n, 2):
            mc += [arg[i] | arg[i+1] << 8]
        pc += (n+1) // 2 * 2
    elif size == 2:
        mc += arg
        pc += size*len(arg)
    elif size == 4:
        for d in arg:
            mc += [d & 0xffff, (d >> 16) & 0xffff]
        pc += size * len(arg)

def argcount(n): # Store the excpected argc in the output.
    global argc
    if n > 6:
        raise Exception("Too many arguments")
    argc = n

def get_directives():
    return {k:globals()[k] for k in ['label', 'align', 'data', 'argcount']}

# ==== Assembler macros ====
def args_to_regs(n):
    argcount(n)
    for i in range(n):
        ldr(r0 + i, [r7, 4*i])

def get_macros():
    return {k:globals()[k] for k in ['args_to_regs']}

# ==== tokens ====
# Add "random" number > 32 bit, silly way to give it a "type"
def def_tokens():
    token_dict = {key:(i + (0x467382 << 32)) for i, key in enumerate(
        ['r0', 'r1', 'r2',  'r3',  'r4',  'r5',  'r6',  'r7',
         'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15',
         'eq', 'ne', 'cs', 'cc', 'mi', 'pl', 'vs', 'vc',
         'hi', 'ls', 'ge', 'lt', 'gt', 'le', 'al'])}
    token_dict['sp'] = token_dict['r13']
    token_dict['lr'] = token_dict['r14']
    token_dict['pc'] = token_dict['r15']
    return token_dict

for k,v in def_tokens().items() : globals()[k]=v

# ==== Argument converters ====
# These converters tries to convert an argument to the bit pattern that should
# be stored in the machine code instruction. If the argument cant be converted
# to the specific type for the converter, it returns None.
#
def rlo(r):  return alt_list(r, [r0, r1, r2, r3, r4, r5, r6, r7])
def rlh(r):  return alt_list(r, [r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, sp, lr, pc])
def rsp(r):  return alt_list(r, [sp])
def cond(c): return alt_list(c, [eq, ne, cs, cc, mi, pl, vs, vc, hi, ls, ge, lt, gt, le, al])
def alt_list(a, al):
    if a not in al:
        return None
    return al.index(a)

def regs_lo(regs):  return regset(regs, [r0, r1, r2, r3, r4, r5, r6, r7])
def regs_pc(regs):  return regset(regs, [r0, r1, r2, r3, r4, r5, r6, r7, pc])
def regs_lr(regs):  return regset(regs, [r0, r1, r2, r3, r4, r5, r6, r7, lr])
def regset(regs, ref):
    if type(regs) != set:
        return None
    v = 0
    for r in regs:
        if r not in ref:
            return None
        v |= 1 << ref.index(r)
    return v

def imm3(v):    return immN(v, 3)
def imm4(v):    return immN(v, 4)
def imm5(v):    return immN(v, 5)
def imm5_1(v):  return immN(v, 5, 1)
def imm5_2(v):  return immN(v, 5, 2)
def imm7_2(v):  return immN(v, 7, 2)
def imm8(v):    return immN(v, 8)
def imm8_2(v):  return immN(v, 8, 2)
def imm16(v):   return immN(v, 16)
def immN(v, n, ez=0):
    if type(v) != int or v & ((1 << ez)-1):  return None
    v >>= ez
    if v < 0 or v > (1 << n): return None
    return v

def rlo_rlo(a):    return arg_list(a, (rlo, rlo))
def rlo_imm5(a):   return arg_list(a, (rlo, imm5))
def rlo_imm5_1(a): return arg_list(a, (rlo, imm5_1))
def rlo_imm5_2(a): return arg_list(a, (rlo, imm5_2))
def sp_imm8_2(a):  arg =  arg_list(a, (rsp, imm8_2)); return arg[1] if arg else arg
def arg_list(arg, types):
    if type(arg) != list or len(arg) != len(types):
        return None
    par = [t(a) for t, a in zip(types, arg)]
    if None in par:
        return None
    return par

def label_u8(a):  return label_n(a, False, 8)
def label_s8(a):  return label_n(a, True,  8)
def label_s11(a): return label_n(a, True, 11)
def label_s24(a): return label_n(a, True, 24)
def label_n(lab, code, n):
    # Using labels for code: signed offset, pc and label is aligned %2
    # Using labels for data: unsigned offset, base is align(pc, 4), label must be aligned % 4
    # When this function is called, pc hasn't yet increased to pos after instruction.
    if type(lab) != str:
        return None
    if lab in labels:
        if code:
            imm = labels[lab] - (pc + 4)
            if -(1 << n) <= imm < (1 << n):
                return (imm & ((1 << (n+1)) -1)) >> 1
        else:
            if labels[lab] % 4 != 0:
                raise Exception("Label not aligned mod 4: %s" % lab)
            imm = labels[lab] - ((pc + 2 + 2) // 4 * 4)
            if 0 <= imm < (1 << (n+2)):
                return (imm & ((1 << (n+2)) - 1)) >> 2
        return None
    else:
        missing_labels.append(lab)
        return 0

# ==== Machine code generators ====
# The machine code generators mix the machine code base with the bit patterns from the
# argument converters. No error checking is needed here, since the argument converters
# already have done that.
#
def mc_0__3_6(m, a, b):    return [m | b[1] << 6 | b[0] << 3 | a]
def mc_0_3_6 (m, a, b, c): return [m | c << 6 | b << 3 | a]
def mc_8_0   (m, a, b):    return [m | a << 8 | b]
def mc_8_x_0 (m, a, b, c): return [m | a << 8 | c]
def mc_0_3   (m, a, b):    return [m | b << 3 | a]
def mc_3     (m, a):       return [m | a << 3]
def mc_0     (m, a):       return [m | a]
def mc_x_0   (m, a, b):    return [m | b]
def mc_40_3  (m, a, b):    return [m | 0x80 & a << 4 | b << 3 | 7 & a]
def mc_none  (m):          return [m]
def mc2_0    (m, a):       return [m[0],           m[1] | a]
def mc2_mrs  (m, a, b):    return [m[0],           m[1] | a << 8 | b]
def mc2_msr  (m, a, b):    return [m[0] | b,       m[1] | a]
def mc2_udf  (m, a):       return [m[0] | a >> 12, m[1] | 0x000f & a]
def mc2_imm24(m, a):       return [m[0] | 0x0400 & a >> 13
                                        | 0x03ff & a >> 11,
                                   m[1] | 0x2000 &(a >>  9 ^ a >> 10 ^ 0x2000)
                                        | 0x0800 &(a >> 10 ^ a >> 12 ^ 0x0800)
                                        | 0x07ff & a]

# ==== asm definitions ====
# The asm definitions will drive the generation of asm functions.
# The initial string is the name of the instruction (function).
# Each instruction can have several formats. It will check if the arguments
# can be converted according to the list of argument converters, and in that
# case it machine code will be generated with the machine code base, and
# machine code generator given at the same line.
#
def def_instructions():
    asm_defs = (
        ('adcs',  (( (rlo, rlo),         0x4140, mc_0_3), )),
        ('adds',  (( (rlo, rlo, imm3),   0x1c00, mc_0_3_6),
                   ( (rlo, imm8),        0x3000, mc_8_0),
                   ( (rlo, rlo, rlo),    0x1800, mc_0_3_6), )),
        ('add',   (( (rlh, rlh),         0x4400, mc_40_3),  # this includes add(rdm, sp, rdm) and add(sp, rm)
                   ( (rlo, rsp, imm8_2), 0xa800, mc_8_x_0),
                   ( (rsp, imm7_2),      0xb000, mc_x_0), )),
        ('adr',   (( (rlo, label_u8),    0xa000, mc_8_0), )),
        ('ands',  (( (rlo, rlo),         0x4000, mc_0_3), )),
        ('asrs',  (( (rlo, rlo, imm5),   0x1000, mc_0_3_6),
                   ( (rlo, rlo),         0x4100, mc_0_3_6), )),
        ('b',     (( (cond, label_s8),   0xd000, mc_8_0),
                   ( (label_s11, ),      0xe000, mc_0), )),
        ('bic',   (( (rlo, rlo),         0x4380, mc_0_3), )),
        ('bkpt',  (( (imm8, ),           0xbe00, mc_0), )),
        ('bl',    (( (label_s24, ),     (0xf000, 0xd000), mc2_imm24), )),
        ('blx',   (( (rlh, ),            0x4780, mc_3), )),
        ('bx',    (( (rlh, ),            0x4700, mc_3), )),
        ('cmn',   (( (rlo, rlo),         0x42c0, mc_0_3), )),
        ('cmp',   (( (rlo, imm8),        0x2800, mc_8_0),
                   ( (rlo, rlo),         0x4280, mc_0_3),
                   ( (rlh, rlh),         0x4500, mc_40_3), )),
        ('dmb',   (( (imm4, ),          (0xf3bf, 0x8f50), mc2_0), )),
        ('dsb',   (( (imm4, ),          (0xf3bf, 0x8f40), mc2_0), )),
        ('eors',  (( (rlo, rlo),         0x4040, mc_0_3), )),
        ('isb',   (( (imm4, ),          (0xf3bf, 0x8f60), mc2_0), )),
        ('ldm',   (( (rlo, regs_lo),     0xc800, mc_8_0), )),
        ('ldr',   (( (rlo, rlo_imm5_2),  0x6800, mc_0__3_6),
                   ( (rlo, sp_imm8_2),   0x9800, mc_8_0),
                   ( (rlo, label_u8),    0x4800, mc_8_0),
                   ( (rlo, rlo_rlo),     0x5800, mc_0__3_6), )),
        ('ldrb',  (( (rlo, rlo_imm5),    0x7800, mc_0__3_6),
                   ( (rlo, rlo_rlo),     0x5c00, mc_0__3_6), )),
        ('ldrh',  (( (rlo, rlo_imm5_1),  0x8800, mc_0__3_6),
                   ( (rlo, rlo_rlo),     0x5a00, mc_0__3_6), )),
        ('ldrsb', (( (rlo, rlo_rlo),     0x5600, mc_0__3_6),
                   ( (rlo, rlo_rlo),     0x5700, mc_0__3_6), )),
        ('lsls',  (( (rlo, rlo, imm5),   0x0000, mc_0_3_6),
                   ( (rlo, rlo),         0x4080, mc_0_3), )),
        ('lsrs',  (( (rlo, rlo, imm5),   0x0800, mc_0_3_6),
                   ( (rlo, rlo),         0x40c0, mc_0_3), )),
        ('movs',  (( (rlo, imm8),        0x2000, mc_8_0),
                   ( (rlo, rlo),         0x0000, mc_0_3), )),                    # repeat of lsls #0
        ('mov',   (( (rlh, rlh),         0x4600, mc_40_3), )),
        ('mrs',   (( (rlh, imm8),       (0xf3ef, 0x8000), mc2_mrs), )),
        ('msr',   (( (rlh, imm8),       (0xf380, 0x8800), mc2_msr), )),
        ('muls',  (( (rlo, rlo),         0x4340, mc_0_3), )), # TODO: this is swapped relative v6m manual.  Manual seem strange.
        ('mvn',   (( (rlo, rlo),         0x43c0, mc_0_3), )),
        ('nop',   (( (),                 0xbf00, mc_none), )),
        ('orrs',  (( (rlo, rlo),         0x4300, mc_0_3), )),
        ('pop',   (( (regs_pc, ),        0xbc00, mc_0), )),
        ('push',  (( (regs_lr, ),        0xb400, mc_0), )),
        ('rev',   (( (rlo, rlo),         0xba00, mc_0_3), )),
        ('rev16', (( (rlo, rlo),         0xba40, mc_0_3), )),
        ('revsh', (( (rlo, rlo),         0xbac0, mc_0_3), )),
        ('rors',  (( (rlo, rlo),         0x41c0, mc_0_3), )),
        ('rsbs',  (( (rlo, rlo),         0x4240, mc_0_3), )),
        ('sbcs',  (( (rlo, rlo),         0x4180, mc_0_3), )),
        ('sev',   (( (),                 0xbf40, mc_none), )),
        ('stm',   (( (rlo, regs_lo),     0xc000, mc_8_0), )),
        ('str',   (( (rlo, rlo_imm5_2),  0x6000, mc_0__3_6),
                   ( (rlo, sp_imm8_2),   0x9000, mc_8_0),
                   ( (rlo, rlo_rlo),     0x5000, mc_0__3_6), )),
        ('strb',  (( (rlo, rlo_imm5),    0x7000, mc_0__3_6),
                   ( (rlo, rlo_rlo),     0x5400, mc_0__3_6), )),
        ('strh',  (( (rlo, rlo_imm5_1),  0x8000, mc_0__3_6),
                   ( (rlo, rlo_rlo),     0x5200, mc_0__3_6), )),
        ('subs',  (( (rlo, rlo, imm3),   0x1e00, mc_0_3_6),
                   ( (rlo, imm8),        0x3800, mc_8_0),
                   ( (rlo, rlo, rlo),    0x1a00, mc_0_3_6), )),
        ('sub',   (( (rsp, imm7_2),      0xb080, mc_x_0), )),
        ('svc',   (( (imm8),             0xdf00, mc_0), )),
        ('sxtb',  (( (rlo, rlo),         0xb240, mc_0_3), )),
        ('sxth',  (( (rlo, rlo),         0xb200, mc_0_3), )),
        ('tst',   (( (rlo, rlo),         0x4200, mc_0_3), )),
        ('udf',   (( (imm8, ),           0xde00, mc_0), )),
        ('udf.w', (( (imm16, ),         (0xf7f0, 0xa000), mc2_udf), )),
        ('uxtb',  (( (rlo, rlo),         0xb2c0, mc_0_3), )),
        ('uxth',  (( (rlo, rlo),         0xb280, mc_0_3), )),
        ('wfe',   (( (),                 0xbf20, mc_none), )),
        ('wfi',   (( (),                 0xbf30, mc_none), )),
        ('yield', (( (),                 0xbf10, mc_none), )),
    )
    return { asm_d[0]:asm_instr_gen(asm_d) for asm_d in asm_defs }

