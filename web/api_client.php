<?php
declare(strict_types=1);

function api(string $method, string $path, ?array $data = null): array {
    $configPath = dirname(__DIR__) . '/.env';
    $file = is_file($configPath) ? parse_ini_file($configPath, false, INI_SCANNER_RAW) : [];
    $base = getenv('API_BASE_URL') ?: ($file['API_BASE_URL'] ?? 'http://127.0.0.1:8000');
    $curl = curl_init(rtrim($base, '/') . $path);
    $headers = ['Accept: application/json'];
    if (isset($_SESSION['token'])) {
        $headers[] = 'Authorization: Bearer ' . $_SESSION['token'];
    }
    if ($data !== null) {
        $headers[] = 'Content-Type: application/json';
        curl_setopt($curl, CURLOPT_POSTFIELDS, json_encode($data, JSON_THROW_ON_ERROR));
    }
    curl_setopt_array($curl, [
        CURLOPT_CUSTOMREQUEST => $method, CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10,
    ]);
    $raw = curl_exec($curl);
    $code = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    curl_close($curl);
    if ($raw === false || $code >= 500) {
        throw new RuntimeException('服務暫時無法使用，請確認 API 與資料庫已啟動。');
    }
    $body = $raw === '' ? [] : json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    if ($code >= 400) {
        $detail = $body['detail'] ?? '';
        throw new RuntimeException(is_string($detail) ? $detail : '請檢查帳號、密碼和角色格式。', $code);
    }
    return $body;
}
