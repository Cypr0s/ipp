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

        self.static_analysis()

    def check_for_main(self) -> None:
        """
        checks for main function and method run
        """
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )
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
                        error_code=ErrorCode.SEM_MAIN,
                        message="Main class has no method named `run`",
                    )
        if not main:
            # error code 31
            raise InterpreterError(error_code=ErrorCode.SEM_MAIN, message="Main class missing")

    def check_classes(self) -> list[str]:
        """
        checks for redefinitions of classes nad undefined parent classes
        """
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )

        classes: list[str] = ["Object", "Nil", "True", "False", "String", "Integer", "Block"]
        for cls in self.current_program.classes:
            # error code 35 check class redefinition
            if cls.name in classes:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_ERROR, message="Redefinition of class"
                )
            classes.append(cls.name)

        # error 32 check parent class names
        for cls in self.current_program.classes:
            if cls.parent not in classes:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_UNDEF, message="Parent class missing"
                )

        return classes

    def check_block(
        self, block: Block, params: list[str], variables: list[str], classes: list[str]
    ) -> None:
        """
        handles all block assigns, like parameter redefinitions, assigns to parameters
        """
        # error 35 param redefinition
        for param in block.parameters:
            if param.name in params:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_ERROR,
                    message="same parameters in block",
                )
            params.append(param.name)

        for assign in block.assigns:
            # err 34 assign into formal parameter
            if assign.target.name in params:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_COLLISION, message="Trying to assign into parameter"
                )

            self.check_expr(assign.expr, params, variables, classes)

            if assign.target.name != "_" and assign.target.name not in variables:
                variables.append(assign.target.name)

    def check_expr(
        self, expression: Expr, params: list[str], variables: list[str], classes: list[str]
    ) -> None:
        """
        handles all expressions(literals, var, blocks, messages and their corresponding errors)
        """
        builtins: list[str] = ["self", "super", "true", "false", "nil"]
        if (
            expression.var is not None
            and expression.var.name not in builtins
            and expression.var.name not in params
            and expression.var.name not in variables
        ):
            # exit code 32 undefined variable
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF,
                message="Trying to access undefined variable",
            )

        # exit code 32 undefined literal class
        if (
            expression.literal is not None
            and expression.literal.class_id == "class"
            and expression.literal.value not in classes
        ):
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF, message="Trying to access undefined class"
            )

        if expression.block is not None:
            self.check_block(expression.block, params.copy(), variables.copy(), classes)

        if expression.send is not None:
            self.check_expr(expression.send.receiver, params, variables, classes)
            for arg in expression.send.args:
                self.check_expr(arg.expr, params, variables, classes)

    def static_analysis(self) -> None:
        """
        Static semantic analysis for error codes 31-35
        """
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )
        # main and run check - err code 31
        self.check_for_main()
        # load and check 32,35 class
        classes: list[str] = self.check_classes()

        # cmethods
        for cls in self.current_program.classes:
            methods: list[str] = []

            for method in cls.methods:
                # error code 35 method redef
                if method.selector in methods:
                    raise InterpreterError(
                        error_code=ErrorCode.SEM_ERROR, message="Redefinition of method"
                    )

                # error code 33 invalid arity
                dd_count: int = method.selector.count(":")
                if dd_count != method.block.arity:
                    raise InterpreterError(
                        error_code=ErrorCode.SEM_ARITY,
                        message="Block arity doesnt match selector",
                    )

                self.check_block(method.block, [], [], classes)

                methods.append(method.selector)

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

        self.scope.create_object("nil", nil_obj)
        self.scope.create_object("true", true_obj)
        self.scope.create_object("false", false_obj)

        logger.info("created global objects.")
        # create main object
        main_obj: SolObject = SolObject(self.classes["Main"], None)

        logger.info("created main object and found method run")
        self.stream = input_io
        # call method run
        self.send_message(main_obj, "run", [], "default_reference", self.classes["Main"])

    def load_classes(self) -> None:
        "Loads both buildin and classes into global class dict for easy lookup"
        # builtins
        self.create_builtins()

        # user classes
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )
        for cls in self.current_program.classes:
            if cls.name not in self.classes:
                # recursively creates classes
                self.create_class(cls)

    def create_class(self, cls: ClassDef) -> None:
        """Creates class and links to parent, if parent doesnt exist recursively creates it"""
        if cls.name in self.classes:
            return
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )

        # recursively create parent-s
        if cls.parent not in self.classes:
            for cls_parent in self.current_program.classes:
                if cls.parent == cls_parent.name:
                    self.create_class(cls_parent)

        parent: SolClass = self.classes[cls.parent]

        # create classs
        self.classes[cls.name] = SolClass(cls.name, parent, {})

        # create methods dict
        for method in cls.methods:
            self.classes[cls.name].methods[method.selector] = SolMethod(
                method.selector, False, method.block, method.block.arity, self.classes[cls.name]
            )

    def create_builtins(self) -> None:
        """
        Creates builtin classes and methods
        """
        # create buildin classes
        object_cls = SolClass("Object", None, {})
        integer_cls = SolClass("Integer", object_cls, {})
        string_cls = SolClass("String", object_cls, {})
        true_cls = SolClass("True", object_cls, {})
        false_cls = SolClass("False", object_cls, {})
        nil_cls = SolClass("Nil", object_cls, {})
        block_cls = SolClass("Block", object_cls, {})

        # link methods

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

        nil_as_string = SolMethod("asString", True, NilBuiltin.as_string, 0, nil_cls)
        nil_is_nil = SolMethod("isNil", True, NilBuiltin.is_nil, 0, nil_cls)

        nil_cls.methods["asString"] = nil_as_string
        nil_cls.methods["isNil"] = nil_is_nil

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

        block_while_true = SolMethod("whileTrue:", True, BlockBuiltin.while_true, 1, block_cls)
        block_is_block = SolMethod("isBlock", True, BlockBuiltin.is_block, 0, block_cls)

        block_cls.methods["whileTrue:"] = block_while_true
        block_cls.methods["isBlock"] = block_is_block

        # true

        true_as_string = SolMethod("asString", True, TrueBuiltin.as_string, 0, true_cls)
        true_not = SolMethod("not", True, TrueBuiltin._not, 0, true_cls)
        true_and = SolMethod("and:", True, TrueBuiltin._and, 1, true_cls)
        true_or = SolMethod("or:", True, TrueBuiltin._or, 1, true_cls)
        true_if = SolMethod("ifTrue:ifFalse:", True, TrueBuiltin.if_true_if_false, 2, true_cls)
        true_is_bool = SolMethod("isBoolean", True, TrueBuiltin.is_boolean, 0, true_cls)

        true_cls.methods["asString"] = true_as_string
        true_cls.methods["not"] = true_not
        true_cls.methods["and:"] = true_and
        true_cls.methods["or:"] = true_or
        true_cls.methods["ifTrue:ifFalse:"] = true_if
        true_cls.methods["isBoolean"] = true_is_bool

        # false

        false_as_string = SolMethod("asString", True, FalseBuiltin.as_string, 0, false_cls)
        false_not = SolMethod("not", True, FalseBuiltin._not, 0, false_cls)
        false_and = SolMethod("and:", True, FalseBuiltin._and, 1, false_cls)
        false_or = SolMethod("or:", True, FalseBuiltin._or, 1, false_cls)
        false_if = SolMethod("ifTrue:ifFalse:", True, FalseBuiltin.if_true_if_false, 2, false_cls)
        false_is_bool = SolMethod("isBoolean", True, FalseBuiltin.is_boolean, 0, false_cls)

        false_cls.methods["asString"] = false_as_string
        false_cls.methods["not"] = false_not
        false_cls.methods["and:"] = false_and
        false_cls.methods["or:"] = false_or
        false_cls.methods["ifTrue:ifFalse:"] = false_if
        false_cls.methods["isBoolean"] = false_is_bool

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
            logger.info(f"sending message:{receiver.name} {selector}, {arguments}")
            ret_val: SolObject = method.function(self, receiver, arguments)
            return ret_val

        # block invocation
        method = receiver.instance_method.get(selector)
        if method is not None:
            self.check_arity(method, arg_count)
            return self.method_call(receiver, method, arguments, method.cls)

        # handle default ref and self
        if send_type == "default_reference" or send_type == "self":
            method = receiver.cls.get_method(selector)
        # handle self
        # handle super
        else:
            if class_ctx.parent is None:
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message="Class has no parent class",
                )

            method = class_ctx.parent.get_method(selector)

        if method is None:
            if arg_count == 0:
                if selector not in receiver.instance_attributes:
                    raise InterpreterError(
                        error_code=ErrorCode.INT_DNU,
                        message=f"Class `{receiver.cls.name}` has no method `{selector}`",
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
                    if class_ctx.parent is None:
                        raise InterpreterError(
                            error_code=ErrorCode.INT_OTHER,
                            message="Class has no parent class",
                        )
                    method = class_ctx.parent.get_method(instance_attr_name)

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
                message=f"Class `{receiver.cls.name}` has no method `{selector}`",
            )

        self.check_arity(method, arg_count)
        logger.info(f"sending message:{receiver.cls.name} {selector}, {arguments}")
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
            return_value = method.function(self, receiver, arguments)
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
            self.scope.create_object(method.function.parameters[i].name, arguments[i])

        # add self into scope
        self.scope.create_object("self", receiver)

        # add super into scope
        self.scope.create_object("super", receiver)
        # exec block
        return_value = self.execute_block(method.function.assigns, class_ctx)

        self.scope = parent_scope
        return return_value

    # execute block
    def execute_block(self, assigns: list[Assign], class_ctx: SolClass) -> SolObject:
        """
        Execute a block of assignments, returning the value of the last expression in the block
        """
        return_obj: SolObject = self.scope.get_object("nil")
        logger.info("Executing block")

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
                self.scope.create_object(target.name, value)

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
            block_obj.closure_scope = self.scope  # save closure scope
            block_obj.instance_method[selector] = method  # save method
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
    def new(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
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
            block_obj.instance_method["value"] = empty_method

            return block_obj

        return SolObject(receiver, None)

    @staticmethod
    def _from(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        """
        Builtin Object from: creates a new object of class receiver,
        copying instance attrs and intern attr
        """
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

        intern_attr: int | str | None = None

        # copy intern attr
        receiver_intern_attr_cls: SolClass | None = receiver.get_intern_attr_cls()

        if receiver_intern_attr_cls is not None:
            from_attr_cls: SolClass | None = from_object.cls.get_intern_attr_cls()

            if receiver_intern_attr_cls is not from_attr_cls:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message=f"Trying to create {receiver.name} from: {from_object.cls.name}",
                )

            intern_attr = from_object.intern_value

        new_obj = SolObject(receiver, intern_attr)

        if receiver.name == "Block":
            new_obj.closure_scope = from_object.closure_scope
            new_obj.instance_method = from_object.instance_method

        # copy instance attrs
        instance_attrs: dict[str, SolObject] = {}

        instance_attrs = dict(from_object.instance_attributes)
        new_obj.instance_attributes = instance_attrs

        return new_obj

    # object methods
    @staticmethod
    def identical_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
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
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Object equalTo: compares internal values of target and receiver
        """
        target: SolObject = args[0]

        if receiver.cls.get_intern_attr_cls() is None:
            return ObjectBuiltin.identical_to(interpreter, receiver, [target])

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Object asString: returns string object with empty internal value
        """
        return SolObject(interpreter.classes["String"], "")

    @staticmethod
    def is_number(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Object isNumber: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Object isString: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_block(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Object isBlock: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_nil(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """
        Builtin Object isNil: returns false singleton object
        """
        return interpreter.scope.get_object("false")

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
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
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Nil as_string: returns nil as object of String
        """
        return SolObject(interpreter.classes["String"], "nil")

    @staticmethod
    def is_nil(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
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
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
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
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Integer greaterThan: compares intern value of target to intern value of receiver
        """
        target: SolObject = args[0]

        if not isinstance(receiver.intern_value, int) or not isinstance(target.intern_value, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`greaterThan: {target.cls.name}` is not class/subclass of Integer",
            )

        if receiver.intern_value > target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def plus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """
        Builtin Integer plus: adds intern value of target to intern value of receiver
        """
        target: SolObject = args[0]

        if not isinstance(receiver.intern_value, int) or not isinstance(target.intern_value, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`plus: {target.cls.name}` is not class/subclass of Integer",
            )

        val = receiver.intern_value + target.intern_value
        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def minus(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """
        Builtin Integer minus: subtracts intern value of target from intern value of receiver
        """

        target: SolObject = args[0]

        if not isinstance(receiver.intern_value, int) or not isinstance(target.intern_value, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`minus: {target.cls.name}` is not class/subclass of Integer",
            )

        val = receiver.intern_value - target.intern_value
        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def multiply_by(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Integer multiplyBy: multiplies intern value of receiver by intern value of target
        """
        target: SolObject = args[0]

        if not isinstance(receiver.intern_value, int) or not isinstance(target.intern_value, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`multiplyBy: {target.cls.name}` is not class/subclass of Integer",
            )

        val = receiver.intern_value * target.intern_value
        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def div_by(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """
        Builtin Integer divBy: divides intern value of receiver by intern value of target
        """
        target: SolObject = args[0]

        if not isinstance(receiver.intern_value, int) or not isinstance(target.intern_value, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`divBy: {target.cls.name}` is not class/subclass of Integer",
            )

        try:
            val = receiver.intern_value // target.intern_value
        except ZeroDivisionError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message="Zero division error",
            ) from e

        return SolObject(interpreter.classes["Integer"], val)

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Integer asString: returns string object created from internal value
        """
        return SolObject(interpreter.classes["String"], str(receiver.intern_value))

    @staticmethod
    def as_integer(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Integer asInteger: returns self
        """
        return receiver

    @staticmethod
    def times_repeat(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Integer timesRepeat: repeats given block N times,
        based on intern value of receiver
        """
        block: SolObject = args[0]
        return_obj: SolObject = interpreter.scope.get_object("nil")
        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message="Argument is not object instance",
            )
        if not isinstance(receiver.intern_value, int):
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message="receiver is not an instance of Integer",
            )

        if receiver.intern_value > 0:
            for i in range(1, receiver.intern_value + 1):
                argument_obj = SolObject(interpreter.classes["Integer"], i)
                return_obj = interpreter.send_message(
                    block, "value:", [argument_obj], "default_reference", receiver.cls
                )

        return return_obj

    @staticmethod
    def is_number(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
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
    def read(interpreter: Interpreter, receiver: SolClass, args: list[SolObject]) -> SolObject:
        """
        Builtin String read: reads line from stdin, returns object
        """
        line = interpreter.stream.readline()
        line = line.rstrip("\n")
        return SolObject(interpreter.classes["String"], line)

    # object methods
    @staticmethod
    def _print(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """
        Builtin String _print: prints intern value of receiver without formatting characters
        """
        print(receiver.intern_value, end="")
        return receiver

    @staticmethod
    def equal_to(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin String equalTo: checks whether receiver and
        target have same intern value string
        """
        target: SolObject = args[0]

        if not target.cls.is_subclass("String"):
            return interpreter.scope.get_object("false")

        if receiver.intern_value == target.intern_value:
            return interpreter.scope.get_object("true")
        return interpreter.scope.get_object("false")

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin String asString: returns self
        """
        return receiver

    @staticmethod
    def as_integer(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin String asInteger: returns Object created from sting intern value
        """
        try:
            if not isinstance(receiver.intern_value, str):
                return interpreter.scope.get_object("nil")

            val = int(receiver.intern_value)
            return SolObject(interpreter.classes["Integer"], val)
        except ValueError:
            return interpreter.scope.get_object("nil")

    @staticmethod
    def concatenate_with(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin String concatenateWith: returns concatenated string
        of receiver and target
        """
        target: SolObject = args[0]

        if not isinstance(target.intern_value, str) or not isinstance(receiver.intern_value, str):
            return interpreter.scope.get_object("nil")

        return SolObject(
            interpreter.classes["String"], receiver.intern_value + target.intern_value
        )

    @staticmethod
    def starts_with_ends_before(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin String startsWith:endsBefore: returns substring
        of receiver
        """

        starts_with: SolObject = args[0]
        ends_before: SolObject = args[1]

        if not isinstance(starts_with.intern_value, int) or not isinstance(
            ends_before.intern_value, int
        ):
            return interpreter.scope.get_object("nil")

        if starts_with.intern_value <= 0 or ends_before.intern_value <= 0:
            return interpreter.scope.get_object("nil")

        if ends_before.intern_value - starts_with.intern_value <= 0:
            return SolObject(interpreter.classes["String"], "")

        if not isinstance(receiver.intern_value, str):
            return interpreter.scope.get_object("nil")

        val: str = receiver.intern_value[
            starts_with.intern_value - 1 : ends_before.intern_value - 1
        ]
        return SolObject(interpreter.classes["String"], val)

    @staticmethod
    def length(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """Builtin String length: return the length of the string"""
        if not isinstance(receiver.intern_value, str):
            raise InterpreterError(
                error_code=ErrorCode.INT_OTHER,
                message="Trying to get length of non-string object",
            )

        length: int = len(receiver.intern_value)
        return SolObject(interpreter.classes["Integer"], length)

    @staticmethod
    def is_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin String isString: return true as string object"""
        return interpreter.scope.get_object("true")


class BlockBuiltin:
    """Class that represent builtin methods for Block class"""

    @staticmethod
    def while_true(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """
        Builtin Block whileTrue: Loop that executes block(sends message)
        until the receiver is false
        """
        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`while_true: `{block.cls.name}` is not class/subclass of Block",
            )
        return_val: SolObject = interpreter.scope.get_object("nil")

        while interpreter.send_message(
            receiver, "value", [], "default_reference", receiver.cls
        ) is interpreter.scope.get_object("true"):
            # eval condition
            return_val = interpreter.send_message(
                block, "value", [], "default_reference", receiver.cls
            )

        return return_val

    @staticmethod
    def is_block(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin Block isBlock: return true as string object"""
        return interpreter.scope.get_object("true")


class TrueBuiltin:
    """
    Class represents Builtin methods for True class
    """

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin True asString: return true as string object"""
        return SolObject(interpreter.classes["String"], "true")

    @staticmethod
    def _not(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """Builtin True not: return singleton false"""
        return interpreter.scope.get_object("false")

    @staticmethod
    def _and(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """Builtin True and: execute first block and return its value"""
        block: SolObject = args[0]

        return interpreter.send_message(block, "value", [], "default_reference", receiver.cls)

    @staticmethod
    def _or(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """Builtin True or: return singleton true"""
        return interpreter.scope.get_object("true")

    @staticmethod
    def if_true_if_false(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin True ifTrue:ifFalse: execute first block and return its value"""
        block: SolObject = args[0]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`ifTrue:ifFalse: `{block.cls.name}` is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference", receiver.cls)

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin True isBoolean: return true as singleton object"""
        return interpreter.scope.get_object("true")


class FalseBuiltin:
    """
    Class represents Builtin methods for False class
    """

    @staticmethod
    def as_string(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin False asString: return false as string object"""
        return SolObject(interpreter.classes["String"], "false")

    @staticmethod
    def _not(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """Builtin False not: return singleton true"""
        return interpreter.scope.get_object("true")

    @staticmethod
    def _and(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """Builtin False and: return signleton false"""
        return interpreter.scope.get_object("false")

    @staticmethod
    def _or(interpreter: Interpreter, receiver: SolObject, args: list[SolObject]) -> SolObject:
        """BuiltinFalse or: execute first block and return its value"""
        block: SolObject = args[0]

        return interpreter.send_message(block, "value", [], "default_reference", receiver.cls)

    @staticmethod
    def if_true_if_false(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin False ifTrue:ifFalse: execute second block and return its value"""
        block: SolObject = args[1]

        if not block.cls.is_subclass("Block"):
            raise InterpreterError(
                error_code=ErrorCode.INT_INVALID_ARG,
                message=f"`ifTrue:ifFalse: `{block.cls.name}` is not class/subclass of Block",
            )
        return interpreter.send_message(block, "value", [], "default_reference", receiver.cls)

    @staticmethod
    def is_boolean(
        interpreter: Interpreter, receiver: SolObject, args: list[SolObject]
    ) -> SolObject:
        """Builtin method isBoolean for False class, returns Solobject true"""
        return interpreter.scope.get_object("true")


class SolClass:
    """
    Class represents runtime classes of SOL26
    """

    def __init__(
        self, name: str, super_class: SolClass | None, methods: dict[str, SolMethod]
    ) -> None:
        self.name: str = name
        self.parent: SolClass | None = super_class
        self.methods: dict[str, SolMethod] = methods
        self.class_methods: dict[str, SolMethod] = {}

    def get_method(self, selector: str) -> SolMethod | None:
        """
        function returns method if class has one with given selector,
        runs through inheritance hierarchy
        """
        if selector in self.methods:
            return self.methods[selector]

        if self.parent is not None:
            return self.parent.get_method(selector)

        return None

    def get_class_method(self, selector: str) -> SolMethod:
        """
        function returns class method if class has one with given selector,
        runs through inheritance hierarchy
        """
        if selector in self.class_methods:
            return self.class_methods[selector]

        if self.parent is not None:
            return self.parent.get_class_method(selector)

        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"Class `{self.name}` has no class method `{selector}`",
        )

    def get_intern_attr_cls(self) -> SolClass | None:
        """
        Returns the class of internal attribute if it exists
        """

        if self.name == "String" or self.name == "Integer":
            return self

        if self.parent is not None:
            return self.parent.get_intern_attr_cls()

        return None

    def is_subclass(self, cls: str) -> bool:
        """
        Checks whether self is a subclass of another SOL26 class
        """

        if self.name == cls:
            return True

        if self.parent is None:
            return False

        return self.parent.is_subclass(cls)


class SolObject:
    """
    class represents runtime objects of SOL26 with different attributs for different
    types of objects
    """

    def __init__(self, cls: SolClass, intern_value: int | str | None) -> None:
        self.cls: SolClass = cls
        self.intern_value: int | str | None = intern_value
        self.instance_attributes: dict[str, SolObject] = {}  # uder defined
        self.instance_method: dict[str, SolMethod] = {}  # block value method
        self.closure_scope: Scope | None = None  # block closure scope


class SolMethod:
    """
    class represents methods of SOL26 with both builtin callable and user blocks as functions
    """

    def __init__(
        self, selector: str, is_builtin: bool, func: object, arity: int, cls: SolClass
    ) -> None:
        self.cls: SolClass = cls
        self.selector: str = selector
        self.is_builtin: bool = is_builtin
        self.function: object = func
        self.arity: int = arity


class Scope:
    """
    Class for creating scopes and finding variables in them, handling everything related to scope
    """

    def __init__(self, parent_scope: Scope | None = None) -> None:
        self.parent_scope = parent_scope
        self.objects: dict[str, SolObject] = {}

    def get_object(self, object_name: str) -> SolObject:
        """
        Try to find an object in scope recursively, if it doesn't exist return None
        """

        if object_name in self.objects:
            return self.objects[object_name]

        if self.parent_scope is not None:
            return self.parent_scope.get_object(object_name)

        raise InterpreterError(
            error_code=ErrorCode.SEM_UNDEF, message=f"No object with `{object_name}` exists"
        )

    def set_object(self, object_name: str, obj: SolObject) -> bool:
        """
        Try to set an object in scope recursively, if it doesn't exist return false
        """
        if object_name in self.objects:
            self.objects[object_name] = obj
            return True

        if self.parent_scope is not None:
            return self.parent_scope.set_object(object_name, obj)

        return False

    def create_object(self, object_name: str, obj: SolObject) -> None:
        """
        Set an object in scope, if it doesn't exist create it, if it exists update it
        """
        created: bool = self.set_object(object_name, obj)
        if not created:
            self.objects[object_name] = obj
