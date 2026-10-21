<?php
declare(strict_types=1);

final class FreepbxBridge
{
    public function __construct(private FreepbxBmo $bmo, private FreepbxTrunkService $trunks, private FreepbxDidService $dids, private array $config)
    {
    }

    public function dispatch(string $operation, array $payload): array
    {
        return match ($operation) {
            'status' => $this->readOnly($payload, fn(): array => $this->dids->status()),
            'list_trunks' => $this->readOnly($payload, fn(): array => $this->trunks->list()),
            'save_trunk' => $this->saveTrunk($payload),
            'save_did' => $this->dids->save($payload),
            'apply' => $this->readOnly($payload, fn(): array => $this->dids->apply()),
            default => throw new FreepbxBridgeError('unknown_operation', 'operation is not supported', 422),
        };
    }

    private function readOnly(array $payload, callable $action): array
    {
        FreepbxValidation::only($payload, [], 'payload');
        return $action();
    }

    private function saveTrunk(array $payload): array
    {
        $lock = new FreepbxBridgeLock($this->config['lock_path']);
        return $this->trunks->save($payload);
    }
}
