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

use InvalidArgumentException;

/**
 * Represents a single discovered test case (that was successfully parsed).
 *
 * IPP: Do not change the output schema of this model, as it is part of the
 * report format evaluated by tooling around this project.
 */
class TestCaseDefinition extends TestCaseDefinitionFile
{
    /** Determines how the test should be executed. */
    public readonly TestCaseType $testType;
    /** Optional human-readable test description. */
    public readonly ?string $description;
    /** Category identifier used for grouping/filtering in reports. */
    public readonly string $category;
    /** Number of points awarded if this test passes. */
    public readonly int $points;

    /** @var list<int>|null */
    public readonly ?array $expectedParserExitCodes;

    /** @var list<int>|null */
    public readonly ?array $expectedInterpreterExitCodes;

    /**
     * @param list<int>|null $expectedParserExitCodes
     * @param list<int>|null $expectedInterpreterExitCodes
     */
    public function __construct(
        string $name,
        string $testSourcePath,
        TestCaseType $testType,
        string $category,
        ?string $stdinFile = null,
        ?string $expectedStdoutFile = null,
        ?string $description = null,
        int $points = 1,
        ?array $expectedParserExitCodes = null,
        ?array $expectedInterpreterExitCodes = null
    ) {
        parent::__construct($name, $testSourcePath, $stdinFile, $expectedStdoutFile);

        $this->testType = $testType;
        $this->description = $description;
        $this->category = $category;
        $this->points = $points;
        $this->expectedParserExitCodes = $this->normalizeExitCodeList(
            $expectedParserExitCodes,
            'parser'
        );
        $this->expectedInterpreterExitCodes = $this->normalizeExitCodeList(
            $expectedInterpreterExitCodes,
            'interpreter'
        );

        $this->validateExitCodes();
    }

    /**
     * @param array<mixed>|null $exitCodes
     * @return list<int>|null
     */
    private function normalizeExitCodeList(?array $exitCodes, string $codeType): ?array
    {
        if ($exitCodes === null) {
            return null;
        }

        $normalized = [];

        foreach ($exitCodes as $exitCode) {
            if (!is_int($exitCode)) {
                throw new InvalidArgumentException(sprintf(
                    'Expected %s exit code to be an integer.',
                    $codeType
                ));
            }

            $normalized[] = $exitCode;
        }

        return $normalized;
    }

    /**
     * @param list<int>|null $exitCodes
     */
    private static function hasNoExitCodes(?array $exitCodes): bool
    {
        return $exitCodes === null || $exitCodes === [];
    }

    private function validateParseOnlyExitCodes(): void
    {
        if (self::hasNoExitCodes($this->expectedParserExitCodes)) {
            throw new InvalidArgumentException(
                'Expected parser exit codes must be provided for parse-only test cases.'
            );
        }

        if ($this->expectedInterpreterExitCodes !== null) {
            throw new InvalidArgumentException(
                'Expected interpreter exit codes should not be provided for parse-only test cases.'
            );
        }
    }

    private function validateExecuteOnlyExitCodes(): void
    {
        if (self::hasNoExitCodes($this->expectedInterpreterExitCodes)) {
            throw new InvalidArgumentException(
                'Expected interpreter exit codes must be provided for execute-only test cases.'
            );
        }

        if ($this->expectedParserExitCodes !== null) {
            throw new InvalidArgumentException(
                'Expected parser exit codes should not be provided for execute-only test cases.'
            );
        }
    }

    private function validateCombinedExitCodes(): void
    {
        if (
            $this->expectedParserExitCodes !== null
            && ($this->expectedParserExitCodes !== [0])
        ) {
            throw new InvalidArgumentException(
                'In combined test cases, the parser exit code must be zero.'
            );
        }

        if (self::hasNoExitCodes($this->expectedInterpreterExitCodes)) {
            throw new InvalidArgumentException(
                'Expected interpreter exit codes must be provided for combined test cases.'
            );
        }
    }

    private function validateExitCodes(): void
    {
        // Validation rules match the Python/TypeScript reference models.
        switch ($this->testType) {
            case TestCaseType::PARSE_ONLY:
                $this->validateParseOnlyExitCodes();
                break;

            case TestCaseType::EXECUTE_ONLY:
                $this->validateExecuteOnlyExitCodes();
                break;

            case TestCaseType::COMBINED:
                $this->validateCombinedExitCodes();
                break;
        }
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        return [
            ...parent::toArray(),
            'test_type' => $this->testType->value,
            'description' => $this->description,
            'category' => $this->category,
            'points' => $this->points,
            'expected_parser_exit_codes' => $this->expectedParserExitCodes,
            'expected_interpreter_exit_codes' => $this->expectedInterpreterExitCodes,
        ];
    }
}
