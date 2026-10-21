<?php
declare(strict_types=1);

final class FreepbxValidation
{
    public static function object(mixed $value, string $name): array
    {
        if (!is_array($value) || (array_is_list($value) && $value !== [])) {
            throw new FreepbxBridgeError('invalid_json', $name . ' must be an object', 422);
        }
        return $value;
    }

    public static function only(array $value, array $allowed, string $name): void
    {
        $unknown = array_diff(array_keys($value), $allowed);
        if ($unknown) {
            throw new FreepbxBridgeError('unknown_field', $name . ' contains an unsupported field', 422);
        }
    }

    public static function didNumber(mixed $value): string
    {
        if (!is_string($value) || !preg_match('/\A\+?[0-9]{1,32}\z/D', $value)) {
            throw new FreepbxBridgeError('invalid_did', 'number must be an exact + or digit string', 422);
        }
        return $value;
    }

    public static function routeId(mixed $value): string
    {
        if (!is_string($value) || !preg_match('/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/i', $value)) {
            throw new FreepbxBridgeError('invalid_route_id', 'route_id must be a UUID', 422);
        }
        return strtolower($value);
    }

    public static function trunkId(mixed $value): string
    {
        if (!is_string($value) || !preg_match('/\A[1-9][0-9]*\z/D', $value)) {
            throw new FreepbxBridgeError('invalid_trunk_id', 'id must be a positive integer string', 422);
        }
        return $value;
    }

    public static function label(mixed $value): string
    {
        if (!is_string($value) || $value === '' || strlen($value) > 200 || preg_match('/[\x00-\x1f\x7f]/', $value)) {
            throw new FreepbxBridgeError('invalid_label', 'label is required and contains invalid characters', 422);
        }
        return $value;
    }

    public static function host(mixed $value): string
    {
        if (!is_string($value) || $value === '' || strlen($value) > 253 || preg_match('/[\x00-\x20\x7f]/', $value)) {
            throw new FreepbxBridgeError('invalid_host', 'host must be a hostname or IP address', 422);
        }
        if (filter_var($value, FILTER_VALIDATE_IP) !== false) {
            return $value;
        }
        $label = '(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)';
        if (!preg_match('/\A' . $label . '(?:\.' . $label . ')*\z/', $value)) {
            throw new FreepbxBridgeError('invalid_host', 'host must be a hostname or IP address', 422);
        }
        return $value;
    }

    public static function port(mixed $value): int
    {
        if (is_int($value)) {
            $port = $value;
        } elseif (is_string($value) && preg_match('/\A[0-9]+\z/', $value)) {
            $port = (int) $value;
        } else {
            throw new FreepbxBridgeError('invalid_port', 'port must be an integer from 1 to 65535', 422);
        }
        if ($port < 1 || $port > 65535) {
            throw new FreepbxBridgeError('invalid_port', 'port must be an integer from 1 to 65535', 422);
        }
        return $port;
    }

    public static function token(mixed $value, string $field, int $max = 256): string
    {
        if (!is_string($value) || strlen($value) > $max || preg_match('/[\x00-\x20\x7f]/', $value)) {
            throw new FreepbxBridgeError('invalid_field', $field . ' contains invalid characters', 422);
        }
        return $value;
    }

    public static function freeText(mixed $value, string $field, int $max = 200): string
    {
        if (!is_string($value) || strlen($value) > $max || preg_match('/[\x00-\x1f\x7f]/', $value)) {
            throw new FreepbxBridgeError('invalid_field', $field . ' contains invalid characters', 422);
        }
        return $value;
    }

    public static function matchList(mixed $value): string
    {
        if (!is_string($value) || strlen($value) > 2048) {
            throw new FreepbxBridgeError('invalid_match', 'match must be a comma separated IP/CIDR list', 422);
        }
        if ($value === '') {
            return '';
        }
        $items = preg_split('/\s*,\s*/', $value, -1, PREG_SPLIT_NO_EMPTY);
        if (!$items || count($items) > 32) {
            throw new FreepbxBridgeError('invalid_match', 'match must be a comma separated IP/CIDR list', 422);
        }
        $result = [];
        foreach ($items as $item) {
            self::parseCidr($item);
            $result[] = $item;
        }
        return implode(',', $result);
    }

