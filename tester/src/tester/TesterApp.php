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
use IPP\Tester\Model\TestCaseDefinition;
use IPP\Tester\Model\TestCaseType;
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
       
        # get test cases
        $tests = [];
        $target_dir = $this->arguments->testsDir;
        $this->get_tests($target_dir,$tests);
        if($this->arguments->dryRun) {
            $report = new TestReport(discoveredTestCases: $tests, unexecuted: [], results: []);
            self::writeResult($report);
            return 0;
        }
        #filter test_cases
        $filtered_tests = $this->filter_tests($tests);
        // Example of how to write the final report:
        $report = new TestReport(discoveredTestCases: [], unexecuted: [], results: []);
        self::writeResult($report);

        return 0;
    }

    public function get_tests(string $targetDir, array &$testCases): void {
        foreach(scandir($targetDir) as $file) {
            if($file === '.' || $file === '..') {
                continue;
            }

            $target_file = $targetDir . '/' . $file;

            if (is_file($target_file) && \str_ends_with($target_file, '.test')) {
                $testCases[] = ($this->load_test_case($targetDir, $file));
            }

            # recursive search if -r flag
            if($this->arguments->recursive === true) {
                if(is_dir($target_file)) {
                    $this->get_tests($target_file, $testCases);
                }
            }
        }
    }

    private function load_test_case(string $test_path, string $test_name): TestCaseDefinition {
        $full_test_path = $test_path . '/' . $test_name;
        $fd = fopen($full_test_path, "r");
        if ($fd === false) {
            throw new RuntimeException(
                sprintf('Failed to open test file: %s', $full_test_path)
            );
        }
        $full_test_path_without_extension = substr($full_test_path, 0, -5);
        $test_description = null;
        $test_category = null;
        $test_points = null;
        $test_exit_codes_compiler = [];
        $test_exit_codes_interpreter = [];
        $test_type = null;
        
        #loop through files
        while (true) {
            $line = fgets($fd);

            if($line === false) {
                break;
            }
            $line = trim($line);
            if ($line === '') {
                break; // end of data
            }

            # description 
            if(\str_starts_with($line, '***')) {
                if($test_description !== null) {
                    throw new RuntimeException(
                        sprintf('Multiple description lines in test file %s', $full_test_path)
                    );
                }
                $test_description = trim(substr($line, 3));
            }
            # category
            else if(\str_starts_with($line, '+++')) {
                if($test_category !== null) {
                    throw new RuntimeException(
                        sprintf('Multiple category lines in test file: %s', $full_test_path)
                    );
                }
                $test_category = trim(substr($line, 3));
            }
            # points weight
            else if(\str_starts_with($line, '>>>')) {
                if($test_points !== null) {
                    throw new RuntimeException(
                        sprintf('Multiple points lines in test file: %s', $full_test_path)
                    );
                }

                $points_str = trim(substr($line, 3));
                if (!is_numeric($points_str)) {
                    throw new RuntimeException(
                        sprintf('Points value is not an integer in test file: %s', $full_test_path)
                    );
                }
                $test_points = (int)$points_str;
            }
            # SOL2XML expected exit code not required, multiple may appear
            else if(\str_starts_with($line, '!C!')) {
                $code_str = trim(substr($line, 3));
                if (!is_numeric($code_str)) {
                    throw new RuntimeException(
                        sprintf('Points value is not an integer in test file: %s', $full_test_path)
                    );
                }
                $test_exit_codes_compiler[] = (int) $code_str;
            }
            #SOL2XML expectet exit code not required, multiple may appear
            else if(\str_starts_with($line, '!I!')) {
                $code_str = trim(substr($line, 3));
                if (!is_numeric($code_str)) {
                    throw new RuntimeException(
                        sprintf('Points value is not an integer in test file: %s', $full_test_path)
                    );
                }
                $test_exit_codes_interpreter[] = (int) $code_str;
            }
            else {
                 throw new RuntimeException(
                    sprintf('Invalid arg in test file: %s', $full_test_path)
                );
            }
        }
        
        # get test type, check exit codes
        $first_program_line = fgets($fd);
        if($first_program_line === false) {
            throw new RuntimeException(
                sprintf('No code program in test file: %s', $full_test_path)
            );
        }
        $has_compiler_codes = $test_exit_codes_compiler !== [];
        $has_interpreter_codes = $test_exit_codes_interpreter !== [];

        #program is in XML
        if(!strcmp(trim($first_program_line), '<?xml version="1.0" encoding="UTF-8"?>')) {
            if($has_compiler_codes) {
                throw new RuntimeException(
                    sprintf('Test interpreter XML code has compiler codes: %s', $full_test_path)
                );
            }
            if(!$has_interpreter_codes) {
                throw new RuntimeException(
                    sprintf('Test interpreter codes are missing but program is in XML in test file: %s', $full_test_path)
                );
            }
            $test_type = TestCaseType::EXECUTE_ONLY;
        }
        #program is in SOL26
        else {
            if($has_compiler_codes && $has_interpreter_codes) {
                $test_type = TestCaseType::COMBINED;
            }
            else if($has_compiler_codes) {
                $test_type = TestCaseType::PARSE_ONLY;
            }
            else {
                throw new RuntimeException(
                    sprintf('Test compiler codes are missing but code is in SOL26 in test file: %s', $full_test_path)
                );
            }
        }

        #check required 'args'
        if($test_category === null) {
            throw new RuntimeException(
                sprintf('Test category is missing in test file: %s', $full_test_path)
            );
        }
        if($test_points === null) {
            throw new RuntimeException(
                sprintf('Test points value is missing in test file: %s', $full_test_path)
            );
        }

        # get oin file
        $test_in_file_name = $full_test_path_without_extension . '.in';
        $test_in_file = file_exists($test_in_file_name) ? $test_in_file_name : null;
        
        # get out file
        $test_out_file_name = $full_test_path_without_extension . '.out';
        $test_out_file = file_exists($test_out_file_name) ? $test_out_file_name : null;
        fclose($fd);
        # create new TestCaseDefinition with created parameters
        return new TestCaseDefinition(
            name: substr($test_name, 0, -5),
            testSourcePath: $full_test_path,
            testType: $test_type,
            category: $test_category,
            stdinFile: $test_in_file,
            expectedStdoutFile: $test_out_file,
            description: $test_description,
            points: $test_points,
            expectedParserExitCodes: $test_exit_codes_compiler,
            expectedInterpreterExitCodes: $test_exit_codes_interpreter,
        );
    }

    private function filter_tests(array $tests): array {

        # filter includes
        $include = $this->arguments->include !== null ? $this->arguments->include : [];
        $include_tests = $this->arguments->includeTest !== null ? $this->arguments->includeTest : [];
        $include_categories = $this->arguments->includeCategory !== null ? $this->arguments->includeCategory : [];
        $filtered_tests = [];
        if($include !== [] || $include_tests !== [] || $include_categories !== []) {
            foreach($tests as $test) {
                if(in_array($test->name, $include, true) || 
                    in_array($test->category, $include,true) || 
                    in_array($test->name, $include_tests, true) ||
                    in_array($test->category, $include_categories, true)) {
                    $filtered_tests[] = $test;
                }
            }
        }
        else {
            $filtered_tests = $tests;
        }

        #exclude
        $exclude =  $this->arguments->exclude !== null ? $this->arguments->exclude : [];
        $exclude_tests = $this->arguments->excludeTest !== null ? $this->arguments->excludeTest : [];
        $exclude_categories = $this->arguments->excludeCategory !== null ? $this->arguments->excludeCategory : [];

        if($exclude !== [] || $exclude_tests !== [] || $exclude_categories !== []) {
            $exclude_filtered = [];
            foreach($filtered_tests as $test) {
                if(!in_array($test->name, $exclude, true) &&
                    !in_array($test->category, $exclude, true) &&
                    !in_array($test->name, $exclude_tests, true) &&
                    !in_array($test->category, $exclude_categories, true)) {
                    $exclude_filtered[] = $test;
                }
            }
            return $exclude_filtered;
        }
        return $filtered_tests;
    }

    public function run_tests(array $tests): void{
        return;
    }
}