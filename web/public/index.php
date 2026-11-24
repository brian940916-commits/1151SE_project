<?php
declare(strict_types=1);
require dirname(__DIR__) . '/api_client.php';
ini_set('session.use_strict_mode', '1');
session_set_cookie_params(['httponly' => true, 'samesite' => 'Lax',
    'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off']);
session_start();
header('Cache-Control: no-store');
$_SESSION['csrf'] ??= bin2hex(random_bytes(32));
function e($s): string { return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function csrf(): void { echo '<input type="hidden" name="csrf" value="' . e($_SESSION['csrf']) . '">'; }
function resetSession(): void {
    $_SESSION = ['csrf' => bin2hex(random_bytes(32))];
    session_regenerate_id(true);
}
$roles = ['student' => '學生', 'teacher' => '老師', 'admin' => '管理員'];
$page = $_GET['page'] ?? 'rooms';
$message = $_SESSION['flash'] ?? '';
unset($_SESSION['flash']);
$error = '';
$user = null;
$list = [];

try {
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!hash_equals($_SESSION['csrf'], (string)($_POST['csrf'] ?? ''))) {
            throw new RuntimeException('表單已失效，請重新整理後再試。');
        }
        switch ($_POST['action'] ?? '') {
            case 'login':
                $login = api('POST', '/api/auth/login', ['username' => $_POST['username'], 'password' => $_POST['password']]);
                resetSession();
                $_SESSION['token'] = $login['access_token'];
                $message = '登入成功';
                $page = 'rooms';
                break;
            case 'register':
                $account = api('POST', '/api/auth/register', ['username' => $_POST['username'], 'password' => $_POST['password'], 'role' => $_POST['role']]);
                $message = $account['approval_status'] === 'approved'
                    ? '學生帳號已建立，請登入。' : '老師帳號已送審，核准後即可登入。';
                $page = 'login';
                break;
            case 'review':
                api('POST', '/api/admin/users/' . (int)$_POST['id'] . '/review', ['status' => $_POST['decision']]);
                $message = '已處理申請';
                $page = 'admin';
                break;
            case 'logout':
                api('POST', '/api/auth/logout');
                resetSession();
                $message = '已登出';
                $page = 'rooms';
                break;
            case 'booking_create':
                $itemIds = array_map('intval', (array)($_POST['item_ids'] ?? []));
                $payload = [
                    'room_id' => (int)($_POST['room_id'] ?? 0),
                    'booking_date' => (string)($_POST['booking_date'] ?? ''),
                    'start_time' => (string)($_POST['start_time'] ?? ''),
                    'end_time' => (string)($_POST['end_time'] ?? ''),
                    'purpose' => trim((string)($_POST['purpose'] ?? '')),
                    'item_ids' => $itemIds,
                ];
                api('POST', '/api/bookings', $payload);
                $message = '借用申請已成功送出，請等待管理員審核。';
                $page = 'booking_history';
                break;
            case 'booking_review':
                $bookingId = (int)($_POST['booking_id'] ?? 0);
                $decision = (string)($_POST['decision'] ?? '');
                $reviewComment = trim((string)($_POST['review_comment'] ?? ''));
                api('POST', "/api/admin/bookings/{$bookingId}/review", [
                    'status' => $decision,
                    'review_comment' => $reviewComment !== '' ? $reviewComment : null,
                ]);
                $message = $decision === 'approved' ? '已核准借用申請。' : '已退件該借用申請。';
                $page = 'booking_admin';
                break;
            case 'booking_checkout':
                $bookingId = (int)($_POST['booking_id'] ?? 0);
                api('POST', "/api/admin/bookings/{$bookingId}/checkout");
                $message = '已完成借出領用登記。';
                $page = 'booking_admin';
                break;
            case 'booking_return':
                $bookingId = (int)($_POST['booking_id'] ?? 0);
                api('POST', "/api/admin/bookings/{$bookingId}/return");
                $message = '已確認歸還完成。';
                $page = 'booking_admin';
                break;
            default:
                throw new RuntimeException('無效的操作');
        }
        $_SESSION['flash'] = $message;
        header('Location: ?page=' . rawurlencode($page), true, 303);
        exit;
    }

    if (isset($_SESSION['token'])) {
        try {
            $user = api('GET', '/api/auth/me');
        } catch (RuntimeException $ex) {
            if ($ex->getCode() !== 401) { throw $ex; }
            resetSession();
            $message = '登入已過期，請重新登入。';
        }
    }

    // 需登入之頁面檢查
    if (in_array($page, ['booking_calendar', 'booking_history', 'booking_admin'], true)) {
        if (!$user) {
            $_SESSION['flash'] = '請先登入系統。';
            header('Location: ?page=login', true, 303);
            exit;
        }
    }

    if ($page === 'admin') {
        $list = api('GET', '/api/admin/pending');
    } elseif ($page === 'rooms') {
        $list = api('GET', '/api/rooms');
    } elseif ($page === 'booking_calendar') {
        $rooms = api('GET', '/api/rooms');
        $items = api('GET', '/api/items');
        $selectedRoomId = (int)($_GET['room_id'] ?? ($rooms[0]['room_id'] ?? 1));
        $weekStartParam = (string)($_GET['week_start'] ?? '');
        $weeklyUrl = "/api/bookings/weekly?room_id={$selectedRoomId}" . ($weekStartParam !== '' ? '&week_start=' . urlencode($weekStartParam) : '');
        $weeklyData = api('GET', $weeklyUrl);
    } elseif ($page === 'booking_history') {
        $bookings = api('GET', '/api/bookings');
    } elseif ($page === 'booking_admin') {
        if ($user['role'] !== 'admin') {
            throw new RuntimeException('需要管理員權限', 403);
        }
        $currentStatus = (string)($_GET['status'] ?? '');
        $adminBookingsUrl = '/api/bookings' . ($currentStatus !== '' ? '?status=' . urlencode($currentStatus) : '');
        $bookings = api('GET', $adminBookingsUrl);
    }
} catch (Exception $ex) {
    $error = $ex->getMessage();
}
?>
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>管院空間與物品預約系統</title>
</head>
<body>
<?php require dirname(__DIR__) . '/templates/nav.php'; ?>
<main>
<?php if ($message): ?><p role="status" style="color: green;"><strong><?=e($message)?></strong></p><?php endif; ?>
<?php if ($error): ?><p role="alert" style="color: red;"><strong><?=e($error)?></strong></p><?php endif; ?>

