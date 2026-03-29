<?php

/**
 * An integration testing script for the SOL26 interpreter.
 *
 * IPP: You can implement the entire tool in this file if you wish, but it is recommended to split
 *      the code into multiple files and modules as you see fit.
 *
 *      Below, you have some code to get you started with the CLI argument parsing and logging setup,
 *      but you are **free to modify it** in whatever way you like.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester;

use RuntimeException;
use IPP\Tester\Cli\CliArguments;
use IPP\Tester\Cli\CliParser;
use IPP\Tester\Model\TestReport;
use Monolog\Formatter\LineFormatter;
use Monolog\Handler\AbstractHandler;
use Monolog\Handler\StreamHandler;
use Monolog\Level;
use Monolog\Logger;
use Monolog\Processor\IntrospectionProcessor;
use Monolog\Processor\PsrLogMessageProcessor;

/**
 * Coordinates the tester workflow: parse CLI args, configure logging, and
 * produce the final JSON report.
 */
class TesterApp
{
    /**
     * Configures the default logger.
     *
     * Logging level defaults to warning and can be raised by `-v` flags.
     *
     * IPP: You do not have to use logging – but it is the recommended practice.
     * See this for more information: https://seldaek.github.io/monolog/
     */
    private static function createLogger(): Logger
    {
        $logger = new Logger('main');
        $handler = new StreamHandler('php://stderr', Level::Warning);
        $handler->setFormatter(
            new LineFormatter(
                "%datetime% %level_name% [%channel%][%extra.class%:%extra.line%] %message%\n",
                'Y-m-d H:i:s',
                true,
                true,
                true
            )
        );

        $logger->pushProcessor(new PsrLogMessageProcessor());
        $logger->pushProcessor(new IntrospectionProcessor(Level::Debug));
        $logger->pushHandler($handler);

        return $logger;
    }

    private readonly Logger $logger;
    private readonly CliArguments $arguments;

    /**
     * @param list<string> $argv
     */
    public function __construct(array $argv)
    {
        // Set up logging
        $this->logger = TesterApp::createLogger();
        // Parse and validate command-line arguments before running the tool.
        $this->arguments = CliParser::parseArguments($this->logger, argv: $argv);
        // Verbosity affects only the selected log level.
        $this->configureLoggerVerbosity();
    }

    /**
     * Configures the logger based on the `-v` count.
     * 0 => warning, 1 => info, >=2 => debug.
     */
    private function configureLoggerVerbosity(): void
    {
        $level = Level::Warning;
        $verbosity = $this->arguments->verbose;

        if ($verbosity >= 2) {
            $level = Level::Debug;
        } elseif ($verbosity === 1) {
            $level = Level::Info;
        }

        foreach ($this->logger->getHandlers() as $handler) {
            if ($handler instanceof AbstractHandler) {
                $handler->setLevel($level);
            }
        }
    }

    /**
     * Writes the serialized JSON report either to file or stdout.
     */
    private function writeResult(TestReport $resultReport): void
    {
        $resultJson = json_encode($resultReport->toArray(), JSON_PRETTY_PRINT);

        if (!\is_string($resultJson)) {
            throw new RuntimeException('Failed to serialize report to JSON.');
        }

        $outputFile = $this->arguments->output;
        if ($outputFile !== null) {
            $written = file_put_contents($outputFile, $resultJson);

            if ($written === false) {
                throw new RuntimeException(
                    sprintf('Failed to write output file: %s', $outputFile)
                );
            }

            return;
        }

        fwrite(STDOUT, $resultJson . PHP_EOL);
    }

    /**
     * Executes the testing logic.
     *
     * @return int The process exit code.
     */
    public function run(): int
    {
        // TODO: Your code for discovering and executing the test cases goes here.

        // Example of how to write the final report:
        $report = new TestReport(discoveredTestCases: [], unexecuted: [], results: []);
        self::writeResult($report);

        return 0;
    }
}
