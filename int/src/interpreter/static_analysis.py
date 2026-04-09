"""
This module contains static analysis class

Author: Kristian Luptak <xluptak00@stud.fit.vut.cz>
"""

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Block, Expr, Program


class StaticAnalysis:
    """
    Class will do static analysis on input program - entry point is static_analysis
    """

    def __init__(self) -> None:
        self.classes: list[str] = ["Object", "Nil", "True", "False", "String", "Integer", "Block"]
        self.builtin_vars: list[str] = ["self", "super", "true", "false", "nil"]

    def check_classes(self, program: Program) -> None:
        """
        checks for main function and method run
        """
        if program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )

        for cls in program.classes:
            if cls.name == "Main":
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

            if cls.name in self.classes:
                raise InterpreterError(
                    # error code 35
                    error_code=ErrorCode.SEM_ERROR,
                    message="Redefinition of class",
                )
            self.classes.append(cls.name)

        if "Main" not in self.classes:
            # error code 31
            raise InterpreterError(error_code=ErrorCode.SEM_MAIN, message="Main class missing")

        for cls in program.classes:
            if cls.parent not in self.classes:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_UNDEF, message="Parent class missing"
                )

    def check_block(self, block: Block, params: list[str], variables: list[str]) -> None:
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

            self.check_expr(assign.expr, params, variables)

            if assign.target.name != "_" and assign.target.name not in variables:
                variables.append(assign.target.name)

    def check_expr(self, expression: Expr, params: list[str], variables: list[str]) -> None:
        """
        handles all expressions(literals, var, blocks, messages and their corresponding errors)
        """
        if (
            expression.var is not None
            and expression.var.name not in self.builtin_vars
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
            and expression.literal.value not in self.classes
        ):
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF, message="Trying to access undefined class"
            )

        if expression.block is not None:
            self.check_block(expression.block, params.copy(), variables.copy())

        if expression.send is not None:
            self.check_expr(expression.send.receiver, params, variables)
            for arg in expression.send.args:
                self.check_expr(arg.expr, params, variables)

    def static_analysis(self, program: Program) -> None:
        """
        Static semantic analysis for error codes 31-35
        """
        if program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER,
                message="Trying to load classes without program",
            )
        # main and run check - err code 31, 32, 35
        self.check_classes(program)

        # check methods
        for cls in program.classes:
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

                self.check_block(method.block, [], [])

                methods.append(method.selector)
