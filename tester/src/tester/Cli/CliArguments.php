<?php

/**
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester\Cli;

/**
 * Represents parsed command-line arguments.
 *
 * Field mapping mirrors the Python/TS templates and the specification:
 * - testsDir: path to test directory (already validated and normalized)
 * - recursive: recurse into subdirectories while discovering tests
 * - output: optional report output file path
 * - dryRun: discover tests only, do not execute them
 * - include/exclude: optional filter lists (trimmed string values)
 * - verbose: number of `-v` occurrences
 * - regexFilters: interpret include/exclude values as regexes
 */
class CliArguments
{
    /** @var list<string>|null */
    public readonly ?array $include;

    /** @var list<string>|null */
    public readonly ?array $includeCategory;

    /** @var list<string>|null */
    public readonly ?array $includeTest;

    /** @var list<string>|null */
    public readonly ?array $exclude;

    /** @var list<string>|null */
    public readonly ?array $excludeCategory;

    /** @var list<string>|null */
    public readonly ?array $excludeTest;

    /**
     * @param list<string>|null $include
     * @param list<string>|null $includeCategory
     * @param list<string>|null $includeTest
     * @param list<string>|null $exclude
     * @param list<string>|null $excludeCategory
     * @param list<string>|null $excludeTest
     */
    public function __construct(
        public readonly string $testsDir,
        public readonly bool $recursive,
        public readonly ?string $output,
        public readonly bool $dryRun,
        ?array $include,
        ?array $includeCategory,
        ?array $includeTest,
        ?array $exclude,
        ?array $excludeCategory,
        ?array $excludeTest,
        public readonly int $verbose,
        public readonly bool $regexFilters
    ) {
        $this->include = $include;
        $this->includeCategory = $includeCategory;
        $this->includeTest = $includeTest;
        $this->exclude = $exclude;
        $this->excludeCategory = $excludeCategory;
        $this->excludeTest = $excludeTest;
    }
}
