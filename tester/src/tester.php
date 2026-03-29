<?php

/**
 * An integration testing script for the SOL26 interpreter.
 *
 * This file is the executable entrypoint only: it delegates CLI parsing and
 * report generation to application classes under the `IPP\Tester` namespace.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

require __DIR__ . '/../vendor/autoload.php';

use IPP\Tester\TesterApp;
use IPP\Tester\Cli\CliArgumentsException;

/** @var list<string> $argv */
$argv = $_SERVER['argv'] ?? [];

try {
    $app = new TesterApp($argv);
    exit($app->run());
} catch (CliArgumentsException $e) {
    // This exception is also used for "successful" CLI exit after using --help
    if ($e->getMessage() !== '') {
        fwrite(STDERR, $e->getMessage() . PHP_EOL);
    }
    exit($e->exitCode);
}
