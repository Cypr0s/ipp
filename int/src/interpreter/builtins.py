from interpreter.runtime_model import *
from interpreter.interpreter import Interpreter


class ObjectBuiltin:
    #class methods
    @staticmethod
    def new(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        if receiver.name == "Integer":
            return SolObject("Integer", 0)

        elif receiver.name == "String":
            return SolObject("String", "")

        elif receiver.name == "Nil":
            return interpreter.scope.get_object("nil")

        return SolObject("Object", None)
    
    @staticmethod
    def _from(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        if len(args) == 0:
            return ObjectBuiltin.new(interpreter, receiver, args)

        if receiver.name == "Integer":
            try: 
                val = int(args[0].value)
            except ValueError:
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,  # idk
                    message=f"ERR:Trying to create integer object from `{args[0].value}`",
                )
            return SolObject("Integer", val)

        elif receiver.name == "String":
            val = str(args[0].value)
            return SolObject("String", val)

        elif receiver.name == "Nil":
            return interpreter.scope.get_object("nil")

        return SolObject("Object", None)
    

    # object methods
    @staticmethod
    def identical_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        if receiver is args[0]:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def identical_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        #todo
        pass

    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject("String", "")

    @staticmethod
    def is_number(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_block(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_nil(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        return interpreter.scope.get_object("false")


class NilBuiltin:
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject("String", "nil")


class IntergerBuiltin:
    @staticmethod
    def equal_to(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        if receiver.value == args[0].value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")
    
    @staticmethod
    def greater_that(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        if receiver.value > args[0].value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")
    
    @staticmethod
    def plus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        val = receiver.value + args[0].value
        return SolObject("Integer", val)
    
    @staticmethod
    def plus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        val = receiver.value + args[0].value
        return SolObject("Integer", val)
    
    @staticmethod
    def minus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        val = receiver.value - args[0].value
        return SolObject("Integer", val)
    
    @staticmethod
    def multiply_by(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        val = receiver.value * args[0].value
        return SolObject("Integer", val)
    
    @staticmethod
    def div_by(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        try:
            val = receiver.value / args[0].value
        except ZeroDivisionError:
             raise InterpreterError(
                error_code=ErrorCode.INT_OTHER,  # idk
                message=f"Zero division error",
            )

        return SolObject("Integer", val)
    
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject("String", str(receiver.value))
    
    @staticmethod
    def as_integer(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return receiver
    
    @staticmethod
    def times_repeat(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        block:SolObject = args[0]
        value_method: SolMethod = block.cls.get_method("value:") 
        return_obj: SolObject = interpreter.scope.get_object("nil")
        if(receiver.value > 0):
            for i in range(1, receiver.value + 1):
                argument_obj = SolObject("Integer", i)
                return_obj = interpreter.send_message(block, value_method, [argument_obj])
        return return_obj
    

    
class StringBuiltin:
    # String class method
    @staticmethod
    def read(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        line = interpreter.stream.readline()
        line.rsplit('\n')
        return SolObject("String", line)
    
    #object methods
    @staticmethod
    def _print(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        print(receiver.value)
        return receiver
    
    @staticmethod
    def equal_to(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        if receiver.value == args[0].value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")
    
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return receiver
    
    @staticmethod
    def as_integer(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        try: 
            val = int(receiver.value)
        except ValueError:
            return interpreter.scope.get_object("nil")

        return SolObject("Integer", val)
    
    @staticmethod
    def concatenate_with(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        is_string: bool = args[0].cls.check_parent("String")
        return_obj: SolObject = interpreter.scope.get_object("nil")
        if(is_string):
            return_obj = SolObject("String", receiver.value + args[0].value)

        return return_obj
    
    @staticmethod
    def concatenate_with(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        pass