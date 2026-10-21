<?php
declare(strict_types=1);

foreach (glob(__DIR__ . '/../../integrations/freepbx/*.php') as $file) {
    if (basename($file) !== 'index.php') { require_once $file; }
}

$checks = 0;
$assert = static function (bool $condition, string $message) use (&$checks): void {
    $checks++;
    if (!$condition) { throw new RuntimeException($message); }
};
$throws = static function (callable $call, string $message) use (&$assert): void {
    try { $call(); } catch (FreepbxBridgeError) { return; }
    $assert(false, $message);
};

$assert(FreepbxValidation::didNumber('+999999920261021') === '+999999920261021', 'exact DID accepted');
$throws(static fn() => FreepbxValidation::didNumber(' 999'), 'DID whitespace rejected');
$throws(static fn() => FreepbxValidation::didNumber('123,1'), 'DID punctuation rejected');
$throws(static fn() => FreepbxValidation::label(''), 'DID label required');
$assert(FreepbxValidation::patternMatches('_X.', '123') === true, 'Asterisk pattern collision detected');
$assert(FreepbxValidation::patternMatches('_X.', 'abc') === false, 'Asterisk pattern rejects letters');
$assert(FreepbxValidation::sourceAllowed('172.18.0.2', ['172.18.0.0/16'], ['172.18.0.1/32']) === true, 'private source allowed');
$assert(FreepbxValidation::sourceAllowed('172.18.0.1', ['172.18.0.0/16'], ['172.18.0.1/32']) === false, 'docker gateway denied');
$assert(FreepbxValidation::sourceAllowed('203.0.113.8', ['172.18.0.0/16'], []) === false, 'public source denied');
$config = FreepbxBridgeConfig::fromArray(['bearer_token' => str_repeat('t', 32), 'allowed_cidrs' => ['172.18.0.0/16']]);
$assert($config['allowed_cidrs'] === ['172.18.0.0/16'], 'private source CIDR accepted');
$throws(static fn() => FreepbxBridgeConfig::fromArray(['bearer_token' => str_repeat('t', 32), 'allowed_cidrs' => ['172.18.0.0/1']]), 'broad private-looking CIDR rejected');
$throws(static fn() => FreepbxBridgeConfig::fromArray(['bearer_token' => str_repeat('t', 32), 'allowed_cidrs' => ['172.18.0.0/16'], 'denied_cidrs' => '172.18.0.2/32']), 'malformed denied CIDR list rejected');
$assert(FreepbxValidation::object([], 'payload') === [], 'empty JSON object accepted');
$throws(static fn() => FreepbxValidation::object(['unexpected'], 'payload'), 'JSON array payload rejected');

$current = [
    'name' => 'Carrier', 'host' => '198.51.100.10', 'port' => 5060, 'transport' => '',
    'authentication' => 'outbound', 'registration' => 'send', 'username' => 'acct',
    'auth_username' => 'auth', 'password' => 'keep-me', 'match' => '198.51.100.10/32',
    'from_domain' => '', 'from_user' => '', 'contact_user' => '', 'outbound_caller_id' => '',
    'codecs' => ['ulaw'], 'enabled' => true,
];
$preserved = FreepbxValidation::trunkPatch(['name' => 'Renamed'], false, $current, ['', '0.0.0.0-udp']);
$assert($preserved['password'] === 'keep-me', 'omitted password preserved');
$assert($preserved['host'] === $current['host'], 'omitted host preserved');
$cleared = FreepbxValidation::trunkPatch(['username' => '', 'auth_username' => '', 'from_domain' => ''], false, array_merge($current, ['authentication' => 'none', 'registration' => 'none', 'match' => '198.51.100.10/32']), ['', '0.0.0.0-udp']);
$assert($cleared['username'] === '' && $cleared['auth_username'] === '' && $cleared['from_domain'] === '', 'explicit optional token clears accepted');
$created = FreepbxValidation::trunkPatch([
    'name' => 'IP carrier', 'host' => '198.51.100.11', 'match' => '198.51.100.11/32',
    'authentication' => 'none', 'registration' => 'none',
], true, [
    'name' => '', 'host' => '', 'port' => 5060, 'transport' => '', 'authentication' => 'none',
    'registration' => 'none', 'username' => '', 'auth_username' => '', 'password' => '',
    'match' => '', 'from_domain' => '', 'from_user' => '', 'contact_user' => '',
    'outbound_caller_id' => '', 'codecs' => [], 'enabled' => true,
], ['', '0.0.0.0-udp']);
$assert($created['port'] === 5060 && $created['match'] === '198.51.100.11/32', 'IP trunk defaults validated');
$throws(static fn() => FreepbxValidation::trunkPatch([
    'name' => 'bad', 'host' => '198.51.100.12', 'authentication' => 'none', 'registration' => 'send',
], true, $current, ['', '0.0.0.0-udp']), 'IP trunk cannot send registration');
$throws(static fn() => FreepbxValidation::trunkPatch([
    'name' => 'bad', 'host' => '198.51.100.12', 'match' => '198.51.100.12/32', 'authentication' => 'outbound', 'registration' => 'send', 'username' => 'acct',
], true, array_merge($current, ['password' => '']), ['', '0.0.0.0-udp']), 'registration requires password');
$throws(static fn() => FreepbxValidation::trunkPatch(['username' => ''], false, $current, ['', '0.0.0.0-udp']), 'outbound username cannot be cleared');
$throws(static fn() => FreepbxValidation::trunkId('not-a-number'), 'trunk id must be numeric');
$throws(static fn() => FreepbxValidation::trunkId('01'), 'trunk id must be canonical');

