<?php
declare(strict_types=1);

require_once __DIR__ . '/errors.php';
require_once __DIR__ . '/validation.php';
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/lock.php';
require_once __DIR__ . '/state.php';
require_once __DIR__ . '/dialplan.php';
require_once __DIR__ . '/bmo.php';
require_once __DIR__ . '/trunks.php';
require_once __DIR__ . '/dids.php';
require_once __DIR__ . '/bridge.php';

final class FreepbxBridgeHttp
{
    public static function run(): void
    {
        ini_set('display_errors', '0');
        header('Content-Type: application/json; charset=utf-8');
        try {
            $config = FreepbxBridgeConfig::load();
            self::authorize($config);
            [$operation, $payload] = self::request($config['max_body_bytes']);
            $bmo = FreepbxBmo::bootstrap($config['freepbx_conf']);
            $bridge = new FreepbxBridge($bmo, new FreepbxTrunkService($bmo), new FreepbxDidService($bmo, new FreepbxRouteState($config['state_path']), $config), $config);
            self::respond(200, ['ok' => true, 'data' => $bridge->dispatch($operation, $payload)]);
        } catch (FreepbxBridgeError $error) {
            self::respond($error->httpStatus, ['ok' => false, 'error' => $error->safeCode, 'message' => $error->getMessage()]);
        } catch (Throwable) {
            self::respond(500, ['ok' => false, 'error' => 'internal_error', 'message' => 'bridge operation failed']);
        }
    }

    private static function authorize(array $config): void
    {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            throw new FreepbxBridgeError('method_not_allowed', 'POST is required', 405);
        }
        $source = $_SERVER['REMOTE_ADDR'] ?? '';
        if (!is_string($source) || !filter_var($source, FILTER_VALIDATE_IP) || !FreepbxValidation::sourceAllowed($source, $config['allowed_cidrs'], $config['denied_cidrs'])) {
            throw new FreepbxBridgeError('source_denied', 'source is not allowed', 403);
        }
        $authorization = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
        if (!is_string($authorization) || !str_starts_with($authorization, 'Bearer ')) {
            throw new FreepbxBridgeError('unauthorized', 'bearer authorization is required', 401);
        }
        $token = substr($authorization, 7);
        if ($token === '' || !hash_equals($config['bearer_token'], $token)) {
            throw new FreepbxBridgeError('unauthorized', 'bearer authorization is invalid', 401);
        }
    }

    private static function request(int $maxBytes): array
    {
        $contentType = strtolower((string) ($_SERVER['CONTENT_TYPE'] ?? ''));
        if (!str_starts_with($contentType, 'application/json')) {
            throw new FreepbxBridgeError('invalid_content_type', 'application/json is required', 415);
        }
        $body = file_get_contents('php://input', false, null, 0, $maxBytes + 1);
        if ($body === false || strlen($body) > $maxBytes) {
            throw new FreepbxBridgeError('body_too_large', 'request body is too large', 413);
        }
        try { $request = json_decode($body, true, 16, JSON_THROW_ON_ERROR); } catch (JsonException) {
            throw new FreepbxBridgeError('invalid_json', 'request body must be valid JSON', 422);
        }
        if (!is_array($request) || array_is_list($request)) {
            throw new FreepbxBridgeError('invalid_json', 'request body must be an object', 422);
        }
        FreepbxValidation::only($request, ['operation', 'payload'], 'request');
        if (!isset($request['operation']) || !is_string($request['operation']) || !isset($request['payload'])) {
            throw new FreepbxBridgeError('invalid_json', 'operation and payload are required', 422);
        }
        return [$request['operation'], FreepbxValidation::object($request['payload'], 'payload')];
    }

    private static function respond(int $status, array $body): void
    {
        http_response_code($status);
        echo json_encode($body, JSON_UNESCAPED_SLASHES) . "\n";
    }
}

if (PHP_SAPI !== 'cli' && realpath((string) ($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) {
    FreepbxBridgeHttp::run();
}
