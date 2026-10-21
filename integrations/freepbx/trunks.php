<?php
declare(strict_types=1);

final class FreepbxTrunkService
{
    public function __construct(private FreepbxBmo $bmo)
    {
    }

    public function list(): array
    {
        $result = [];
        foreach ($this->bmo->trunks() as $raw) {
            $view = $this->view($raw);
            $registration = (string) ($raw['details']['registration'] ?? 'none');
            $name = (string) ($raw['details']['trunk_name'] ?? $raw['details']['channelid'] ?? '');
            try {
                $view['registration_status'] = $this->bmo->registrationStatus($name, $registration);
            } catch (Throwable) {
                $view['registration_status'] = 'unknown';
            }
            $result[] = $view;
        }
        return $result;
    }

    public function save(array $payload): array
    {
        $id = array_key_exists('id', $payload) ? (int) FreepbxValidation::trunkId($payload['id']) : null;
        $raw = $id === null ? null : $this->bmo->trunk($id);
        if ($raw === null) {
            $name = FreepbxValidation::freeText($payload['name'] ?? '', 'name');
            $candidateName = $this->stableName($name);
            foreach ($this->bmo->trunks() as $existing) {
                if ((string) ($existing['details']['trunk_name'] ?? '') === $candidateName) {
                    throw new FreepbxBridgeError('trunk_collision', 'a trunk with this name already exists', 409);
                }
            }
        }
        $current = $raw === null ? $this->defaults() : $this->current($raw);
        $transports = $this->bmo->transports();
        $merged = FreepbxValidation::trunkPatch($payload, $raw === null, $current, $transports);
        $settings = $this->settings($merged, $raw, $id);
        $snapshot = $raw === null ? [] : ['row' => $raw['row'], 'settings' => $this->settingsFromRaw($raw)];
        $savedId = $this->bmo->saveTrunk($merged['name'], $settings, $id, $snapshot);
        $this->bmo->markReload();
        $readback = $this->bmo->trunk($savedId);
        $view = $this->view($readback);
        $view['registration_status'] = 'unknown';
        try {
            $name = (string) ($readback['details']['trunk_name'] ?? '');
            $view['registration_status'] = $this->bmo->registrationStatus($name, (string) ($readback['details']['registration'] ?? 'none'));
        } catch (Throwable) {
            // A successful BMO save still remains pending when live status is unavailable.
        }
        return $view;
    }

    private function defaults(): array
    {
        return [
            'name' => '', 'host' => '', 'port' => 5060, 'transport' => '',
            'authentication' => 'none', 'registration' => 'none', 'username' => '',
            'auth_username' => '', 'password' => '', 'match' => '', 'from_domain' => '',
            'from_user' => '', 'contact_user' => '', 'outbound_caller_id' => '',
            'codecs' => [], 'enabled' => true,
        ];
    }

    private function current(array $raw): array
    {
        $row = $raw['row'];
        $d = $raw['details'];
        $authentication = (string) ($d['authentication'] ?? 'none');
        if ($authentication === 'off') { $authentication = 'none'; }
        $codecs = array_values(array_filter(array_map('trim', explode(',', (string) ($d['codecs'] ?? '')))));
        return [
            'name' => (string) ($row['name'] ?? ''),
            'host' => (string) ($d['sip_server'] ?? ''),
            'port' => ($d['sip_server_port'] ?? '') === '' ? null : (int) $d['sip_server_port'],
            'transport' => (string) ($d['transport'] ?? ''),
            'authentication' => $authentication,
            'registration' => (string) ($d['registration'] ?? 'none'),
            'username' => (string) ($d['username'] ?? ''),
            'auth_username' => (string) ($d['auth_username'] ?? ''),
            'password' => (string) ($d['secret'] ?? ''),
            'match' => (string) ($d['match'] ?? ''),
            'from_domain' => (string) ($d['from_domain'] ?? ''),
            'from_user' => (string) ($d['from_user'] ?? ''),
            'contact_user' => (string) ($d['contact_user'] ?? ''),
            'outbound_caller_id' => (string) ($row['outcid'] ?? ''),
            'codecs' => $codecs,
            'enabled' => (string) ($row['disabled'] ?? 'off') !== 'on',
        ];
    }

