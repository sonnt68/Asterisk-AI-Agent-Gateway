<?php
declare(strict_types=1);

final class FreepbxDidService
{
    private string $customPath;
    private string $managedPath;
    private string $lockPath;

    public function __construct(private FreepbxBmo $bmo, private FreepbxRouteState $state, array $config)
    {
        $this->customPath = $config['extensions_custom_path'];
        $this->managedPath = $config['managed_dialplan_path'];
        $this->lockPath = $config['lock_path'];
    }

    public function status(): array
    {
        $routes = $this->state->load();
        $needsApply = $this->bmo->reloadNeeded();
        try { $needsApply = $needsApply || !$this->readback($routes); } catch (Throwable) { $needsApply = true; }
        return [
            'needs_apply' => $needsApply,
            'transports' => $this->bmo->transports(),
            'managed_routes' => $routes,
        ];
    }

    public function save(array $payload): array
    {
        FreepbxValidation::only($payload, ['route_id', 'number', 'label'], 'payload');
        $routeId = FreepbxValidation::routeId($payload['route_id'] ?? null);
        $number = FreepbxValidation::didNumber($payload['number'] ?? null);
        $label = FreepbxValidation::label($payload['label'] ?? '');
        $lock = new FreepbxBridgeLock($this->lockPath());
        $routes = $this->state->load();
        $owned = $this->ownedRoute($routes, $routeId);
        if ($owned !== null && $owned['number'] !== $number) {
            throw new FreepbxBridgeError('route_id_remap', 'route_id cannot be remapped by the PBX bridge', 409);
        }
        $existing = $this->bmo->did($number);
        if ($existing !== false && ($owned === null || !$this->isManaged($existing, $number))) {
            $this->assertNoCollision($number);
            throw new FreepbxBridgeError('did_collision', 'DID is already owned outside the gateway bridge', 409);
        }
        if ($existing === false) {
            $this->assertNoCollision($number);
        }
        $candidate = $routes;
        if ($owned === null) { $candidate[] = ['route_id' => $routeId, 'number' => $number]; }
        $oldCustom = FreepbxGatewayDialplan::read($this->customPath);
        $oldManaged = FreepbxGatewayDialplan::read($this->managedPath);
        $newManaged = FreepbxGatewayDialplan::render($candidate);
        $oldCustomForWrite = $oldCustom ?? '';
        try {
            FreepbxGatewayDialplan::writeAtomic($this->managedPath, $newManaged);
            FreepbxGatewayDialplan::writeAtomic($this->customPath, FreepbxGatewayDialplan::ensureInclude($oldCustomForWrite));
            $didSettings = ['extension' => $number, 'cidnum' => '', 'destination' => $this->destination($number), 'description' => $label];
            if ($existing === false) {
                if (!$this->bmo->addDid($didSettings)) {
                    throw new FreepbxBridgeError('did_save_failed', 'FreePBX did not accept the managed route', 503);
                }
            } elseif (!$this->bmo->editDid($didSettings)) {
                throw new FreepbxBridgeError('did_save_failed', 'FreePBX did properties could not be updated', 503);
            }
            $read = $this->bmo->did($number);
            if ($read === false || !$this->isManaged($read, $number)) {
                throw new FreepbxBridgeError('did_readback_failed', 'managed DID readback did not match', 503);
            }
            if ($owned === null) { $this->state->save($candidate); }
            $this->bmo->markReload();
        } catch (Throwable $error) {
            if ($existing === false) {
                try { $this->bmo->deleteDid($number); } catch (Throwable) { /* report below */ }
            }
            $this->restore($this->customPath, $oldCustom);
            $this->restore($this->managedPath, $oldManaged);
            if ($error instanceof FreepbxBridgeError) { throw $error; }
            throw new FreepbxBridgeError('did_save_failed', 'managed DID save failed and recovery was attempted', 503, $error);
        }
        return ['route_id' => $routeId, 'number' => $number];
    }

    public function apply(): array
    {
        $lock = new FreepbxBridgeLock($this->lockPath());
        $routes = $this->state->load();
        if ($this->bmo->activeChannels() > 0) {
            throw new FreepbxBridgeError('active_calls', 'PBX Apply requires zero active channels', 409);
        }
        if (!$this->readback($routes, false)) {
            throw new FreepbxBridgeError('route_drift', 'managed route readback is uncertain; apply was refused', 409);
        }
        $this->bmo->reload();
        if (!$this->readback($routes, true)) {
            throw new FreepbxBridgeError('apply_readback_failed', 'reload completed without exact managed route readback', 503);
        }
        return ['applied_routes' => $routes];
    }

    private function readback(array $routes, bool $checkAsterisk = true): bool
    {
        $managed = FreepbxGatewayDialplan::read($this->managedPath);
        $custom = FreepbxGatewayDialplan::read($this->customPath);
        if (!$routes && $managed === null && ($custom === null || !preg_match('/^\s*#(?:try)?include\s+(?:\/etc\/asterisk\/)?extensions_gateway_managed\.conf\s*$/m', $custom))) {
            return true;
        }
        if ($managed !== FreepbxGatewayDialplan::render($routes) || $custom === null || FreepbxGatewayDialplan::ensureInclude($custom) !== $custom) {
            return false;
        }
        foreach ($routes as $route) {
            $did = $this->bmo->did($route['number']);
            if ($did === false || !$this->isManaged($did, $route['number'])) { return false; }
        }
        if (!$checkAsterisk || !$routes) { return true; }
        $output = $this->bmo->command('dialplan show from-ai-gateway-managed');
        foreach ($routes as $route) {
            if (!FreepbxGatewayDialplan::hasExactRoute($output, $route['number'])) {
                return false;
            }
        }
        return true;
    }

    private function assertNoCollision(string $number): void
    {
        foreach ($this->bmo->allDids() as $row) {
            $extension = (string) ($row['extension'] ?? '');
            if ($extension === '' || FreepbxValidation::patternMatches($extension, $number)) {
                throw new FreepbxBridgeError('did_collision', 'DID overlaps an existing FreePBX route', 409);
            }
        }
    }

    private function isManaged(array $did, string $number): bool
    {
        return (string) ($did['extension'] ?? '') === $number && (string) ($did['cidnum'] ?? '') === '' && ($did['destination'] ?? '') === $this->destination($number);
    }

    private function ownedRoute(array $routes, string $routeId): ?array
    {
        foreach ($routes as $route) { if ($route['route_id'] === $routeId) { return $route; } }
        return null;
    }

    private function destination(string $number): string
    {
        return 'from-ai-gateway-managed,' . $number . ',1';
    }

    private function restore(string $path, ?string $contents): void
    {
        if ($contents === null) {
            if (file_exists($path)) { @unlink($path); }
            return;
        }
        try { FreepbxGatewayDialplan::writeAtomic($path, $contents); } catch (Throwable) { /* report operation failure */ }
    }

    private function lockPath(): string
    {
        return $this->lockPath;
    }
}
