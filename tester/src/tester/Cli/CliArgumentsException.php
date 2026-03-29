<?php

/**
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester\Cli;

use RuntimeException;

/**
 * Signals a CLI parsing/validation error with a specific process exit code.
 */
class CliArgumentsException extends RuntimeException
{
    public function __construct(string $message, public readonly int $exitCode)
    {
        parent::__construct($message, $exitCode);
    }
}
