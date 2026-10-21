<?php
declare(strict_types=1);

final class FreepbxBridgeLock
{
    private $handle;

    public function __construct(string $path)
    {
        if (!is_dir(dirname($path)) || is_link($path)) {
            throw new FreepbxBridgeError('lock_unavailable', 'bridge lock directory is unavailable', 503);
        }
        $this->handle = fopen($path, 'c');
        if ($this->handle === false || !flock($this->handle, LOCK_EX)) {
            throw new FreepbxBridgeError('lock_unavailable', 'bridge lock is unavailable', 503);
        }
        @chmod($path, 0600);
    }

    public function __destruct()
    {
        if (is_resource($this->handle)) {
            flock($this->handle, LOCK_UN);
            fclose($this->handle);
        }
    }
}
