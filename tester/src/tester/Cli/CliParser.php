<?php

/**
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 *
 * AI usage notice: The author used OpenAI Codex to create the implementation of this
 *                  module based on its Python counterpart.
 */

declare(strict_types=1);

namespace IPP\Tester\Cli;

use Psr\Log\LoggerInterface;
use Symfony\Component\Console\Exception\ExceptionInterface as ConsoleException;
use Symfony\Component\Console\Input\ArgvInput;
use Symfony\Component\Console\Input\InputArgument;
use Symfony\Component\Console\Input\InputDefinition;
use Symfony\Component\Console\Input\InputOption;

/**
 * Parses CLI arguments for the tester.
 *
 * The supported options intentionally mirror the Python/TypeScript templates
 * and the project specification in `ipp26.tex`.
 */
class CliParser
{
    private const HELP_TEXT = [
        'Usage:',
        '  tester [options] tests_dir',
        '',
        'Positional arguments:',
        '  tests_dir                 Path to a directory with the test cases in the SOLtest format.',
        '',
        'Options:',
        '  -h, --help                Show this help message and exit.',
        '  -r, --recursive           Recursively search for test cases in subdirectories of the provided directory.',
        '  -o, --output <path>       The output file to write the test results to.'
        . ' If not provided, results will be printed to standard output.',
        '  --dry-run                 Perform a dry run: discover the test cases but do not execute them.',
        '  -i, --include <value>     Include only test cases with the specified name or category.'
        . ' Can be used multiple times.',
        '  -ic, --include-category <value>',
        '                            Include only test cases with the specified category. Can be used multiple times.',
        '  -it, --include-test <value>',
        '                            Include only test cases with the specified name. Can be used multiple times.',
        '  -e, --exclude <value>     Exclude test cases with the specified name or category.'
        . ' Can be used multiple times.',
        '  -ec, --exclude-category <value>',
        '                            Exclude test cases with the specified category. Can be used multiple times.',
        '  -et, --exclude-test <value>',
        '                            Exclude test cases with the specified name. Can be used multiple times.',
        '  -g, --regex-filters       Interpret include/exclude filters as regular expressions.',
        '  -v, --verbose             Enable verbose logging output'
        . ' (using once = INFO level, using twice = DEBUG level).',
    ];

    /**
     * @param list<string> $argv
     * @return list<string>
     */
    public static function normalizeArgv(array $argv): array
    {
        // Symfony treats short option sets (e.g. `-ic`) as `-i -c`.
        // For IPP flags, `-ic/-it/-ec/-et` are distinct options, so we rewrite
        // them to long-form before parsing.
        $normalized = [];

        foreach ($argv as $argument) {
            if ($argument === '-ic') {
                $normalized[] = '--include-category';
                continue;
            }

            if ($argument === '-it') {
                $normalized[] = '--include-test';
                continue;
            }

            if ($argument === '-ec') {
                $normalized[] = '--exclude-category';
                continue;
            }

            if ($argument === '-et') {
                $normalized[] = '--exclude-test';
                continue;
            }

            if (str_starts_with($argument, '-ic=')) {
                $normalized[] = '--include-category=' . substr($argument, 4);
                continue;
            }

            if (str_starts_with($argument, '-it=')) {
                $normalized[] = '--include-test=' . substr($argument, 4);
                continue;
            }

            if (str_starts_with($argument, '-ec=')) {
                $normalized[] = '--exclude-category=' . substr($argument, 4);
                continue;
            }

            if (str_starts_with($argument, '-et=')) {
                $normalized[] = '--exclude-test=' . substr($argument, 4);
                continue;
            }

            $normalized[] = $argument;
        }

        return $normalized;
    }

    /**
     * @param list<string> $argv
     */
    private static function containsHelpOption(array $argv): bool
    {
        // Manual help detection keeps output stable with the provided template.
        foreach (array_slice($argv, 1) as $argument) {
            if ($argument === '--') {
                break;
            }

            if ($argument === '-h' || $argument === '--help') {
                return true;
            }
        }

        return false;
    }

    private static function printHelp(): void
    {
        fwrite(STDOUT, implode(PHP_EOL, self::HELP_TEXT) . PHP_EOL);
    }

    /**
     * Builds the Symfony CLI schema (positional args + options).
     */
    private static function buildInputDefinition(): InputDefinition
    {
        return new InputDefinition([
            new InputArgument(
                'tests_dir',
                InputArgument::REQUIRED,
                'Path to a directory with the test cases in the SOLtest format.'
            ),
            new InputOption(
                'recursive',
                'r',
                InputOption::VALUE_NONE,
                'Recursively search for test cases in subdirectories of the provided directory.'
            ),
            new InputOption(
                'output',
                'o',
                InputOption::VALUE_REQUIRED,
                'The output file to write the test results to. If not provided, results are printed to standard output.'
            ),
            new InputOption(
                'dry-run',
                null,
                InputOption::VALUE_NONE,
                'Perform a dry run: discover test cases but do not execute them.'
            ),
            new InputOption(
                'include',
                'i',
                InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                'Include only test cases with the specified name or category. Can be used multiple times.'
            ),
            new InputOption(
                'include-category',
                null,
                InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                'Include only test cases with the specified category. Can be used multiple times.'
            ),
            new InputOption(
                'include-test',
                null,
                InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                'Include only test cases with the specified name. Can be used multiple times.'
            ),
            new InputOption(
                'exclude',
                'e',
                InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                'Exclude test cases with the specified name or category. Can be used multiple times.'
            ),
            new InputOption(
                'exclude-category',
                null,
                InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                'Exclude test cases with the specified category. Can be used multiple times.'
            ),
            new InputOption(
                'exclude-test',
                null,
                InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                'Exclude test cases with the specified name. Can be used multiple times.'
            ),
            new InputOption(
                'regex-filters',
                'g',
                InputOption::VALUE_NONE,
                'Interpret include/exclude filters as regular expressions.'
            ),
            new InputOption(
                'verbose',
                'v',
                InputOption::VALUE_NONE,
                'Enable verbose logging output (using once = INFO level, using twice = DEBUG level).'
            ),
        ]);
    }

