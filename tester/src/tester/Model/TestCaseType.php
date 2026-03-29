<?php

/**
 * A part of the definition of the input model.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester\Model;

/**
 * Represents the type of a test case: SOL2XML, interpretation only, combined.
 */
enum TestCaseType: int
{
    /** Parse-only test (SOL -> XML translation only). */
    case PARSE_ONLY = 0;
    /** Execute-only test (XML interpretation only). */
    case EXECUTE_ONLY = 1;
    /** Combined test (parse then execute). */
    case COMBINED = 2;
}
