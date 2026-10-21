<?php
declare(strict_types=1);

final class FreepbxBridgeError extends RuntimeException
{
    public string $safeCode;
    public int $httpStatus;

    public function __construct(string $safeCode, string $message, int $httpStatus = 400, ?Throwable $previous = null)
    {
        parent::__construct($message, 0, $previous);
        $this->safeCode = $safeCode;
        $this->httpStatus = $httpStatus;
    }
}
