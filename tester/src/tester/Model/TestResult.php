<?php

/**
 * A part of the definition of the output model.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester\Model;

/**
 * Represents the result of an executed test case.
 */
enum TestResult: string
{
    /** Test passed. */
    case PASSED = 'passed';
    /** Parser returned an unexpected exit code. */
    case UNEXPECTED_PARSER_EXIT_CODE = 'parse_fail';
    /** Interpreter returned an unexpected exit code. */
    case UNEXPECTED_INTERPRETER_EXIT_CODE = 'int_fail';
    /** Interpreter stdout differs from expected output (.out). */
    case INTERPRETER_RESULT_DIFFERS = 'diff_fail';
}