    /**
     * @param list<string> $argv
     */
    public static function parseArguments(LoggerInterface $logger, array $argv): CliArguments
    {
        $argv = CliParser::normalizeArgv($argv);

        if (self::containsHelpOption($argv)) {
            self::printHelp();
            throw new CliArgumentsException("", 0);
        }

        try {
            $input = new ArgvInput($argv, self::buildInputDefinition());
        } catch (ConsoleException $e) {
            // Invalid CLI syntax/values are treated as argument errors (exit code 2).
            throw new CliArgumentsException($e->getMessage(), 2);
        }

        $testsDirValue = $input->getArgument('tests_dir');
        if (!\is_string($testsDirValue) || $testsDirValue === '') {
            throw new CliArgumentsException('Exactly one positional argument (tests_dir) is required.', 2);
        }

        if (!is_dir($testsDirValue)) {
            throw new CliArgumentsException('The provided path is not a directory.', 1);
        }

        $testsDir = $testsDirValue;
        $resolvedTestsDir = realpath($testsDir);
        if (\is_string($resolvedTestsDir)) {
            $testsDir = $resolvedTestsDir;
        }

        $outputValue = $input->getOption('output');
        if ($outputValue !== null && !\is_string($outputValue)) {
            throw new CliArgumentsException('Invalid --output value.', 2);
        }

        if (\is_string($outputValue)) {
            $outputParent = dirname($outputValue);

            if (!is_dir($outputParent)) {
                throw new CliArgumentsException(
                    'The parent directory of the output file does not exist.',
                    1
                );
            }

            if (file_exists($outputValue)) {
                // Overwrite is allowed, but should be visible in logs.
                $logger->warning(
                    'The output file will be overwritten: {output_file}',
                    ['output_file' => $outputValue]
                );
            }
        }

        return new CliArguments(
            testsDir: $testsDir,
            recursive: (bool) $input->getOption('recursive'),
            output: $outputValue,
            dryRun: (bool) $input->getOption('dry-run'),
            include: self::sanitizeFilterValues($input->getOption('include'), '--include'),
            includeCategory: self::sanitizeFilterValues(
                $input->getOption('include-category'),
                '--include-category'
            ),
            includeTest: self::sanitizeFilterValues($input->getOption('include-test'), '--include-test'),
            exclude: self::sanitizeFilterValues($input->getOption('exclude'), '--exclude'),
            excludeCategory: self::sanitizeFilterValues(
                $input->getOption('exclude-category'),
                '--exclude-category'
            ),
            excludeTest: self::sanitizeFilterValues($input->getOption('exclude-test'), '--exclude-test'),
            verbose: self::countVerboseFlags($argv),
            regexFilters: (bool) $input->getOption('regex-filters')
        );
    }

    /**
     * @param mixed $rawValues
     * @return list<string>|null
     */
    private static function sanitizeFilterValues(mixed $rawValues, string $optionName): ?array
    {
        if (!is_array($rawValues)) {
            throw new CliArgumentsException(sprintf('Invalid value for option %s.', $optionName), 2);
        }

        if ($rawValues === []) {
            return null;
        }

        $normalized = [];

        foreach ($rawValues as $value) {
            if (!\is_string($value)) {
                throw new CliArgumentsException(
                    sprintf('Invalid value for option %s.', $optionName),
                    2
                );
            }

            $trimmedValue = trim($value);
            if ($trimmedValue === '') {
                throw new CliArgumentsException(
                    sprintf('Option %s requires a non-empty value.', $optionName),
                    2
                );
            }

            $normalized[] = $trimmedValue;
        }

        return $normalized;
    }

    /**
     * @param list<string> $argv
     */
    private static function countVerboseFlags(array $argv): int
    {
        // Symfony VALUE_NONE option cannot count multiple occurrences by itself,
        // so we derive the count from raw argv (`-v`, `-vv`, `--verbose`).
        $count = 0;

        foreach (array_slice($argv, 1) as $argument) {
            if ($argument === '--') {
                break;
            }

            if ($argument === '--verbose' || $argument === '-v') {
                $count++;
                continue;
            }

            if (preg_match('/^-v{2,}$/', $argument) === 1) {
                $count += strlen($argument) - 1;
            }
        }

        return $count;
    }
}
