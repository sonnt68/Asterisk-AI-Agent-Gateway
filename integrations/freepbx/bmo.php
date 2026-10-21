<?php
declare(strict_types=1);

final class FreepbxBmo
{
    public function __construct(private object $core, private object $framework, private object $astman)
    {
    }

    public static function bootstrap(string $freepbxConf): self
    {
        if (!is_file($freepbxConf) || !is_readable($freepbxConf)) {
            throw new FreepbxBridgeError('freepbx_unavailable', 'FreePBX bootstrap is unavailable', 503);
        }
        // freepbx.conf assigns the database settings used by BMO's Database
        // class.  Keep those assignments in PHP's global symbol table: a
        // require performed from this method would otherwise make $amp_conf
        // local to this method and BMO would see no AMPDBUSER/AMPDBNAME.
        global $amp_conf, $db, $astman;
        // The bridge already authenticates its private bearer request.  Ask
        // FreePBX to skip GUI authentication so its BMO loader exposes the
        // enabled module classes to this non-GUI request.
        $bootstrap_settings = ['freepbx_auth' => false];
        require_once $freepbxConf;
        if (!class_exists('FreePBX')) {
            throw new FreepbxBridgeError('freepbx_unavailable', 'FreePBX bootstrap is unavailable', 503);
        }
        $bmo = \FreePBX::create();
        return new self(\FreePBX::Core(), \FreePBX::Framework(), $bmo->astman);
    }

    public function transports(): array
    {
        $driver = $this->core->getDriver('pjsip');
        if ($driver === false || !method_exists($driver, 'getActiveTransports')) {
            throw new FreepbxBridgeError('pjsip_unavailable', 'PJSIP trunk driver is unavailable', 503);
        }
        $values = [];
        foreach ($driver->getActiveTransports() as $transport) {
            if (is_array($transport) && isset($transport['value']) && is_string($transport['value'])) {
                $values[] = $transport['value'];
            }
        }
        return array_values(array_filter(array_unique($values), static fn(string $value): bool => $value !== ''));
    }

    public function pjsipDefaults(): array
    {
        if (!method_exists($this->core, 'checkPJSIPsettings')) {
            throw new FreepbxBridgeError('pjsip_unavailable', 'PJSIP defaults are unavailable', 503);
        }
        $defaults = $this->core->checkPJSIPsettings([], ['imports' => []]);
        if (!is_array($defaults)) {
            throw new FreepbxBridgeError('pjsip_unavailable', 'PJSIP defaults are unavailable', 503);
        }
        return $defaults;
    }

    public function trunk(int $id): array
    {
        $row = $this->core->getTrunkByID($id);
        if (!is_array($row) || strtolower((string) ($row['tech'] ?? '')) !== 'pjsip') {
            throw new FreepbxBridgeError('trunk_not_found', 'PJSIP trunk was not found', 404);
        }
        $details = $this->core->getTrunkDetails($id);
        if (!is_array($details)) {
            throw new FreepbxBridgeError('trunk_unavailable', 'PJSIP trunk details are unavailable', 503);
        }
        return ['row' => $row, 'details' => $details];
    }

    public function trunks(): array
    {
        $rows = $this->core->listTrunks(false);
        $result = [];
        foreach (is_array($rows) ? $rows : [] as $row) {
            $id = (int) ($row['trunkid'] ?? 0);
            if ($id < 1 || strtolower((string) ($row['tech'] ?? '')) !== 'pjsip') {
                continue;
            }
            $result[] = $this->trunk($id);
        }
        return $result;
    }

    public function saveTrunk(string $name, array $settings, ?int $id, array $snapshot = []): int
    {
        $oldPost = $_POST ?? [];
        $_POST = [];
        try {
            if ($id === null) {
                try {
                    $saved = $this->core->addTrunk($name, 'pjsip', $settings, false);
                } catch (Throwable $error) {
                    $this->cleanupCreated((string) ($settings['trunk_name'] ?? ''));
                    throw new FreepbxBridgeError('trunk_save_failed', 'new trunk save failed and recovery was attempted', 503, $error);
                }
            } else {
                $deleted = $this->core->deleteTrunk($id, 'pjsip', true);
                if ($deleted !== true) {
                    throw new FreepbxBridgeError('trunk_edit_failed', 'existing trunk could not be prepared for edit', 503);
                }
                try {
                    $settings['trunknum'] = $id;
                    $saved = $this->core->addTrunk($name, 'pjsip', $settings, true);
                } catch (Throwable $error) {
                    $this->restoreTrunk($snapshot, $id);
                    throw new FreepbxBridgeError('trunk_edit_failed', 'existing trunk edit failed and recovery was attempted', 503, $error);
                }
            }
        } finally {
            $_POST = $oldPost;
        }
        if ((int) $saved < 1 || ($id !== null && (int) $saved !== $id)) {
            if ($id !== null) { $this->restoreTrunk($snapshot, $id); }
            else { $this->cleanupCreated((string) ($settings['trunk_name'] ?? '')); }
            throw new FreepbxBridgeError('trunk_save_failed', 'trunk save did not return a valid identifier', 503);
        }
        return (int) $saved;
    }