<?php if ($page === 'login' || $page === 'register'): $register = $page === 'register'; ?>
  <h1><?=$register ? '註冊帳號' : '登入'?></h1>
  <form method="post"><?php csrf(); ?>
  <p><label>帳號 <input name="username" autocomplete="username" pattern="[A-Za-z0-9_.\-]{3,40}" required></label>（3–40 個英數字、底線、點或短橫線）</p>
  <p><label>密碼 <input type="password" name="password" minlength="8" maxlength="128" autocomplete="<?=$register ? 'new-password' : 'current-password'?>" required></label>（至少 8 字元）</p>
  <?php if ($register): ?><p><label>申請身分 <select name="role"><option value="student">學生</option><option value="teacher">老師</option></select></label>　學生註冊後可直接登入；老師帳號須由管理員核准。</p><?php endif; ?>
  <button name="action" value="<?=$page?>"><?=$register ? '送出申請' : '登入'?></button></form>

<?php elseif ($page === 'admin' && !$error): ?>
  <h1>待審帳號</h1>
  <?php if (!$list): ?><p>目前沒有待審申請。</p><?php endif; ?>
  <?php foreach ($list as $person): ?>
  <form method="post"><?php csrf(); ?>
  <input type="hidden" name="id" value="<?=e($person['user_id'])?>"><input type="hidden" name="action" value="review">
  <?=e($person['username'])?> · <?=e($roles[$person['role']])?>
  <button name="decision" value="approved">核准</button> <button name="decision" value="rejected">退件</button></form>
  <?php endforeach; ?>

<?php elseif ($page === 'rooms' && !$error): ?>
  <h1>管院教室清單</h1><p>共 <?=count($list)?> 筆。借用及排課資格待確認。</p>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;"><thead><tr><th>房號</th><th>樓層</th><th>空間名稱</th><th>容量（人）</th><th>空間借用</th></tr></thead><tbody>
  <?php foreach ($list as $room): ?>
    <tr>
      <td><?=e($room['room_code'])?></td>
      <td><?=e($room['floor'])?></td>
      <td><?=e($room['name'])?></td>
      <td><?=e($room['capacity'] ?? '待確認')?></td>
      <td><a href="?page=booking_calendar&room_id=<?=e($room['room_id'])?>">檢視週借用／申請預約</a></td>
    </tr>
  <?php endforeach; ?>
  </tbody></table>

<?php elseif ($page === 'booking_calendar' && !$error): ?>
  <?php require dirname(__DIR__) . '/pages/bookings/calendar.php'; ?>

<?php elseif ($page === 'booking_history' && !$error): ?>
  <?php require dirname(__DIR__) . '/pages/bookings/history.php'; ?>

<?php elseif ($page === 'booking_admin' && !$error): ?>
  <?php require dirname(__DIR__) . '/pages/bookings/admin.php'; ?>

<?php endif; ?>
</main>
</body>
</html>
