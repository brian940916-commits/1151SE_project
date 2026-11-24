<?php
declare(strict_types=1);
/**
 * @var array $bookings
 * @var string $currentStatus
 */
$statusLabels = [
    'pending' => '待審核',
    'approved' => '已核准 (待領用)',
    'checked_out' => '借出中 (待歸還)',
    'returned' => '已歸還',
    'rejected' => '已退件',
];
$filterList = [
    '' => '全部紀錄',
    'pending' => '待審核',
    'approved' => '已核准 (待領用)',
    'checked_out' => '借出中 (待歸還)',
    'returned' => '已歸還',
    'rejected' => '已退件',
];
?>
<section>
  <h1>空間與物品借用管理（管理員專區）</h1>
  <p>處理各空間與物品借用審核、登記借出鑰匙與器材領用，以及確認歸還作業。</p>

  <!-- 篩選列 -->
  <p>
    <strong>狀態篩選：</strong>
    <?php foreach ($filterList as $st => $label): ?>
      <?php if ($st === $currentStatus): ?>
        <strong>[<?=e($label)?>]</strong>
      <?php else: ?>
        <a href="?page=booking_admin<?= $st !== '' ? '&status=' . urlencode($st) : '' ?>"><?=e($label)?></a>
      <?php endif; ?>
      &nbsp;|&nbsp;
    <?php endforeach; ?>
  </p>

  <?php if (empty($bookings)): ?>
    <p>目前沒有符合條件的借用申請紀錄。</p>
  <?php else: ?>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
      <thead>
        <tr bgcolor="#f0f0f0">
          <th>編號</th>
          <th>申請人</th>
          <th>空間</th>
          <th>日期與時段</th>
          <th>借用物品</th>
          <th>事由</th>
          <th>目前狀態</th>
          <th>紀錄與經手人</th>
          <th style="min-width: 220px;">管理操作</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($bookings as $b): ?>
          <tr valign="top">
            <td align="center">#<?=e($b['booking_id'])?></td>
            <td>
              <strong><?=e($b['applicant_username'])?></strong><br>
              <small>(<?=e($b['applicant_role'])?>)</small>
            </td>
            <td><?=e($b['room_code'])?><br><small><?=e($b['room_name'])?></small></td>
            <td>
              <?=e($b['booking_date'])?><br>
              <strong><?=e($b['start_time'])?> - <?=e($b['end_time'])?></strong>
            </td>
            <td>
              <?php if (empty($b['items'])): ?>
                <span style="color:#888;">(無物品)</span>
              <?php else: ?>
                <ul style="margin:0; padding-left:16px;">
                  <?php foreach ($b['items'] as $it): ?>
                    <li><?=e($it['item_name'])?> <small>(<?=e($it['status'])?>)</small></li>
                  <?php endforeach; ?>
                </ul>
              <?php endif; ?>
            </td>
            <td><?=e($b['purpose'])?></td>
            <td align="center">
              <strong><?=e($statusLabels[$b['status']] ?? $b['status'])?></strong>
            </td>
            <td>
              <?php if (!empty($b['review_comment'])): ?>
                審核意見：<?=e($b['review_comment'])?><br>
              <?php endif; ?>
              <?php if (!empty($b['reviewer_username'])): ?>
                審核：<?=e($b['reviewer_username'])?> (<?=e(substr($b['reviewed_at'], 0, 16))?>)<br>
              <?php endif; ?>
              <?php if (!empty($b['checkout_operator'])): ?>
                借出：<?=e($b['checkout_operator'])?> (<?=e(substr($b['checked_out_at'], 0, 16))?>)<br>
              <?php endif; ?>
              <?php if (!empty($b['return_operator'])): ?>
                歸還：<?=e($b['return_operator'])?> (<?=e(substr($b['returned_at'], 0, 16))?>)
              <?php endif; ?>
            </td>
            <td>
              <?php if ($b['status'] === 'pending'): ?>
                <!-- 待審核操作 -->
                <form method="post" action="">
                  <?php csrf(); ?>
                  <input type="hidden" name="action" value="booking_review">
                  <input type="hidden" name="booking_id" value="<?=e($b['booking_id'])?>">
                  <input type="text" name="review_comment" placeholder="審核備註/意見 (可選)" style="width: 95%; margin-bottom: 5px;"><br>
                  <button type="submit" name="decision" value="approved">核准申請</button>
                  <button type="submit" name="decision" value="rejected" onclick="return confirm('確定退件此申請？')">退件</button>
                </form>
              <?php elseif ($b['status'] === 'approved'): ?>
                <!-- 註記借出領用 -->
                <form method="post" action="">
                  <?php csrf(); ?>
                  <input type="hidden" name="action" value="booking_checkout">
                  <input type="hidden" name="booking_id" value="<?=e($b['booking_id'])?>">
                  <button type="submit" onclick="return confirm('確認已發放鑰匙與相關物品並登記借出？')">
                    註記借出領用
                  </button>
                </form>
              <?php elseif ($b['status'] === 'checked_out'): ?>
                <!-- 確認歸還 -->
                <form method="post" action="">
                  <?php csrf(); ?>
                  <input type="hidden" name="action" value="booking_return">
                  <input type="hidden" name="booking_id" value="<?=e($b['booking_id'])?>">
                  <button type="submit" onclick="return confirm('確認空間鑰匙與借用物品皆已如數歸還？')">
                    確認歸還完成
                  </button>
                </form>
              <?php else: ?>
                <span style="color:#666;">處理完畢</span>
              <?php endif; ?>
            </td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  <?php endif; ?>
</section>
