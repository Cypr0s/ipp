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
 *         Kristian Luptak <xluptak00@stud.fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester;

use RuntimeException;
use IPP\Tester\Cli\CliArguments;
use IPP\Tester\Cli\CliParser;
use IPP\Tester\Model\CategoryReport;
use IPP\Tester\Model\TestCaseDefinition;
use IPP\Tester\Model\TestCaseDefinitionFile;
use IPP\Tester\Model\TestCaseReport;
use IPP\Tester\Model\TestCaseType;
use IPP\Tester\Model\TestReport;
use IPP\Tester\Model\TestResult;
use IPP\Tester\Model\UnexecutedReason;
use IPP\Tester\Model\UnexecutedReasonCode;
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
     * @var list<TestCaseDefinition>
     */
    private array $discovered_tests = [];

    /**
     * @var array<string, UnexecutedReason>
     */
    private array $unexecuted_tests = [];

    /**
     * @var array<string, CategoryReport>
     */
    private array $executed_tests = [];

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

        // get test cases
        $target_dir = $this->arguments->testsDir;
        $this->getTests($target_dir);
        // filter test_cases
        $filtered_tests = $this->filterTests();
        if ($this->arguments->dryRun) {
            $report = new TestReport(
                discoveredTestCases: $this->discovered_tests,
                unexecuted: $this->unexecuted_tests,
                results: []
            );

            self::writeResult($report);
            return 0;
        }
        $this->executeTests($filtered_tests);
        // Example of how to write the final report:
        $report = new TestReport(
            discoveredTestCases:  $this->discovered_tests,
            unexecuted: $this->unexecuted_tests,
            results: $this->executed_tests
        );
        self::writeResult($report);

        return 0;
    }


    public function getTests(string $target_dir): void
    {
        $dir = scandir($target_dir);
        if ($dir === false) {
            return;
        }
        $this->logger->debug("SCANNING DIR: name:" .  $target_dir);
        foreach ($dir as $file) {
            if ($file === '.' || $file === '..') {
                continue;
            }

            $target_file = $target_dir . '/' . $file;

            if (is_file($target_file) && \str_ends_with($target_file, '.test')) {
                $this->loadTestCase($target_dir, $file);
            }

            // recursive search if -r flag
            if ($this->arguments->recursive === true) {
                if (is_dir($target_file)) {
                    $this->getTests($target_file);
                }
            }
        }
    }

    private function loadTestCase(string $t_path, string $t_name): void
    {
        $full_test_path = $t_path . '/' . $t_name;
        $fd = fopen($full_test_path, 'r');
        $test_name = substr($t_name, 0, -5);
        if ($fd === false) {
            $message = 'Failed to open test file';
            $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                UnexecutedReasonCode::OTHER,
                $message
            );
            return;
        }
        $full_test_path_without_extension = substr($full_test_path, 0, -5);
        $test_description = null;
        $test_category = null;
        $test_points = null;
        $test_exit_codes_parser = [];
        $test_exit_codes_interpreter = [];
        $test_type = null;

        // loop through files
        while (true) {
            $line = fgets($fd);

            if ($line === false) {
                break;
            }
            $line = trim($line);
            if ($line === '') {
                break; // end of data
            }

            // description
            if (\str_starts_with($line, '***')) {
                if ($test_description !== null) {
                    $message = 'Multiple description lines';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                        $message
                    );
                    fclose($fd);
                    return;
                }
                $test_description = trim(substr($line, 3));
            } elseif (\str_starts_with($line, '+++')) {
                // category
                if ($test_category !== null) {
                    $message = 'Multiple category lines';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                        $message
                    );
                    fclose($fd);
                    return;
                }
                $test_category = trim(substr($line, 3));
            } elseif (\str_starts_with($line, '>>>')) {
                // points weight
                if ($test_points !== null) {
                    $message = 'Multiple points lines';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                        $message
                    );
                    fclose($fd);
                    return;
                }

                $points_str = trim(substr($line, 3));
                if (!is_numeric($points_str)) {
                    $message = 'Points value is not an integer';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                        $message
                    );
                    fclose($fd);
                    return;
                }
                $test_points = (int)$points_str;
            } elseif (\str_starts_with($line, '!C!')) {
                // SOL2XML expected exit code not required, multiple may appear
                $code_str = trim(substr($line, 3));
                if (!is_numeric($code_str)) {
                    $message = 'Exit code value is not an integer';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                        $message
                    );
                    fclose($fd);
                    return;
                }
                $test_exit_codes_parser[] = (int) $code_str;
            } elseif (\str_starts_with($line, '!I!')) {
                // SOL2XML expectet exit code not required, multiple may appear
                $code_str = trim(substr($line, 3));
                if (!is_numeric($code_str)) {
                    $message = 'Exit code value is not an integer';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                        $message
                    );
                    fclose($fd);
                    return;
                }
                $test_exit_codes_interpreter[] = (int) $code_str;
            } else {
                $message = 'Invalid arg';
                $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                    UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                    $message
                );
                fclose($fd);
                return;
            }
        }

        // get test type, check exit codes
        $first_program_line = fgets($fd);
        if ($first_program_line === false) {
            $message = 'No program code';
            $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                $message
            );
            fclose($fd);
            return;
        }
        $has_parser_codes = $test_exit_codes_parser !== [];
        $has_interpreter_codes = $test_exit_codes_interpreter !== [];

        // program is in XML
        if (str_starts_with(trim($first_program_line), '<?xml')) {
            if ($has_parser_codes) {
                $message = 'Test interpreter XML code has parser exit codes';
                $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                    UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                    $message
                );
                fclose($fd);
                return;
            }
            if (!$has_interpreter_codes) {
                $message = 'Test interpreter codes are missing but program is in XML';
                $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                    UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                    $message
                );
                fclose($fd);
                return;
            }
            $test_type = TestCaseType::EXECUTE_ONLY;
        } else {
            // program is in SOL26
            if ($has_parser_codes && $has_interpreter_codes) {
                if (!in_array(0, $test_exit_codes_parser, true)) {
                    $message = 'Code is supposed to be parsed and interptreted but 0 code for parser is missing';
                    $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                        UnexecutedReasonCode::CANNOT_DETERMINE_TYPE,
                        $message
                    );
                    fclose($fd);
                    return;
                }
                $test_type = TestCaseType::COMBINED;
            } elseif ($has_parser_codes) {
                $test_type = TestCaseType::PARSE_ONLY;
            } else {
                $message = 'Test parser codes are missing but code is in SOL26';
                $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                    UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                    $message
                );
                fclose($fd);
                return;
            }
        }

        // check required 'args'
        if ($test_category === null) {
            $message = 'Test category is missing';
            $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                $message
            );
            fclose($fd);
            return;
        }
        if ($test_points === null) {
            $message = 'Test points value is missing';
            $this->unexecuted_tests[$test_name] = new UnexecutedReason(
                UnexecutedReasonCode::MALFORMED_TEST_CASE_FILE,
                $message
            );
            fclose($fd);
            return;
        }

        // get oin file
        $test_in_file_name = $full_test_path_without_extension . '.in';
        $test_in_file = file_exists($test_in_file_name) ? $test_in_file_name : null;

        // get out file
        $test_out_file_name = $full_test_path_without_extension . '.out';
        $test_out_file = file_exists($test_out_file_name) ? $test_out_file_name : null;

        // create new TestCaseDefinition with created parameters
        $this->logger->debug("LOADING TEST: name:" .  $test_name);
        $this->discovered_tests[] = new TestCaseDefinition(
            name: $test_name,
            testSourcePath: $full_test_path,
            testType: $test_type,
            category: $test_category,
            stdinFile: $test_in_file,
            expectedStdoutFile: $test_out_file,
            description: $test_description,
            points: $test_points,
            expectedParserExitCodes: $test_exit_codes_parser === [] ? null : $test_exit_codes_parser,
            expectedInterpreterExitCodes: $test_exit_codes_interpreter === [] ? null : $test_exit_codes_interpreter,
        );
        fclose($fd);
    }

    /** @return list<TestCaseDefinition> */
    private function filterTests(): array
    {

        // filter includes
        $include = $this->arguments->include !== null ?
                    $this->arguments->include : [];
        $include_tests = $this->arguments->includeTest !== null ?
                        $this->arguments->includeTest : [];
        $include_categories = $this->arguments->includeCategory !== null ?
                                $this->arguments->includeCategory : [];
        $filtered_tests = [];
        if ($include !== [] || $include_tests !== [] || $include_categories !== []) {
            foreach ($this->discovered_tests as $test) {
                if (
                    in_array($test->name, $include, true) ||
                    in_array($test->category, $include, true) ||
                    in_array($test->name, $include_tests, true) ||
                    in_array($test->category, $include_categories, true)
                ) { 
                    $this->logger->debug("Filter: test included: name:" .  $test->name);
                    $filtered_tests[] = $test;
                } else {
                    $message = "Test file was not included";
                    $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                        UnexecutedReasonCode::FILTERED_OUT,
                        $message
                    );
                }
            }
        } else {
            $filtered_tests = $this->discovered_tests;
        }

        // exclude
        $exclude = $this->arguments->exclude !== null ?
                    $this->arguments->exclude : [];
        $exclude_tests = $this->arguments->excludeTest !== null ?
                            $this->arguments->excludeTest : [];
        $exclude_categories = $this->arguments->excludeCategory !== null ?
                                $this->arguments->excludeCategory : [];

        if ($exclude !== [] || $exclude_tests !== [] || $exclude_categories !== []) {
            $exclude_filtered = [];
            foreach ($filtered_tests as $test) {
                if (
                    !in_array($test->name, $exclude, true) &&
                    !in_array($test->category, $exclude, true) &&
                    !in_array($test->name, $exclude_tests, true) &&
                    !in_array($test->category, $exclude_categories, true)
                ) {
                    $this->logger->debug("Filter: test excluded: name:" .  $test->name);
                    $exclude_filtered[] = $test;
                } else {
                    $message = "Test file was excluded";
                    $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                        UnexecutedReasonCode::FILTERED_OUT,
                        $message
                    );
                }
            }
            return $exclude_filtered;
        }
        return $filtered_tests;
    }

    /** @param list<TestCaseDefinition> $tests */
    public function executeTests(array $tests): void
    {
        $total_points = [];
        $passed_points = [];
        $test_results = [];

        foreach ($tests as $test) {
            // firstly try to create category
            $this->logger->debug("Execute: name:" .  $test->name);
            if (!isset($total_points[$test->category])) {
                $total_points[$test->category] = 0;
                $passed_points[$test->category] = 0;
                $test_results[$test->category] = [];
            }


            // create temp file
            $lines = file($test->testSourcePath);
            if ($lines === false) {
                $message = "Failed to open test file";
                $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                    UnexecutedReasonCode::CANNOT_EXECUTE,
                    $message
                );
                continue;
            }

            $i = 0;
            while (trim($lines[$i]) !== '') {
                $i++;
            }

            $source_code = implode('', array_slice($lines, $i + 1));
            $temp_file = "/tester/tmp.out";
            file_put_contents($temp_file, $source_code);

            $total_points[$test->category] += $test->points;

            // parsing only, create object of result
            if ($test->testType === TestCaseType::PARSE_ONLY) {
                $vals = $this->runParser($test, $temp_file);
                if ($vals[0] === null) {
                    continue;
                }

                $test_result = TestResult::PASSED;
                if (
                    $test->expectedParserExitCodes === null ||
                    !in_array($vals[0], $test->expectedParserExitCodes)
                ) {
                    $test_result = TestResult::UNEXPECTED_PARSER_EXIT_CODE;
                }

                $test_results[$test->category][$test->name] = new TestCaseReport(
                    result: $test_result,
                    parserExitCode: $vals[0],
                    interpreterExitCode: null,
                    parserStdout: $vals[1],
                    parserStderr: $vals[2],
                    interpreterStdout: null,
                    interpreterStderr: null,
                    diffOutput: null
                );
                if ($test_result === TestResult::PASSED) {
                    $passed_points[$test->category] += $test->points;
                }
            } elseif ($test->testType === TestCaseType::EXECUTE_ONLY) {
                // interpreter execute
                $interpreter_vals = $this->runInterpreter($test, $temp_file);
                if ($interpreter_vals[0] === null) {
                    continue;
                }


                $diff_vals = [TestResult::PASSED, null];
                if (
                    $test->expectedInterpreterExitCodes === null ||
                    !in_array($interpreter_vals[0], $test->expectedInterpreterExitCodes)
                ) {
                    $diff_vals[0] = TestResult::UNEXPECTED_INTERPRETER_EXIT_CODE;
                } elseif ($interpreter_vals[0] === 0 && $test->expectedStdoutFile !== null) {
                    $diff_vals = $this->runGnuDiff($test, $temp_file);
                    if ($diff_vals[0] === null) {
                        continue;
                    }
                }

                $test_results[$test->category][$test->name] = new TestCaseReport(
                    result: $diff_vals[0],
                    parserExitCode: null,
                    interpreterExitCode: $interpreter_vals[0],
                    parserStdout: null,
                    parserStderr: null,
                    interpreterStdout: $interpreter_vals[1],
                    interpreterStderr: $interpreter_vals[2],
                    diffOutput: $diff_vals[1]
                );

                if ($diff_vals[0] === TestResult::PASSED) {
                    $passed_points[$test->category] += $test->points;
                }
            } else {
                $parser_vals = $this->runParser($test, $temp_file);
                if ($parser_vals[0] === null) {
                    continue;
                }

                if ($parser_vals[0] !== 0) {
                    $test_result = TestResult::UNEXPECTED_PARSER_EXIT_CODE;
                    $test_results[$test->category][$test->name] = new TestCaseReport(
                        result: $test_result,
                        parserExitCode: $parser_vals[0],
                        interpreterExitCode: null,
                        parserStdout: $parser_vals[1],
                        parserStderr: $parser_vals[2],
                        interpreterStdout: null,
                        interpreterStderr: null,
                        diffOutput: null
                    );
                } else {
                    $interpreter_vals = $this->runInterpreter($test, $temp_file);
                    if ($interpreter_vals[0] === null) {
                        continue;
                    }

                    $diff_vals = [TestResult::PASSED, null];
                    if (
                        $test->expectedInterpreterExitCodes === null ||
                        !in_array($interpreter_vals[0], $test->expectedInterpreterExitCodes)
                    ) {
                        $diff_vals[0] = TestResult::UNEXPECTED_INTERPRETER_EXIT_CODE;
                    } elseif ($interpreter_vals[0] === 0 && $test->expectedStdoutFile !== null) {
                        $diff_vals = $this->runGnuDiff($test, $temp_file);
                        if ($diff_vals[0] === null) {
                            continue;
                        }
                    }

                    $test_results[$test->category][$test->name] = new TestCaseReport(
                        result: $diff_vals[0],
                        parserExitCode: $parser_vals[0],
                        interpreterExitCode: $interpreter_vals[0],
                        parserStdout: $parser_vals[1],
                        parserStderr: $parser_vals[2],
                        interpreterStdout: $interpreter_vals[1],
                        interpreterStderr: $interpreter_vals[2],
                        diffOutput: $diff_vals[1]
                    );

                    if ($diff_vals[0] === TestResult::PASSED) {
                        $passed_points[$test->category] += $test->points;
                    }
                }
            }
        }
        foreach ($total_points as $category => $points) {
            $this->executed_tests[$category] = new CategoryReport(
                $points,
                $passed_points[$category],
                $test_results[$category]
            );
        }
    }

    /** @return array{int|null, string|null, string|null} */
    private function runParser(TestCaseDefinition $test, string $temp_file): array
    {
        $process = proc_open("python3 /tester/sol2xml/sol_to_xml.py", [
            0 => ['file', $temp_file, 'r'], // stdin
            1 => ['pipe', 'w'],  // stdout
            2 => ['pipe', 'w'],  // stderr
        ], $pipes);

        if ($process === false) {
            $message = "Failure running parser";
            $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                UnexecutedReasonCode::CANNOT_EXECUTE,
                $message
            );
            return [null, null, null];
        }

        $stdout = stream_get_contents($pipes[1]);
        $stderr = stream_get_contents($pipes[2]);

        if ($stdout === false || $stderr === false) {
            fclose($pipes[1]);
            fclose($pipes[2]);
            proc_close($process);
            $message = "Failure running parser, missing stdout or stderr";
            $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                UnexecutedReasonCode::CANNOT_EXECUTE,
                $message
            );
            return [null, null, null];
        }

        fclose($pipes[1]);
        fclose($pipes[2]);

        $exit_code = proc_close($process);
        if ($exit_code === 0) {
            file_put_contents($temp_file, $stdout);
        }

        return [$exit_code, $stdout, $stderr];
    }

    /** @return array{int|null, string|null, string|null} */
    private function runInterpreter(TestCaseDefinition $test, string $temp_file): array
    {
        $command = "python3 /int/src/solint.py -s $temp_file";
        if ($test->stdinFile !== null) {
            $command = $command . " -i $test->stdinFile";
        }
        $process = proc_open($command, [
            1 => ['pipe', 'w'],  // stdout
            2 => ['pipe', 'w'],  // stderr
        ], $pipes);

        if ($process === false) {
            $message = "Failure running interpreter";
            $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                UnexecutedReasonCode::CANNOT_EXECUTE,
                $message
            );
            return [null, null, null];
        }

        $stdout = stream_get_contents($pipes[1]);
        $stderr = stream_get_contents($pipes[2]);
        if ($stdout === false || $stderr === false) {
            fclose($pipes[1]);
            fclose($pipes[2]);
            proc_close($process);
            $message = "Failure running interpreter, missing stdout or stderr";
            $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                UnexecutedReasonCode::CANNOT_EXECUTE,
                $message
            );
            return [null, null, null];
        }

        fclose($pipes[1]);
        fclose($pipes[2]);

        $exit_code = proc_close($process);

        if ($exit_code === 0) {
            file_put_contents($temp_file, $stdout);
        }

        return [$exit_code, $stdout, $stderr];
    }

    /** @return array{TestResult|null, string|null} */
    private function runGnuDiff(TestCaseDefinition $test, string $temp_file): array
    {
        $diff_stdout = null;

        $diff_exit_code = 0;
        $result = exec("diff $temp_file $test->expectedStdoutFile", $diff_stdout, $diff_exit_code);
        if ($result === false || $diff_exit_code === -1) {
            $message = "Failure running gnu diff";
            $this->unexecuted_tests[$test->name] = new UnexecutedReason(
                UnexecutedReasonCode::CANNOT_EXECUTE,
                $message
            );
            return [null, null];
        }
        $diff_stdout = implode("\n", $diff_stdout);


        if ($diff_exit_code !== 0) {
            return [TestResult::INTERPRETER_RESULT_DIFFERS, $diff_stdout];
        }
        return [TestResult::PASSED, $diff_stdout];
    }
}
