<?php
declare(strict_types=1);
/**
 * @var array $rooms
 * @var array $items
 * @var array $weeklyData
 * @var int $selectedRoomId
 * @var string $weekStart
 */
$weekStartObj = new DateTimeImmutable($weeklyData['week_start'] ?? date('Y-m-d'));
$prevWeek = $weekStartObj->modify('-7 days')->format('Y-m-d');
$nextWeek = $weekStartObj->modify('+7 days')->format('Y-m-d');
$currentWeek = (new DateTimeImmutable())->modify('this week monday')->format('Y-m-d');

$daysOfWeek = ['一', '二', '三', '四', '五', '六', '日'];
$daySlots = [];
for ($i = 0; $i < 7; $i++) {
    $d = $weekStartObj->modify("+{$i} days");
    $daySlots[$d->format('Y-m-d')] = [
        'date' => $d->format('Y-m-d'),
        'label' => '週' . $daysOfWeek[$i] . ' (' . $d->format('m/d') . ')',
        'bookings' => [],
    ];
}

foreach ($weeklyData['bookings'] ?? [] as $b) {
    $bDate = $b['booking_date'];
    if (isset($daySlots[$bDate])) {
        $daySlots[$bDate]['bookings'][] = $b;
    }
}

$statusLabels = [
    'pending' => '審核中',
    'approved' => '已核准',
    'checked_out' => '借出中',
    'returned' => '已歸還',
    'rejected' => '已退件',
];
?>
<section>
  <h1>空間與物品預約</h1>
  <p>以週為單位檢視空間借用情形，相鄰時段（例如 10:00–11:00 與 11:00–12:00）可銜接借用。</p>

  <!-- 1. 教室切換與週次導航 -->
  <fieldset>
    <legend>檢視設定</legend>
    <form method="get" action="" style="display:inline-block; margin-bottom: 10px;">
      <input type="hidden" name="page" value="booking_calendar">
      <label>選擇空間：
        <select name="room_id" onchange="this.form.submit()">
          <?php foreach ($rooms as $r): ?>
            <option value="<?=e($r['room_id'])?>" <?= $r['room_id'] == $selectedRoomId ? 'selected' : '' ?>>
              <?=e($r['room_code'])?> - <?=e($r['name'])?> (<?=e($r['floor'])?>F, 容量 <?=e($r['capacity'] ?? '待確認')?>人)
            </option>
          <?php endforeach; ?>
        </select>
      </label>
      <input type="hidden" name="week_start" value="<?=e($weeklyData['week_start'])?>">
      <noscript><button type="submit">切換教室</button></noscript>
    </form>

    <div style="margin-top: 5px;">
      <span><strong>目前週次：</strong><?=e($weeklyData['week_start'])?> ～ <?=e($weeklyData['week_end'])?></span>
      · <a href="?page=booking_calendar&room_id=<?=e($selectedRoomId)?>&week_start=<?=e($prevWeek)?>">&laquo; 上一週</a>
      · <a href="?page=booking_calendar&room_id=<?=e($selectedRoomId)?>&week_start=<?=e($currentWeek)?>">回到本週</a>
      · <a href="?page=booking_calendar&room_id=<?=e($selectedRoomId)?>&week_start=<?=e($nextWeek)?>">下一週 &raquo;</a>
    </div>
  </fieldset>

  <!-- 2. 週占用檢視表 -->
  <h2>週借用占用狀況</h2>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%; margin-bottom: 25px;">
    <thead>
      <tr bgcolor="#f0f0f0">
        <?php foreach ($daySlots as $slot): ?>
          <th style="width:14.28%; text-align:center;"><?=e($slot['label'])?></th>
        <?php endforeach; ?>
      </tr>
    </thead>
    <tbody>
      <tr valign="top">
        <?php foreach ($daySlots as $slot): ?>
          <td>
            <?php if (empty($slot['bookings'])): ?>
              <span style="color:#888;">(無預約)</span>
            <?php else: ?>
              <?php foreach ($slot['bookings'] as $bk): ?>
                <div style="border-bottom: 1px dashed #ccc; margin-bottom: 6px; padding-bottom: 4px;">
                  <strong><?=e($bk['start_time'])?>-<?=e($bk['end_time'])?></strong><br>
                  狀態：[<?=e($statusLabels[$bk['status']] ?? $bk['status'])?>]<br>
                  事由：<?=e($bk['purpose'])?><br>
                  申請人：<?=e($bk['applicant_username'] ?? '使用者')?>
                </div>
              <?php endforeach; ?>
            <?php endif; ?>
          </td>
        <?php endforeach; ?>
      </tr>
    </tbody>
  </table>

  <!-- 3. 新增預約表單 -->
  <h2>填寫借用申請</h2>
  <form method="post" action="">
    <?php csrf(); ?>
    <input type="hidden" name="action" value="booking_create">

    <p>
      <label>借用空間：
        <select name="room_id" required>
          <?php foreach ($rooms as $r): ?>
            <option value="<?=e($r['room_id'])?>" <?= $r['room_id'] == $selectedRoomId ? 'selected' : '' ?>>
              <?=e($r['room_code'])?> - <?=e($r['name'])?> (<?=e($r['floor'])?>F)
            </option>
          <?php endforeach; ?>
        </select>
      </label>
    </p>

    <p>
      <label>借用日期：
        <input type="date" name="booking_date" min="<?=date('Y-m-d')?>" value="<?=e(max(date('Y-m-d'), $weeklyData['week_start']))?>" required>
      </label>
    </p>

    <p>
      <label>開始時間：
        <input type="time" name="start_time" value="10:00" step="1800" required>
      </label>
      ～
      <label>結束時間：
        <input type="time" name="end_time" value="12:00" step="1800" required>
      </label>
      <small>（時段須相容銜接，結束時間須晚於開始時間）</small>
    </p>

    <fieldset style="margin-bottom: 15px;">
      <legend>借用物品（多選）</legend>
      <?php if (empty($items)): ?>
        <p>目前無可用借用物品。</p>
      <?php else: ?>
        <?php foreach ($items as $it): ?>
          <label style="display:inline-block; margin-right: 15px; margin-bottom: 5px;">
            <input type="checkbox" name="item_ids[]" value="<?=e($it['item_id'])?>">
            <strong><?=e($it['item_name'])?></strong>
            <?php if (!empty($it['description'])): ?>
              <small>(<?=e($it['description'])?>)</small>
            <?php endif; ?>
          </label>
        <?php endforeach; ?>
      <?php endif; ?>
    </fieldset>

    <p>
      <label>借用事由：<br>
        <textarea name="purpose" rows="3" cols="50" required placeholder="請詳細說明活動名稱、使用目的或課程相關資訊..."></textarea>
      </label>
    </p>

    <p>
      <button type="submit">送出預約申請</button>
    </p>
  </form>
</section>