    public static function parseCidr(string $value): array
    {
        $parts = explode('/', $value, 2);
        $ip = $parts[0];
        $packed = filter_var($ip, FILTER_VALIDATE_IP) !== false ? inet_pton($ip) : false;
        if ($packed === false) {
            throw new FreepbxBridgeError('invalid_cidr', 'source or match contains an invalid IP/CIDR', 422);
        }
        $bits = strlen($packed) * 8;
        $prefix = $bits;
        if (isset($parts[1])) {
            if (!preg_match('/\A[0-9]+\z/', $parts[1])) {
                throw new FreepbxBridgeError('invalid_cidr', 'source or match contains an invalid IP/CIDR', 422);
            }
            $prefix = (int) $parts[1];
            if ($prefix < 0 || $prefix > $bits) {
                throw new FreepbxBridgeError('invalid_cidr', 'source or match contains an invalid IP/CIDR', 422);
            }
        }
        return [$packed, $prefix, $bits];
    }

    public static function cidrContains(string $ip, string $cidr): bool
    {
        $candidate = inet_pton($ip);
        if ($candidate === false) {
            return false;
        }
        [$network, $prefix, $bits] = self::parseCidr($cidr);
        if (strlen($candidate) !== strlen($network)) {
            return false;
        }
        $whole = intdiv($prefix, 8);
        if ($whole && substr($candidate, 0, $whole) !== substr($network, 0, $whole)) {
            return false;
        }
        $rest = $prefix % 8;
        if ($rest === 0) {
            return true;
        }
        $mask = (0xff << (8 - $rest)) & 0xff;
        return (ord($candidate[$whole]) & $mask) === (ord($network[$whole]) & $mask);
    }

    public static function sourceAllowed(string $ip, array $allowed, array $denied): bool
    {
        foreach ($denied as $cidr) {
            if (self::cidrContains($ip, $cidr)) {
                return false;
            }
        }
        foreach ($allowed as $cidr) {
            if (self::cidrContains($ip, $cidr)) {
                return true;
            }
        }
        return false;
    }

