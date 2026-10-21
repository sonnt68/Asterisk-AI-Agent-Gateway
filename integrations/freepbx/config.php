<?php
declare(strict_types=1);

final class FreepbxBridgeConfig
{
    public static function load(string $path = '/etc/asterisk/gateway-provisioner.json'): array
    {
        if (!is_file($path) || !is_readable($path)) {
            throw new FreepbxBridgeError('config_unavailable', 'bridge configuration is unavailable', 503);
        }
        $raw = file_get_contents($path);
        $config = json_decode($raw === false ? '' : $raw, true);
        if (!is_array($config) || array_is_list($config)) {
            throw new FreepbxBridgeError('config_invalid', 'bridge configuration is invalid', 503);
        }
        return self::fromArray($config);
    }

    public static function fromArray(array $input): array
    {
        $allowed = ['bearer_token', 'allowed_cidrs', 'denied_cidrs', 'state_path', 'lock_path', 'freepbx_conf', 'extensions_custom_path', 'managed_dialplan_path', 'max_body_bytes'];
        FreepbxValidation::only($input, $allowed, 'configuration');
        $token = $input['bearer_token'] ?? '';
        if (!is_string($token) || strlen($token) < 32 || strlen($token) > 512 || preg_match('/[\x00-\x20\x7f]/', $token)) {
            throw new FreepbxBridgeError('config_invalid', 'bridge token is invalid', 503);
        }
        $allowedCidrs = self::cidrs($input['allowed_cidrs'] ?? [], true);
        $configuredDenied = self::cidrs($input['denied_cidrs'] ?? [], false);
        $deniedCidrs = self::cidrs(array_values(array_unique(array_merge(['172.18.0.1/32'], $configuredDenied))), false);
        $paths = [
            'state_path' => '/var/lib/asterisk/gateway-provisioner/state.json',
            'lock_path' => '/var/lock/asterisk-ai-gateway-provisioner.lock',
            'freepbx_conf' => '/etc/freepbx.conf',
            'extensions_custom_path' => '/etc/asterisk/extensions_custom.conf',
            'managed_dialplan_path' => '/etc/asterisk/extensions_gateway_managed.conf',
        ];
        foreach ($paths as $key => $default) {
            $value = $input[$key] ?? $default;
            if (!is_string($value) || $value === '' || $value[0] !== '/' || str_contains($value, "\0") || str_contains($value, '..')) {
                throw new FreepbxBridgeError('config_invalid', 'bridge path is invalid', 503);
            }
            $paths[$key] = $value;
        }
        $maxBody = $input['max_body_bytes'] ?? 65536;
        if (!is_int($maxBody) || $maxBody < 1024 || $maxBody > 1048576) {
            throw new FreepbxBridgeError('config_invalid', 'max_body_bytes is invalid', 503);
        }
        return [
            'bearer_token' => $token,
            'allowed_cidrs' => $allowedCidrs,
            'denied_cidrs' => $deniedCidrs,
            'max_body_bytes' => $maxBody,
        ] + $paths;
    }

    private static function cidrs(mixed $values, bool $required): array
    {
        if (!is_array($values) || !array_is_list($values) || (!$values && $required)) {
            throw new FreepbxBridgeError('config_invalid', 'source CIDR configuration is invalid', 503);
        }
        $result = [];
        foreach ($values as $value) {
            if (!is_string($value)) {
                throw new FreepbxBridgeError('config_invalid', 'source CIDR configuration is invalid', 503);
            }
            [$packed, $prefix, $bits] = FreepbxValidation::parseCidr($value);
            if ($required && $prefix === 0) {
                throw new FreepbxBridgeError('config_invalid', 'allowed source CIDR is too broad', 503);
            }
            if ($required && !self::privateNetwork($packed, $prefix, $bits)) {
                throw new FreepbxBridgeError('config_invalid', 'allowed source CIDR must be private', 503);
            }
            $result[] = $value;
        }
        return $result;
    }

    private static function privateNetwork(string $packed, int $prefix, int $bits): bool
    {
        if ($bits === 32) {
            foreach (['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '169.254.0.0/16'] as $privateCidr) {
                [, $privatePrefix] = FreepbxValidation::parseCidr($privateCidr);
                if ($prefix >= $privatePrefix && self::containsPacked($packed, $privateCidr)) {
                    return true;
                }
            }
            return false;
        }
        $first = ord($packed[0]);
        $second = ord($packed[1]);
        return ($prefix >= 7 && (($first & 0xfe) === 0xfc)) || ($prefix >= 10 && $first === 0xfe && (($second & 0xc0) === 0x80)) || ($prefix === $bits && $packed === inet_pton('::1'));
    }

    private static function containsPacked(string $packed, string $cidr): bool
    {
        $ip = inet_ntop($packed);
        return $ip !== false && FreepbxValidation::cidrContains($ip, $cidr);
    }
}
