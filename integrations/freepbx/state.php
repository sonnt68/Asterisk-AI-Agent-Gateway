<?php
declare(strict_types=1);

final class FreepbxRouteState
{
    public function __construct(private string $path)
    {
    }

    public function load(): array
    {
        if (!file_exists($this->path)) {
            return [];
        }
        if (is_link($this->path) || !is_readable($this->path)) {
            throw new FreepbxBridgeError('state_unavailable', 'managed route state is unavailable', 503);
        }
        $raw = file_get_contents($this->path);
        $decoded = json_decode($raw === false ? '' : $raw, true);
        if (!is_array($decoded) || array_keys($decoded) !== ['routes'] || !is_array($decoded['routes']) || !array_is_list($decoded['routes'])) {
            throw new FreepbxBridgeError('state_invalid', 'managed route state is invalid', 503);
        }
        $routes = [];
        $ids = [];
        $numbers = [];
        foreach ($decoded['routes'] as $route) {
            if (!is_array($route) || array_keys($route) !== ['route_id', 'number']) {
                throw new FreepbxBridgeError('state_invalid', 'managed route state is invalid', 503);
            }
            $routeId = FreepbxValidation::routeId($route['route_id']);
            $number = FreepbxValidation::didNumber($route['number']);
            if (isset($ids[$routeId]) || isset($numbers[$number])) {
                throw new FreepbxBridgeError('state_invalid', 'managed route state has duplicate ownership', 503);
            }
            $ids[$routeId] = true;
            $numbers[$number] = true;
            $routes[] = ['route_id' => $routeId, 'number' => $number];
        }
        usort($routes, static fn(array $a, array $b): int => strcmp($a['route_id'], $b['route_id']));
        return $routes;
    }

    public function save(array $routes): void
    {
        if (!is_dir(dirname($this->path)) || is_link($this->path)) {
            throw new FreepbxBridgeError('state_unavailable', 'managed route state directory is unavailable', 503);
        }
        usort($routes, static fn(array $a, array $b): int => strcmp($a['route_id'], $b['route_id']));
        $json = json_encode(['routes' => array_values($routes)], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
        $tmp = tempnam(dirname($this->path), '.gateway-state-');
        if ($tmp === false || file_put_contents($tmp, $json, LOCK_EX) === false || !chmod($tmp, 0600) || !rename($tmp, $this->path)) {
            if ($tmp !== false && is_file($tmp)) { @unlink($tmp); }
            throw new FreepbxBridgeError('state_write_failed', 'managed route state could not be saved', 503);
        }
    }
}
