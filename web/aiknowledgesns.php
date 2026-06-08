<?php
if (isset($_GET['return']) && is_string($_GET['return']) && strpos($_GET['return'], '/') === 0 && strpos($_GET['return'], '//') !== 0) {
    $_GET['return'] = 'https://kurage.exbridge.jp' . $_GET['return'];
    $_SERVER['QUERY_STRING'] = http_build_query($_GET);
}
$query = isset($_SERVER['QUERY_STRING']) && $_SERVER['QUERY_STRING'] !== '' ? '?' . $_SERVER['QUERY_STRING'] : '';
header('Location: https://aiknowledgecms.exbridge.jp/aiknowledgesns.php' . $query);
exit;
