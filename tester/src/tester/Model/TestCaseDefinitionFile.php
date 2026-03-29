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

use JsonSerializable;

/**
 * Represents a single discovered test case file.
 *
 * IPP: This model may (or may not) be useful for your internal processing.
 * You can also build your own internal models and only create
 * `TestCaseDefinition` instances for the output report.
 */
class TestCaseDefinitionFile implements JsonSerializable
{
    /**
     * @param string $name Test case name (filename without `.test`)
     * @param string $testSourcePath Path to the `.test` definition file
     * @param string|null $stdinFile Optional `.in` file path
     * @param string|null $expectedStdoutFile Optional `.out` file path
     */
    public function __construct(
        public readonly string $name,
        public readonly string $testSourcePath,
        public readonly ?string $stdinFile = null,
        public readonly ?string $expectedStdoutFile = null
    ) {
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        // Keep snake_case keys aligned with Python/TS output schema.
        return [
            'name' => $this->name,
            'test_source_path' => $this->testSourcePath,
            'stdin_file' => $this->stdinFile,
            'expected_stdout_file' => $this->expectedStdoutFile,
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
