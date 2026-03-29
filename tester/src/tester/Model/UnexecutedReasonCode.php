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
 * Represents the reason why a test case was not executed.
 */
enum UnexecutedReasonCode: int
{
    /** The test case was filtered out by include/exclude criteria. */
    case FILTERED_OUT = 0;
    /** The test definition file could not be parsed as valid SOLtest. */
    case MALFORMED_TEST_CASE_FILE = 1;
    /** The tool could not determine parse-only/execute-only/combined type. */
    case CANNOT_DETERMINE_TYPE = 2;
    /** Required external executable could not be run. */
    case CANNOT_EXECUTE = 3;
    /** Unexpected error. */
    case OTHER = 4;
}
