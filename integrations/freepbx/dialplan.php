<?php
declare(strict_types=1);

final class FreepbxGatewayDialplan
{
    public static function render(array $routes): string
    {
        $lines = [
            '; Managed by Asterisk AI Agent Gateway. Changes are generated from route state.',
            '[from-ai-gateway-managed]',
        ];
        usort($routes, static fn(array $a, array $b): int => strcmp($a['number'], $b['number']));
        foreach ($routes as $route) {
            $number = FreepbxValidation::didNumber($route['number']);
            $lines[] = 'exten => ' . $number . ',1,NoOp(Asterisk AI Agent Gateway managed DID)';
            $lines[] = ' same => n,Set(AI_GATEWAY_DID=' . $number . ')';
            $lines[] = ' same => n,Stasis(asterisk-ai-gateway)';
            $lines[] = ' same => n,Hangup()';
        }
        return implode("\n", $lines) . "\n";
    }

    public static function ensureInclude(string $contents): string
    {
        $lines = preg_split('/\R/', $contents) ?: [];
        $result = [];
        $seen = false;
        foreach ($lines as $line) {
            if (preg_match('/^\s*#(?:try)?include\s+(?:\/etc\/asterisk\/)?extensions_gateway_managed\.conf\s*$/', $line)) {
                if (!$seen) {
                    $result[] = '#include extensions_gateway_managed.conf';
                    $seen = true;
                }
                continue;
            }
            $result[] = $line;
        }
        if (!$seen) {
            $result[] = '#include extensions_gateway_managed.conf';
        }
        while ($result && end($result) === '') { array_pop($result); }
        return implode("\n", $result) . "\n";
    }

    public static function writeAtomic(string $path, string $contents): void
    {
        if (is_link($path) || !is_dir(dirname($path))) {
            throw new FreepbxBridgeError('dialplan_write_failed', 'managed dialplan path is unavailable', 503);
        }
        $tmp = tempnam(dirname($path), '.gateway-dialplan-');
        if ($tmp === false || file_put_contents($tmp, $contents, LOCK_EX) === false || !chmod($tmp, 0640) || !rename($tmp, $path)) {
            if ($tmp !== false && is_file($tmp)) { @unlink($tmp); }
            throw new FreepbxBridgeError('dialplan_write_failed', 'managed dialplan could not be saved', 503);
        }
    }

    public static function read(string $path): ?string
    {
        if (!file_exists($path)) { return null; }
        if (is_link($path) || !is_readable($path)) {
            throw new FreepbxBridgeError('dialplan_unavailable', 'managed dialplan is unavailable', 503);
        }
        $contents = file_get_contents($path);
        if ($contents === false) {
            throw new FreepbxBridgeError('dialplan_unavailable', 'managed dialplan is unavailable', 503);
        }
        return $contents;
    }

    public static function hasExactRoute(string $output, string $number): bool
    {
        $number = FreepbxValidation::didNumber($number);
        $current = null;
        $blocks = [];
        foreach (preg_split('/\R/', $output) ?: [] as $line) {
            $extension = null;
            $step = null;
            $application = null;
            if (preg_match('/^\s*\'([^\']+)\'\s*=>\s*([0-9]+)\.\s*(.*)$/', $line, $match)) {
                $extension = $match[1];
                $step = (int) $match[2];
                $application = trim($match[3]);
            } elseif (preg_match('/^\s*exten\s*=>\s*([^,]+),([0-9]+),(.*)$/i', $line, $match)) {
                $extension = trim($match[1]);
                $step = (int) $match[2];
                $application = trim($match[3]);
            } elseif ($current !== null && preg_match('/^\s*([0-9]+)\.\s*(.*)$/', $line, $match)) {
                $extension = $current['extension'];
                $step = (int) $match[1];
                $application = trim($match[2]);
            }
            if ($extension === null || $step === null || $application === null) {
                continue;
            }
            $application = preg_replace('/\s+\[[^\]\r\n]+:[0-9]+\]\s*\z/', '', $application) ?? $application;
            if ($current === null || $extension !== $current['extension'] || $step === 1) {
                if ($current !== null) { $blocks[] = $current; }
                $current = ['extension' => $extension, 'steps' => [], 'invalid' => false];
            }
            if (array_key_exists($step, $current['steps'])) { $current['invalid'] = true; }
            $current['steps'][$step] = $application;
        }
        if ($current !== null) { $blocks[] = $current; }

        foreach ($blocks as $block) {
            if ($block['extension'] !== $number) { continue; }
            $steps = $block['steps'];
            return !$block['invalid']
                && array_keys($steps) === [1, 2, 3, 4]
                && preg_match('/\ANoOp\([^\r\n]*\)\z/', $steps[1] ?? '') === 1
                && ($steps[2] ?? '') === 'Set(AI_GATEWAY_DID=' . $number . ')'
                && ($steps[3] ?? '') === 'Stasis(asterisk-ai-gateway)'
                && ($steps[4] ?? '') === 'Hangup()';
        }
        return false;
    }
}