    public static function trunkPatch(array $payload, bool $creating, array $current, array $transports): array
    {
        $allowed = ['id', 'name', 'host', 'port', 'transport', 'authentication', 'registration', 'username', 'auth_username', 'password', 'match', 'from_domain', 'from_user', 'contact_user', 'outbound_caller_id', 'codecs', 'enabled'];
        self::only($payload, $allowed, 'payload');
        if (array_key_exists('id', $payload)) { self::trunkId($payload['id']); }
        $final = $current;
        $final['name'] = $current['name'] ?? '';
        foreach (['name' => 'freeText', 'host' => 'host', 'port' => 'port', 'username' => 'token', 'auth_username' => 'token', 'match' => 'matchList', 'from_domain' => 'token', 'from_user' => 'token', 'contact_user' => 'token', 'outbound_caller_id' => 'freeText'] as $field => $validator) {
            if (array_key_exists($field, $payload)) {
                $final[$field] = match ($validator) {
                    'freeText' => self::freeText($payload[$field], $field),
                    'token' => self::token($payload[$field], $field),
                    default => self::{$validator}($payload[$field]),
                };
            }
        }
        if (array_key_exists('name', $payload) && $final['name'] === '') {
            throw new FreepbxBridgeError('invalid_name', 'name is required', 422);
        }
        if ($creating && $final['name'] === '') {
            throw new FreepbxBridgeError('invalid_name', 'name is required', 422);
        }
        if (array_key_exists('transport', $payload)) {
            if (!is_string($payload['transport']) || ($payload['transport'] !== '' && !in_array($payload['transport'], $transports, true))) {
                throw new FreepbxBridgeError('invalid_transport', 'transport is not active on this PBX', 422);
            }
            $final['transport'] = $payload['transport'];
        }
        foreach (['authentication' => ['none', 'outbound'], 'registration' => ['none', 'send']] as $field => $values) {
            if (array_key_exists($field, $payload)) {
                if (!is_string($payload[$field]) || !in_array($payload[$field], $values, true)) {
                    throw new FreepbxBridgeError('invalid_trunk_mode', $field . ' is outside the supported subset', 422);
                }
                $final[$field] = $payload[$field];
            }
        }
        if (array_key_exists('enabled', $payload)) {
            if (!is_bool($payload['enabled'])) {
                throw new FreepbxBridgeError('invalid_enabled', 'enabled must be boolean', 422);
            }
            $final['enabled'] = $payload['enabled'];
        }
        if (array_key_exists('codecs', $payload)) {
            if (!is_array($payload['codecs']) || !array_is_list($payload['codecs'])) {
                throw new FreepbxBridgeError('invalid_codecs', 'codecs must be an array', 422);
            }
            $known = ['alaw', 'g722', 'g726', 'g726_aal2', 'gsm', 'ilbc', 'opus', 'slin', 'slin16', 'slin48', 'slin96', 'slin192', 'speex', 'ulaw'];
            $final['codecs'] = [];
            foreach ($payload['codecs'] as $codec) {
                if (!is_string($codec) || !in_array($codec, $known, true) || in_array($codec, $final['codecs'], true)) {
                    throw new FreepbxBridgeError('invalid_codecs', 'codecs contains an unsupported value', 422);
                }
                $final['codecs'][] = $codec;
            }
        }
        $final['password'] = $current['password'] ?? '';
        if (array_key_exists('password', $payload)) {
            if (!is_string($payload['password']) || strlen($payload['password']) > 512 || preg_match('/[\x00-\x1f\x7f]/', $payload['password'])) {
                throw new FreepbxBridgeError('invalid_password', 'password contains invalid characters', 422);
            }
            $final['password'] = $payload['password'];
        }
        if ((!isset($final['host']) || $final['host'] === '') && ($creating || ($final['registration'] ?? 'none') === 'send' || ($final['authentication'] ?? 'none') === 'outbound')) {
            throw new FreepbxBridgeError('invalid_host', 'host is required for a managed trunk', 422);
        }
        $modeChanged = array_key_exists('authentication', $payload) || array_key_exists('registration', $payload);
        if (($final['registration'] ?? 'none') === 'send' && ($final['authentication'] ?? 'none') !== 'outbound' && ($creating || $modeChanged)) {
            throw new FreepbxBridgeError('invalid_trunk_mode', 'send registration requires outbound authentication', 422);
        }
        if (($final['authentication'] ?? 'none') === 'outbound' && ($creating || $modeChanged || array_key_exists('username', $payload) || array_key_exists('password', $payload))) {
            if (($final['username'] ?? '') === '' || ($final['password'] ?? '') === '') {
                throw new FreepbxBridgeError('missing_credentials', 'outbound authentication requires username and password', 422);
            }
        }
        if (($final['authentication'] ?? 'none') === 'none' && ($final['registration'] ?? 'none') === 'none' && ($final['match'] ?? '') === '' && ($creating || $modeChanged || array_key_exists('match', $payload))) {
            throw new FreepbxBridgeError('missing_match', 'IP-authenticated trunks require match', 422);
        }
        if (!isset($final['port']) || $final['port'] === null || $final['port'] === '') {
            $final['port'] = $creating ? 5060 : null;
        }
        return $final;
    }

    public static function patternMatches(string $pattern, string $number): bool
    {
        if ($pattern === '') {
            return true;
        }
        if ($pattern[0] !== '_') {
            return $pattern === $number;
        }
        $pattern = substr($pattern, 1);
        $regex = '';
        for ($i = 0, $length = strlen($pattern); $i < $length; $i++) {
            $char = $pattern[$i];
            if ($char === 'X') { $regex .= '[0-9]'; continue; }
            if ($char === 'Z') { $regex .= '[1-9]'; continue; }
            if ($char === 'N') { $regex .= '[2-9]'; continue; }
            if ($char === '.') { $regex .= '[0-9#+*]+?'; continue; }
            if ($char === '!') { $regex .= '.*'; continue; }
            if ($char === '[') {
                $end = strpos($pattern, ']', $i + 1);
                if ($end === false) { return true; }
                $set = substr($pattern, $i + 1, $end - $i - 1);
                if (!preg_match('/\A[0-9A-Fa-f\-]+\z/', $set)) { return true; }
                $regex .= '[' . $set . ']';
                $i = $end;
                continue;
            }
            $regex .= preg_quote($char, '/');
        }
        return preg_match('/\A' . $regex . '\z/', $number) === 1;
    }
}
