<?php
declare(strict_types=1);
$rolesMap = ['student' => '學生', 'teacher' => '老師', 'admin' => '管理員'];
$currentPage = $page ?? '';
?>
<nav>
  <a href="?page=rooms"<?= $currentPage === 'rooms' ? ' aria-current="page"' : '' ?>>教室清單</a>
  <?php if (!empty($user)): ?>
    · <a href="?page=booking_calendar"<?= $currentPage === 'booking_calendar' ? ' aria-current="page"' : '' ?>>空間／物品預約</a>
    · <a href="?page=booking_history"<?= $currentPage === 'booking_history' ? ' aria-current="page"' : '' ?>>我的借用紀錄</a>
    <?php if ($user['role'] === 'admin'): ?>
      · <a href="?page=booking_admin"<?= $currentPage === 'booking_admin' ? ' aria-current="page"' : '' ?>>審核與領還管理</a>
      · <a href="?page=admin"<?= $currentPage === 'admin' ? ' aria-current="page"' : '' ?>>帳號審核</a>
    <?php endif; ?>
    · <strong><?=e($user['username'])?></strong>（<?=e($rolesMap[$user['role']] ?? $user['role'])?>）
    <form method="post" style="display:inline;">
      <?php csrf(); ?>
      <button name="action" value="logout">登出</button>
    </form>
  <?php else: ?>
    · <a href="?page=login"<?= $currentPage === 'login' ? ' aria-current="page"' : '' ?>>登入</a>
    · <a href="?page=register"<?= $currentPage === 'register' ? ' aria-current="page"' : '' ?>>註冊</a>
  <?php endif; ?>
</nav>
<hr>
