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
 * Represents the reason why a test case was not executed, including an
 * optional human-readable message.
 *
 * IPP: The exact message wording is up to the implementation.
 */
class UnexecutedReason implements JsonSerializable
{
    public function __construct(
        public readonly UnexecutedReasonCode $code,
        public readonly ?string $message = null
    ) {
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        return [
            'code' => $this->code->value,
            'message' => $this->message,
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
