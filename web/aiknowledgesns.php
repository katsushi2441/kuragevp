<?php
require_once __DIR__ . '/auth_common.php';

$THIS_FILE = 'aiknowledgesns.php';
url2ai_auth_handle_login_flow('/kuragevp.php');

header('Location: /kuragevp.php');
exit;
