<?php
declare(strict_types=1);

$source = $argv[2] ?? (__DIR__ . '/../../integrations/freepbx');
require_once $source . '/errors.php';
require_once $source . '/validation.php';
require_once $source . '/bmo.php';
require_once $source . '/trunks.php';

$freepbxConf = $argv[1] ?? '/etc/freepbx.conf';
$bmo = FreepbxBmo::bootstrap($freepbxConf);
$trunks = (new FreepbxTrunkService($bmo))->list();

echo json_encode([
    'transports' => $bmo->transports(),
    'active_channels' => $bmo->activeChannels(),
    'reload_needed' => $bmo->reloadNeeded(),
    'trunk_count' => count($trunks),
    'trunk_ids' => array_map(static fn(array $trunk): string => $trunk['id'], $trunks),
    'registration_statuses' => array_map(static fn(array $trunk): string => (string) $trunk['registration_status'], $trunks),
    'password_set_flags' => array_map(static fn(array $trunk): bool => (bool) $trunk['password_set'], $trunks),
], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
