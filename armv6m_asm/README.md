
# ARMv6-M assembler

This is an assembler for micropython. It can be used to add inline assembler to your python project. It implements all instructions in ARMv6-M, and does it in a way that makes it possible to use python as a preprocessor. 

The syntax is a pythonification of ARM UAL (Unified Assembler Language), with some changes.
We start with an example, pointing out some differences to ASM UAL or @micropython.arm_thumb:

```
import armv6m_asm

@armv6m_asm.asm_thumb
@a6a.asm_thumb
def sum():                 # No args, since the decorator can't see them. 
                           # The launcher will give arguments as argc/argv in r6/r7 instead.
    movs(r0, 0)            # Sets flags, so it is 'movs'
    movs(r1, 0)
    b('loop_check')        # Labels are strings.
    label('again')
    ldr(r2, [r7, r1])      # r2 = mem_read32(r7 + r1)
    adds(r0, r0, r2)
    adds(r1, 4)
    label('loop_check')
    subs(r6, 1)
    b(ge, 'again')         # Condition is an argument, not part of the instruction (not 'bge')
```

All assembler intructions are written as python functions with small letters. 
There is no support for the .n and .w field (except for the udf.w instruction).
The trailing 's' on instructions that updates flags is needed. (This is a change from @micropython.asm_thumb.) 
Conditions are written as an argument, not attached to the instruction. (This is a change fom ARM UAL.)
There are no implicit or redundant register arguments. Ie, the assembler must have as many arguments as is coded in the machine code.

push, pop, ldm, and stm  uses the python set to give a register list,
ldm and stm is do not use the ! character. (When the pointer register isn't updated.)

## Assembler directives

The assembler directives includes the same as with @micropython.asm_thumb.

`align(4)`

Moves PC forward to nearest mod 4 address. The skipped bytes are filled with zerq.

`data(size, data0, data1, ...)`

Each data item is size bytes. The start is aligned mod size. Each data statement always ends on a mod 2 address. Ths means that a data directive with an odd number of bytes (size==1), will have the bytes packed, but an extra 0 is added at the end.

`label('my_label')`

Labels are strings. The label value is the current PC value. 

Note that this means that a label before a `data(4, ...)` directive might not point to the upcomming data, since it might move PC in an alignment. When PC might not be aligned mod 4, it's best to do:
```
align(4)
label('my_label')
data(4, ...)
```
There is also a new directive:

`argcount(argc)`

This stores argc in the output, so that the launcher can check the argument count.

## Preprocessor macro

`args_to_regs(n)`

This inserts assembler instructions to unpack the r6=argc r7=argv format to the more common format with arguments in r0, r1, ...

## Python preprocessor

The internal working of the assembling process is done by calling the decorated function. The assembeler functions are regular python functions that will emit the machine code that represent the instruction. This is important to know to understand how python can be used for preprocessing. It is possible to mix the assembler functions with regular python code to calculate constants, and even to control program flow to select what assembler instructions to emit. But note that this code must only depend on things known at assembly time.

The register tokens (r0, r1, ...) are actually variables with large integers. They are too big to be misstaken for a 32 bit integer. But since they are consecutive integers, it's possible to do tricks like writing r0+i to get register #i.


# Calling the assembled function

```
from arm_native import run_native
run_native(sum, 2, 3, 4)      # Simple usage: Multiple integers

from array import array
a = array('I', (1, 2, 3, 4))
run_native(sum, a)            # Advanced usage: one array
```

The simplest way to call the function is the first one. But the second one has the advantage that the assembler can update the array to get multiple bidirectional arguments.

