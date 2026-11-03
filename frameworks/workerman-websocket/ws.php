<?php

use Workerman\Worker;

require __DIR__ . '/vendor/autoload.php';

$worker = new Worker('websocket://0.0.0.0:8080');
$worker->reusePort = true;
$worker->count = (int) shell_exec('nproc');

$worker->onMessage = static function ($connection, $data) {
    $connection->send($data);
};

Worker::runAll();
