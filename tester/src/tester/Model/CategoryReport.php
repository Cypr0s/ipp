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
 * Represents the report for a category of test cases.
 */
class CategoryReport implements JsonSerializable
{
    /** @var array<string, TestCaseReport> */
    public readonly array $testResults;

    /**
     * @param int $totalPoints Sum of points for all executed tests in category
     * @param int $passedPoints Sum of points gained for passed tests in category
     * @param array<string, TestCaseReport> $testResults
     */
    public function __construct(
        public readonly int $totalPoints,
        public readonly int $passedPoints,
        array $testResults
    ) {
        $this->testResults = $testResults;
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        $serializedResults = [];

        foreach ($this->testResults as $testName => $report) {
            $serializedResults[$testName] = $report->toArray();
        }

        return [
            'total_points' => $this->totalPoints,
            'passed_points' => $this->passedPoints,
            // Encode empty maps as JSON object `{}` instead of `[]`.
            'test_results' => $serializedResults === [] ? (object) [] : $serializedResults,
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
