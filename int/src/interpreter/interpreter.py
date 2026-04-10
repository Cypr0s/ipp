"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Kristian Luptak <xluptak00@stud.fit.vut.cz>
"""

import logging
from pathlib import Path
from typing import TextIO

from lxml import etree
from lxml.etree import ParseError
from pydantic import ValidationError

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import (
    Assign,
    Block,
    ClassDef,
    Expr,
    Literal,
    Program,
    Send,
    Var,
)
from interpreter.runtime_model import Scope, SolClass, SolMethod, SolObject
from interpreter.static_analysis import StaticAnalysis

logger = logging.getLogger(__name__)


class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
        self.current_program: Program | None = None
        self.classes: dict[str, SolClass] = {}
        self.scope: Scope = Scope(None)
        self.stream: TextIO

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

        analyzer: StaticAnalysis = StaticAnalysis()
        analyzer.static_analysis(self.current_program)

    def execute(self, input_io: TextIO) -> None:
        """
        Executes the currently loaded program, using the provided input stream as standard input.
        """
        logger.info("Executing program")

        # create dict of userclasses,
        self.load_classes()
        logger.info("Loaded user and buildin classes.")
        # add user functions and methods

        # create global scope with null, true, false objects
        true_obj = SolObject(self.classes["True"], None)
        false_obj = SolObject(self.classes["False"], None)
        nil_obj = SolObject(self.classes["Nil"], None)

        self.scope.set_variable("nil", nil_obj)
        self.scope.set_variable("true", true_obj)
        self.scope.set_variable("false", false_obj)

        logger.info("created global objects.")
        # create main object
        main_obj: SolObject = SolObject(self.classes["Main"], None)

        logger.info("created main object and found method run")
        self.stream = input_io
        # call method run
        logger.info("Calling method run on main obj")
        self.send_message(main_obj, "run", [], "default_reference", self.classes["Main"])

    def load_classes(self) -> None:
        "Loads both buildin and classes into global class dict for easy lookup"

        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )

        # builtins
        self.create_builtins()

        # user classes
        for cls in self.current_program.classes:
            if cls.name not in self.classes:
                # recursively creates classes
                self.create_class(cls)

    def create_class(self, cls: ClassDef) -> None:
        """Creates class and links to parent, if parent doesnt exist recursively create it"""
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )

        if cls.name in self.classes:
            return

        # recursively create parent-s
        if cls.parent not in self.classes:
            for cls_parent in self.current_program.classes:
                if cls.parent == cls_parent.name:
                    self.create_class(cls_parent)

        parent: SolClass = self.classes[cls.parent]

        # create classs
        self.classes[cls.name] = SolClass(cls.name, parent)

        # create methods dict
        for method in cls.methods:
            self.classes[cls.name].set_method(
                method.selector,
                SolMethod(
                    method.selector,
                    False,
                    method.block,
                    method.block.arity,
                    self.classes[cls.name],
                ),
            )

    def create_builtins(self) -> None:
        """
        Creates builtin classes and methods
        """
        # create buildin classes
        object_cls = SolClass("Object", None)
        integer_cls = SolClass("Integer", object_cls)
        string_cls = SolClass("String", object_cls)
        true_cls = SolClass("True", object_cls)
        false_cls = SolClass("False", object_cls)
        nil_cls = SolClass("Nil", object_cls)
        block_cls = SolClass("Block", object_cls)

        # object methods

        object_from = SolMethod("from:", True, ObjectBuiltin._from, 1, object_cls)
        object_new = SolMethod("new", True, ObjectBuiltin.new, 0, object_cls)
        object_identical_to = SolMethod(
            "identicalTo:", True, ObjectBuiltin.identical_to, 1, object_cls
        )
        object_equal_to = SolMethod("equalTo:", True, ObjectBuiltin.equal_to, 1, object_cls)
        object_as_string = SolMethod("asString", True, ObjectBuiltin.as_string, 0, object_cls)
        object_is_number = SolMethod("isNumber", True, ObjectBuiltin.is_number, 0, object_cls)
        object_is_string = SolMethod("isString", True, ObjectBuiltin.is_string, 0, object_cls)
        object_is_block = SolMethod("isBlock", True, ObjectBuiltin.is_block, 0, object_cls)
        object_is_nil = SolMethod("isNil", True, ObjectBuiltin.is_nil, 0, object_cls)
        object_is_boolean = SolMethod("isBoolean", True, ObjectBuiltin.is_boolean, 0, object_cls)

        object_cls.set_class_method("from:", object_from)
        object_cls.set_class_method("new", object_new)
        object_cls.set_method("identicalTo:", object_identical_to)
        object_cls.set_method("equalTo:", object_equal_to)
        object_cls.set_method("asString", object_as_string)
        object_cls.set_method("isNumber", object_is_number)
        object_cls.set_method("isString", object_is_string)
        object_cls.set_method("isBlock", object_is_block)
        object_cls.set_method("isNil", object_is_nil)
        object_cls.set_method("isBoolean", object_is_boolean)

        # nil methods

        nil_as_string = SolMethod("asString", True, NilBuiltin.as_string, 0, nil_cls)
        nil_is_nil = SolMethod("isNil", True, NilBuiltin.is_nil, 0, nil_cls)

        nil_cls.set_method("asString", nil_as_string)
        nil_cls.set_method("isNil", nil_is_nil)

        # integer methods

        integer_equal_to = SolMethod("equalTo:", True, IntegerBuiltin.equal_to, 1, integer_cls)
        integer_greater_than = SolMethod(
            "greaterThan:", True, IntegerBuiltin.greater_than, 1, integer_cls
        )
        integer_plus = SolMethod("plus:", True, IntegerBuiltin.plus, 1, integer_cls)
        integer_minus = SolMethod("minus:", True, IntegerBuiltin.minus, 1, integer_cls)
        integer_multiply_by = SolMethod(
            "multiplyBy:", True, IntegerBuiltin.multiply_by, 1, integer_cls
        )
        integer_div_by = SolMethod("divBy:", True, IntegerBuiltin.div_by, 1, integer_cls)
        integer_as_string = SolMethod("asString", True, IntegerBuiltin.as_string, 0, integer_cls)
        integer_as_integer = SolMethod(
            "asInteger", True, IntegerBuiltin.as_integer, 0, integer_cls
        )
        integer_times_repeat = SolMethod(
            "timesRepeat:", True, IntegerBuiltin.times_repeat, 1, integer_cls
        )
        integer_is_number = SolMethod("isNumber", True, IntegerBuiltin.is_number, 0, integer_cls)

        integer_cls.set_method("equalTo:", integer_equal_to)
        integer_cls.set_method("greaterThan:", integer_greater_than)
        integer_cls.set_method("plus:", integer_plus)
        integer_cls.set_method("minus:", integer_minus)
        integer_cls.set_method("multiplyBy:", integer_multiply_by)
        integer_cls.set_method("divBy:", integer_div_by)
        integer_cls.set_method("asString", integer_as_string)
        integer_cls.set_method("asInteger", integer_as_integer)
        integer_cls.set_method("timesRepeat:", integer_times_repeat)
        integer_cls.set_method("isNumber", integer_is_number)

        # string methods

        string_read = SolMethod("read", True, StringBuiltin.read, 0, string_cls)
        string_print = SolMethod("print", True, StringBuiltin._print, 0, string_cls)
        string_equal_to = SolMethod("equalTo:", True, StringBuiltin.equal_to, 1, string_cls)
        string_as_string = SolMethod("asString", True, StringBuiltin.as_string, 0, string_cls)
        string_as_integer = SolMethod("asInteger", True, StringBuiltin.as_integer, 0, string_cls)
        string_concat = SolMethod(
            "concatenateWith:", True, StringBuiltin.concatenate_with, 1, string_cls
        )
        string_substring = SolMethod(
            "startsWith:endsBefore:", True, StringBuiltin.starts_with_ends_before, 2, string_cls
        )
        string_length = SolMethod("length", True, StringBuiltin.length, 0, string_cls)
        string_is_string = SolMethod("isString", True, StringBuiltin.is_string, 0, string_cls)

        string_cls.set_class_method("read", string_read)
        string_cls.set_method("print", string_print)
        string_cls.set_method("equalTo:", string_equal_to)
        string_cls.set_method("asString", string_as_string)
        string_cls.set_method("asInteger", string_as_integer)
        string_cls.set_method("concatenateWith:", string_concat)
        string_cls.set_method("startsWith:endsBefore:", string_substring)
        string_cls.set_method("length", string_length)
        string_cls.set_method("isString", string_is_string)

        # block

        block_while_true = SolMethod("whileTrue:", True, BlockBuiltin.while_true, 1, block_cls)
        block_is_block = SolMethod("isBlock", True, BlockBuiltin.is_block, 0, block_cls)

        block_cls.set_method("whileTrue:", block_while_true)
        block_cls.set_method("isBlock", block_is_block)

        # true

        true_as_string = SolMethod("asString", True, TrueBuiltin.as_string, 0, true_cls)
        true_not = SolMethod("not", True, TrueBuiltin._not, 0, true_cls)
        true_and = SolMethod("and:", True, TrueBuiltin._and, 1, true_cls)
        true_or = SolMethod("or:", True, TrueBuiltin._or, 1, true_cls)
        true_if = SolMethod("ifTrue:ifFalse:", True, TrueBuiltin.if_true_if_false, 2, true_cls)
        true_is_bool = SolMethod("isBoolean", True, TrueBuiltin.is_boolean, 0, true_cls)

        true_cls.set_method("asString", true_as_string)
        true_cls.set_method("not", true_not)
        true_cls.set_method("and:", true_and)
        true_cls.set_method("or:", true_or)
        true_cls.set_method("ifTrue:ifFalse:", true_if)
        true_cls.set_method("isBoolean", true_is_bool)

        # false

        false_as_string = SolMethod("asString", True, FalseBuiltin.as_string, 0, false_cls)
        false_not = SolMethod("not", True, FalseBuiltin._not, 0, false_cls)
        false_and = SolMethod("and:", True, FalseBuiltin._and, 1, false_cls)
        false_or = SolMethod("or:", True, FalseBuiltin._or, 1, false_cls)
        false_if = SolMethod("ifTrue:ifFalse:", True, FalseBuiltin.if_true_if_false, 2, false_cls)
        false_is_bool = SolMethod("isBoolean", True, FalseBuiltin.is_boolean, 0, false_cls)

        false_cls.set_method("asString", false_as_string)
        false_cls.set_method("not", false_not)
        false_cls.set_method("and:", false_and)
        false_cls.set_method("or:", false_or)
        false_cls.set_method("ifTrue:ifFalse:", false_if)
        false_cls.set_method("isBoolean", false_is_bool)

        # link classes
        self.classes["Object"] = object_cls
        self.classes["Integer"] = integer_cls
        self.classes["String"] = string_cls
        self.classes["True"] = true_cls
        self.classes["False"] = false_cls
        self.classes["Nil"] = nil_cls
        self.classes["Block"] = block_cls

    @staticmethod
    def check_arity(receiver: SolMethod, count: int) -> None:
        """
        Compares arity between method and arg count
        """
        if receiver.arity != count:
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message="Method is being called with invalid number of args",
            )

    def send_message(
        self,
        receiver: SolObject | SolClass,
        selector: str,
        arguments: list[SolObject] | None,
        send_type: str,
        class_ctx: SolClass,
    ) -> SolObject:
        """
        Send message to receiver, lookup method and handle self and super references
        """
        if arguments is None:
            arguments = []
        arg_count: int = len(arguments)
        method: SolMethod | None

        # class method
        if isinstance(receiver, SolClass):
            method = receiver.get_class_method(selector)

            if not callable(method.function):
                raise InterpreterError(
                    error_code=ErrorCode.GENERAL_OTHER,
                    message="Builtin cls method function is not callable",
                )

            self.check_arity(method, arg_count)
            logger.info(f"sending message:{receiver.get_name()} selector:{selector}")
            ret_val: SolObject = method.function(self, receiver, arguments, class_ctx)
            return ret_val

        # block invocation
        method = receiver.instance_method.get(selector)
        if method is not None:
            self.check_arity(method, arg_count)
            return self.method_call(receiver, method, arguments, method.cls)

        # handle default ref and self
        if send_type == "default_reference" or send_type == "self":
            method = receiver.cls.get_method(selector)
        # handle super
        else:
            parent: SolClass | None = class_ctx.get_parent_cls()
            if parent is None:
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message="Class has no parent class",
                )

            method = parent.get_method(selector)

        if method is None:
            if arg_count == 0:
                if selector not in receiver.instance_attributes:
                    raise InterpreterError(
                        error_code=ErrorCode.INT_DNU,
                        message=f"Class `{receiver.get_cls().get_name()}`\
                                 has no method `{selector}`",
                    )

                return receiver.instance_attributes[selector]
            # 1 arg
            if arg_count == 1:
                instance_attr_name: str = selector[:-1]
                if send_type == "default_reference":
                    method = receiver.cls.get_method(instance_attr_name)

                elif send_type == "self":
                    method = class_ctx.get_method(instance_attr_name)
                else:
                    parent = class_ctx.get_parent_cls()
                    if parent is None:
                        raise InterpreterError(
                            error_code=ErrorCode.INT_OTHER,
                            message="Class has no parent class",
                        )
                    method = parent.get_method(instance_attr_name)

                if method is not None:
                    raise InterpreterError(
                        error_code=ErrorCode.INT_INST_ATTR,
                        message="Trying to create instance attr with the same name as method",
                    )

                receiver.instance_attributes[instance_attr_name] = arguments[0]
                return receiver
            # 2 args

            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=f"Class `{receiver.get_cls().get_name()}` has no method `{selector}`",
            )

        self.check_arity(method, arg_count)
        logger.info(f"sending message:{receiver.get_cls().get_name()} selector:{selector}")
        return self.method_call(receiver, method, arguments, method.cls)

    def method_call(
        self,
        receiver: SolObject,
        method: SolMethod,
        arguments: list[SolObject] | None,
        class_ctx: SolClass,
    ) -> SolObject:
        """
        Call method, create new scope, set parameters, bind self and super into scope
        """
        if arguments is None:
            arguments = []

        return_value: SolObject

        # builtin method
        if method.is_builtin:
            if not callable(method.function):
                raise InterpreterError(
                    error_code=ErrorCode.GENERAL_OTHER,
                    message="Builtin method function is not callable",
                )
            return_value = method.function(self, receiver, arguments, class_ctx)
            return return_value
        new_scope: Scope
        # create scope
        if receiver.closure_scope is not None:
            new_scope = Scope(receiver.closure_scope)
        else:
            new_scope = Scope(self.scope)

        if not isinstance(method.function, Block):
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER, message="Trying to execute non-block method"
            )

        parent_scope: Scope = self.scope
        self.scope = new_scope

        # set parameters into scope
        arg_count: int = len(arguments)
        for i in range(arg_count):
            self.scope.set_parameter(method.function.parameters[i].name, arguments[i])

        if not receiver.cls.is_subclass("Block"):
            # add self and super into scope
            self.scope.set_parameter("self", receiver)
            self.scope.set_parameter("super", receiver)

        # exec block
        logger.info(f"executing block, method:{method.selector} class_ctx:{class_ctx.get_name()}")
        return_value = self.execute_block(method.function.assigns, class_ctx)

        self.scope = parent_scope
        return return_value

    # execute block
    def execute_block(self, assigns: list[Assign], class_ctx: SolClass) -> SolObject:
        """
        Execute a block of assignments, returning the value of the last expression in the block
        """
        return_obj: SolObject = self.scope.get_object("nil")

        for assign in assigns:
            target = assign.target
            logger.info(f"Executing assign, target: {target}")
            value: SolObject | SolClass = self.eval_expr(assign.expr, class_ctx)
            if isinstance(value, SolClass):
                raise InterpreterError(
                    error_code=ErrorCode.GENERAL_OTHER,
                    message="Trying to assign class into variable",
                )

            if target.name != "_":
                self.scope.set_variable(target.name, value)

            return_obj = value

        return return_obj

    # eval all expressions
    def eval_expr(self, expr: Expr, class_ctx: SolClass) -> SolObject | SolClass:
        """
        Evaluate expression node base on its type
        """
        if expr.send is not None:
            return self.handle_send(expr.send, class_ctx)

        if expr.block is not None:
            cnt = expr.block.arity

            selector: str = "value" if cnt == 0 else "value:" * cnt

            method = SolMethod(selector, False, expr.block, cnt, class_ctx)
            block_obj = SolObject(self.classes["Block"], None)
            block_obj.set_closure_scope(self.scope)  # save closure scope
            block_obj.set_instance_method(selector, method)  # save method
            return block_obj

        if expr.literal is not None:
            return self.handle_literal(expr.literal)

        if expr.var is not None:
            return self.handle_var(expr.var)

        raise InterpreterError(error_code=ErrorCode.SEM_UNDEF, message="Invalid expression type")

    def handle_var(self, var: Var) -> SolObject:
        """
        Handles variable expressions, returning correct objects
        """
        if var.name == "self":
            return self.scope.get_object("self")

        if var.name == "super":
            return self.scope.get_object("super")

        if var.name == "true":
            return self.scope.get_object("true")

        if var.name == "false":
            return self.scope.get_object("false")

        if var.name == "nil":
            return self.scope.get_object("nil")

        return self.scope.get_object(var.name)

    def handle_send(self, send: Send, class_ctx: SolClass) -> SolObject:
        """
        Handles send expression, evaulating receiver and args
        """
        receiver_obj: SolObject | SolClass = self.eval_expr(send.receiver, class_ctx)

        send_type: str = "default_reference"

        if send.receiver.var is not None and send.receiver.var.name == "super":
            send_type = "super"

        elif send.receiver.var is not None and send.receiver.var.name == "self":
            send_type = "self"

        send_args: list[SolObject] = []
        for arg in send.args:
            arg_evaled: SolObject | SolClass = self.eval_expr(arg.expr, class_ctx)
            if isinstance(arg_evaled, SolClass):
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="Trying to send class as argument",
                )
            send_args.append(arg_evaled)

        # actually send msg
        return self.send_message(receiver_obj, send.selector, send_args, send_type, class_ctx)

    def handle_literal(self, literal: Literal) -> SolObject | SolClass:
        """
        Handles literal expressions, creating the appropriate objects for them.
        """
        if literal.class_id == "String":
            return SolObject(self.classes["String"], literal.value)

        if literal.class_id == "Integer":
            try:
                val: int = int(literal.value)
            except ValueError as e:
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,  # idk
                    message=f"ERR:Trying to create integer object from `{literal.value}`",
                ) from e

            return SolObject(self.classes["Integer"], val)

        if literal.class_id == "Nil":
            return self.scope.get_object("nil")

        if literal.class_id == "True":
            return self.scope.get_object("true")

        if literal.class_id == "False":
            return self.scope.get_object("false")

        if literal.value in self.classes:
            return self.classes[literal.value]

        raise InterpreterError(
            error_code=ErrorCode.SEM_UNDEF,
            message=f"Calling undefined literal class `{literal.class_id}`",
        )

class ObjectBuiltin:
    """
    Class that represents builtin methods of Object class
    """

    # class methods
    @staticmethod
    def new(
        interpreter: Interpreter, receiver: SolClass, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object new: creates new obect of class receiver with default internal values
        """
        if receiver.name == "Integer":
            return SolObject(interpreter.classes["Integer"], 0)

        if receiver.name == "String":
            return SolObject(interpreter.classes["String"], "")

        if receiver.name == "Nil":
            return interpreter.scope.get_object("nil")

        if receiver.name == "True":
            return interpreter.scope.get_object("true")

        if receiver.name == "False":
            return interpreter.scope.get_object("false")

        if receiver.name == "Block":
            empty_block = Block(parameters=[], assigns=[], arity=0)
            empty_method = SolMethod("value", False, empty_block, 0, interpreter.classes["Block"])
            block_obj = SolObject(interpreter.classes["Block"], None)
            block_obj.set_instance_method("value", empty_method)

            return block_obj

        return SolObject(receiver, None)

    @staticmethod
    def _from(
        interpreter: Interpreter, receiver: SolClass, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object from: creates a new object of class receiver,
        copying instance attrs and intern attr
        """
        if len(args) == 0:
            return ObjectBuiltin.new(interpreter, receiver, args, class_ctx)

        from_object: SolObject = args[0]

        # handle true false or nil
        if receiver.name == "True":
            return interpreter.scope.get_object("true")

        if receiver.name == "False":
            return interpreter.scope.get_object("false")

        if receiver.name == "Nil":
            return interpreter.scope.get_object("nil")

        intern_attr: int | str | None = None

        # copy intern attr
        receiver_intern_attr_cls: SolClass | None = receiver.get_intern_cls_attr()
        if receiver_intern_attr_cls is not None:
            from_attr_cls: SolClass | None = from_object.cls.get_intern_cls_attr()

            if receiver_intern_attr_cls is not from_attr_cls:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message=f"Trying to create {receiver.get_name()} from:\
                            {from_object.get_cls().get_name()}",
                )

            intern_attr = from_object.get_intern_value()

        new_obj = SolObject(receiver, intern_attr)

        if receiver.name == "Block":
            new_obj.closure_scope = from_object.get_closure_scope()
            new_obj.instance_method = from_object.instance_method

        # copy instance attrs
        instance_attrs: dict[str, SolObject] = {}

        instance_attrs = dict(from_object.instance_attributes)
        new_obj.instance_attributes = instance_attrs

        return new_obj

    # object methods
    @staticmethod
    def identical_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object identicalTo: compares identity of target and receiver
        """
        target: SolObject = args[0]
        if receiver is target:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def equal_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object equalTo: compares internal values of target and receiver
        """
        target: SolObject = args[0]

        if receiver.cls.get_intern_cls_attr() is None:
            return ObjectBuiltin.identical_to(interpreter, receiver, [target], class_ctx)

        if receiver.get_intern_value() == target.get_intern_value():
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object asString: returns string object with empty internal value
        """
        return SolObject(interpreter.classes["String"], "")

    @staticmethod
    def is_number(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object isNumber: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object isString: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_block(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object isBlock: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_nil(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object isNil: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Object isBoolean: returns false singleton object
        """
        return interpreter.scope.get_object("false")


class NilBuiltin:
    """
    Class that represents builtin methods of Nil class
    """

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Nil as_string: returns nil as object of String
        """
        return SolObject(interpreter.classes["String"], "nil")

    @staticmethod
    def is_nil(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Nil is_nil: returns true singleton object
        """
        return interpreter.scope.get_object("true")


class IntegerBuiltin:
    """
    Class that represents builtin methods of Integer class
    """

    @staticmethod
    def equal_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer equal_to: compares intern value of target to intern value of receiver
        """
        target: SolObject = args[0]
        if not isinstance(receiver.intern_value, int) or not isinstance(target.intern_value, int):
            return interpreter.scope.get_object("false")

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def greater_than(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer greaterThan: compares intern value of target to intern value of receiver
        """
        target: SolObject = args[0]
        receiver_intern_val: str | int | None = receiver.get_intern_value()
        target_intern_val: str | int | None = target.get_intern_value()

        if not isinstance(receiver_intern_val, int) or not isinstance(target_intern_val, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`greaterThan: {target.get_cls().get_name()}`\
                         is not class/subclass of Integer",
            )

        if receiver_intern_val > target_intern_val:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def plus(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer plus: adds intern value of target to intern value of receiver
        """
        target: SolObject = args[0]
        receiver_intern_val: str | int | None = receiver.get_intern_value()
        target_intern_val: str | int | None = target.get_intern_value()

        if not isinstance(receiver_intern_val, int) or not isinstance(target_intern_val, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`plus: {target.get_cls().get_name()}` is not class/subclass of Integer",
            )

        val = receiver_intern_val + target_intern_val
        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def minus(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer minus: subtracts intern value of target from intern value of receiver
        """

        target: SolObject = args[0]
        receiver_intern_val: str | int | None = receiver.get_intern_value()
        target_intern_val: str | int | None = target.get_intern_value()

        if not isinstance(receiver_intern_val, int) or not isinstance(target_intern_val, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`minus: {target.get_cls().get_name()}` is not class/subclass of Integer",
            )

        val = receiver_intern_val - target_intern_val
        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def multiply_by(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer multiplyBy: multiplies intern value of receiver by intern value of target
        """
        target: SolObject = args[0]
        receiver_intern_val: str | int | None = receiver.get_intern_value()
        target_intern_val: str | int | None = target.get_intern_value()

        if not isinstance(receiver_intern_val, int) or not isinstance(target_intern_val, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`multiplyBy: {target.get_cls().get_name()}`\
                         is not class/subclass of Integer",
            )

        val = receiver_intern_val * target_intern_val
        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def div_by(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer divBy: divides intern value of receiver by intern value of target
        """
        target: SolObject = args[0]
        receiver_intern_val: str | int | None = receiver.get_intern_value()
        target_intern_val: str | int | None = target.get_intern_value()

        if not isinstance(receiver_intern_val, int) or not isinstance(target_intern_val, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`divBy: {target.get_cls().get_name()}` is not class/subclass of Integer",
            )

        try:
            val = int(receiver_intern_val / target_intern_val)
        except ZeroDivisionError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message="Zero division error",
            ) from e

        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer asString: returns string object created from internal value
        """
        return SolObject(interpreter.classes["String"], str(receiver.get_intern_value()))

    @staticmethod
    def as_integer(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer asInteger: returns self
        """
        return receiver

    @staticmethod
    def times_repeat(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer timesRepeat: repeats given block N times,
        based on intern value of receiver
        """
        block: SolObject = args[0]
        return_obj: SolObject = interpreter.scope.get_object("nil")
        if not block.get_cls().is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message="Argument is not object instance",
            )
        receiver_intern_val: str | int | None = receiver.get_intern_value()

        if not isinstance(receiver_intern_val, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message="receiver is not an instance of Integer",
            )

        if receiver_intern_val > 0:
            for i in range(1, receiver_intern_val + 1):
                argument_obj = SolObject(interpreter.classes["Integer"], i)
                return_obj = interpreter.send_message(
                    block, "value:", [argument_obj], "default_reference", class_ctx
                )

        return return_obj

    @staticmethod
    def is_number(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Integer isNumber: returns singleton true
        """
        return interpreter.scope.get_object("true")


class StringBuiltin:
    """
    Class that represent builtin methods for String class
    """

    # String class method
    @staticmethod
    def read(
        interpreter: Interpreter, receiver: SolClass, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String read: reads line from stdin, returns object
        """
        line = interpreter.stream.readline()
        line = line.rstrip("\n")
        return SolObject(interpreter.classes["String"], line)

    # object methods
    @staticmethod
    def _print(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String _print: prints intern value of receiver without formatting characters
        """
        print(receiver.get_intern_value(), end="")
        return receiver

    @staticmethod
    def equal_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String equalTo: checks whether receiver and
        target have same intern value string
        """
        target: SolObject = args[0]

        if not target.get_cls().is_subclass("String"):
            return interpreter.scope.get_object("false")

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String asString: returns self
        """
        return receiver

    @staticmethod
    def as_integer(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String asInteger: returns Object created from sting intern value
        """
        receiver_intern_val: str | int | None = receiver.get_intern_value()

        try:
            if not isinstance(receiver_intern_val, str):
                return interpreter.scope.get_object("nil")

            val = int(receiver_intern_val)
            return SolObject(interpreter.classes["Integer"], val)
        except ValueError:
            return interpreter.scope.get_object("nil")

    @staticmethod
    def concatenate_with(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String concatenateWith: returns concatenated string
        of receiver and target
        """
        target: SolObject = args[0]
        receiver_intern_val: str | int | None = receiver.get_intern_value()
        target_intern_val: str | int | None = target.get_intern_value()

        if not isinstance(target_intern_val, str) or not isinstance(receiver_intern_val, str):
            return interpreter.scope.get_object("nil")

        val: str = receiver_intern_val + target_intern_val

        return SolObject(interpreter.classes["String"], val)

    @staticmethod
    def starts_with_ends_before(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin String startsWith:endsBefore: returns substring
        of receiver
        """

        starts_with: SolObject = args[0]
        ends_before: SolObject = args[1]
        starts_with_intern_val: str | int | None = starts_with.get_intern_value()
        ends_before_intern_val: str | int | None = ends_before.get_intern_value()
        receiver_intern_val: str | int | None = receiver.get_intern_value()

        if not isinstance(starts_with_intern_val, int) or not isinstance(
            ends_before_intern_val, int
        ):
            return interpreter.scope.get_object("nil")

        if starts_with_intern_val <= 0 or ends_before_intern_val <= 0:
            return interpreter.scope.get_object("nil")

        if ends_before_intern_val - starts_with_intern_val <= 0:
            return SolObject(interpreter.classes["String"], "")

        if not isinstance(receiver_intern_val, str):
            return interpreter.scope.get_object("nil")

        end: int = min(ends_before_intern_val - 1, len(receiver_intern_val))
        val: str = receiver_intern_val[starts_with_intern_val - 1 : end]
        return SolObject(interpreter.classes["String"], val)

    @staticmethod
    def length(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin String length: return the length of the string"""
        receiver_intern_val: str | int | None = receiver.get_intern_value()

        if not isinstance(receiver_intern_val, str):
            raise InterpreterError(
                error_code=ErrorCode.INT_OTHER,
                message="Trying to get length of non-string object",
            )

        length: int = len(receiver_intern_val)
        return SolObject(interpreter.classes["Integer"], length)

    @staticmethod
    def is_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin String isString: return true as string object"""
        return interpreter.scope.get_object("true")


class BlockBuiltin:
    """Class that represent builtin methods for Block class"""

    @staticmethod
    def while_true(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """
        Builtin Block whileTrue: Loop that executes block(sends message)
        until the receiver is false
        """
        block: SolObject = args[0]

        if not block.get_cls().is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`while_true: `{block.get_cls().get_name()}`\
                             is not class/subclass of Block",
            )
        return_val: SolObject = interpreter.scope.get_object("nil")

        while interpreter.send_message(
            receiver, "value", [], "default_reference", class_ctx
        ) is interpreter.scope.get_object("true"):
            # eval condition
            return_val = interpreter.send_message(
                block, "value", [], "default_reference", class_ctx
            )

        return return_val

    @staticmethod
    def is_block(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin Block isBlock: return true as string object"""
        return interpreter.scope.get_object("true")


class TrueBuiltin:
    """
    Class represents Builtin methods for True class
    """

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin True asString: return true as string object"""
        return SolObject(interpreter.classes["String"], "true")

    @staticmethod
    def _not(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin True not: return singleton false"""
        return interpreter.scope.get_object("false")

    @staticmethod
    def _and(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin True and: execute first block and return its value"""
        block: SolObject = args[0]

        return interpreter.send_message(block, "value", [], "default_reference", class_ctx)

    @staticmethod
    def _or(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin True or: return singleton true"""
        return interpreter.scope.get_object("true")

    @staticmethod
    def if_true_if_false(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin True ifTrue:ifFalse: execute first block and return its value"""
        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`ifTrue:ifFalse: `{block.get_cls().get_name()}`\
                             is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference", class_ctx)

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin True isBoolean: return true as singleton object"""
        return interpreter.scope.get_object("true")


class FalseBuiltin:
    """
    Class represents Builtin methods for False class
    """

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin False asString: return false as string object"""
        return SolObject(interpreter.classes["String"], "false")

    @staticmethod
    def _not(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin False not: return singleton true"""
        return interpreter.scope.get_object("true")

    @staticmethod
    def _and(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin False and: return signleton false"""
        return interpreter.scope.get_object("false")

    @staticmethod
    def _or(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """BuiltinFalse or: execute first block and return its value"""
        block: SolObject = args[0]

        return interpreter.send_message(block, "value", [], "default_reference", class_ctx)

    @staticmethod
    def if_true_if_false(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin False ifTrue:ifFalse: execute second block and return its value"""
        block: SolObject = args[1]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`ifTrue:ifFalse: `{block.get_cls().get_name()}`\
                             is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference", class_ctx)

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject], class_ctx: SolClass
    ) -> SolObject:
        """Builtin method isBoolean for False class, returns Solobject true"""
        return interpreter.scope.get_object("true")
