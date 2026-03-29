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
 * Represents the report generated after processing the test cases.
 */
class TestReport implements JsonSerializable
{
    /** @var list<TestCaseDefinition> Successfully parsed discovered test cases. */
    public readonly array $discoveredTestCases;

    /** @var array<string, UnexecutedReason> Tests skipped with reason by test name. */
    public readonly array $unexecuted;

    /** @var array<string, CategoryReport>|null Results grouped by category. */
    public readonly ?array $results;

    /**
     * @param list<TestCaseDefinition> $discoveredTestCases
     * @param array<string, UnexecutedReason> $unexecuted
     * @param array<string, CategoryReport>|null $results
     * `results` is omitted from JSON when null or empty.
     */
    public function __construct(
        array $discoveredTestCases = [],
        array $unexecuted = [],
        ?array $results = null
    ) {
        $this->discoveredTestCases = $discoveredTestCases;
        $this->unexecuted = $unexecuted;
        $this->results = $results;
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        $serializedDiscoveredTestCases = [];

        foreach ($this->discoveredTestCases as $testCase) {
            $serializedDiscoveredTestCases[] = $testCase->toArray();
        }

        $serializedUnexecuted = [];

        foreach ($this->unexecuted as $testName => $reason) {
            $serializedUnexecuted[$testName] = $reason->toArray();
        }

        $data = [
            'discovered_test_cases' => $serializedDiscoveredTestCases,
            // Keep empty maps as JSON object `{}` for schema compatibility.
            'unexecuted' => $serializedUnexecuted === [] ? (object) [] : $serializedUnexecuted,
        ];

        if ($this->results !== null && $this->results !== []) {
            $serializedResults = [];

            foreach ($this->results as $category => $categoryReport) {
                $serializedResults[$category] = $categoryReport->toArray();
            }

            $data['results'] = $serializedResults;
        }

        return $data;
    }

    /**
     * @return array<string, mixed>
     */
    public function jsonSerialize(): array
    {
        return $this->toArray();
    }
}
