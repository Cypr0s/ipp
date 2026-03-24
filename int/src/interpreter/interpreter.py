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
from interpreter.input_model import Block, ClassDef, Program, Expr, Literal, Send
from interpreter.runtime_model import *

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
        run_method: SolMethod = main_obj.cls.get_method("run")

        logger.info("created main object and found method run")
        self.stream = input_io
        # call method run
        self.send_message(main_obj, run_method, [])

    def load_classes(self):
        "Loads both buildin and classes into global class dict for easy lookup"
        # builtins
        object_cls = SolClass("Object", None, {})
        integer_cls = SolClass("Integer", object_cls, {})
        string_cls = SolClass("String", object_cls, {})
        true_cls = SolClass("True", object_cls, {})
        false_cls = SolClass("Frue", object_cls, {})
        nil_cls = SolClass("Nil", object_cls, {})
        block_cls = SolClass("Block", object_cls, {})

        self.classes["Object"] = object_cls
        self.classes["Integer"] = integer_cls
        self.classes["String"] = string_cls
        self.classes["True"] = true_cls
        self.classes["False"] = false_cls
        self.classes["Nil"] = nil_cls
        self.classes["Block"] = block_cls

        # user classes
        for cls in self.current_program.classes:
            if cls.name not in self.classes:
                # recursively creates classes
                self.create_class(cls.name)

    def create_class(self, cls: ClassDef) -> None:
        """Creates class and links to parent, if parent doesnt exist recursively creates it"""
        if cls.name in self.classes:
            return

        # parent doesnt exist??
        if cls.parent is None:
            pass

        # recursively create parent-s
        if cls.parent not in self.classes:
            for cls_parent in self.current_program.classes:
                if cls.parent == cls_parent.name:
                    self.create_class(self, cls_parent)

        # create methods dict
        parent: SolClass = self.classes[cls.parent]
        methods: dict[str, SolMethod] = {}
        for method in cls.methods:
            if method.selector in methods:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_ERROR, message="Redefinition of Method in class"
                )
            methods[method.selector] = SolMethod(
                method.selector, False, method.block, method.block.arity
            )

        # create classs
        self.classes[cls.name] = SolClass(cls.name, parent, methods)

    def send_message(
        self, receiver: SolObject, method: SolMethod, arguments: list[SolObject] | None = []
    ) -> SolObject:
        # builtin method check arity and exec
        arg_count: int = len(arguments)
        if method.arity != arg_count:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ARITY,
                message=f"Arity of method `{method.selector}` `{method.arity}` is called with `{arg_count}` arguments",
            )
        if method.is_builtin:
            method.function(receiver, arguments)
        # otherwise its a block
        # create new scope, call block with new scope
        new_scope = Scope(self.scope)
        parent_scope = self.scope
        self.scope = new_scope

        self.execute_block(method.block)

        self.scope = parent_scope

        return

    # execute block
    def execute_block(self, block: Block) -> SolObject:
        return_obj: SolObject
        for assign in block.assigns:
            target = assign.target
            value = self.eval_expr(assign.expr)
            if target != "_":
                self.scope.set_object(target, value)

            return_obj = value
        return return_obj

    # eval all expressions
    def eval_expr(self, expr: Expr) -> SolObject:
        if expr.send is not None:
            return self.handle_send(expr.send)

        elif expr.block is not None:
            return SolObject("Block", expr.block)

        elif expr.literal is not None:
            return self.handle_literal(expr.literal)

        elif expr.var is not None:
            return self.scope.get_object(expr.var)

        raise InterpreterError(error_code=ErrorCode.SEM_UNDEF, message="Invalid expression type")

    def handle_send(self, send: Send) -> SolObject:
        receiver_obj = self.eval_expr(send.receiver)  # eval obj receiver

        selector_method = receiver_obj.cls.get_method(send.selector)  # eval method

        send_args: list[SolObject] = []
        for arg in send.args:
            send_args.append(self.eval_expr(arg))

        # actually send msg
        return self.send_message(receiver_obj, selector_method, send_args)

    # handle literals
    def handle_literal(self, literal: Literal) -> SolObject:
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
            return SolObject(self.classes["Block"], literal.value)

        elif literal.class_id == "Nil":
            return self.scope.get_object("nil")

        elif literal.class_id == "True":
            return self.scope.get_object("true")

        elif literal.class_id == "False":
            return self.scope.get_object("false")

        if literal.class_id in self.classes:
            return SolObject(self.classes[literal.class_id], literal.value)

        raise InterpreterError(
            error_code=ErrorCode.SEM_UNDEF,
            message=f"Calling undefined literal class `{literal.class_id}`",
        )
