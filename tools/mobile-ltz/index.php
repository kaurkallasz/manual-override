<?php
// Stable DreamHost entry: always obtain the current local server's UI build.
declare(strict_types=1);
define('MOBILE_ENTRY', true);
$_GET['path'] = 'client/latest/index.html';
require __DIR__ . '/api.php';
