<?php
declare(strict_types=1);
/**
 * @var array $bookings
 */
$statusLabels = [
    'pending' => '待審核',
    'approved' => '已核准 (待領用)',
    'checked_out' => '借出中',
    'returned' => '已歸還',
    'rejected' => '已退件',
];
?>
<section>
  <h1>我的空間與物品借用紀錄</h1>
  <p>檢視您的借用申請審核進度、借用物品清單與物品領取／歸還狀態。</p>

  <?php if (empty($bookings)): ?>
    <p>目前尚無借用紀錄。<a href="?page=booking_calendar">前往預約空間與物品</a></p>
  <?php else: ?>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
      <thead>
        <tr bgcolor="#f0f0f0">
          <th>編號</th>
          <th>空間</th>
          <th>借用日期</th>
          <th>借用時段</th>
          <th>借用物品</th>
          <th>借用事由</th>
          <th>審核狀態</th>
          <th>審核意見</th>
          <th>領用時間</th>
          <th>歸還時間</th>
          <th>申請時間</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($bookings as $b): ?>
          <tr>
            <td align="center">#<?=e($b['booking_id'])?></td>
            <td><?=e($b['room_code'])?> <?=e($b['room_name'])?></td>
            <td align="center"><?=e($b['booking_date'])?></td>
            <td align="center"><?=e($b['start_time'])?> - <?=e($b['end_time'])?></td>
            <td>
              <?php if (empty($b['items'])): ?>
                <span style="color:#888;">(無物品)</span>
              <?php else: ?>
                <ul style="margin:0; padding-left:18px;">
                  <?php foreach ($b['items'] as $it): ?>
                    <li><?=e($it['item_name'])?> (<?=e($it['status'])?>)</li>
                  <?php endforeach; ?>
                </ul>
              <?php endif; ?>
            </td>
            <td><?=e($b['purpose'])?></td>
            <td align="center">
              <strong><?=e($statusLabels[$b['status']] ?? $b['status'])?></strong>
            </td>
            <td><?=e($b['review_comment'] ?? '-')?></td>
            <td align="center">
              <?= $b['checked_out_at'] ? e(substr($b['checked_out_at'], 0, 16)) : '-' ?>
              <?php if (!empty($b['checkout_operator'])): ?><br><small>(經手: <?=e($b['checkout_operator'])?>)</small><?php endif; ?>
            </td>
            <td align="center">
              <?= $b['returned_at'] ? e(substr($b['returned_at'], 0, 16)) : '-' ?>
              <?php if (!empty($b['return_operator'])): ?><br><small>(經手: <?=e($b['return_operator'])?>)</small><?php endif; ?>
            </td>
            <td align="center"><small><?= $b['created_at'] ? e(substr($b['created_at'], 0, 16)) : '-' ?></small></td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  <?php endif; ?>
</section>
