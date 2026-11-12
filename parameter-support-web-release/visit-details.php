<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('X-Content-Type-Options: nosniff');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    header('Allow: POST');
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

$configFile = 'D:/visit-counter-private/visit-counter-config.php';
if (!is_file($configFile)) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Visit details unavailable']);
    exit;
}
require $configFile;

$input = json_decode((string) file_get_contents('php://input'), true);
$password = is_array($input) ? (string) ($input['password'] ?? '') : '';
if (!defined('VISIT_ADMIN_PASSWORD') || !hash_equals((string) VISIT_ADMIN_PASSWORD, $password)) {
    usleep(350000);
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
    exit;
}

try {
    $pdo = new PDO(
        'mysql:host=' . DB_HOST . ';port=' . DB_PORT . ';dbname=' . DB_NAME . ';charset=utf8mb4',
        DB_USER,
        DB_PASSWORD,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]
    );
    $pdo->exec("SET time_zone = '+08:00'");
    $rows = $pdo->query("SELECT DATE_FORMAT(visited_at, '%Y-%m-%d %H:%i:%s') AS time, ip_address AS ip, location, device_info AS device FROM visit_details ORDER BY id DESC LIMIT 100")->fetchAll();
    echo json_encode(['ok' => true, 'visits' => $rows], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
} catch (Throwable $error) {
    error_log('Visit details error: ' . $error->getMessage());
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Visit details unavailable']);
}