$routes = [['route_id' => '11111111-1111-4111-8111-111111111111', 'number' => '+999999920261021']];
$dialplan = FreepbxGatewayDialplan::render($routes);
$assert(str_contains($dialplan, 'AI_GATEWAY_DID=+999999920261021'), 'managed DID variable generated');
$assert(str_contains($dialplan, 'Stasis(asterisk-ai-gateway)'), 'gateway Stasis generated');
$assert(!str_contains($dialplan, 'AI_GATEWAY_AGENT'), 'legacy agent variable is absent');
$cliOutput = "[ Context 'from-ai-gateway-managed' created by 'pbx_config' ]\n"
    . "  '9898' => 1. NoOp(Asterisk AI Agent Gateway managed DID)\n"
    . "            2. Set(AI_GATEWAY_DID=9898)\n"
    . "            3. Stasis(asterisk-ai-gateway)\n"
    . "            4. Hangup()\n"
    . "  '9999' => 1. NoOp(Asterisk AI Agent Gateway managed DID)\n"
    . "            2. Set(AI_GATEWAY_DID=9999)\n"
    . "            3. Stasis(other-app)\n"
    . "            4. Hangup()\n";
$assert(FreepbxGatewayDialplan::hasExactRoute($cliOutput, '9898'), 'native CLI exact route parsed');
$annotatedCliOutput = "  '9898' => 1. NoOp(Asterisk AI Agent Gateway test) [extensions_custom.conf:25]\n"
    . "            2. Set(AI_GATEWAY_DID=9898) [extensions_custom.conf:26]\n"
    . "            3. Stasis(asterisk-ai-gateway) [extensions_custom.conf:27]\n"
    . "            4. Hangup() [extensions_custom.conf:28]\n";
$assert(FreepbxGatewayDialplan::hasExactRoute($annotatedCliOutput, '9898'), 'native CLI source annotations parsed');
$assert(!FreepbxGatewayDialplan::hasExactRoute($cliOutput, '9999'), 'wrong Stasis app rejected for target route');
$wrongVariable = str_replace('Set(AI_GATEWAY_DID=9898)', 'Set(AI_GATEWAY_DID=9999)', $cliOutput);
$assert(!FreepbxGatewayDialplan::hasExactRoute($wrongVariable, '9898'), 'wrong DID variable rejected for target route');
$noncontiguous = str_replace('2. Set(AI_GATEWAY_DID=9898)', '3. Set(AI_GATEWAY_DID=9898)', $cliOutput);
$assert(!FreepbxGatewayDialplan::hasExactRoute($noncontiguous, '9898'), 'noncontiguous route steps rejected');
$included = FreepbxGatewayDialplan::ensureInclude("[from-internal-custom]\n#include extensions_gateway_managed.conf\n#tryinclude /etc/asterisk/extensions_gateway_managed.conf\n");
$assert(substr_count($included, '#include extensions_gateway_managed.conf') === 1, 'managed include is singular');

$temp = sys_get_temp_dir() . '/freepbx-bridge-' . bin2hex(random_bytes(5));
mkdir($temp, 0700, true);
$state = new FreepbxRouteState($temp . '/state.json');
$state->save($routes);
$loaded = $state->load();
$assert($loaded === $routes, 'route state round trip');
$stateRaw = json_decode((string) file_get_contents($temp . '/state.json'), true);
$assert(array_keys($stateRaw['routes'][0]) === ['route_id', 'number'], 'state stores only route ownership');
unlink($temp . '/state.json');
$lockTarget = $temp . '/real-lock';
file_put_contents($lockTarget, '');
symlink($lockTarget, $temp . '/lock-link');
$throws(static fn() => new FreepbxBridgeLock($temp . '/lock-link'), 'lock symlink rejected');
unlink($temp . '/lock-link');
unlink($lockTarget);
rmdir($temp);

echo "freepbx bridge checks: {$checks} passed\n";