    private function restoreTrunk(array $snapshot, int $id): void
    {
        if (!$snapshot || !isset($snapshot['row'], $snapshot['settings'])) {
            return;
        }
        try {
            $this->core->deleteTrunk($id, 'pjsip', true);
            $oldPost = $_POST ?? [];
            $_POST = [];
            $this->core->addTrunk((string) ($snapshot['row']['name'] ?? ''), 'pjsip', $snapshot['settings'], true);
            $_POST = $oldPost;
        } catch (Throwable) {
            $_POST = $oldPost ?? [];
        }
    }

    private function cleanupCreated(string $trunkName): void
    {
        if ($trunkName === '' || !method_exists($this->core, 'getPJSIPtrunkIDByName')) {
            return;
        }
        try {
            $id = (int) $this->core->getPJSIPtrunkIDByName($trunkName);
            if ($id > 0) { $this->core->deleteTrunk($id, 'pjsip', false); }
        } catch (Throwable) {
            // The caller reports the original save failure; no raw PBX detail is returned.
        }
    }

    public function addDid(array $settings): bool
    {
        return $this->core->addDID($settings) === true;
    }

    public function editDid(array $settings): bool
    {
        return $this->core->editDIDProperties($settings) === true;
    }

    public function deleteDid(string $number): void
    {
        $this->core->delDID($number, '');
    }

    public function did(string $number): array|false
    {
        $result = $this->core->getDID($number, '');
        return is_array($result) ? $result : false;
    }

    public function allDids(): array
    {
        $result = $this->core->getAllDIDs('extension');
        return is_array($result) ? $result : [];
    }

    public function markReload(): void
    {
        if (function_exists('needreload')) {
            needreload();
        }
    }

    public function reloadNeeded(): bool
    {
        if (!function_exists('check_reload_needed')) {
            throw new FreepbxBridgeError('freepbx_unavailable', 'FreePBX reload state is unavailable', 503);
        }
        return (bool) check_reload_needed(true);
    }

    public function activeChannels(): int
    {
        $channels = $this->astman->CoreShowChannels();
        if ($channels === false || !is_array($channels)) {
            throw new FreepbxBridgeError('asterisk_unavailable', 'Asterisk active-channel status is unavailable', 503);
        }
        return count($channels);
    }

    public function reload(): array
    {
        $result = $this->framework->doReload(false);
        if (!is_array($result) || ($result['status'] ?? false) !== true || (int) ($result['code'] ?? 1) !== 0) {
            throw new FreepbxBridgeError('reload_failed', 'FreePBX reload failed', 503);
        }
        return ['status' => true];
    }

    public function command(string $command): string
    {
        $allowed = ['dialplan show from-ai-gateway-managed', 'pjsip show registrations'];
        if (!in_array($command, $allowed, true)) {
            throw new FreepbxBridgeError('internal_error', 'unsupported Asterisk readback', 500);
        }
        $response = $this->astman->send_request('Command', ['Command' => $command]);
        if (!is_array($response) || ($response['Response'] ?? '') !== 'Success') {
            throw new FreepbxBridgeError('asterisk_unavailable', 'Asterisk readback is unavailable', 503);
        }
        $data = $response['data'] ?? ($response['Output'] ?? '');
        if (!is_string($data)) {
            throw new FreepbxBridgeError('asterisk_unavailable', 'Asterisk readback is unavailable', 503);
        }
        return $data;
    }

    public function registrationStatus(string $trunkName, string $registration): string
    {
        if (!in_array($registration, ['send', 'receive'], true)) {
            return 'not_applicable';
        }
        if ($trunkName === '') {
            return 'unknown';
        }
        if ($registration === 'receive') {
            if (!method_exists($this->astman, 'PJSIPShowRegistrationInboundContactStatuses')) {
                return 'unknown';
            }
            $events = $this->astman->PJSIPShowRegistrationInboundContactStatuses();
            if (!is_array($events)) { return 'unknown'; }
            foreach ($events as $event) {
                if (!is_array($event)) { continue; }
                $name = (string) ($event['EndpointName'] ?? $event['ObjectName'] ?? $event['AOR'] ?? $event['Aor'] ?? '');
                if ($name !== $trunkName) { continue; }
                $status = strtolower((string) ($event['ContactStatus'] ?? $event['Status'] ?? ''));
                if (preg_match('/reachable|available|created/', $status)) { return 'registered'; }
                if (preg_match('/unreachable|unavailable|removed|rejected|failed/', $status)) { return 'unregistered'; }
            }
            return 'unknown';
        }
        $output = $this->command('pjsip show registrations');
        $namePattern = preg_quote($trunkName, '/');
        foreach (preg_split('/\R/', $output) ?: [] as $line) {
            if (!preg_match('/(?:^|\s)' . $namePattern . '(?:\/|\s|$)/i', $line)) {
                continue;
            }
            $lower = strtolower($line);
            if (preg_match('/\b(unregistered|not registered|rejected|failed)\b/', $lower)) { return 'unregistered'; }
            if (preg_match('/\bregistered\b/', $lower)) { return 'registered'; }
            if (str_contains($lower, 'request sent')) { return 'registering'; }
        }
        return 'unknown';
    }
}