    private function settings(array $merged, ?array $raw, ?int $id): array
    {
        $settings = $raw === null ? $this->newDefaults() : $this->settingsFromRaw($raw);
        $trunkName = (string) ($settings['trunk_name'] ?? '');
        if ($trunkName === '') {
            $trunkName = $this->stableName($merged['name']);
        }
        $settings['trunk_name'] = $trunkName;
        if (($settings['channelid'] ?? '') === '') { $settings['channelid'] = $trunkName; }
        $settings['tech'] = 'pjsip';
        $settings['outcid'] = $merged['outbound_caller_id'];
        $settings['sip_server'] = $merged['host'];
        $settings['sip_server_port'] = $merged['port'] === null ? '' : (string) $merged['port'];
        $settings['transport'] = $merged['transport'];
        $settings['authentication'] = $merged['authentication'];
        $settings['registration'] = $merged['registration'];
        $settings['username'] = $merged['username'];
        $settings['auth_username'] = $merged['auth_username'];
        $settings['secret'] = $merged['password'];
        $settings['match'] = $merged['match'];
        $settings['from_domain'] = $merged['from_domain'];
        $settings['from_user'] = $merged['from_user'];
        $settings['contact_user'] = $merged['contact_user'];
        $settings['disabletrunk'] = $merged['enabled'] ? 'off' : 'on';
        if ($merged['codecs']) {
            $settings['codec'] = array_fill_keys($merged['codecs'], 1);
        } else {
            unset($settings['codec']);
        }
        if ($id !== null) { $settings['trunknum'] = $id; }
        return $settings;
    }

    private function newDefaults(): array
    {
        $defaults = $this->bmo->pjsipDefaults();
        $defaults['context'] = 'from-pstn';
        $defaults['disabletrunk'] = 'off';
        return $defaults;
    }

    private function settingsFromRaw(array $raw): array
    {
        $row = $raw['row'];
        $settings = $raw['details'];
        $settings['trunknum'] = (int) $row['trunkid'];
        $settings['tech'] = 'pjsip';
        foreach (['outcid', 'keepcid', 'maxchans', 'failtrunk', 'dialoutprefix', 'channelid', 'usercontext', 'provider', 'continue', 'dialopts'] as $field) {
            if (array_key_exists($field, $row)) { $settings[$field] = $row[$field]; }
        }
        $settings['disabletrunk'] = (string) ($row['disabled'] ?? 'off');
        $codecValues = array_values(array_filter(array_map('trim', explode(',', (string) ($settings['codecs'] ?? '')))));
        $settings['codec'] = array_fill_keys($codecValues, 1);
        return $settings;
    }

    private function stableName(string $displayName): string
    {
        $slug = strtolower(trim((string) preg_replace('/[^a-z0-9]+/i', '_', $displayName), '_'));
        $slug = substr($slug === '' ? 'trunk' : $slug, 0, 18);
        return 'gateway_' . $slug . '_' . substr(hash('sha256', $displayName), 0, 10);
    }

    private function view(array $raw): array
    {
        $current = $this->current($raw);
        return [
            'id' => (string) $raw['row']['trunkid'],
            'name' => $current['name'],
            'host' => $current['host'],
            'port' => $current['port'],
            'transport' => $current['transport'],
            'authentication' => $current['authentication'],
            'registration' => $current['registration'],
            'username' => $current['username'],
            'auth_username' => $current['auth_username'],
            'password_set' => $current['password'] !== '',
            'match' => $current['match'],
            'from_domain' => $current['from_domain'],
            'from_user' => $current['from_user'],
            'contact_user' => $current['contact_user'],
            'outbound_caller_id' => $current['outbound_caller_id'],
            'codecs' => $current['codecs'],
            'enabled' => $current['enabled'],
        ];
    }
}
