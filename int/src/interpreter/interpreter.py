#TODO testing
"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Kristian Luptak
"""

import logging
from pathlib import Path
from typing import TextIO

from lxml import etree
from lxml.etree import ParseError
from pydantic import ValidationError

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Block, ClassDef, Program, Expr, Literal, Send, Assign, Var

logger = logging.getLogger(__name__)


class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
        self.current_program: Program | None = None
        self.classes: dict[str, SolClass] = {}
        self.scope: Scope = None
        self.stream: TextIO = None

    def load_program(self, source_file_path: Path) -> None:
        """
        Reads the source SOL-XML file and stores it as the target program for this interpreter.
        If any program was previously loaded, it is replaced by the new one.

        IPP: If you wish to run static checks on the program before execution, this is a good place
             to call them from.
        """
        logger.info("Opening source file: %s", source_file_path)
        try:
            xml_tree = etree.parse(source_file_path)
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        try:
            self.current_program = Program.from_xml_tree(xml_tree.getroot())  # type: ignore
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e

        self.static_analysis()
    
    def static_analysis(self) -> None:
        """
        Static semantic analysis for error codes 31, 34, 35
        """
        #main and run check - err code 31
        main: bool = False
        for cls in self.current_program.classes:
            if cls.name == "Main":
                main = True
                run: bool = False
                for method in cls.methods:
                    if method.selector == "run":
                        run = True
                if not run:
                    # error code 31
                    raise InterpreterError(
                        error_code=ErrorCode.SEM_MAIN, message="Main class has no method named `run`"
                    )
        if not main:
            # error code 31
            raise InterpreterError(
                error_code=ErrorCode.SEM_MAIN, message="Main class missing"
            )

        # check classes
        classes: list[str] = []
        for cls in self.current_program.classes:
            # check for class redefinition
            if cls.name in classes:
                # error code 35
                raise InterpreterError(
                    error_code=ErrorCode.SEM_ERROR, message=f"Redefinition of class"
                )
            
            methods: list[str] = []
            for method in cls.methods:
                if method.selector in methods:
                    # error code 35
                    raise InterpreterError(
                        error_code=ErrorCode.SEM_ERROR, message=f"Redefinition of method"
                    )
                # error code 33
                dd_count: int = method.selector.count(":")
                if dd_count != method.block.arity:
                    raise InterpreterError(
                        error_code=ErrorCode.SEM_ARITY,
                        message=f"Block arity doesnt match selector",
                    )

                # check for redefinition of parameter
                params: list[str] = []
                for param in method.block.parameters:
                    if param.name in params:
                        # error code 35
                        raise InterpreterError(
                            error_code=ErrorCode.SEM_ERROR,
                            message=f"same parameters in block",
                        )
                    params.append(param.name)

                # check for invalid assign targets
                for assign in method.block.assigns:
                    if assign.target.name in params:
                        # error code 34
                        raise InterpreterError(
                            error_code=ErrorCode.SEM_COLLISION,
                            message=f"Trying to assign into parameter",
                        )


                methods.append(method.selector)

            classes.append(cls.name)
    
    def execute(self, input_io: TextIO) -> None:
        """
        Executes the currently loaded program, using the provided input stream as standard input.
        """
        logger.info("Executing program")

        # create dict of userclasses,
        self.load_classes()
        logger.info("Loaded user and buildin classes.")
        # add user functions and methods

        if "Main" not in self.classes:
            raise InterpreterError(error_code=ErrorCode.SEM_MAIN, message="Main class missing")

        # create global scope with null, true, false objects
        self.scope = Scope(None)
        true_obj = SolObject(self.classes["True"], True)
        false_obj = SolObject(self.classes["False"], False)
        nil_obj = SolObject(self.classes["Nil"], None)

        self.scope.set_object("nil", nil_obj)
        self.scope.set_object("true", true_obj)
        self.scope.set_object("false", false_obj)

        logger.info("created global objects.")
        # create main object
        main_obj: SolObject = SolObject(self.classes["Main"], None)

        logger.info("created main object and found method run")
        self.stream = input_io
        # call method run
        self.send_message(main_obj, "run", [], "default_reference")

    @staticmethod
    def check_arity(target: SolMethod, arg_count: int)-> None:
        if(target.arity != arg_count):
            raise InterpreterError(
                error_code=ErrorCode.SEM_ARITY,
                message=f"Invalid arity in method call",
            )

    def load_classes(self):
        "Loads both buildin and classes into global class dict for easy lookup"
        # builtins
        self.create_builtins()

        # user classes
        for cls in self.current_program.classes:
            if cls.name not in self.classes:
                # recursively creates classes
                self.create_class(cls)

    def create_class(self, cls: ClassDef) -> None:
        """Creates class and links to parent, if parent doesnt exist recursively creates it"""
        if cls.name in self.classes:
            return

        # recursively create parent-s
        if cls.parent not in self.classes:
            for cls_parent in self.current_program.classes:
                if cls.parent == cls_parent.name:
                    self.create_class(cls_parent)

        # create methods dict
        parent: SolClass = self.classes[cls.parent]
        methods: dict[str, SolMethod] = {}
        for method in cls.methods:
            methods[method.selector] = SolMethod(
                method.selector, False, method.block, method.block.arity
            )

        # create classs
        self.classes[cls.name] = SolClass(cls.name, parent, methods)

    def create_builtins(self) -> None:
        #create buildin classes 
        object_cls = SolClass("Object", None, {})
        integer_cls = SolClass("Integer", object_cls, {})
        string_cls = SolClass("String", object_cls, {})
        true_cls = SolClass("True", object_cls, {})
        false_cls = SolClass("False", object_cls, {})
        nil_cls = SolClass("Nil", object_cls, {})
        block_cls = SolClass("Block", object_cls, {})

        #link methods

        # object methods

        object_from = SolMethod("from:", True, ObjectBuiltin._from, 1)
        object_new = SolMethod("new", True, ObjectBuiltin.new, 0)
        object_identical_to = SolMethod("identicalTo:", True, ObjectBuiltin.identical_to, 1)
        object_equal_to = SolMethod("equalTo:", True, ObjectBuiltin.equal_to, 1)
        object_as_string = SolMethod("asString", True, ObjectBuiltin.as_string, 0)
        object_is_number = SolMethod("isNumber", True, ObjectBuiltin.is_number, 0)
        object_is_string = SolMethod("isString", True, ObjectBuiltin.is_string, 0)
        object_is_block =  SolMethod("isBlock", True, ObjectBuiltin.is_block, 0)
        object_is_nil =   SolMethod("isNil", True, ObjectBuiltin.is_nil, 0)
        object_is_boolean =   SolMethod("isBoolean", True, ObjectBuiltin.is_boolean, 0)
        
        object_cls.class_methods["from:"] = object_from
        object_cls.class_methods["new"] = object_new
        object_cls.methods["identicalTo:"] = object_identical_to
        object_cls.methods["equalTo:"] = object_equal_to
        object_cls.methods["asString"] = object_as_string
        object_cls.methods["isNumber"] = object_is_number
        object_cls.methods["isString"] = object_is_string
        object_cls.methods["isBlock"] = object_is_block
        object_cls.methods["isNil"] = object_is_nil
        object_cls.methods["isBoolean"] = object_is_boolean

        # nil methods

        nil_as_string = SolMethod("asString", True, NilBuiltin.as_string, 0)
        nil_is_nil = SolMethod("isNil", True, NilBuiltin.is_nil, 0)

        nil_cls.methods["asString"] = nil_as_string
        nil_cls.methods["isNil"] = nil_is_nil

        # integer methods

        integer_equal_to = SolMethod("equalTo:", True, IntegerBuiltin.equal_to, 1)
        integer_greater_than = SolMethod("greaterThan:", True, IntegerBuiltin.greater_than, 1)
        integer_plus = SolMethod("plus:", True, IntegerBuiltin.plus, 1)
        integer_minus = SolMethod("minus:", True, IntegerBuiltin.minus, 1)
        integer_multiply_by = SolMethod("multiplyBy:", True, IntegerBuiltin.multiply_by, 1)
        integer_div_by = SolMethod("divBy:", True, IntegerBuiltin.div_by, 1)
        integer_as_string = SolMethod("asString", True, IntegerBuiltin.as_string, 0)
        integer_as_integer = SolMethod("asInteger", True, IntegerBuiltin.as_integer, 0)
        integer_times_repeat = SolMethod("timesRepeat:", True, IntegerBuiltin.times_repeat, 1)
        integer_is_number = SolMethod("isNumber", True, IntegerBuiltin.is_number, 0)

        integer_cls.methods["equalTo:"] = integer_equal_to
        integer_cls.methods["greaterThan:"] = integer_greater_than
        integer_cls.methods["plus:"] = integer_plus
        integer_cls.methods["minus:"] = integer_minus
        integer_cls.methods["multiplyBy:"] = integer_multiply_by
        integer_cls.methods["divBy:"] = integer_div_by
        integer_cls.methods["asString"] = integer_as_string
        integer_cls.methods["asInteger"] = integer_as_integer
        integer_cls.methods["timesRepeat:"] = integer_times_repeat
        integer_cls.methods["isNumber"] = integer_is_number

        # string methods

        string_read = SolMethod("read", True, StringBuiltin.read, 0)
        string_print = SolMethod("print", True, StringBuiltin._print, 0)
        string_equal_to = SolMethod("equalTo:", True, StringBuiltin.equal_to, 1)
        string_as_string = SolMethod("asString", True, StringBuiltin.as_string, 0)
        string_as_integer = SolMethod("asInteger", True, StringBuiltin.as_integer, 0)
        string_concat = SolMethod("concatenateWith:", True, StringBuiltin.concatenate_with, 1)
        string_substring = SolMethod("startsWith:endsBefore:", True, StringBuiltin.starts_with_ends_before, 2)
        string_length = SolMethod("length", True, StringBuiltin.length, 0)
        string_is_string = SolMethod("isString", True, StringBuiltin.is_string, 0)

        string_cls.class_methods["read"] = string_read
        string_cls.methods["print"] = string_print
        string_cls.methods["equalTo:"] = string_equal_to
        string_cls.methods["asString"] = string_as_string
        string_cls.methods["asInteger"] = string_as_integer
        string_cls.methods["concatenateWith:"] = string_concat
        string_cls.methods["startsWith:endsBefore:"] = string_substring
        string_cls.methods["length"] = string_length
        string_cls.methods["isString"] = string_is_string

        # block

        block_while_true = SolMethod("whileTrue:", True, BlockBuiltin.while_true, 1)
        block_is_block = SolMethod("isBlock", True, BlockBuiltin.is_block, 0)
    
        block_cls.methods["whileTrue:"] = block_while_true
        block_cls.methods["isBlock"] = block_is_block

        # true

        true_as_string = SolMethod("asString", True, TrueBuiltin.as_string, 0)
        true_not = SolMethod("not", True, TrueBuiltin._not, 0)
        true_and = SolMethod("and:", True, TrueBuiltin._and, 1)
        true_or = SolMethod("or:", True, TrueBuiltin._or, 1)
        true_if = SolMethod("ifTrue:ifFalse:", True, TrueBuiltin.if_true_if_false, 2)
        true_is_bool = SolMethod("isBoolean", True, TrueBuiltin.is_boolean, 0)

        true_cls.methods["asString"] = true_as_string
        true_cls.methods["not"] = true_not
        true_cls.methods["and:"] = true_and
        true_cls.methods["or:"] = true_or
        true_cls.methods["ifTrue:ifFalse:"] = true_if
        true_cls.methods["isBoolean"] = true_is_bool

        #false 

        false_as_string = SolMethod("asString", True, FalseBuiltin.as_string, 0)
        false_not = SolMethod("not", True, FalseBuiltin._not, 0)
        false_and = SolMethod("and:", True, FalseBuiltin._and, 1)
        false_or = SolMethod("or:", True, FalseBuiltin._or, 1)
        false_if = SolMethod("ifTrue:ifFalse:", True, FalseBuiltin.if_true_if_false, 2)
        false_is_bool = SolMethod("isBoolean", True, FalseBuiltin.is_boolean, 0)

        false_cls.methods["asString"] = false_as_string
        false_cls.methods["not"] = false_not
        false_cls.methods["and:"] = false_and
        false_cls.methods["or:"] = false_or
        false_cls.methods["ifTrue:ifFalse:"] = false_if
        false_cls.methods["isBoolean"] = false_is_bool


        #link classes
        self.classes["Object"] = object_cls
        self.classes["Integer"] = integer_cls
        self.classes["String"] = string_cls
        self.classes["True"] = true_cls
        self.classes["False"] = false_cls
        self.classes["Nil"] = nil_cls
        self.classes["Block"] = block_cls

    def send_message(
        self, receiver: SolObject | SolClass, selector: str, arguments: list[SolObject] | None = [], send_type: str = "default_reference"
    ) -> SolObject:
        # builtin method check arity and exec
        arg_count: int = len(arguments)

        #class method
        if(isinstance(receiver, SolClass)):
            logger.info(f"sending message:{receiver.name} {selector}, {arguments}")
            method: SolMethod = receiver.get_class_method(selector)
            return method.function(self, receiver, arguments)
            
        #block invocation
        method: SolMethod = receiver.instance_method.get(selector)
        if method is not None:
            self.check_arity(method, arg_count)
            return self.method_call(receiver, method, arguments)

        # 0 args
        if arg_count == 0:
            # self and basic reference
            if send_type == "default_reference" or send_type == "self":
                method: SolMethod = receiver.cls.get_method(selector)
            # super
            else:
                method: SolMethod = receiver.cls.parent.get_method(selector)
            
            if method is None:
                if selector not in receiver.instance_attributes:
                    raise InterpreterError(
                        error_code=ErrorCode.INT_DNU,
                        message=f"Class `{receiver.cls.name}` has no method `{selector}`",
                    )
                return receiver.instance_attributes[selector]

            self.check_arity(method, arg_count)

            logger.info(f"sending message:{receiver.cls.name} {selector}, {arguments}")
            return self.method_call(receiver, method, arguments)
        # 1 arg
        elif arg_count == 1:
            if send_type == "default_reference" or send_type == "self":
                method: SolMethod = receiver.cls.get_method(selector)
            else:
                method: SolMethod = receiver.cls.parent.get_method(selector)

            if method is None:
                instance_attr_name: str = selector[:-1]
                if send_type == "default_reference" or send_type == "self":
                    method: SolMethod = receiver.cls.get_method(instance_attr_name)
                else:
                    method: SolMethod = receiver.cls.parent.get_method(instance_attr_name)

                if method is None:
                    receiver.instance_attributes[instance_attr_name] = arguments[0]
                    return receiver

                raise InterpreterError(
                    error_code=ErrorCode.INT_INST_ATTR,
                    message=f"Trying to create instance attr with the same name as method",
                )
            # method found exec it
            self.check_arity(method, arg_count)

            logger.info(f"sending message:{receiver.cls.name} {selector}, {arguments}")
            return self.method_call(receiver, method, arguments)
        # 2 or more args
        else:
            # self and basic reference
            if send_type == "default_reference" or send_type == "self":
                method: SolMethod = receiver.cls.get_method(selector)
            # super
            else:
                method: SolMethod = receiver.cls.parent.get_method(selector)

            if method is None:
                raise InterpreterError(
                    error_code=ErrorCode.INT_DNU,
                    message=f"Class `{receiver.cls.name}` has no method `{selector}`",
                )

            self.check_arity(method, arg_count)

            logger.info(f"sending message:{receiver.cls.name} {selector}, {arguments}")
            return self.method_call(receiver, method, arguments)
       
    def method_call(self, receiver: SolObject, method: SolMethod, arguments: list[SolObject]) -> SolObject:
        #builtin method
        if method.is_builtin:
            return method.function(self, receiver, arguments)

        # create scope
        if receiver.closure_scope is not None:
            new_scope: Scope = Scope(receiver.closure_scope)
        else:
            new_scope: Scope = Scope(self.scope)

        parent_scope: Scope = self.scope
        self.scope = new_scope
        
        #set parameters into scope
        arg_count: int = len(arguments)
        parameters: list[str] =[]
        for i in range (0, arg_count):
            parameters.append(method.function.parameters[i].name)
            self.scope.set_object(parameters[i], arguments[i])

        # add self into scope
        
        self.scope.set_object("self", receiver)

        #add super into scope
        self.scope.set_object("super", receiver)

        #exec block
        return_value: SolObject = self.execute_block(method.function, parameters)

        self.scope = parent_scope
        return return_value

    # execute block
    def execute_block(self, assigns: list[Assign], parameters: list[str]) -> SolObject:
        return_obj: SolObject = self.scope.get_object("nil")
        logger.info(f"Executing block")

        for assign in assigns:
            target = assign.target
            logger.info(f"Executing assign, target: {target}")
            value = self.eval_expr(assign.expr)
            
            if target.name != "_":

                self.scope.set_object(target.name, value)

            return_obj = value

        return return_obj

    # eval all expressions
    def eval_expr(self, expr: Expr) -> SolObject:
        
        if expr.send is not None:
            return self.handle_send(expr.send)

        elif expr.block is not None:
            cnt = expr.block.arity
            if cnt == 0:
                selector = "value"
            else:
                selector = "value:" * cnt

            method = SolMethod(selector, False, expr.block, cnt)
            block_obj = SolObject(self.classes["Block"], Block)
            block_obj.closure_scope = self.scope # save closure scope
            block_obj.instance_method[selector] = method # save method
            return block_obj

        elif expr.literal is not None:
            return self.handle_literal(expr.literal)

        elif expr.var is not None:
            return self.handle_var(expr.var)

        raise InterpreterError(error_code=ErrorCode.SEM_UNDEF, message="Invalid expression type")

    # eval var
    def handle_var(self, var: Var) -> SolObject:
        if var.name == "self":
            return self.scope.get_object("self")

        elif var.name == "super":
            return self.scope.get_object("super")

        elif var.name == "true":
            return self.scope.get_object("true")

        elif var.name == "false":
            return self.scope.get_object("false")

        elif var.name == "nil":
            return self.scope.get_object("nil")

        else:
            obj = self.scope.get_object(var.name)
            if obj is None:
                # check for error 32
                raise InterpreterError(
                    error_code=ErrorCode.SEM_UNDEF, message=f"No object with `{var.name}` exists"
                )

            return obj

    def handle_send(self, send: Send) -> SolObject:
        # eval obj receiver
        receiver_obj: SolObject | SolClass = self.eval_expr(send.receiver)

        send_type: str = "default_reference"


        if send.receiver.var is not None and send.receiver.var.name == "super":
            send_type = "super"
        elif send.receiver.var is not None and send.receiver.var.name == "self":
            send_type = "self"

        send_args: list[SolObject] = []
        for arg in send.args:
            send_args.append(self.eval_expr(arg))

        # actually send msg
        return self.send_message(receiver_obj, send.selector, send_args, send_type)

    # handle literals
    def handle_literal(self, literal: Literal) -> SolObject | SolClass:
        if literal.class_id == "String":
            return SolObject(self.classes["String"], literal.value)

        elif literal.class_id == "Integer":
            try:
                val: int = int(literal.value)
            except ValueError as e:
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,  # idk
                    message=f"ERR:Trying to create integer object from `{literal.value}`",
                )
            return SolObject(self.classes["Integer"], val)

        elif literal.class_id == "Block":
            cnt = literal.value
            if cnt == 0:
                selector = "value"
            else:
                selector = "value:" * cnt

            method = SolMethod(selector, False, literal.value, cnt)
            block_obj = SolObject(self.classes["Block"], Block)
            block_obj.instance_method[selector] = method
            return block_obj

        elif literal.class_id == "Nil":
            return self.scope.get_object("nil")

        elif literal.class_id == "True":
            return self.scope.get_object("true")

        elif literal.class_id == "False":
            return self.scope.get_object("false")

        elif literal.class_id == "class":
            if literal.value in self.classes:
                return self.classes[literal.value]

            # error code 32
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF,
                message=f"Calling undefined literal class `{literal.class_id}`",
            )

class ObjectBuiltin:
    #class methods
    @staticmethod
    def new(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        if receiver.name == "Integer":
            return SolObject(interpreter.classes["Integer"], 0)

        elif receiver.name == "String":
            return SolObject(interpreter.classes["String"], "")

        elif receiver.name == "Nil":
            return interpreter.scope.get_object("nil")

        elif receiver.name == "Block":
            empty_block = Block(params=[], assigns=[])
            empty_method = SolMethod("value", False, empty_block, 0)
            block_obj = SolObject(interpreter.classes["Block"], None)
            block_obj.instance_method["value"] =empty_method

            return block_obj

        return SolObject(receiver, None)
    
    @staticmethod
    def _from(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        if len(args) == 0:
            return ObjectBuiltin.new(interpreter, receiver, args)
    
        from_object: SolObject = args[0]

        # handle true false or nil
        if receiver.name == "True":
            return interpreter.scope.get_object("true")
        
        if receiver.name == "False":
            return interpreter.scope.get_object("false")
        
        if receiver.name == "Nil":
            return interpreter.scope.get_object("nil")

        # copy instance attrs
        instance_attrs: dict[str, SolObject] = {}

        for instance_attr_name, instance_attr_value in from_object.instance_attributes.items():
            instance_attrs[instance_attr_name] = instance_attr_value

        intern_attr: int | str | None = None

        # copy intern attr
        receiver_intern_attr_cls: SolClass = receiver.get_intern_attr_cls()

        if receiver_intern_attr_cls is not None:
            from_attr_cls: SolClass = args[0].cls.get_intern_attr_cls()

            if receiver_intern_attr_cls is not from_attr_cls:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message=f"Trying to create {receiver.name} from: {args[0].cls.name}, internal attributes dont match",
                )

            intern_attr = from_object.intern_value
        
        new_obj = SolObject(receiver, intern_attr)
        new_obj.instance_attributes =instance_attrs
        return new_obj
    

    # object methods
    @staticmethod
    def identical_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        target: SolObject = args[0]
        if receiver is target:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def equal_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:

        target: SolObject = args[0]

        if receiver.cls.get_intern_attr_cls() is None:
            return ObjectBuiltin.identical_to(interpreter, receiver, [target])

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject(interpreter.classes["String"], "")

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
        return SolObject(interpreter.classes["String"], "nil")

    @staticmethod
    def is_nil(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("true")

class IntegerBuiltin:
    @staticmethod
    def equal_to(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        target: SolObject = args[0]
        if not target.cls.is_subclass("Integer"):
            return interpreter.scope.get_object("false")

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")
    
    @staticmethod
    def greater_than(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        
        target: SolObject = args[0]

        if not target.cls.is_subclass("Integer"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`greaterThan: {target.cls.name}` is not class/subclass of Integer",
            )

        if receiver.intern_value > args[0].intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")
    
    @staticmethod
    def plus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:

        target: SolObject = args[0]

        if not target.cls.is_subclass("Integer"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`plus: {target.cls.name}` is not class/subclass of Integer",
            )

        val = receiver.intern_value + target.intern_value
        return SolObject(interpreter.classes["Integer"], val)
    
    @staticmethod
    def minus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:

        target: SolObject = args[0]

        if not target.cls.is_subclass("Integer"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`minus: {target.cls.name}` is not class/subclass of Integer",
            )

        val = receiver.intern_value - target.intern_value
        return SolObject(interpreter.classes["Integer"], val)
    
    @staticmethod
    def multiply_by(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        target: SolObject = args[0]

        if not target.cls.is_subclass("Integer"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`multiplyBy: {target.cls.name}` is not class/subclass of Integer",
            )

        val = receiver.intern_value * target.intern_value
        return SolObject(interpreter.classes["Integer"], val)
    
    @staticmethod
    def div_by(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:

        target: SolObject = args[0]

        if not target.cls.is_subclass("Integer"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`multiplyBy: {target.cls.name}` is not class/subclass of Integer",
            )

        try:
            val = receiver.intern_value // target.intern_value
        except ZeroDivisionError:
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"Zero division error",
            )

        return SolObject(interpreter.classes["Integer"], val)
    
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject(interpreter.classes["String"], str(receiver.intern_value))
    
    @staticmethod
    def as_integer(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return receiver
    
    @staticmethod
    def times_repeat(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        block:SolObject = args[0]
        return_obj: SolObject = interpreter.scope.get_object("nil")

        if(receiver.intern_value > 0):
            for i in range(1, receiver.intern_value + 1):
                argument_obj = SolObject(interpreter.classes["Integer"], i)
                return_obj = interpreter.send_message(block, "value:", [argument_obj], "default_reference")

        return return_obj
    
    @staticmethod
    def is_number(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        return interpreter.scope.get_object("true")
    

class StringBuiltin:
    # String class method
    @staticmethod
    def read(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        line = interpreter.stream.readline()
        line = line.rstrip('\n')
        return SolObject(interpreter.classes["String"], line)
    
    #object methods
    @staticmethod
    def _print(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        print(receiver.intern_value, end="")
        return receiver
    
    @staticmethod
    def equal_to(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        
        target: SolObject = args[0]

        if not target.cls.is_subclass("String"):
            return interpreter.scope.get_object("false")

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")
    
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return receiver
    
    @staticmethod
    def as_integer(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        try: 
            val = int(receiver.intern_value)
            return SolObject(interpreter.classes["Integer"], val)
        except ValueError:
            return interpreter.scope.get_object("nil")
    
    @staticmethod
    def concatenate_with(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        target: SolObject = args[0]

        if not target.cls.is_subclass("String"):
            return interpreter.scope.get_object("nil")
        
        return SolObject(interpreter.classes["String"], receiver.intern_value + target.intern_value)
    
    @staticmethod
    def starts_with_ends_before(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:

    
        starts_with: SolObject = args[0]
        ends_before: SolObject = args[1]

        if not starts_with.cls.is_subclass("Integer"):
            return interpreter.scope.get_object("nil")

        if not ends_before.cls.is_subclass("Integer"):
            return interpreter.scope.get_object("nil")
    
        if starts_with.intern_value <= 0 or ends_before.intern_value <= 0:
            return interpreter.scope.get_object("nil")
        
        if ends_before.intern_value - starts_with.intern_value <= 0:
            return SolObject(interpreter.classes["String"], "")
        val: str = receiver.intern_value[starts_with.intern_value - 1 : ends_before.intern_value - 1]
        return SolObject(interpreter.classes["String"], val)

    @staticmethod
    def length(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject(interpreter.classes["Integer"], len(receiver.intern_value))

    @staticmethod
    def is_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("true")
    

class BlockBuiltin:
    @staticmethod
    def while_true(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:

        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`while_true: `{block.cls.name}` is not class/subclass of Block",
            )
        return_val: SolObject = interpreter.scope.get_object("nil")

        while interpreter.send_message(receiver,"value",[], "default_reference") is interpreter.scope.get_object("true"):
            #eval condition
            return_val = interpreter.send_message(block, "value", [], "default_reference")
        
        return return_val    

    @staticmethod
    def is_block(interpreter, receiver, args):
        return interpreter.scope.get_object("true")

class TrueBuiltin:
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject(interpreter.classes["String"], "true")

    @staticmethod
    def _not(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("false")

    @staticmethod
    def _and(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`and: `{block.cls.name}` is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference")

    @staticmethod
    def _or(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("true")

    @staticmethod
    def if_true_if_false(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`ifTrue:ifFalse: `{block.cls.name}` is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference")

    @staticmethod
    def is_boolean(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("true")


class FalseBuiltin:
    @staticmethod
    def as_string(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return SolObject(interpreter.classes["String"], "false")

    @staticmethod
    def _not(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("true")

    @staticmethod
    def _and(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("false")

    @staticmethod
    def _or(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`or: `{block.cls.name}` is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference")
    
    @staticmethod
    def if_true_if_false(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        block: SolObject = args[1]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`ifTrue:ifFalse: `{block.cls.name}` is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference")

    @staticmethod
    def is_boolean(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        return interpreter.scope.get_object("true") 


class SolClass:
    """
    Class represents runtime classes of SOL26
    """

    def __init__(
        self, name: str, super_class: SolClass | None, methods: dict[str, SolMethod]
    ) -> None:
        self.name: str = name
        self.parent: SolClass = super_class
        self.methods: dict[str, SolMethod] = methods
        self.class_methods: dict[str, SolMethod] = {}

    def get_method(self, selector: str) -> SolMethod | None:
        if selector in self.methods:
            return self.methods[selector]

        if self.parent is not None:
            return self.parent.get_method(selector)

        if selector == "run":
            raise InterpreterError(
                error_code=ErrorCode.SEM_MAIN, message="Main class has no method named `run`"
            )
        return None

    def get_class_method(self, selector: str) -> SolMethod | None:
        if selector in self.class_methods:
            return self.class_methods[selector]

        if self.parent is not None:
            return self.parent.get_class_method(selector)

        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"Class `{self.name}` has no class method `{selector}`",
        )

    def get_intern_attr_cls(self) -> SolClass | None:
        if self.name == "String" or self.name == "Integer":
            return self
        
        if self.parent is not None:
            return self.parent.get_intern_attr_cls()
        
        return None
    
    def is_subclass(self, cls: str) -> bool:
        if self.name == cls:
            return True

        if self.parent is None:
            return False
        
        return self.parent.is_subclass(cls)

class SolObject:
    def __init__(self, cls: SolClass, intern_value: int | str | None) -> None:
        self.cls: SolClass = cls
        self.intern_value: int | str | None = intern_value
        self.instance_attributes: dict[str, SolObject] = {} #uder defined
        self.instance_method: dict[str, SolMethod] = {} # block value method
        self.closure_scope: Scope | None = None # block closure scope


    

class SolMethod:
    def __init__(
        self, selector: str, is_builtin: bool, func: "callable | Block", arity: int
    ) -> None:
        self.selector: str = selector
        self.is_builtin: bool = is_builtin
        self.function: "callable | Block" = func
        self.arity: int = arity


class Scope:
    """
    Class for creating scopes and finding variables in them, handling everything related to scope
    """

    def __init__(self, parent_scope: Scope | None = None) -> None:
        self.parent_scope = parent_scope
        self.objects: dict[str, SolObject] = {}

    def get_object(self, object_name: str) -> SolObject | None:
        if object_name in self.objects:
            return self.objects[object_name]

        if self.parent_scope != None:
            return self.parent_scope.get_object(object_name)

        return None

    def set_object(self, object_name: str, object: SolObject) -> None:
        self.objects[object_name] = object
