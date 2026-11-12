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

// Keep database credentials outside the public website directory.
// Website root: D:/web_gmy
// Private config: D:/visit-counter-private/visit-counter-config.php
$configFile = 'D:/visit-counter-private/visit-counter-config.php';
if (!is_file($configFile)) {
    error_log('Visit counter configuration is missing.');
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Visit counter unavailable']);
    exit;
}
require $configFile;

function getVisitorIp(): string
{
    // The current deployment connects directly to Apache without a trusted CDN.
    // Do not trust client-supplied X-Forwarded-For headers here.
    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    return filter_var($ip, FILTER_VALIDATE_IP) ? $ip : '0.0.0.0';
}

function getDeviceInfo(): string
{
    $ua = (string) ($_SERVER['HTTP_USER_AGENT'] ?? '');
    if ($ua === '') return '未知设备';

    if (preg_match('/iPad|Tablet|PlayBook|Silk/i', $ua)) {
        $type = '平板';
    } elseif (preg_match('/Mobile|Android|iPhone|iPod|IEMobile|Opera Mini/i', $ua)) {
        $type = '手机';
    } else {
        $type = '电脑';
    }

    if (preg_match('/Windows NT 10\.0/i', $ua)) {
        $os = 'Windows 10/11';
    } elseif (preg_match('/Windows/i', $ua)) {
        $os = 'Windows';
    } elseif (preg_match('/Android\s+([0-9.]+)/i', $ua, $match)) {
        $os = 'Android ' . $match[1];
    } elseif (preg_match('/iPhone OS\s+([0-9_]+)/i', $ua, $match)) {
        $os = 'iOS ' . str_replace('_', '.', $match[1]);
    } elseif (preg_match('/iPad.*OS\s+([0-9_]+)/i', $ua, $match)) {
        $os = 'iPadOS ' . str_replace('_', '.', $match[1]);
    } elseif (preg_match('/Mac OS X\s+([0-9_]+)/i', $ua, $match)) {
        $os = 'macOS ' . str_replace('_', '.', $match[1]);
    } elseif (preg_match('/Linux/i', $ua)) {
        $os = 'Linux';
    } else {
        $os = '未知系统';
    }

    if (preg_match('/Edg\/([0-9.]+)/i', $ua, $match)) {
        $browser = 'Edge ' . explode('.', $match[1])[0];
    } elseif (preg_match('/OPR\/([0-9.]+)/i', $ua, $match)) {
        $browser = 'Opera ' . explode('.', $match[1])[0];
    } elseif (preg_match('/Chrome\/([0-9.]+)/i', $ua, $match)) {
        $browser = 'Chrome ' . explode('.', $match[1])[0];
    } elseif (preg_match('/Firefox\/([0-9.]+)/i', $ua, $match)) {
        $browser = 'Firefox ' . explode('.', $match[1])[0];
    } elseif (preg_match('/Version\/([0-9.]+).*Safari/i', $ua, $match)) {
        $browser = 'Safari ' . explode('.', $match[1])[0];
    } else {
        $browser = '未知浏览器';
    }

    return $type . ' · ' . $os . ' · ' . $browser;
}

function fetchLocationJson(string $url): ?array
{
    if (!function_exists('curl_init')) return null;
    $curl = curl_init($url);
    curl_setopt_array($curl, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 2,
        CURLOPT_TIMEOUT => 3,
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_USERAGENT => 'ParameterSupportVisitCounter/1.0',
    ]);
    $body = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    if ($status !== 200 || !is_string($body) || $body === '') return null;
    $data = json_decode($body, true);
    return is_array($data) ? $data : null;
}

function queryIpLocation(string $ip): string
{
    if ($ip === '127.0.0.1' || $ip === '::1' || !filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE)) {
        return '本地/内网';
    }

    // Primary HTTPS provider, then a second provider as fallback.
    $data = fetchLocationJson('https://ipwho.is/' . rawurlencode($ip) . '?lang=zh');
    if (is_array($data) && ($data['success'] ?? false) === true) {
        $parts = array_filter([
            $data['country'] ?? '',
            $data['region'] ?? '',
            $data['city'] ?? '',
            $data['connection']['isp'] ?? '',
        ]);
        if ($parts) return implode(' · ', array_unique($parts));
    }

    $data = fetchLocationJson('http://ip-api.com/json/' . rawurlencode($ip) . '?lang=zh-CN&fields=status,country,regionName,city,isp');
    if (!is_array($data) || ($data['status'] ?? '') !== 'success') return '未知';
    $parts = array_filter([$data['country'] ?? '', $data['regionName'] ?? '', $data['city'] ?? '', $data['isp'] ?? '']);
    return $parts ? implode(' · ', array_unique($parts)) : '未知';
}

try {
    $pdo = new PDO(
        'mysql:host=' . DB_HOST . ';port=' . DB_PORT . ';dbname=' . DB_NAME . ';charset=utf8mb4',
        DB_USER,
        DB_PASSWORD,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]
    );
    // Count "today" using China Standard Time regardless of server defaults.
    $pdo->exec("SET time_zone = '+08:00'");

    // Each successful page open or refresh adds one PV to today's row.
    $pdo->beginTransaction();
    $pdo->exec(
        "INSERT INTO page_views (visit_date, views) VALUES (CURDATE(), 1)
         ON DUPLICATE KEY UPDATE views = views + 1"
    );
    $row = $pdo->query(
        "SELECT
            COALESCE(SUM(CASE WHEN visit_date = CURDATE() THEN views ELSE 0 END), 0) AS today,
            COALESCE(SUM(views), 0) AS total
         FROM page_views"
    )->fetch();
    $pdo->commit();

    // Visit-detail recording is optional and must never stop the PV counter.
    try {
        $ip = getVisitorIp();
        $locationQuery = $pdo->prepare("SELECT location FROM ip_location_cache WHERE ip_address = ? AND updated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)");
        $locationQuery->execute([$ip]);
        $location = $locationQuery->fetchColumn();
        if (!is_string($location) || $location === '') {
            $location = queryIpLocation($ip);
            // Do not cache transient lookup failures for 30 days.
            if ($location !== '未知') {
                $cache = $pdo->prepare(
                    "INSERT INTO ip_location_cache (ip_address, location, updated_at) VALUES (?, ?, NOW())
                     ON DUPLICATE KEY UPDATE location = VALUES(location), updated_at = VALUES(updated_at)"
                );
                $cache->execute([$ip, $location]);
                $repair = $pdo->prepare("UPDATE visit_details SET location = ? WHERE ip_address = ? AND location = '未知'");
                $repair->execute([$location, $ip]);
            } else {
                error_log('IP location lookup failed for ' . $ip);
            }
        }
        $device = getDeviceInfo();
        $visit = $pdo->prepare("INSERT INTO visit_details (visited_at, ip_address, location, device_info) VALUES (NOW(), ?, ?, ?)");
        $visit->execute([$ip, $location, $device]);
    } catch (Throwable $detailError) {
        error_log('Visit detail recording error: ' . $detailError->getMessage());
    }

    echo json_encode([
        'ok' => true,
        'today' => (int) $row['today'],
        'total' => (int) $row['total'],
    ], JSON_UNESCAPED_UNICODE);
} catch (Throwable $error) {
    if (isset($pdo) && $pdo instanceof PDO && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    error_log('Visit counter error: ' . $error->getMessage());
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Visit counter unavailable']);
}
