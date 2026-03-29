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

use JsonSerializable;

/**
 * Represents the report for a single test case after processing.
 */
class TestCaseReport implements JsonSerializable
{
    /**
     * Stores result metadata for one executed test case, including captured
     * outputs from parser/interpreter and optional diff output.
     */
    public function __construct(
        public readonly TestResult $result,
        public readonly ?int $parserExitCode = null,
        public readonly ?int $interpreterExitCode = null,
        public readonly ?string $parserStdout = null,
        public readonly ?string $parserStderr = null,
        public readonly ?string $interpreterStdout = null,
        public readonly ?string $interpreterStderr = null,
        public readonly ?string $diffOutput = null
    ) {
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        return [
            'result' => $this->result->value,
            'parser_exit_code' => $this->parserExitCode,
            'interpreter_exit_code' => $this->interpreterExitCode,
            'parser_stdout' => $this->parserStdout,
            'parser_stderr' => $this->parserStderr,
            'interpreter_stdout' => $this->interpreterStdout,
            'interpreter_stderr' => $this->interpreterStderr,
            'diff_output' => $this->diffOutput,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public function jsonSerialize(): array
    {
        return $this->toArray();
    }
}
